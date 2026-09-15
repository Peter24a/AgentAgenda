import ipaddress
import hmac
from typing import Callable, Optional
from fastapi import Depends, HTTPException, Request, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.session import get_db_session
from app.models.auth import AuthContext
from app.services.auth_service import DEFAULT_CLIENT_SCOPES, auth_service

bearer_scheme = HTTPBearer(auto_error=False)


def is_client_network_trusted(request: Request) -> bool:
    """Valida si la petición proviene de una red local/privada o loopback."""
    trusted_cfg = getattr(settings, "trusted_fallback_networks", "private,loopback").strip()
    if trusted_cfg == "*":
        return True

    # Forwarded headers are client input here. Only the ASGI server, configured
    # with explicit trusted proxies, may normalize request.client.
    client_host = request.client.host if request.client else ""

    if client_host in ("localhost", "testclient", "test"):
        return True

    try:
        ip = ipaddress.ip_address(client_host)
        # Si la IP es global (enrutada en internet público), denegar fallback
        if ip.is_global:
            return False
        if "loopback" in trusted_cfg and ip.is_loopback:
            return True
        private_networks = ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "fc00::/7")
        if "private" in trusted_cfg and any(ip in ipaddress.ip_network(net) for net in private_networks):
            return True
    except ValueError:
        pass

    return False


def is_app_secret_valid(request: Request) -> bool:
    """Verifica si la petición incluye la clave precompartida de compilación (X-App-Key o X-App-Secret)."""
    app_key = request.headers.get("x-app-key") or request.headers.get("x-app-secret")
    if app_key and settings.secret_key and hmac.compare_digest(app_key.strip(), settings.secret_key.strip()):
        return True
    return False


async def get_explicit_auth(
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
    session: AsyncSession = Depends(get_db_session),
) -> AuthContext:
    """Exige un token Bearer explícito y válido. Usado para endpoints de gestión de credenciales."""
    if not credentials or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciales de autenticación no proporcionadas o formato inválido",
            headers={"WWW-Authenticate": "Bearer"},
        )

    auth = await auth_service.authenticate_token(session, credentials.credentials)
    if not auth:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token de acceso inválido, expirado o revocado",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return auth


async def get_current_auth(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
    session: AsyncSession = Depends(get_db_session),
) -> AuthContext:
    """Autenticación canónica con fallback automático seguro para uso personal (Opción A y B).
    
    Opción A: Token Bearer explícito (validado contra base de datos y revocaciones).
    Opción B: Fallback automático a default_user:
      - Permitido únicamente si allow_anonymous_fallback está activo.
      - Requiere que la petición provenga de una red privada/local O que incluya la clave precompartida (X-App-Key).
      - Bloquea accesos anónimos desde internet público para evitar brechas de seguridad.
    """
    # 1. Si el cliente envió un token Bearer, validarlo estrictamente
    if credentials and credentials.scheme.lower() == "bearer":
        auth = await auth_service.authenticate_token(session, credentials.credentials)
        if not auth:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token de acceso inválido, expirado o revocado",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return auth

    # 2. Si no hay credenciales, evaluar el fallback automático seguro (Opción B)
    if settings.allow_anonymous_fallback:
        trusted_net = is_client_network_trusted(request)
        valid_secret = is_app_secret_valid(request)

        # Si viene de red privada o tiene la clave de compilación, conceder acceso directo
        if trusted_net or valid_secret:
            return AuthContext(
                user_id="default_user",
                device_id="dev-fallback-local",
                token_id="tok-fallback-local",
                scopes=DEFAULT_CLIENT_SCOPES,
                device_name="Dispositivo Personal Directo (Fallback)",
                platform="android",
            )

        # Si viene de una red pública desconocida sin clave ni token, rechazar de inmediato
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Acceso directo anónimo denegado desde red pública no confiable. Proporcione un token Bearer o X-App-Key.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Fallback desactivado
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Credenciales de autenticación no proporcionadas",
        headers={"WWW-Authenticate": "Bearer"},
    )


async def get_current_auth_optional(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
    session: AsyncSession = Depends(get_db_session),
) -> Optional[AuthContext]:
    """Variante opcional: devuelve AuthContext si se autentica o por fallback, None si no."""
    try:
        return await get_current_auth(request, credentials, session)
    except HTTPException:
        return None


async def get_current_device(
    auth: AuthContext = Depends(get_current_auth),
) -> AuthContext:
    """Valida que la autenticación provenga de un dispositivo registrado y activo."""
    if not auth.device_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Se requiere un dispositivo registrado para realizar esta operación",
        )
    return auth


def has_scope(auth: AuthContext, required_scope: str) -> bool:
    scopes = set(auth.scopes or [])
    return bool(scopes & {"*", "admin", required_scope, required_scope.split(":")[0] + ":*"})


def require_scope(required_scope: str) -> Callable:
    """Fábrica de dependencias para validar permisos granulares (scopes).
    
    Soporta:
    - Coincidencia exacta: ej. 'agenda:read'
    - Comodín global: '*'
    - Comodín de categoría: ej. 'agenda:*' cubre 'agenda:read' y 'agenda:write'
    """
    async def _scope_checker(
        auth: AuthContext = Depends(get_current_auth),
    ) -> AuthContext:
        user_scopes = set(auth.scopes or [])

        # Permiso total
        if "*" in user_scopes or "admin" in user_scopes:
            return auth

        # Coincidencia exacta
        if required_scope in user_scopes:
            return auth

        # Coincidencia por categoría
        if ":" in required_scope:
            domain = required_scope.split(":")[0]
            if f"{domain}:*" in user_scopes:
                return auth

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Permiso insuficiente: se requiere el alcance '{required_scope}'",
        )

    return _scope_checker
