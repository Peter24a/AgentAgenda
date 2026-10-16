"""Confirm calendar proposals once, checking current commitments under the owner lock."""
import hashlib
import json
import unicodedata
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.canonical import Proposal, ProposalContext, Event, WeeklyRoutine
from app.models.proposal import (
    AgentProposalModel, ProposalStatus, ProposalActionResponse, WeeklyRoutineProposal,
)
from app.models.agenda import AgendaItemModel
from app.services.agenda_service import agenda_service
from app.services.weekly_routines import HORIZON_DAYS, expand_routine
from app.importing.schedule import prepare_events


def _title(value):
    text = unicodedata.normalize("NFKD", value or "").casefold()
    return " ".join("".join(c for c in text if not unicodedata.combining(c)).split())


def _routine_model(user_id, spec):
    identity = spec.model_dump(mode="json")
    # Formatting, descriptions and category do not create another identical series.
    identity.pop("description", None)
    identity.pop("category", None)
    identity["title"] = _title(spec.title)
    fingerprint = json.dumps(identity, sort_keys=True, separators=(",", ":"))
    routine_id = "routine-chat-" + hashlib.sha256((user_id + "\0" + fingerprint).encode()).hexdigest()[:40]
    return WeeklyRoutine(
        id=routine_id, user_id=user_id, name=spec.title, timezone=spec.timezone,
        starts_on=spec.starts_on.isoformat(),
        ends_on=spec.ends_on.isoformat() if spec.ends_on else None,
        template_json=[dict(
            id=f"weekday-{weekday}", iso_weekday=weekday, title=spec.title,
            description=spec.description or "", category=spec.category.value,
            start_time=spec.start_time, end_time=spec.end_time,
            clock_time_origin="explicit_user",
        ) for weekday in spec.iso_weekdays],
        enabled=True, generation=1,
    )


def _same_slot(left, right):
    return (_title(left["title"]) == _title(right["title"])
            and left["start_time"] == right["start_time"]
            and left["end_time"] == right["end_time"])


def _overlap(left, right):
    left_end = left["end_time"] or left["start_time"] + timedelta(microseconds=1)
    right_end = right["end_time"] or right["start_time"] + timedelta(microseconds=1)
    return left["start_time"] < right_end and right["start_time"] < left_end


def _event_data(event):
    return {key: getattr(event, key) for key in (
        "id", "title", "description", "start_time", "end_time", "timezone", "category", "is_completed",
    )}


