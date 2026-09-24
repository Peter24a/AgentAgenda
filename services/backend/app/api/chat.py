from datetime import datetime, timedelta, timezone
import uuid
from sqlalchemy import select, and_, or_, exists
from sqlalchemy.exc import IntegrityError
import json
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_auth, get_db_session, require_scope
from app.models.auth import AuthContext
from app.models.chat import (
    ChatMessageResponse,
    ChatWindowResponse,
    CheckInRequest,
    ChatRequest,
    ChatTurnResponse,
    CreateTurnRequest,
)
from app.services.chat_orchestrator import chat_orchestrator

router = APIRouter(prefix="/v1/chat", tags=["Durable Chat & LLM"])


def _can_read_documents(auth: AuthContext) -> bool:
    return bool(set(auth.scopes or []) & {"documents:read", "documents:*", "*", "admin"})


def _can_read_memory(auth: AuthContext) -> bool:
    return bool(set(auth.scopes or []) & {"memory:read", "memory:*", "*", "admin"})


@router.post(
    "/turns",
    response_model=ChatTurnResponse,
    summary="Crear o recuperar turno de conversación durable",
    description="Persiste de inmediato el mensaje de usuario en base de datos con status 'queued' e inicia la generación desacoplada en segundo plano.",
)
async def create_chat_turn(
    req: CreateTurnRequest,
    session: AsyncSession = Depends(get_db_session),
    auth: AuthContext = Depends(require_scope("chat:write")),
):
    turn_response, created = await chat_orchestrator.create_or_get_turn(
        session=session,
        user_id=auth.user_id,
        device_id=auth.device_id,
        req=req,
        allow_document_context=_can_read_documents(auth),
        allow_memory_context=_can_read_memory(auth),
    )
    return turn_response


@router.get(
    "/turns/{turn_id}",
    response_model=ChatTurnResponse,
    summary="Consultar estado durable de un turno",
    description="Permite recuperar el estado y contenido completo del asistente tras reconexión (queued, running, completed, failed).",
)
async def get_chat_turn(
    turn_id: str,
    session: AsyncSession = Depends(get_db_session),
    auth: AuthContext = Depends(require_scope("chat:read")),
):
    turn_resp = await chat_orchestrator.get_turn_response(
        session=session,
        user_id=auth.user_id,
        turn_id=turn_id,
    )
    if not turn_resp:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Turno '{turn_id}' no encontrado",
        )
    return turn_resp


