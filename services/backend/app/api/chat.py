import json
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_auth, get_db_session, require_scope
from app.models.auth import AuthContext
from app.models.chat import (
    ChatMessageResponse,
    ChatRequest,
    ChatTurnResponse,
    CreateTurnRequest,
)
from app.services.chat_orchestrator import chat_orchestrator

router = APIRouter(prefix="/v1/chat", tags=["Durable Chat & LLM"])


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