class ProposalService:
    async def get_proposal(self, session: AsyncSession, user_id: str, proposal_id: str) -> Optional[Proposal]:
        return (await session.execute(select(Proposal).where(
            Proposal.id == proposal_id, Proposal.user_id == user_id,
        ))).scalar_one_or_none()

    async def get_latest_pending(self, session: AsyncSession, user_id: str) -> Optional[Proposal]:
        return (await session.execute(select(Proposal).where(
            Proposal.user_id == user_id, Proposal.status == "pending",
        ).order_by(Proposal.created_at.desc()).limit(1))).scalar_one_or_none()

    def prepare_recurring_proposal(self, user_id, proposal, routine, now=None):
        spec = WeeklyRoutineProposal.model_validate(routine)
        instant = now or proposal.created_at or datetime.now(timezone.utc)
        if instant.tzinfo is None:
            instant = instant.replace(tzinfo=timezone.utc)
        start = max(spec.starts_on, instant.astimezone(ZoneInfo(spec.timezone)).date())
        through = start + timedelta(days=HORIZON_DAYS - 1)
        row = _routine_model(user_id, spec)
        plan = expand_routine(row, start, through)
        prepared = prepare_events(plan, user_id)[1] if plan["dated_events"] else []
        if not prepared:
            raise ValueError("La rutina no tiene fechas futuras en el período indicado")
        zone = ZoneInfo(spec.timezone)
        items = [AgendaItemModel(
            id=event["id"], title=event["title"], description=event["description"] or None,
            start_time=event["start_time"].replace(tzinfo=timezone.utc).astimezone(zone),
            end_time=event["end_time"].replace(tzinfo=timezone.utc).astimezone(zone),
            category=event["category"],
        ) for event in prepared]
        return proposal.model_copy(update={"routine": spec, "resulting_items": items})

    async def _guard_items(self, session, user_id, items):
        """Plan the entire final state before changing any row (including intra-batch conflicts)."""
        existing = list((await session.scalars(select(Event).where(Event.user_id == user_id))).all())
        by_id = {event.id: event for event in existing}
        parsed, ids = [], set()
        for item in items:
            item_id = item.get("id") or "evt-" + uuid.uuid4().hex[:16]
            if item_id in ids:
                raise ValueError("La propuesta repite una actividad; pide una propuesta nueva")
            ids.add(item_id)
            old = by_id.get(item_id)
            if item.get("action") == "delete":
                if old is None or old.is_deleted:
                    raise ValueError("La actividad que quieres cancelar ya no está disponible")
                zone_name = item.get("timezone") or "America/Mexico_City"
                reviewed_start = agenda_service._utc_input(datetime.fromisoformat(item["start_time"]), zone_name)
                reviewed_end = agenda_service._utc_input(datetime.fromisoformat(item["end_time"]), zone_name) if item.get("end_time") else None
                if (old.title != item.get("title") or old.start_time != reviewed_start
                        or old.end_time != reviewed_end or old.category != item.get("category", "general")):
                    raise ValueError("La actividad cambió desde que se preparó la cancelación. Pide una propuesta nueva para revisar sus datos actuales.")
                parsed.append(("delete", old, None))
                continue
            if old is not None and old.is_deleted:
                raise ValueError("La actividad fue eliminada; pide una propuesta nueva")
            zone_name = item.get("timezone") or "America/Mexico_City"
            start = datetime.fromisoformat(item["start_time"])
            end = datetime.fromisoformat(item["end_time"]) if item.get("end_time") else None
            start = agenda_service._utc_input(start, zone_name)
            end = agenda_service._utc_input(end, zone_name)
            if end is not None and end <= start:
                raise ValueError("El final debe ser posterior al inicio")
            data = dict(id=item_id, title=item.get("title", "Nueva actividad"),
                        description=item.get("description"), start_time=start, end_time=end,
                        timezone=zone_name, category=item.get("category", "general"),
                        is_completed=bool(item.get("is_completed", False)))
            parsed.append(("update" if old is not None else "create", old, data))

        # All changed/deleted targets are removed first so legitimate swaps and
        # adjacent moves are evaluated against the final proposed calendar.
        busy = [_event_data(event) for event in existing if not event.is_deleted and event.id not in ids]
        operations, duplicates = [], 0
        for action, old, data in parsed:
            if action == "delete":
                operations.append((action, old, None))
                continue
            duplicate = next((other for other in busy if _same_slot(data, other)), None)
            if duplicate is not None:
                if old is not None:
                    raise ValueError(f'Ya existe "{duplicate["title"]}" en ese horario. Aclara cuál actividad quieres conservar.')
                # Another request or another item already created this exact
                # commitment. Preserve its ID, metadata and completion status.
                duplicates += 1
                continue
            conflict = next((other for other in busy if _overlap(data, other)), None)
            if conflict is not None:
                local = conflict["start_time"].replace(tzinfo=timezone.utc).astimezone(ZoneInfo(data["timezone"]))
                raise ValueError(
                    f'El horario se cruza con "{conflict["title"]}" ({local:%Y-%m-%d %H:%M}). '
                    'Elige otro horario o aclara qué actividad quieres mover antes de confirmar.'
                )
            busy.append(data)
            if old is not None and all(getattr(old, key) == value for key, value in data.items()):
                duplicates += 1
                continue
            operations.append((action, old, data))
        return operations, duplicates

    async def _guard_routine(self, session, user_id, spec):
        candidate = _routine_model(user_id, spec)
        routines = (await session.scalars(select(WeeklyRoutine).where(WeeklyRoutine.user_id == user_id))).all()
        for old in routines:
            if old.id == candidate.id:
                if not old.enabled:
                    raise ValueError("Esa rutina está pausada. Aclara si quieres reactivarla antes de crear otra.")
                return old, False
            if not old.enabled or old.timezone != candidate.timezone or _title(old.name) != _title(candidate.name):
                continue
            old_slots = {(item.get("iso_weekday"), item.get("start_time"), item.get("end_time")) for item in old.template_json}
            new_slots = {(item["iso_weekday"], item["start_time"], item["end_time"]) for item in candidate.template_json}
            if old_slots != new_slots:
                continue
            old_end, new_end = old.ends_on or "9999-12-31", candidate.ends_on or "9999-12-31"
            if candidate.starts_on <= old_end and old.starts_on <= new_end:
                raise ValueError("Ya existe una rutina igual para parte de ese período. Aclara si quieres cambiar su duración; no crearé otra encima.")
        return candidate, True

    async def validate_proposal(self, session, user_id, proposal):
        if proposal.routine is not None:
            proposal = self.prepare_recurring_proposal(user_id, proposal, proposal.routine)
            _, new_routine = await self._guard_routine(session, user_id, proposal.routine)
            if not new_routine:
                return proposal
        items = [item.model_dump(mode="json") for item in proposal.resulting_items]
        if proposal.routine is not None:
            for item in items:
                item["timezone"] = proposal.routine.timezone
        await self._guard_items(session, user_id, items)
        return proposal

    async def save_proposal(self, session: AsyncSession, user_id: str, model: AgentProposalModel) -> Proposal:
        # Match confirmation's lock order; an old replay may never reset accepted
        # status or replace its contents while a confirmation is being committed.
        await agenda_service._lock_head(session, user_id)
        prop = await self.get_proposal(session, user_id, model.id)
        if prop is not None and prop.status != "pending":
            await session.commit()
            return prop
        if model.routine is not None:
            model = self.prepare_recurring_proposal(user_id, model, model.routine)
        items_data = [item.model_dump(mode="json") for item in model.resulting_items]
        if model.routine is not None:
            for item in items_data:
                item["timezone"] = model.routine.timezone
        if prop is None:
            prop = Proposal(id=model.id, user_id=user_id, created_at=model.created_at or datetime.utcnow())
            session.add(prop)
        prop.summary, prop.reason = model.summary, model.reason
        prop.resulting_items, prop.status = items_data, "pending"
        prop.updated_at = datetime.utcnow()
        # There is deliberately no ORM relationship from optional context to
        # Proposal. Flush the parent explicitly before its FK-bearing context;
        # mapper ordering must not depend on SQLite's default FK enforcement.
        await session.flush()
        context = await session.get(ProposalContext, model.id)
        if context is not None and context.user_id != user_id:
            raise ValueError("La propuesta no pertenece a este usuario")
        if model.routine is not None:
            if context is None:
                context = ProposalContext(id=model.id, user_id=user_id)
                session.add(context)
            context.payload = {**(context.payload or {}), "routine": model.routine.model_dump(mode="json")}
        elif context is not None and "routine" in (context.payload or {}):
            context.payload = {key: value for key, value in context.payload.items() if key != "routine"}
        await session.commit()
        await session.refresh(prop)
        return prop

    async def confirm_proposal(self, session: AsyncSession, user_id: str, proposal_id: str) -> ProposalActionResponse:
        head = await agenda_service._lock_head(session, user_id)
        stmt = select(Proposal).where(Proposal.id == proposal_id, Proposal.user_id == user_id)
        if session.bind and session.bind.dialect.name == "postgresql":
            stmt = stmt.with_for_update()
        prop = (await session.execute(stmt)).scalar_one_or_none()
        if prop is None:
            await session.rollback()
            return ProposalActionResponse(success=False, proposal_id=proposal_id, status=ProposalStatus.rejected, message="Propuesta no encontrada")
        if prop.status != "pending":
            await session.commit()
            return self._processed(prop)
        context = await session.get(ProposalContext, proposal_id)
        routine, new_routine = None, False
        if context is not None and context.user_id == user_id and context.payload.get("routine"):
            spec = WeeklyRoutineProposal.model_validate(context.payload["routine"])
            routine, new_routine = await self._guard_routine(session, user_id, spec)
        if routine is not None and not new_routine:
            # Re-requesting a confirmed series must preserve edits, completions,
            # and tombstones of its occurrences, just like the rolling worker.
            operations, duplicates = [], len(prop.resulting_items or [])
        else:
            operations, duplicates = await self._guard_items(session, user_id, prop.resulting_items or [])
        now = datetime.utcnow()
        for action, event, data in operations:
            if action == "delete":
                event.is_deleted = True
                event.version += 1
                event.updated_at = now
            elif event is not None:
                for key, value in data.items():
                    setattr(event, key, value)
                event.version += 1
                event.updated_at = now
            else:
                event = Event(**data, user_id=user_id, version=1, is_deleted=False, created_at=now, updated_at=now)
                session.add(event)
            agenda_service._record_change(session, head, event, "event", action)
        if routine is not None and new_routine:
            routine.created_at = routine.updated_at = now
            routine.last_materialized_at = now
            if prop.resulting_items:
                latest = max(datetime.fromisoformat(item["start_time"]).astimezone(ZoneInfo(routine.timezone)).date() for item in prop.resulting_items)
                routine.materialized_through = latest.isoformat()
            session.add(routine)
        prop.status, prop.updated_at = "accepted", now
        await session.commit()
        message = "Propuesta aceptada e integrada en tu agenda con éxito."
        if not operations and not new_routine:
            message = "La actividad o rutina ya estaba en tu agenda; no se creó ningún duplicado."
        elif routine is not None:
            message = "Rutina semanal confirmada. Sus próximas actividades se mantendrán en tu agenda automáticamente."
        return ProposalActionResponse(success=True, proposal_id=proposal_id, status=ProposalStatus.accepted, message=message)

    def _processed(self, prop):
        return ProposalActionResponse(success=False, proposal_id=prop.id, status=ProposalStatus(prop.status),
                                      message=f"La propuesta ya fue procesada anteriormente ({prop.status})")

    async def reject_proposal(self, session: AsyncSession, user_id: str, proposal_id: str) -> ProposalActionResponse:
        await agenda_service._lock_head(session, user_id)
        prop = await self.get_proposal(session, user_id, proposal_id)
        if prop is None:
            await session.rollback()
            return ProposalActionResponse(success=False, proposal_id=proposal_id, status=ProposalStatus.rejected, message="Propuesta no encontrada")
        if prop.status != "pending":
            await session.commit()
            return self._processed(prop)
        prop.status, prop.updated_at = "rejected", datetime.utcnow()
        await session.commit()
        return ProposalActionResponse(success=True, proposal_id=proposal_id, status=ProposalStatus.rejected, message="Propuesta descartada.")


proposal_service = ProposalService()
