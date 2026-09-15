from datetime import datetime
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_auth_optional, get_db_session
from app.models.auth import AuthContext
from app.models.agenda import AgendaItemModel, AgendaItemCreate, ActivityCategory
from app.models.canonical import Event, Task
from app.services.agenda_service import agenda_service
from app.db.database import (
    get_events_for_date as get_sqlite_events,
    delete_event as delete_sqlite_event,
    toggle_event as toggle_sqlite_event,
)

router = APIRouter(prefix="/v1/agenda", tags=["Agenda & Tasks"])


def _event_to_model(e: Event) -> AgendaItemModel:
    cat = e.category if e.category in [c.value for c in ActivityCategory] else "general"
    return AgendaItemModel(
        id=e.id,
        title=e.title,
        description=e.description,
        start_time=e.start_time,
        end_time=e.end_time,
        category=ActivityCategory(cat),
        is_completed=e.is_completed,
    )


@router.get("/events", response_model=List[AgendaItemModel])
async def list_events(
    date: Optional[str] = Query(None, description="Fecha YYYY-MM-DD"),
    start_date: Optional[str] = Query(None, description="Fecha inicio YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="Fecha fin YYYY-MM-DD"),
    timezone: str = Query("America/Mexico_City", description="Zona horaria IANA"),
    session: AsyncSession = Depends(get_db_session),
    auth: Optional[AuthContext] = Depends(get_current_auth_optional),
):
    user_id = auth.user_id if auth else "default_user"
    target_date = date
    if not date and not (start_date and end_date):
        target_date = datetime.now().strftime("%Y-%m-%d")

    events = await agenda_service.list_events(
        session=session,
        user_id=user_id,
        date=target_date,
        start_date=start_date,
        end_date=end_date,
        timezone=timezone,
    )
    if not events and target_date:
        try:
            legacy_events = await get_sqlite_events(target_date)
            if legacy_events:
                return legacy_events
        except Exception:
            pass

    return [_event_to_model(e) for e in events]


@router.post("/events", response_model=AgendaItemModel)
async def create_or_update_event(
    item: AgendaItemCreate,
    timezone: str = Query("America/Mexico_City", description="Zona horaria IANA"),
    session: AsyncSession = Depends(get_db_session),
    auth: Optional[AuthContext] = Depends(get_current_auth_optional),
):
    user_id = auth.user_id if auth else "default_user"
    event = await agenda_service.upsert_event(
        session=session,
        user_id=user_id,
        item=item,
        timezone=timezone,
    )
    return _event_to_model(event)


@router.delete("/events/{event_id}")
async def remove_event(
    event_id: str,
    session: AsyncSession = Depends(get_db_session),
    auth: Optional[AuthContext] = Depends(get_current_auth_optional),
):
    user_id = auth.user_id if auth else "default_user"
    deleted = await agenda_service.delete_event(session, user_id, event_id)
    if not deleted:
        try:
            sqlite_deleted = await delete_sqlite_event(event_id)
            if sqlite_deleted:
                return {"success": True, "deleted_id": event_id}
        except Exception:
            pass
        raise HTTPException(status_code=404, detail="Evento no encontrado")
    return {"success": True, "deleted_id": event_id}


@router.post("/events/{event_id}/toggle", response_model=AgendaItemModel)
async def toggle_event_completed(
    event_id: str,
    session: AsyncSession = Depends(get_db_session),
    auth: Optional[AuthContext] = Depends(get_current_auth_optional),
):
    user_id = auth.user_id if auth else "default_user"
    updated = await agenda_service.toggle_event_completed(session, user_id, event_id)
    if updated:
        return _event_to_model(updated)

    try:
        legacy_updated = await toggle_sqlite_event(event_id)
        if legacy_updated:
            return legacy_updated
    except Exception:
        pass

    raise HTTPException(status_code=404, detail="Evento no encontrado")


@router.get("/tasks")
async def list_tasks(
    status: Optional[str] = Query(None, description="pending, completed, all"),
    session: AsyncSession = Depends(get_db_session),
    auth: Optional[AuthContext] = Depends(get_current_auth_optional),
):
    user_id = auth.user_id if auth else "default_user"
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
    auth: Optional[AuthContext] = Depends(get_current_auth_optional),
):
    user_id = auth.user_id if auth else "default_user"
    updated = await agenda_service.toggle_task_completed(session, user_id, task_id)
    if not updated:
        raise HTTPException(status_code=404, detail="Tarea no encontrada")
    return {
        "id": updated.id,
        "title": updated.title,
        "status": updated.status,
        "version": updated.version,
    }