@router.get(
    "/turns/{turn_id}/stream",
    summary="Suscripción SSE a la generación de un turno",
    description="Envía tokens en tiempo real vía Server-Sent Events. Si el cliente se desconecta, la persistencia en el backend continúa hasta completarse.",
)
async def stream_chat_turn(
    turn_id: str,
    auth: AuthContext = Depends(require_scope("chat:read")),
):
    return StreamingResponse(
        chat_orchestrator.subscribe_turn_sse(turn_id, auth.user_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get(
    "/messages",
    response_model=List[ChatMessageResponse],
    summary="Historial durable de mensajes",
    description="Devuelve el historial de conversación paginado mediante cursor.",
)
async def list_chat_messages(
    cursor: Optional[str] = Query(None, description="Cursor para paginación"),
    limit: int = Query(50, ge=1, le=100, description="Cantidad máxima de mensajes"),
    session: AsyncSession = Depends(get_db_session),
    auth: AuthContext = Depends(require_scope("chat:read")),
):
    return await chat_orchestrator.list_messages(
        session=session,
        user_id=auth.user_id,
        cursor=cursor,
        limit=limit,
    )


@router.get("/history", response_model=ChatWindowResponse)
async def chat_history_window(
    before: Optional[datetime] = None,
    cursor: Optional[str] = None,
    limit: int = Query(60, ge=1, le=100),
    session: AsyncSession = Depends(get_db_session),
    auth: AuthContext = Depends(require_scope("chat:read")),
):
    from app.models.canonical import ChatMessage
    end = before or datetime.now(timezone.utc)
    end = end.astimezone(timezone.utc).replace(tzinfo=None) if end.tzinfo else end
    start = end - timedelta(hours=12)
    filters = [ChatMessage.user_id == auth.user_id, ChatMessage.created_at >= start, ChatMessage.created_at < end]
    if cursor:
        anchor = await session.scalar(select(ChatMessage).where(ChatMessage.id == cursor, ChatMessage.user_id == auth.user_id))
        if not anchor or not start <= anchor.created_at < end:
            raise HTTPException(400, "Cursor de historial inválido")
        filters.append(or_(ChatMessage.created_at < anchor.created_at,
                           and_(ChatMessage.created_at == anchor.created_at, ChatMessage.id < anchor.id)))
    rows = list((await session.scalars(select(ChatMessage).where(*filters)
                .order_by(ChatMessage.created_at.desc(), ChatMessage.id.desc()).limit(limit + 1))).all())
    more_in_window = len(rows) > limit
    rows = rows[:limit]
    has_older = more_in_window or bool(await session.scalar(select(exists().where(
        ChatMessage.user_id == auth.user_id, ChatMessage.created_at < start))))
    return ChatWindowResponse(
        messages=[ChatMessageResponse.model_validate(row) for row in reversed(rows)],
        window_start=start.replace(tzinfo=timezone.utc), window_end=end.replace(tzinfo=timezone.utc),
        next_cursor=rows[-1].id if more_in_window else None, has_older=has_older,
    )


@router.post("/check-ins", response_model=ChatMessageResponse)
async def open_check_in(
    req: CheckInRequest,
    session: AsyncSession = Depends(get_db_session),
    auth: AuthContext = Depends(require_scope("chat:write")),
):
    from app.models.canonical import ChatMessage, Event
    message_id = 'check-' + uuid.uuid5(uuid.NAMESPACE_URL, auth.user_id + ':' + req.notification_key).hex
    existing = await session.get(ChatMessage, message_id)
    if existing:
        return ChatMessageResponse.model_validate(existing)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    scheduled = req.scheduled_at
    scheduled = scheduled.astimezone(timezone.utc).replace(tzinfo=None) if scheduled and scheduled.tzinfo else scheduled
    can_read_agenda = bool(set(auth.scopes or []) & {"agenda:read", "agenda:*", "*", "admin"})
    event = await session.scalar(select(Event).where(Event.id == req.event_id, Event.user_id == auth.user_id, Event.is_deleted.is_(False))) if req.event_id and can_read_agenda else None
    if can_read_agenda and event is None and req.event_id is None and req.kind == 'check_in':
        event = await session.scalar(select(Event).where(
            Event.user_id == auth.user_id, Event.is_deleted.is_(False), Event.category != 'sleep',
            Event.end_time <= now, Event.end_time >= now - timedelta(hours=3),
        ).order_by(Event.end_time.desc()).limit(1))
    fresh = scheduled is not None and abs((now - scheduled).total_seconds()) < 4 * 3600
    if event and fresh:
        if req.kind == 'reminder' and abs((event.start_time - scheduled).total_seconds()) <= 3600:
            prompt = f'Tienes programado «{event.title}». ¿Necesitas ajustar algo o preparar lo necesario?'
        elif event.end_time and event.end_time <= now and (now - event.end_time).total_seconds() <= 4 * 3600:
            prompt = f'¿Cómo te fue con «{event.title}»? Cuéntame si lo hiciste, cambió el plan o necesitas retomarlo.'
        else:
            prompt = '¿Cómo va tu día? Cuéntame qué has hecho y qué necesitas ajustar.'
    else:
        prompt = '¿Cómo va tu día? Cuéntame qué has hecho, cómo te sientes y qué te gustaría ajustar.'
    message = ChatMessage(id=message_id, user_id=auth.user_id, role='assistant', content=prompt, received_at=now, created_at=now)
    session.add(message)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        message = await session.get(ChatMessage, message_id)
    return ChatMessageResponse.model_validate(message)


@router.post(
    "/stream",
    summary="Streaming de compatibilidad con app móvil existente",
    description="Crea un turno durable en segundo plano y emite el stream SSE de forma transparente.",
)
async def chat_stream_legacy(
    request: ChatRequest,
    session: AsyncSession = Depends(get_db_session),
    auth: AuthContext = Depends(require_scope("chat:write")),
):
    # Convertir petición legacy a CreateTurnRequest
    turn_req = CreateTurnRequest(
        message=request.message,
        date=request.date,
        history=request.history,
    )
    turn_resp, _ = await chat_orchestrator.create_or_get_turn(
        session=session,
        user_id=auth.user_id,
        device_id=auth.device_id,
        req=turn_req,
        allow_document_context=_can_read_documents(auth),
        allow_memory_context=_can_read_memory(auth),
    )

    return StreamingResponse(
        chat_orchestrator.subscribe_turn_sse(turn_resp.turn_id, auth.user_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
