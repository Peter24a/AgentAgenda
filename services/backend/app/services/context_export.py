import hashlib
import json
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.canonical import Document, Event, Memory, Task
from app.services.context_visibility import safe_document_filters
from app.services.memory_service import memory_service
from app.models.memory import MemorySearchRequest


class ContextExportService:
    async def export_canonical_context(
        self,
        session: AsyncSession,
        user_id: str,
        export_format: str = "json",
        include_documents: bool = False,
        as_of: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        ref_time = as_of or datetime.now(timezone.utc).replace(tzinfo=None)
        now_iso = datetime.now(timezone.utc).isoformat()

        # 1. Eventos
        ev_stmt = (
            select(Event)
            .where(Event.user_id == user_id, Event.is_deleted.is_(False))
            .order_by(Event.start_time.asc())
        )
        ev_res = await session.execute(ev_stmt)
        events = list(ev_res.scalars().all())
        events_data = [
            {
                "id": ev.id,
                "title": ev.title,
                "description": ev.description,
                "start_time": ev.start_time.isoformat() if ev.start_time else None,
                "end_time": ev.end_time.isoformat() if ev.end_time else None,
                "timezone": ev.timezone,
                "category": ev.category,
                "is_completed": ev.is_completed,
            }
            for ev in events
        ]

        # 2. Tareas
        task_stmt = (
            select(Task)
            .where(Task.user_id == user_id, Task.is_deleted.is_(False))
            .order_by(Task.due_date.asc().nulls_last())
        )
        task_res = await session.execute(task_stmt)
        tasks = list(task_res.scalars().all())
        tasks_data = [
            {
                "id": t.id,
                "title": t.title,
                "description": t.description,
                "status": t.status,
                "priority": t.priority,
                "due_date": t.due_date.isoformat() if t.due_date else None,
            }
            for t in tasks
        ]

        # 3. Memorias activas
        memories, memories_total = await memory_service.search_memories(
            session, user_id, MemorySearchRequest(as_of=ref_time, limit=200), for_model=True,
        )
        memories_data = [
            {
                "id": m.id,
                "memory_type": m.memory_type,
                "predicate": m.predicate,
                "value": m.value,
                "context_text": m.context_text,
                "version": m.version,
                "valid_from": m.valid_from.isoformat() if m.valid_from else None,
                "valid_to": m.valid_to.isoformat() if m.valid_to else None,
                "sources": [{"source_kind": source.source_kind, "source_id": source.source_id} for source in m.sources],
            }
            for m in memories
        ]

        # 4. Documentos (si se solicitan)
        documents_data = []
        if include_documents:
            doc_stmt = (
                select(Document)
                .where(*safe_document_filters(user_id))
                .order_by(Document.title.asc())
            )
            doc_res = await session.execute(doc_stmt)
            docs = list(doc_res.scalars().all())
            documents_data = [
                {
                    "id": d.id,
                    "title": d.title,
                    "alias": d.alias,
                    "doc_type": d.doc_type,
                    "issuer": d.issuer,
                    "holder": d.holder,
                    "expiry_date": d.expiry_date.isoformat() if d.expiry_date else None,
                }
                for d in docs
            ]

        # Ensamblar payload canónico
        payload = {
            "schema_version": "1.1",
            "user_id": user_id,
            "exported_at": now_iso,
            "as_of": ref_time.isoformat(),
            "valid_until": (datetime.now(timezone.utc) + timedelta(days=7)).isoformat(),
            "purpose": "selected_context_copy",
            "restorable_backup": False,
            "memory_results_truncated": memories_total > len(memories),
            "events_count": len(events_data),
            "tasks_count": len(tasks_data),
            "memories_count": len(memories_data),
            "documents_count": len(documents_data),
            "events": events_data,
            "tasks": tasks_data,
            "memories": memories_data,
            "documents": documents_data,
        }

        # Calcular hash de integridad SHA-256
        canon_bytes = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
        sha256_digest = hashlib.sha256(canon_bytes).hexdigest()

        if export_format.lower() == "markdown":
            md_lines = [
                f"# DOSSIER DE CONTEXTO CANÓNICO - AGENTAGENDA",
                f"> Exportado el: `{now_iso}` | Usuario: `{user_id}` | Copia de contexto, no respaldo restaurable.\n",
                f"## 1. Memoria Fáctica y Preferencias ({len(memories_data)})",
            ]
            for m in memories_data:
                ctx_note = f" *({m['context_text']})*" if m.get("context_text") else ""
                md_lines.append(f"- **{m['predicate']}**: {m['value']}{ctx_note}")

            md_lines.append(f"\n## 2. Compromisos y Eventos ({len(events_data)})")
            for ev in events_data:
                time_str = ev["start_time"][:16].replace("T", " ") if ev["start_time"] else "Sin hora"
                desc_text = f" ({ev['description']})" if ev.get("description") else ""
                md_lines.append(f"- `[{time_str}]` **{ev['title']}**{desc_text}")

            md_lines.append(f"\n## 3. Tareas Registradas ({len(tasks_data)})")
            for t in tasks_data:
                due = f" [Vence: {t['due_date'][:10]}]" if t["due_date"] else ""
                status_box = "[x]" if t["status"] == "completed" else "[ ]"
                md_lines.append(f"- {status_box} **{t['title']}** ({t['priority']}){due}")

            if include_documents:
                md_lines.append(f"\n## 4. Archivo Documental Privado ({len(documents_data)})")
                for d in documents_data:
                    md_lines.append(f"- **{d['title']}** | Tipo: {d['doc_type']} | Emisor: {d['issuer'] or 'N/A'}")

            content = "\n".join(md_lines)
            markdown_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
            return {
                "format": "markdown",
                "sha256": markdown_hash,
                "hash_target": "content_utf8",
                "exported_at": now_iso,
                "content": content,
            }

        return {
            "format": "json",
            "sha256": sha256_digest,
            "hash_target": "json.dumps(data, sort_keys=True, ensure_ascii=False).encode('utf-8')",
            "exported_at": now_iso,
            "data": payload,
        }


context_export_service = ContextExportService()
