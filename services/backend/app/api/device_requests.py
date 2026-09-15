from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db_session, require_scope
from app.models.auth import AuthContext
from app.models.canonical import DeviceObservation
from app.models.device_request import (
    CreateDeviceRequest,
    DeviceObservationPayload,
    DeviceObservationResponse,
    DeviceRequestResponse,
)
from app.services.device_request_service import device_request_service

router = APIRouter(prefix="/v1/device-requests", tags=["Device Requests & Mobile Context"])


@router.post(
    "",
    response_model=DeviceRequestResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Crear solicitud asíncrona de contexto al dispositivo móvil",
)
async def create_device_request(
    req: CreateDeviceRequest,
    session: AsyncSession = Depends(get_db_session),
    auth: AuthContext = Depends(require_scope("device_requests:write")),
):
    target_dev = req.device_id or auth.device_id or "dev-unspecified"
    dreq = await device_request_service.create_request(
        session=session,
        user_id=auth.user_id,
        target_device_id=target_dev,
        req=req,
    )
    return DeviceRequestResponse.model_validate(dreq)


@router.get(
    "/pending",
    response_model=List[DeviceRequestResponse],
    summary="Consultar solicitudes pendientes para el dispositivo",
)
async def get_pending_requests(
    device_id: Optional[str] = Query(None, description="ID del dispositivo (por defecto el del token)"),
    session: AsyncSession = Depends(get_db_session),
    auth: AuthContext = Depends(require_scope("device_requests:read")),
):
    dev = device_id or auth.device_id
    requests = await device_request_service.get_pending_requests(
        session=session,
        user_id=auth.user_id,
        device_id=dev,
    )
    return [DeviceRequestResponse.model_validate(r) for r in requests]


@router.get(
    "/{id}",
    response_model=DeviceRequestResponse,
    summary="Consultar estado de una solicitud al dispositivo",
)
async def get_device_request(
    id: str,
    session: AsyncSession = Depends(get_db_session),
    auth: AuthContext = Depends(require_scope("device_requests:read")),
):
    dreq = await device_request_service.get_request_by_id(session, auth.user_id, id)
    if not dreq:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Solicitud '{id}' no encontrada",
        )
    return DeviceRequestResponse.model_validate(dreq)


@router.post(
    "/{id}/response",
    response_model=DeviceRequestResponse,
    summary="Entregar observación o respuesta desde el dispositivo",
)
async def respond_to_device_request(
    id: str,
    obs: DeviceObservationPayload,
    session: AsyncSession = Depends(get_db_session),
    auth: AuthContext = Depends(require_scope("device_requests:write")),
):
    try:
        dreq, _ = await device_request_service.record_observation(
            session=session,
            user_id=auth.user_id,
            device_id=auth.device_id or "dev-unknown",
            request_id=id,
            obs=obs,
        )
        return DeviceRequestResponse.model_validate(dreq)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get(
    "/{id}/observation",
    response_model=DeviceObservationResponse,
    summary="Consultar la observación guardada para una solicitud",
)
async def get_request_observation(
    id: str,
    session: AsyncSession = Depends(get_db_session),
    auth: AuthContext = Depends(require_scope("device_requests:read")),
):
    res = await session.execute(
        select(DeviceObservation).where(
            DeviceObservation.request_id == id,
            DeviceObservation.user_id == auth.user_id,
        )
    )
    obs = res.scalar_one_or_none()
    if not obs:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No se encontró observación registrada para la solicitud '{id}'",
        )
    return DeviceObservationResponse.model_validate(obs)
