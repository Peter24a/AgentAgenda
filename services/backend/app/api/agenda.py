from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query
from app.models.agenda import AgendaItemModel, AgendaItemCreate
from app.db.database import get_events_for_date, upsert_event, delete_event

router = APIRouter(prefix="/v1/agenda", tags=["Agenda"])

@router.get("/events", response_model=List[AgendaItemModel])
async def list_events(date: Optional[str] = Query(None, description="Fecha YYYY-MM-DD")):
    target_date = date or datetime.now().strftime("%Y-%m-%d")
    events = await get_events_for_date(target_date)
    return events

@router.post("/events", response_model=AgendaItemModel)
async def create_or_update_event(item: AgendaItemCreate):
    import uuid
    item_id = item.id or f"evt-{uuid.uuid4().hex[:8]}"
    model = AgendaItemModel(
        id=item_id,
        title=item.title,
        description=item.description,
        start_time=item.start_time,
        end_time=item.end_time,
        category=item.category,
        is_completed=item.is_completed,
    )
    await upsert_event(model)
    return model

@router.delete("/events/{event_id}")
async def remove_event(event_id: str):
    await delete_event(event_id)
    return {"success": True, "deleted_id": event_id}

@router.post("/events/{event_id}/toggle")
async def toggle_event_completed(event_id: str, date: Optional[str] = None):
    target_date = date or datetime.now().strftime("%Y-%m-%d")
    events = await get_events_for_date(target_date)
    found = next((e for e in events if e.id == event_id), None)
    if not found:
        raise HTTPException(status_code=404, detail="Evento no encontrado")

    updated = found.model_copy(update={"is_completed": not found.is_completed})
    await upsert_event(updated)
    return updated
