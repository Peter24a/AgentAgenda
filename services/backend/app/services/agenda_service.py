import uuid
from datetime import datetime, time
from typing import Any, Dict, List, Optional
import pytz
from sqlalchemy import select, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.canonical import Event, Task, ChangeBatch, SyncHead
from app.models.agenda import AgendaItemCreate, ActivityCategory


class AgendaService:
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
        local_end = tz.localize(datetime.combine(dt.date(), time.max))

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
            conditions.append(Event.start_time >= utc_start)
            conditions.append(Event.start_time <= utc_end)
        elif start_date and end_date:
            utc_start, _ = self._parse_date_range(start_date, timezone)
            _, utc_end = self._parse_date_range(end_date, timezone)
            conditions.append(Event.start_time >= utc_start)
            conditions.append(Event.start_time <= utc_end)

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
        stmt = select(Event).where(Event.id == event_id, Event.user_id == user_id)
        res = await session.execute(stmt)
        event = res.scalar_one_or_none()

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

        await session.commit()
        await session.refresh(event)
        return event

    async def delete_event(
        self, session: AsyncSession, user_id: str, event_id: str
    ) -> bool:
        stmt = select(Event).where(Event.id == event_id, Event.user_id == user_id)
        res = await session.execute(stmt)
        event = res.scalar_one_or_none()
        if not event or event.is_deleted:
            return False

        event.is_deleted = True
        event.version += 1
        event.updated_at = datetime.utcnow()
        await session.commit()
        return True

    async def toggle_event_completed(
        self, session: AsyncSession, user_id: str, event_id: str
    ) -> Optional[Event]:
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
        stmt = select(Task).where(Task.id == tid, Task.user_id == user_id)
        res = await session.execute(stmt)
        task = res.scalar_one_or_none()

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

        await session.commit()
        await session.refresh(task)
        return task

    async def delete_task(
        self, session: AsyncSession, user_id: str, task_id: str
    ) -> bool:
        stmt = select(Task).where(Task.id == task_id, Task.user_id == user_id)
        res = await session.execute(stmt)
        task = res.scalar_one_or_none()
        if not task or task.is_deleted:
            return False

        task.is_deleted = True
        task.version += 1
        task.updated_at = datetime.utcnow()
        await session.commit()
        return True

    async def toggle_task_completed(
        self, session: AsyncSession, user_id: str, task_id: str
    ) -> Optional[Task]:
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
        await session.commit()
        await session.refresh(task)
        return task


agenda_service = AgendaService()
