from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_auth, get_db_session, get_explicit_auth
from app.models.auth import (
    AuthContext,
    ChallengeResponse,
    PairRequest,
    PairResponse,
    RefreshTokenRequest,
    RefreshTokenResponse,
    RevokeRequest,
    RevokeResponse,
)
from app.services.auth_service import auth_service

router = APIRouter(prefix="/v1/auth", tags=["Auth & Devices"])


@router.post(
    "/challenge",
    response_model=ChallengeResponse,
    summary="Generar código de emparejamiento de un solo uso",
    description="Crea un desafío alfanumérico temporal con caducidad para emparejar un nuevo dispositivo.",
)
async def generate_pairing_challenge():
    code, expires_at, ttl = auth_service.create_pairing_challenge()
    return ChallengeResponse(
        pairing_code=code,
        expires_at=expires_at,
        ttl_minutes=ttl,
    )


@router.post(
    "/pair",
    response_model=PairResponse,
    summary="Emparejar dispositivo con desafío",
    description="Consume el desafío de emparejamiento, registra el dispositivo y emite credenciales revocables.",
)
async def pair_device(
    req: PairRequest,
    session: AsyncSession = Depends(get_db_session),
):
    try:
        response = await auth_service.pair_device(session, req)
        return response
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.post(
    "/refresh",
    response_model=RefreshTokenResponse,
    summary="Renovar credenciales de sesión",
    description="Acepta un refresh_token activo, lo rota (revocando el anterior) y emite un nuevo par de tokens.",
)
async def refresh_credentials(
    req: RefreshTokenRequest,
    session: AsyncSession = Depends(get_db_session),
):
    try:
        response = await auth_service.refresh_tokens(session, req.refresh_token)
        return response
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"},
        )


@router.post(
    "/revoke",
    response_model=RevokeResponse,
    summary="Revocar token o dispositivo",
    description="Revoca de inmediato un token específico o desvincula un dispositivo completo invalidando sus sesiones.",
)
async def revoke_credentials(
    req: RevokeRequest,
    session: AsyncSession = Depends(get_db_session),
    auth: Optional[AuthContext] = Depends(get_explicit_auth),
):
    # Si no se indica device_id ni token en el body, revocar el token actual autenticado
    raw_token = req.token
    device_id = req.device_id

    if not raw_token and not device_id and auth:
        device_id = auth.device_id

    success, message = await auth_service.revoke(
        session, raw_token=raw_token, device_id=device_id
    )
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=message,
        )
    return RevokeResponse(success=True, message=message)


@router.get(
    "/me",
    response_model=AuthContext,
    summary="Consultar identidad y permisos actuales",
    description="Devuelve el usuario, dispositivo y lista de alcances del token activo.",
)
async def get_my_identity(
    auth: AuthContext = Depends(get_explicit_auth),
):
    return auth
