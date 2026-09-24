from datetime import datetime, timezone as dt_timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
import hashlib
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db_session, require_scope
from app.models.auth import AuthContext
from app.models.agenda import AgendaItemModel, AgendaItemCreate, ActivityCategory
from app.models.canonical import Event, Task, Memory
from app.services.agenda_service import agenda_service


router = APIRouter(prefix="/v1/agenda", tags=["Agenda & Tasks"])


def _event_to_model(e: Event) -> AgendaItemModel:
    cat = e.category if e.category in [c.value for c in ActivityCategory] else "general"
    return AgendaItemModel(
        id=e.id,
        title=e.title,
        description=e.description,
        start_time=e.start_time.replace(tzinfo=dt_timezone.utc),
        end_time=e.end_time.replace(tzinfo=dt_timezone.utc) if e.end_time else None,
        category=ActivityCategory(cat),
        is_completed=e.is_completed,
    )


class ActivityCheckIn(BaseModel):
    request_id: str = Field(min_length=1, max_length=100)
    activity: str = Field(min_length=1, max_length=2000)
    observed_at: datetime

    @field_validator('activity')
    @classmethod
    def nonempty_activity(cls, value):
        if not value.strip():
            raise ValueError('Describe la actividad')
        return value.strip()

    @field_validator('observed_at')
    @classmethod
    def explicit_timezone(cls, value):
        if value.tzinfo is None:
            raise ValueError('La fecha debe incluir zona horaria')
        return value


@router.post('/check-ins', summary='Recordar una actividad declarada por el usuario')
async def record_activity(
    req: ActivityCheckIn,
    session: AsyncSession = Depends(get_db_session),
    auth: AuthContext = Depends(require_scope('memory:write')),
):
    memory_id = 'mem-activity-' + hashlib.sha256((auth.user_id + '\0' + req.request_id).encode()).hexdigest()[:40]
    observed = req.observed_at.astimezone(dt_timezone.utc).replace(tzinfo=None)
    existing = await session.get(Memory, memory_id)
    if existing:
        if existing.value != req.activity or existing.valid_from != observed or existing.status != 'active':
            raise HTTPException(409, 'El registro ya existe con otro contenido o fue retirado')
        return {'memory_id': memory_id, 'status': 'recorded'}
    now = datetime.now(dt_timezone.utc).replace(tzinfo=None)
    session.add(Memory(
        id=memory_id, user_id=auth.user_id, memory_type='episodic',
        predicate='activity_check_in', value=req.activity,
        context_text='Actividad declarada al responder al chat durante un hueco del horario.',
        source_kind='phone', status='active', valid_from=observed, valid_to=observed,
        version=1, created_at=now, updated_at=now,
    ))
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        existing = await session.get(Memory, memory_id)
        if not existing or existing.value != req.activity or existing.valid_from != observed or existing.status != 'active':
            raise HTTPException(409, 'Conflicto al guardar la actividad')
    return {'memory_id': memory_id, 'status': 'recorded'}


