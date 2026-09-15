import uuid
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Tuple

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.security import (
    create_challenge,
    generate_raw_token,
    hash_token,
    verify_and_consume_challenge,
)
from app.models.auth import (
    AuthContext,
    PairRequest,
    PairResponse,
    RefreshTokenResponse,
)
from app.models.canonical import AuthToken, Device

DEFAULT_CLIENT_SCOPES = [
    "agenda:read",
    "agenda:write",
    "tasks:read",
    "tasks:write",
    "sync:read",
    "sync:write",
    "chat:read",
    "chat:write",
    "documents:read",
    "documents:write",
    "memory:read",
    "memory:write",
    "device_requests:read",
    "device_requests:write",
    "jobs:read",
    "jobs:write",
    "mcp:read",
    "mcp:write",
]


class AuthService:
    def create_pairing_challenge(
        self, user_id: str = "default_user"
    ) -> Tuple[str, datetime, int]:
        code, expires_at = create_challenge(user_id=user_id)
        ttl = settings.pairing_challenge_ttl_minutes
        return code, expires_at, ttl

    async def pair_device(
        self,
        session: AsyncSession,
        req: PairRequest,
        default_user_id: str = "default_user",
    ) -> PairResponse:
        user_id = verify_and_consume_challenge(req.pairing_code)
        if not user_id:
            raise ValueError("Código de emparejamiento inválido, expirado o ya utilizado")

        now = datetime.now(timezone.utc).replace(tzinfo=None)

        # Determinar si reutilizamos o creamos dispositivo
        device: Optional[Device] = None
        if req.client_device_id:
            res = await session.execute(
                select(Device).where(Device.id == req.client_device_id)
            )
            device = res.scalar_one_or_none()

        if device:
            device.device_name = req.device_name
            device.platform = req.platform
            device.capabilities = req.capabilities or []
            device.is_active = True
            device.last_seen_at = now
        else:
            device_id = req.client_device_id or f"dev-{uuid.uuid4().hex[:12]}"
            device = Device(
                id=device_id,
                user_id=user_id,
                device_name=req.device_name,
                platform=req.platform,
                capabilities=req.capabilities or [],
                is_active=True,
                created_at=now,
                last_seen_at=now,
            )
            session.add(device)

        await session.flush()

        # Emitir access_token (duración según settings.token_expire_days)
        raw_access = generate_raw_token(32)
        access_hash = hash_token(raw_access)
        access_expires = now + timedelta(days=settings.token_expire_days)

        access_token_record = AuthToken(
            id=f"tok-{uuid.uuid4().hex[:12]}",
            device_id=device.id,
            user_id=user_id,
            token_hash=access_hash,
            scopes=DEFAULT_CLIENT_SCOPES,
            expires_at=access_expires,
            created_at=now,
        )
        session.add(access_token_record)

        # Emitir refresh_token (duración 3 veces mayor con alcance exclusivo refresh)
        raw_refresh = generate_raw_token(48)
        refresh_hash = hash_token(raw_refresh)
        refresh_expires = now + timedelta(days=settings.token_expire_days * 3)

        refresh_token_record = AuthToken(
            id=f"tok-{uuid.uuid4().hex[:12]}",
            device_id=device.id,
            user_id=user_id,
            token_hash=refresh_hash,
            scopes=["refresh"],
            expires_at=refresh_expires,
            created_at=now,
        )
        session.add(refresh_token_record)

        await session.commit()

        expires_in_seconds = int(settings.token_expire_days * 86400)
        return PairResponse(
            device_id=device.id,
            access_token=raw_access,
            refresh_token=raw_refresh,
            token_type="bearer",
            expires_in=expires_in_seconds,
            scopes=DEFAULT_CLIENT_SCOPES,
        )

    async def refresh_tokens(
        self, session: AsyncSession, raw_refresh_token: str
    ) -> RefreshTokenResponse:
        refresh_hash = hash_token(raw_refresh_token)
        now = datetime.now(timezone.utc).replace(tzinfo=None)

        res = await session.execute(
            select(AuthToken).where(
                AuthToken.token_hash == refresh_hash,
                AuthToken.revoked_at.is_(None),
            )
        )
        token = res.scalar_one_or_none()

        if not token or token.expires_at <= now:
            raise ValueError("Token de refresco inválido, revocado o expirado")

        if "refresh" not in (token.scopes or []):
            raise ValueError("El token proporcionado no es un token de refresco válido")

        # Verificar si el dispositivo sigue activo
        if token.device_id:
            dev_res = await session.execute(
                select(Device).where(Device.id == token.device_id)
            )
            device = dev_res.scalar_one_or_none()
            if not device or not device.is_active:
                raise ValueError("El dispositivo asociado ha sido desactivado o revocado")
            device.last_seen_at = now

        # Rotación estricta de token: revocar el refresh_token utilizado
        token.revoked_at = now

        # Emitir nuevos pares de tokens
        new_raw_access = generate_raw_token(32)
        new_access_hash = hash_token(new_raw_access)
        access_expires = now + timedelta(days=settings.token_expire_days)

        new_access = AuthToken(
            id=f"tok-{uuid.uuid4().hex[:12]}",
            device_id=token.device_id,
            user_id=token.user_id,
            token_hash=new_access_hash,
            scopes=DEFAULT_CLIENT_SCOPES,
            expires_at=access_expires,
            created_at=now,
        )
        session.add(new_access)

        new_raw_refresh = generate_raw_token(48)
        new_refresh_hash = hash_token(new_raw_refresh)
        refresh_expires = now + timedelta(days=settings.token_expire_days * 3)

        new_refresh = AuthToken(
            id=f"tok-{uuid.uuid4().hex[:12]}",
            device_id=token.device_id,
            user_id=token.user_id,
            token_hash=new_refresh_hash,
            scopes=["refresh"],
            expires_at=refresh_expires,
            created_at=now,
        )
        session.add(new_refresh)

        await session.commit()

        expires_in_seconds = int(settings.token_expire_days * 86400)
        return RefreshTokenResponse(
            access_token=new_raw_access,
            refresh_token=new_raw_refresh,
            token_type="bearer",
            expires_in=expires_in_seconds,
            scopes=DEFAULT_CLIENT_SCOPES,
        )

    async def revoke(
        self,
        session: AsyncSession,
        raw_token: Optional[str] = None,
        device_id: Optional[str] = None,
    ) -> Tuple[bool, str]:
        now = datetime.now(timezone.utc).replace(tzinfo=None)

        if device_id:
            dev_res = await session.execute(
                select(Device).where(Device.id == device_id)
            )
            device = dev_res.scalar_one_or_none()
            if device:
                device.is_active = False

            await session.execute(
                update(AuthToken)
                .where(
                    AuthToken.device_id == device_id,
                    AuthToken.revoked_at.is_(None),
                )
                .values(revoked_at=now)
            )
            await session.commit()
            return True, f"Dispositivo '{device_id}' y todos sus tokens han sido revocados exitosamente"

        if raw_token:
            h = hash_token(raw_token)
            res = await session.execute(
                select(AuthToken).where(
                    AuthToken.token_hash == h,
                    AuthToken.revoked_at.is_(None),
                )
            )
            token = res.scalar_one_or_none()
            if token:
                token.revoked_at = now
                await session.commit()
                return True, "Token revocado exitosamente"
            return False, "Token no encontrado o ya revocado"

        return False, "Se requiere proporcionar un token o un device_id para revocar"

    async def authenticate_token(
        self, session: AsyncSession, raw_token: str
    ) -> Optional[AuthContext]:
        h = hash_token(raw_token)
        now = datetime.now(timezone.utc).replace(tzinfo=None)

        query = (
            select(AuthToken, Device)
            .outerjoin(Device, AuthToken.device_id == Device.id)
            .where(
                AuthToken.token_hash == h,
                AuthToken.revoked_at.is_(None),
            )
        )
        res = await session.execute(query)
        row = res.first()
        if not row:
            return None

        token, device = row
        if token.expires_at <= now:
            return None

        if device:
            if not device.is_active:
                return None
            device.last_seen_at = now
            await session.commit()

        return AuthContext(
            user_id=token.user_id,
            device_id=token.device_id,
            token_id=token.id,
            scopes=token.scopes or [],
            device_name=device.device_name if device else None,
            platform=device.platform if device else None,
        )


auth_service = AuthService()
