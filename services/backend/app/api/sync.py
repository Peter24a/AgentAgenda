from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_auth, get_db_session
from app.models.auth import AuthContext
from app.models.sync import (
    SyncBootstrapResponse,
    SyncPushRequest,
    SyncPushResponse,
    SyncPullResponse,
    SyncAckRequest,
    SyncAckResponse,
    OperationReceiptResponse,
)
from app.services.sync_service import sync_service

router = APIRouter(prefix="/v1", tags=["Sync Protocol"])


@router.post(
    "/sync/bootstrap",
    response_model=SyncBootstrapResponse,
    summary="Inicialización y réplica base (Bootstrap)",
    description="Devuelve un snapshot consistente de agenda y tareas junto al watermark actual del cursor.",
)
async def sync_bootstrap(
    session: AsyncSession = Depends(get_db_session),
    auth: AuthContext = Depends(get_current_auth),
):
    return await sync_service.get_bootstrap(session, auth.user_id)


@router.post(
    "/sync/push",
    response_model=SyncPushResponse,
    summary="Enviar lote de mutaciones offline (Push)",
    description="Procesa un conjunto ordenado de operaciones lógicas con deduplicación idempotente y detección de conflictos.",
)
async def sync_push(
    req: SyncPushRequest,
    session: AsyncSession = Depends(get_db_session),
    auth: AuthContext = Depends(get_current_auth),
):
    return await sync_service.push_operations(
        session=session,
        user_id=auth.user_id,
        device_id=auth.device_id or req.device_id,
        req=req,
    )


@router.get(
    "/sync/pull",
    response_model=SyncPullResponse,
    summary="Consultar cambios incrementales (Pull)",
    description="Devuelve la secuencia de cambios confirmados a partir del commit_seq indicado por el cliente.",
)
async def sync_pull(
    since_seq: int = Query(0, ge=0, description="Último commit_seq conocido por el cliente"),
    limit: int = Query(100, ge=1, le=500, description="Límite máximo de cambios por lote"),
    session: AsyncSession = Depends(get_db_session),
    auth: AuthContext = Depends(get_current_auth),
):
    return await sync_service.pull_changes(
        session=session,
        user_id=auth.user_id,
        since_seq=since_seq,
        limit=limit,
    )


@router.post(
    "/sync/ack",
    response_model=SyncAckResponse,
    summary="Confirmar recepción y aplicación local (Ack)",
    description="Informa al servidor que el cliente ha aplicado los cambios hasta una secuencia específica.",
)
async def sync_ack(
    req: SyncAckRequest,
    session: AsyncSession = Depends(get_db_session),
    auth: AuthContext = Depends(get_current_auth),
):
    return await sync_service.acknowledge(
        session=session,
        user_id=auth.user_id,
        ack_req=req,
    )


@router.get(
    "/operations/{operation_id}",
    response_model=OperationReceiptResponse,
    summary="Consultar estado de operación por ID",
    description="Permite recuperar el recibo de ejecución tras un corte de red o timeout durante un push.",
)
async def get_operation_receipt(
    operation_id: str,
    session: AsyncSession = Depends(get_db_session),
    auth: AuthContext = Depends(get_current_auth),
):
    receipt = await sync_service.get_operation_receipt(
        session=session,
        user_id=auth.user_id,
        operation_id=operation_id,
    )
    if not receipt:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Recibo de operación '{operation_id}' no encontrado",
        )
    return receipt