@router.get("/events", response_model=List[AgendaItemModel])
async def list_events(
    date: Optional[str] = Query(None, description="Fecha YYYY-MM-DD"),
    start_date: Optional[str] = Query(None, description="Fecha inicio YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="Fecha fin YYYY-MM-DD"),
    timezone: str = Query("America/Mexico_City", description="Zona horaria IANA"),
    session: AsyncSession = Depends(get_db_session),
    auth: AuthContext = Depends(require_scope("agenda:read")),
):
    user_id = auth.user_id
    target_date = date
    if not date and not (start_date and end_date):
        try:
            target_date = datetime.now(ZoneInfo(timezone)).strftime("%Y-%m-%d")
        except (ValueError, ZoneInfoNotFoundError):
            raise HTTPException(422, "Zona horaria inválida") from None

    try:
        ZoneInfo(timezone)
        for value in (target_date, start_date, end_date):
            if value is not None:
                datetime.strptime(value, "%Y-%m-%d")
        if bool(start_date) != bool(end_date) or (start_date and end_date and start_date > end_date):
            raise ValueError()
    except (ValueError, ZoneInfoNotFoundError):
        raise HTTPException(422, "Intervalo o zona horaria inválidos") from None

    events = await agenda_service.list_events(
        session=session,
        user_id=user_id,
        date=target_date,
        start_date=start_date,
        end_date=end_date,
        timezone=timezone,
    )
    return [_event_to_model(e) for e in events]


@router.post("/events", response_model=AgendaItemModel)
async def create_or_update_event(
    item: AgendaItemCreate,
    timezone: str = Query("America/Mexico_City", description="Zona horaria IANA"),
    session: AsyncSession = Depends(get_db_session),
    auth: AuthContext = Depends(require_scope("agenda:write")),
):
    user_id = auth.user_id
    try:
        event = await agenda_service.upsert_event(
            session=session,
            user_id=user_id,
            item=item,
            timezone=timezone,
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    return _event_to_model(event)


@router.delete("/events/{event_id}")
async def remove_event(
    event_id: str,
    session: AsyncSession = Depends(get_db_session),
    auth: AuthContext = Depends(require_scope("agenda:write")),
):
    user_id = auth.user_id
    deleted = await agenda_service.delete_event(session, user_id, event_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Evento no encontrado")
    return {"success": True, "deleted_id": event_id}


@router.post("/events/{event_id}/toggle", response_model=AgendaItemModel)
async def toggle_event_completed(
    event_id: str,
    session: AsyncSession = Depends(get_db_session),
    auth: AuthContext = Depends(require_scope("agenda:write")),
):
    user_id = auth.user_id
    updated = await agenda_service.toggle_event_completed(session, user_id, event_id)
    if updated:
        return _event_to_model(updated)

    raise HTTPException(status_code=404, detail="Evento no encontrado")


@router.get("/tasks")
async def list_tasks(
    status: Optional[str] = Query(None, description="pending, completed, all"),
    session: AsyncSession = Depends(get_db_session),
    auth: AuthContext = Depends(require_scope("agenda:read")),
):
    user_id = auth.user_id
    tasks = await agenda_service.list_tasks(session, user_id, status=status)
    return [
        {
            "id": t.id,
            "title": t.title,
            "description": t.description,
            "status": t.status,
            "priority": t.priority,
            "due_date": t.due_date.isoformat() if t.due_date else None,
            "version": t.version,
        }
        for t in tasks
    ]


@router.post("/tasks/{task_id}/toggle")
async def toggle_task_completed(
    task_id: str,
    session: AsyncSession = Depends(get_db_session),
    auth: AuthContext = Depends(require_scope("agenda:write")),
):
    user_id = auth.user_id
    updated = await agenda_service.toggle_task_completed(session, user_id, task_id)
    if not updated:
        raise HTTPException(status_code=404, detail="Tarea no encontrada")
    return {
        "id": updated.id,
        "title": updated.title,
        "status": updated.status,
        "version": updated.version,
    }


class RoutineEnabledRequest(BaseModel):
    enabled: bool


@router.get('/routines')
async def list_routines(session: AsyncSession = Depends(get_db_session), auth: AuthContext = Depends(require_scope('agenda:read'))):
    from sqlalchemy import select
    from app.models.canonical import WeeklyRoutine
    rows = (await session.scalars(select(WeeklyRoutine).where(WeeklyRoutine.user_id == auth.user_id))).all()
    return [{'id': r.id, 'name': r.name, 'enabled': r.enabled, 'timezone': r.timezone,
             'materialized_through': r.materialized_through} for r in rows]


@router.put('/routines/{routine_id}/enabled')
async def enable_routine(routine_id: str, req: RoutineEnabledRequest, auth: AuthContext = Depends(require_scope('agenda:write'))):
    from app.services.weekly_routines import set_routine_enabled
    result = await set_routine_enabled(routine_id, auth.user_id, req.enabled)
    if result is None:
        raise HTTPException(404, 'Rutina no encontrada')
    return result
