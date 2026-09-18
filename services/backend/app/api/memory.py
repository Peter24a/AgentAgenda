from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db_session, require_scope, has_scope
from app.models.auth import AuthContext
from app.models.memory import (
    ContextAssembleRequest,
    ContextAssembleResponse,
    MemoryCorrectRequest,
    MemoryCreateRequest,
    MemoryDetail,
    MemoryForgetRequest,
    MemorySearchRequest,
    MemorySearchResponse,
)
from app.services.context_engine import context_engine
from app.services.memory_service import memory_service

router = APIRouter(tags=["Structured Memory & Context Engine"])


def validate_context_scopes(auth, include_agenda):
    if include_agenda and not all(has_scope(auth, scope) for scope in ("agenda:read", "tasks:read")):
        raise HTTPException(status_code=403, detail="Se requieren agenda:read y tasks:read para incluir agenda")


@router.post(
    "/v1/memory",
    response_model=MemoryDetail,
    status_code=status.HTTP_201_CREATED,
    summary="Registrar un nuevo hecho o recuerdo en la memoria canónica",
)
async def create_memory(
    req: MemoryCreateRequest,
    session: AsyncSession = Depends(get_db_session),
    auth: AuthContext = Depends(require_scope("memory:write")),
):
    mem = await memory_service.create_memory(
        session=session,
        user_id=auth.user_id,
        req=req,
    )
    return MemoryDetail.model_validate(mem)


@router.post(
    "/v1/memory/search",
    response_model=MemorySearchResponse,
    summary="Búsqueda y consulta de hechos en memoria",
)
async def search_memories(
    req: MemorySearchRequest,
    session: AsyncSession = Depends(get_db_session),
    auth: AuthContext = Depends(require_scope("memory:read")),
):
    memories, total = await memory_service.search_memories(
        session=session,
        user_id=auth.user_id,
        req=req,
    )
    return MemorySearchResponse(
        total=total,
        memories=[MemoryDetail.model_validate(m) for m in memories],
    )


@router.get(
    "/v1/memory/{id}",
    response_model=MemoryDetail,
    summary="Consultar detalle y fuentes de una memoria específica",
)
async def get_memory(
    id: str,
    session: AsyncSession = Depends(get_db_session),
    auth: AuthContext = Depends(require_scope("memory:read")),
):
    mem = await memory_service.get_memory_by_id(session, auth.user_id, id)
    if not mem:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Memoria '{id}' no encontrada",
        )
    return MemoryDetail.model_validate(mem)


@router.post(
    "/v1/memory/correct",
    response_model=MemoryDetail,
    summary="Corregir un hecho existente (versionado y linaje)",
    description="Marca la versión anterior como superseded y crea una nueva versión activa con el hecho actualizado.",
)
async def correct_memory(
    req: MemoryCorrectRequest,
    session: AsyncSession = Depends(get_db_session),
    auth: AuthContext = Depends(require_scope("memory:write")),
):
    try:
        new_mem = await memory_service.correct_memory(
            session=session,
            user_id=auth.user_id,
            req=req,
        )
        return MemoryDetail.model_validate(new_mem)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post(
    "/v1/memory/forget",
    summary="Olvidar o revocar un hecho (revocación canónica)",
    description="Marca el hecho como revoked. Nunca más se inyectará en ensamblajes de contexto.",
)
async def forget_memory(
    req: MemoryForgetRequest,
    session: AsyncSession = Depends(get_db_session),
    auth: AuthContext = Depends(require_scope("memory:write")),
):
    try:
        await memory_service.forget_memory(
            session=session,
            user_id=auth.user_id,
            req=req,
        )
        return {"status": "revoked", "memory_id": req.memory_id}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get(
    "/v1/context",
    response_model=ContextAssembleResponse,
    summary="Ensamblar bloque de contexto estructurado con presupuesto de tokens",
)
async def get_context(
    purpose: str = Query("general_chat", description="Propósito del contexto"),
    as_of: Optional[datetime] = Query(None, description="Fecha de referencia"),
    token_budget: int = Query(6144, ge=256, le=24576),
    include_agenda: bool = Query(True),
    include_memories: bool = Query(True),
    session: AsyncSession = Depends(get_db_session),
    auth: AuthContext = Depends(require_scope("memory:read")),
):
    validate_context_scopes(auth, include_agenda)
    req = ContextAssembleRequest(
        purpose=purpose,
        as_of=as_of,
        token_budget=token_budget,
        include_agenda=include_agenda,
        include_memories=include_memories,
    )
    return await context_engine.assemble_context(
        session=session,
        user_id=auth.user_id,
        req=req,
    )


@router.post(
    "/v1/context",
    response_model=ContextAssembleResponse,
    summary="Ensamblar bloque de contexto estructurado mediante especificación JSON",
)
async def assemble_context_post(
    req: ContextAssembleRequest,
    session: AsyncSession = Depends(get_db_session),
    auth: AuthContext = Depends(require_scope("memory:read")),
):
    validate_context_scopes(auth, req.include_agenda)
    return await context_engine.assemble_context(
        session=session,
        user_id=auth.user_id,
        req=req,
    )
