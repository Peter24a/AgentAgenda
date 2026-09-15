import uuid
from datetime import datetime, timezone
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db_session, require_scope
from app.models.auth import AuthContext
from app.models.canonical import Event, Job, Reminder
from app.models.job import (
    JobBatchProcessResponse,
    JobCreateRequest,
    JobResponse,
    ReminderDetail,
)
from app.worker.worker import background_worker

router = APIRouter(tags=["Durable Worker & Outbox Reminders"])


@router.post(
    "/v1/jobs",
    response_model=JobResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Encolar un trabajo en segundo plano",
)
async def create_job(
    req: JobCreateRequest,
    session: AsyncSession = Depends(get_db_session),
    auth: AuthContext = Depends(require_scope("jobs:write")),
):
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    job = Job(
        id=f"job-{uuid.uuid4().hex[:12]}",
        job_type=req.job_type,
        payload_json=req.payload,
        status="pending",
        attempts=0,
        max_attempts=req.max_attempts,
        scheduled_at=req.scheduled_at or now,
        created_at=now,
        updated_at=now,
    )
    session.add(job)
    await session.commit()
    await session.refresh(job)
    return JobResponse.model_validate(job)


@router.get(
    "/v1/jobs/{id}",
    response_model=JobResponse,
    summary="Consultar estado y resultado de un trabajo",
)
async def get_job(
    id: str,
    session: AsyncSession = Depends(get_db_session),
    auth: AuthContext = Depends(require_scope("jobs:read")),
):
    res = await session.execute(select(Job).where(Job.id == id))
    job = res.scalar_one_or_none()
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Trabajo '{id}' no encontrado",
        )
    return JobResponse.model_validate(job)


@router.post(
    "/v1/jobs/process-pending",
    response_model=JobBatchProcessResponse,
    summary="Procesar lote de trabajos pendientes de inmediato",
    description="Disparador para ejecutar el bucle del worker sobre trabajos programados y pendientes.",
)
async def process_pending_jobs(
    limit: int = Query(10, ge=1, le=50),
    session: AsyncSession = Depends(get_db_session),
    auth: AuthContext = Depends(require_scope("jobs:write")),
):
    proc, succ, fail, jobs = await background_worker.process_pending_jobs(session, limit=limit)
    return JobBatchProcessResponse(
        processed_count=proc,
        succeeded_count=succ,
        failed_count=fail,
        jobs=[JobResponse.model_validate(j) for j in jobs],
    )


@router.get(
    "/v1/agenda/reminders/pending",
    response_model=List[ReminderDetail],
    summary="Consultar recordatorios pendientes de ser notificados",
)
async def get_pending_reminders(
    session: AsyncSession = Depends(get_db_session),
    auth: AuthContext = Depends(require_scope("agenda:read")),
):
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    stmt = (
        select(Reminder)
        .where(
            Reminder.user_id == auth.user_id,
            Reminder.status == "pending",
            Reminder.remind_at <= now,
        )
        .order_by(Reminder.remind_at.asc())
    )
    res = await session.execute(stmt)
    reminders = list(res.scalars().all())

    # Cargar títulos de eventos asociados
    details: List[ReminderDetail] = []
    for r in reminders:
        title = "Recordatorio de Agenda"
        if r.event_id:
            ev_res = await session.execute(select(Event).where(Event.id == r.event_id))
            ev = ev_res.scalar_one_or_none()
            if ev:
                title = f"Recordatorio: {ev.title}"

        details.append(
            ReminderDetail(
                id=r.id,
                user_id=r.user_id,
                event_id=r.event_id,
                task_id=r.task_id,
                remind_at=r.remind_at,
                offset_minutes=r.offset_minutes,
                status=r.status,
                channel=r.channel,
                title=title,
                created_at=r.created_at,
            )
        )

    return details


@router.post(
    "/v1/agenda/reminders/{id}/dismiss",
    summary="Descartar o confirmar notificación de un recordatorio",
)
async def dismiss_reminder(
    id: str,
    session: AsyncSession = Depends(get_db_session),
    auth: AuthContext = Depends(require_scope("agenda:write")),
):
    stmt = select(Reminder).where(Reminder.id == id, Reminder.user_id == auth.user_id)
    res = await session.execute(stmt)
    rem = res.scalar_one_or_none()
    if not rem:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Recordatorio '{id}' no encontrado",
        )

    rem.status = "dismissed"
    await session.commit()
    return {"status": "dismissed", "id": id}
