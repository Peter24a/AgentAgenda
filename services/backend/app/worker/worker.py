import os
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.canonical import DocumentRevision, Event, Job, Reminder


class BackgroundWorker:
    async def handle_document_extraction(
        self, session: AsyncSession, payload: Dict
    ) -> str:
        revision_id = payload.get("revision_id")
        if not revision_id:
            raise ValueError("Falta 'revision_id' en payload de extracción documental")

        res = await session.execute(
            select(DocumentRevision).where(DocumentRevision.id == revision_id)
        )
        rev = res.scalar_one_or_none()
        if not rev:
            raise ValueError(f"Revisión '{revision_id}' no encontrada en base de datos")

        if not os.path.exists(rev.storage_path):
            rev.extraction_status = "failed"
            await session.commit()
            raise ValueError(f"El archivo físico '{rev.storage_path}' no existe en disco")

        # Extracción resiliente de texto
        extracted = ""
        try:
            with open(rev.storage_path, "rb") as f:
                raw = f.read(1024 * 512) # Leer hasta 512 KB
                text_content = raw.decode("utf-8", errors="ignore")
                words = re.findall(r"[a-zA-Z0-9_\-áéíóúÁÉÍÓÚñÑ\.,;:\s]{4,}", text_content)
                extracted = " ".join([w.strip() for w in words if len(w.strip()) > 3])
                if not extracted:
                    extracted = f"Documento binario indexado: {rev.original_filename} ({rev.mime_type})"
        except Exception as e:
            rev.extraction_status = "failed"
            await session.commit()
            raise e

        rev.extracted_text = extracted[:4000] # Limitar a 4000 caracteres de resumen
        rev.extraction_status = "ready"
        await session.commit()
        return f"Texto extraído ({len(rev.extracted_text)} caracteres)"

    async def handle_generate_reminders(
        self, session: AsyncSession, payload: Dict
    ) -> str:
        user_id = payload.get("user_id", "default_user")
        hours_ahead = payload.get("hours_ahead", 48)
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        horizon = now + timedelta(hours=hours_ahead)

        # Buscar eventos próximos sin recordatorio pendiente
        ev_stmt = select(Event).where(
            Event.user_id == user_id,
            Event.is_deleted.is_(False),
            Event.start_time >= now,
            Event.start_time <= horizon,
        )
        ev_res = await session.execute(ev_stmt)
        events = list(ev_res.scalars().all())

        created_count = 0
        for ev in events:
            # Comprobar si ya tiene recordatorio
            rem_stmt = select(Reminder).where(
                Reminder.event_id == ev.id,
                Reminder.status.in_(("pending", "sent")),
            )
            rem_res = await session.execute(rem_stmt)
            existing = rem_res.scalar_one_or_none()
            if not existing:
                offset_min = 60
                target_remind = ev.start_time - timedelta(minutes=offset_min)
                if target_remind < now:
                    target_remind = now

                reminder = Reminder(
                    id=f"rem-{uuid.uuid4().hex[:12]}",
                    user_id=user_id,
                    event_id=ev.id,
                    task_id=None,
                    remind_at=target_remind,
                    offset_minutes=offset_min,
                    status="pending",
                    channel="local_alarm",
                    created_at=now,
                )
                session.add(reminder)
                created_count += 1

        await session.commit()
        return f"Generados {created_count} recordatorios para {len(events)} eventos próximos"

    async def handle_cleanup_temp_uploads(
        self, session: AsyncSession, payload: Dict
    ) -> str:
        max_age_seconds = payload.get("max_age_seconds", 3600)
        temp_dir = os.path.join(settings.storage_path, "temp")
        if not os.path.exists(temp_dir):
            return "Directorio temporal no existe"

        now_ts = datetime.now().timestamp()
        deleted_count = 0

        for entry in os.listdir(temp_dir):
            if entry.endswith(".part"):
                file_path = os.path.join(temp_dir, entry)
                try:
                    mtime = os.path.getmtime(file_path)
                    if (now_ts - mtime) > max_age_seconds:
                        os.remove(file_path)
                        deleted_count += 1
                except OSError:
                    pass

        return f"Eliminados {deleted_count} archivos temporales huérfanos"

    async def process_single_job(
        self, session: AsyncSession, job: Job
    ) -> bool:
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        job.attempts += 1
        job.status = "processing"
        job.updated_at = now
        await session.commit()

        success = False
        try:
            if job.job_type == "document_extraction":
                await self.handle_document_extraction(session, job.payload_json)
            elif job.job_type == "generate_reminders":
                await self.handle_generate_reminders(session, job.payload_json)
            elif job.job_type == "cleanup_temp_uploads":
                await self.handle_cleanup_temp_uploads(session, job.payload_json)
            else:
                raise ValueError(f"Tipo de trabajo desconocido: {job.job_type}")

            job.status = "completed"
            job.error_message = None
            success = True
        except Exception as e:
            job.error_message = str(e)
            if job.attempts >= job.max_attempts:
                job.status = "failed"
            else:
                job.status = "pending" # Reintentar
            success = False

        job.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
        await session.commit()
        return success

    async def process_pending_jobs(
        self, session: AsyncSession, limit: int = 10
    ) -> Tuple[int, int, int, List[Job]]:
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        stmt = (
            select(Job)
            .where(
                Job.status == "pending",
                Job.scheduled_at <= now,
            )
            .order_by(Job.scheduled_at.asc())
            .limit(limit)
        )
        res = await session.execute(stmt)
        jobs = list(res.scalars().all())

        processed = 0
        succeeded = 0
        failed = 0

        for j in jobs:
            ok = await self.process_single_job(session, j)
            processed += 1
            if ok:
                succeeded += 1
            else:
                failed += 1

        return processed, succeeded, failed, jobs


background_worker = BackgroundWorker()
