import uuid
import hashlib
from datetime import datetime, time, timedelta
from typing import Any, Dict, List, Optional
import pytz
from sqlalchemy import select, and_, or_, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.canonical import Event, Task, ChangeBatch, SyncHead
from app.models.agenda import AgendaItemCreate, ActivityCategory


class AgendaService:
    async def _lock_head(self, session: AsyncSession, user_id: str) -> SyncHead:
        # Same lock/order as schedule reconciliation: head before event rows.
        if session.bind and session.bind.dialect.name == "postgresql":
            key = int.from_bytes(hashlib.sha256(("schedule\0" + user_id).encode()).digest()[:8], "big", signed=True)
            await session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": key})
        stmt = select(SyncHead).where(SyncHead.user_id == user_id)
        if session.bind and session.bind.dialect.name == "postgresql":
            stmt = stmt.with_for_update()
        head = (await session.execute(stmt)).scalar_one_or_none()
        if head is None:
            head = SyncHead(user_id=user_id, current_seq=0, updated_at=datetime.utcnow())
            session.add(head)
            await session.flush()
        return head

    def _record_change(self, session, head, entity, entity_type, action):
        fields = ("id", "title", "description", "start_time", "end_time", "timezone", "category", "is_completed", "is_deleted", "version") if entity_type == "event" else ("id", "title", "description", "status", "priority", "due_date", "is_deleted", "version")
        payload = {}
        for field in fields:
            value = getattr(entity, field)
            payload[field] = value.isoformat() + "Z" if isinstance(value, datetime) else value
        head.current_seq += 1
        head.updated_at = datetime.utcnow()
        session.add(ChangeBatch(
            id="cb-agenda-" + uuid.uuid4().hex, user_id=head.user_id,
            commit_seq=head.current_seq, entity_type=entity_type, entity_id=entity.id,
            change_type=action, entity_version=entity.version, payload_json=payload,
            created_at=datetime.utcnow(),
        ))

    def _utc_input(self, value, tz_name):
        if value is None:
            return None
        try:
            tz = pytz.timezone(tz_name)
            aware = tz.localize(value, is_dst=None) if value.tzinfo is None else value
            return aware.astimezone(pytz.UTC).replace(tzinfo=None)
        except (pytz.UnknownTimeZoneError, pytz.AmbiguousTimeError, pytz.NonExistentTimeError):
            raise ValueError("Hora local ambigua o zona horaria inválida") from None

    def _parse_date_range(
        self, date_str: str, tz_name: str
    ) -> tuple[datetime, datetime]:
        """Calcula el rango UTC [inicio, fin) para una fecha local YYYY-MM-DD dada."""
        try:
            tz = pytz.timezone(tz_name)
        except Exception:
            tz = pytz.timezone(settings.default_timezone)

        dt = datetime.strptime(date_str, "%Y-%m-%d")
        local_start = tz.localize(datetime.combine(dt.date(), time.min))
        local_end = tz.localize(datetime.combine(dt.date() + timedelta(days=1), time.min))

        utc_start = local_start.astimezone(pytz.UTC).replace(tzinfo=None)
        utc_end = local_end.astimezone(pytz.UTC).replace(tzinfo=None)
        return utc_start, utc_end

    async def list_events(
        self,
        session: AsyncSession,
        user_id: str,
        date: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        timezone: str = "America/Mexico_City",
    ) -> List[Event]:
        conditions = [Event.user_id == user_id, Event.is_deleted == False]

        if date:
            utc_start, utc_end = self._parse_date_range(date, timezone)
            conditions.append(or_(Event.end_time > utc_start, and_(Event.end_time.is_(None), Event.start_time >= utc_start)))
            conditions.append(Event.start_time < utc_end)
        elif start_date and end_date:
            utc_start, _ = self._parse_date_range(start_date, timezone)
            _, utc_end = self._parse_date_range(end_date, timezone)
            conditions.append(or_(Event.end_time > utc_start, and_(Event.end_time.is_(None), Event.start_time >= utc_start)))
            conditions.append(Event.start_time < utc_end)

        stmt = select(Event).where(and_(*conditions)).order_by(Event.start_time.asc())
        res = await session.execute(stmt)
        return list(res.scalars().all())

    async def get_event(
        self, session: AsyncSession, user_id: str, event_id: str
    ) -> Optional[Event]:
        stmt = select(Event).where(
            Event.id == event_id, Event.user_id == user_id, Event.is_deleted == False
        )
        res = await session.execute(stmt)
        return res.scalar_one_or_none()

    async def upsert_event(
        self,
        session: AsyncSession,
        user_id: str,
        item: AgendaItemCreate,
        timezone: str = "America/Mexico_City",
    ) -> Event:
        event_id = item.id or f"evt-{uuid.uuid4().hex[:8]}"
        item = item.model_copy(update={
            'start_time': self._utc_input(item.start_time, timezone),
            'end_time': self._utc_input(item.end_time, timezone),
        })
        if item.end_time and item.end_time <= item.start_time:
            raise ValueError("El final debe ser posterior al inicio")
        head = await self._lock_head(session, user_id)
        stmt = select(Event).where(Event.id == event_id, Event.user_id == user_id)
        res = await session.execute(stmt)
        event = res.scalar_one_or_none()

        action = "update" if event else "create"
        if event:
            event.title = item.title
            event.description = item.description
            event.start_time = item.start_time
            event.end_time = item.end_time
            event.category = item.category.value if isinstance(item.category, ActivityCategory) else str(item.category)
            event.is_completed = item.is_completed
            event.timezone = timezone
            event.is_deleted = False
            event.version += 1
            event.updated_at = datetime.utcnow()
        else:
            event = Event(
                id=event_id,
                user_id=user_id,
                title=item.title,
                description=item.description,
                start_time=item.start_time,
                end_time=item.end_time,
                timezone=timezone,
                category=item.category.value if isinstance(item.category, ActivityCategory) else str(item.category),
                is_completed=item.is_completed,
                version=1,
                is_deleted=False,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
            session.add(event)

        self._record_change(session, head, event, "event", action)
        await session.commit()
        await session.refresh(event)
        return event

    async def delete_event(
        self, session: AsyncSession, user_id: str, event_id: str
    ) -> bool:
        head = await self._lock_head(session, user_id)
        stmt = select(Event).where(Event.id == event_id, Event.user_id == user_id)
        res = await session.execute(stmt)
        event = res.scalar_one_or_none()
        if not event or event.is_deleted:
            return False

        event.is_deleted = True
        event.version += 1
        event.updated_at = datetime.utcnow()
        self._record_change(session, head, event, "event", "delete")
        await session.commit()
        return True

    async def toggle_event_completed(
        self, session: AsyncSession, user_id: str, event_id: str
    ) -> Optional[Event]:
        head = await self._lock_head(session, user_id)
        stmt = select(Event).where(
            Event.id == event_id, Event.user_id == user_id, Event.is_deleted == False
        )
        res = await session.execute(stmt)
        event = res.scalar_one_or_none()
        if not event:
            return None

        event.is_completed = not event.is_completed
        event.version += 1
        event.updated_at = datetime.utcnow()
        self._record_change(session, head, event, "event", "update")
        await session.commit()
        await session.refresh(event)
        return event

    async def list_tasks(
        self, session: AsyncSession, user_id: str, status: Optional[str] = None
    ) -> List[Task]:
        conditions = [Task.user_id == user_id, Task.is_deleted == False]
        if status and status != "all":
            conditions.append(Task.status == status)

        stmt = select(Task).where(and_(*conditions)).order_by(
            Task.due_date.asc().nulls_last(), Task.created_at.desc()
        )
        res = await session.execute(stmt)
        return list(res.scalars().all())

    async def create_or_update_task(
        self,
        session: AsyncSession,
        user_id: str,
        task_id: Optional[str],
        title: str,
        description: Optional[str] = None,
        status: str = "pending",
        priority: str = "medium",
        due_date: Optional[datetime] = None,
    ) -> Task:
        tid = task_id or f"tsk-{uuid.uuid4().hex[:8]}"
        head = await self._lock_head(session, user_id)
        stmt = select(Task).where(Task.id == tid, Task.user_id == user_id)
        res = await session.execute(stmt)
        task = res.scalar_one_or_none()

        action = "update" if task else "create"
        if task:
            task.title = title
            task.description = description
            task.status = status
            task.priority = priority
            task.due_date = due_date
            task.is_deleted = False
            task.version += 1
            task.updated_at = datetime.utcnow()
        else:
            task = Task(
                id=tid,
                user_id=user_id,
                title=title,
                description=description,
                status=status,
                priority=priority,
                due_date=due_date,
                version=1,
                is_deleted=False,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
            session.add(task)

        self._record_change(session, head, task, "task", action)
        await session.commit()
        await session.refresh(task)
        return task

    async def delete_task(
        self, session: AsyncSession, user_id: str, task_id: str
    ) -> bool:
        head = await self._lock_head(session, user_id)
        stmt = select(Task).where(Task.id == task_id, Task.user_id == user_id)
        res = await session.execute(stmt)
        task = res.scalar_one_or_none()
        if not task or task.is_deleted:
            return False

        task.is_deleted = True
        task.version += 1
        task.updated_at = datetime.utcnow()
        self._record_change(session, head, task, "task", "delete")
        await session.commit()
        return True

    async def toggle_task_completed(
        self, session: AsyncSession, user_id: str, task_id: str
    ) -> Optional[Task]:
        head = await self._lock_head(session, user_id)
        stmt = select(Task).where(
            Task.id == task_id, Task.user_id == user_id, Task.is_deleted == False
        )
        res = await session.execute(stmt)
        task = res.scalar_one_or_none()
        if not task:
            return None

        task.status = "completed" if task.status != "completed" else "pending"
        task.version += 1
        task.updated_at = datetime.utcnow()
        self._record_change(session, head, task, "task", "update")
        await session.commit()
        await session.refresh(task)
        return task


agenda_service = AgendaService()
