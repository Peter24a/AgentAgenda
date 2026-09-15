from datetime import datetime, time, timedelta, timezone
from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.canonical import Event, Memory, Task
from app.models.memory import ContextAssembleRequest, ContextAssembleResponse
from app.services.memory_service import memory_service


class ContextEngine:
    def _estimate_tokens(self, text: str) -> int:
        """Estimación conservadora de tokens basada en longitud de caracteres y palabras."""
        if not text:
            return 0
        # Promedio estándar para español/inglés: ~4 caracteres por token
        return max(1, len(text) // 4)

    async def assemble_context(
        self,
        session: AsyncSession,
        user_id: str,
        req: ContextAssembleRequest,
    ) -> ContextAssembleResponse:
        as_of = req.as_of or datetime.now(timezone.utc).replace(tzinfo=None)
        budget = req.token_budget

        sections: List[str] = []
        events_count = 0
        tasks_count = 0
        memories_count = 0

        sections.append(f"### [CONTEXTO PERSONAL CANÓNICO]")
        sections.append(f"- Propósito: {req.purpose}")
        sections.append(f"- Fecha de referencia: {as_of.strftime('%Y-%m-%d %H:%M UTC')}")

        # 1. Agenda del día (Eventos y Tareas)
        if req.include_agenda:
            start_day = datetime.combine(as_of.date(), time.min)
            end_day = datetime.combine(as_of.date(), time.max)

            # Eventos
            ev_stmt = (
                select(Event)
                .where(
                    Event.user_id == user_id,
                    Event.is_deleted.is_(False),
                    Event.start_time >= start_day,
                    Event.start_time <= end_day,
                )
                .order_by(Event.start_time.asc())
            )
            ev_res = await session.execute(ev_stmt)
            events = list(ev_res.scalars().all())
            events_count = len(events)

            # Tareas pendientes
            task_stmt = (
                select(Task)
                .where(
                    Task.user_id == user_id,
                    Task.is_deleted.is_(False),
                    Task.status != "completed",
                )
                .order_by(Task.due_date.asc().nulls_last())
                .limit(10)
            )
            task_res = await session.execute(task_stmt)
            tasks = list(task_res.scalars().all())
            tasks_count = len(tasks)

            agenda_lines: List[str] = ["\n#### Compromisos y Actividades del Día:"]
            if events:
                for ev in events:
                    time_str = ev.start_time.strftime("%H:%M") if ev.start_time else "Todo el día"
                    desc_str = f" ({ev.description})" if ev.description else ""
                    agenda_lines.append(f"- [{time_str}] {ev.title}{desc_str}")
            else:
                agenda_lines.append("- No hay eventos agendados para este día.")

            if tasks:
                agenda_lines.append("\n#### Tareas Pendientes:")
                for t in tasks:
                    due_str = f" (Vence: {t.due_date.strftime('%Y-%m-%d')})" if t.due_date else ""
                    agenda_lines.append(f"- [ ] {t.title}{due_str} [Prioridad: {t.priority}]")

            sections.append("\n".join(agenda_lines))

        # 2. Memorias canónicas vigentes
        if req.include_memories:
            from app.models.memory import MemorySearchRequest
            search_req = MemorySearchRequest(
                status="active",
                as_of=as_of,
                limit=100,
            )
            mems, total = await memory_service.search_memories(session, user_id, search_req)

            # Agrupar por tipo de memoria
            semantic_mems = [m for m in mems if m.memory_type == "semantic"]
            procedural_mems = [m for m in mems if m.memory_type == "procedural"]
            episodic_mems = [m for m in mems if m.memory_type == "episodic"]
            prospective_mems = [m for m in mems if m.memory_type == "prospective"]

            mem_lines: List[str] = ["\n#### Hechos y Preferencias Relevantes:"]

            all_ordered = semantic_mems + procedural_mems + prospective_mems + episodic_mems
            memories_count = len(all_ordered)

            if all_ordered:
                for m in all_ordered:
                    line = f"- [{m.predicate}]: {m.value}"
                    if m.context_text:
                        line += f" ({m.context_text})"
                    mem_lines.append(line)
            else:
                mem_lines.append("- No hay memorias registradas.")

            sections.append("\n".join(mem_lines))

        # Ensamble final
        full_text = "\n".join(sections)
        est_tokens = self._estimate_tokens(full_text)

        # Si excede el presupuesto de tokens, recortar texto de forma elegante
        if est_tokens > budget:
            char_limit = budget * 4
            full_text = full_text[:char_limit] + "\n... [Contexto truncado por límite de presupuesto de tokens]"
            est_tokens = self._estimate_tokens(full_text)

        total_items = events_count + tasks_count + memories_count

        return ContextAssembleResponse(
            purpose=req.purpose,
            as_of=as_of,
            token_budget=budget,
            estimated_tokens=est_tokens,
            items_included_count=total_items,
            memories_count=memories_count,
            events_count=events_count,
            tasks_count=tasks_count,
            assembled_context=full_text,
        )


context_engine = ContextEngine()
