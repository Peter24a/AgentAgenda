import pytest
from datetime import datetime, timedelta, timezone
from fastapi import Depends
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.api.deps import require_scope
from app.core.security import hash_token
from app.main import app
from app.models.canonical import AuthToken, Device


# Endpoint de prueba temporal para validar scopes
@app.get("/test/scope-agenda", tags=["Test"])
async def _test_agenda_scope(auth=Depends(require_scope("agenda:read"))):
    return {"allowed": True, "scope": "agenda:read", "user_id": auth.user_id}


@app.get("/test/scope-admin", tags=["Test"])
async def _test_admin_scope(auth=Depends(require_scope("admin:restricted"))):
    return {"allowed": True, "scope": "admin:restricted"}


@pytest.mark.asyncio
async def test_challenge_lifecycle(client):
    # 1. Solicitar desafío
    res = await client.post("/v1/auth/challenge")
    assert res.status_code == 200
    data = res.json()
    assert "pairing_code" in data
    assert data["ttl_minutes"] > 0
    code = data["pairing_code"]

    # 2. Emparejar dispositivo usando el código
    pair_res = await client.post(
        "/v1/auth/pair",
        json={
            "pairing_code": code,
            "device_name": "Pixel 9 Pro",
            "platform": "android",
            "capabilities": ["location", "calendar"],
        },
    )
    assert pair_res.status_code == 200
    pair_data = pair_res.json()
    assert "device_id" in pair_data
    assert "access_token" in pair_data
    assert "refresh_token" in pair_data
    assert "agenda:read" in pair_data["scopes"]

    # 3. Reusar el mismo código debe fallar (desafío de un solo uso)
    second_pair = await client.post(
        "/v1/auth/pair",
        json={
            "pairing_code": code,
            "device_name": "Otro Teléfono",
            "platform": "android",
        },
    )
    assert second_pair.status_code == 400
    assert "inválido, expirado o ya utilizado" in second_pair.json()["detail"]


@pytest.mark.asyncio
async def test_pairing_invalid_code(client):
    res = await client.post(
        "/v1/auth/pair",
        json={
            "pairing_code": "CODIGO-FALSO-9999",
            "device_name": "Pixel Test",
        },
    )
    assert res.status_code == 400


@pytest.mark.asyncio
async def test_authentication_and_route_protection(client):
    # 1. Sin encabezado -> 401
    unauth = await client.get("/v1/auth/me")
    assert unauth.status_code == 401

    # 2. Con token falso -> 401
    bad_token = await client.get(
        "/v1/auth/me",
        headers={"Authorization": "Bearer token_falso_invalido_123"},
    )
    assert bad_token.status_code == 401

    # 3. Generar par real y autenticar
    ch_res = await client.post("/v1/auth/challenge")
    code = ch_res.json()["pairing_code"]
    pair_res = await client.post(
        "/v1/auth/pair",
        json={"pairing_code": code, "device_name": "Test Device"},
    )
    access_token = pair_res.json()["access_token"]
    device_id = pair_res.json()["device_id"]

    me_res = await client.get(
        "/v1/auth/me",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert me_res.status_code == 200
    me_data = me_res.json()
    assert me_data["device_id"] == device_id
    assert me_data["user_id"] == "default_user"
    assert "agenda:read" in me_data["scopes"]


@pytest.mark.asyncio
async def test_refresh_token_rotation_and_revocation(client):
    # Generar tokens
    ch = await client.post("/v1/auth/challenge")
    pair = await client.post(
        "/v1/auth/pair",
        json={"pairing_code": ch.json()["pairing_code"], "device_name": "Test Phone"},
    )
    orig_access = pair.json()["access_token"]
    orig_refresh = pair.json()["refresh_token"]

    # 1. Intentar refrescar usando el access_token debe fallar (no es token de refresco)
    bad_refresh = await client.post(
        "/v1/auth/refresh",
        json={"refresh_token": orig_access},
    )
    assert bad_refresh.status_code == 401

    # 2. Refrescar con refresh_token válido
    ref_res = await client.post(
        "/v1/auth/refresh",
        json={"refresh_token": orig_refresh},
    )
    assert ref_res.status_code == 200
    new_tokens = ref_res.json()
    assert "access_token" in new_tokens
    assert "refresh_token" in new_tokens
    new_access = new_tokens["access_token"]
    new_refresh = new_tokens["refresh_token"]
    assert new_access != orig_access

    # 3. El nuevo access_token funciona
    me = await client.get(
        "/v1/auth/me",
        headers={"Authorization": f"Bearer {new_access}"},
    )
    assert me.status_code == 200

    # 4. El refresh_token anterior debe haber sido revocado (rotación estricta)
    replay_refresh = await client.post(
        "/v1/auth/refresh",
        json={"refresh_token": orig_refresh},
    )
    assert replay_refresh.status_code == 401


@pytest.mark.asyncio
async def test_token_explicit_revocation(client):
    # Generar par
    ch = await client.post("/v1/auth/challenge")
    pair = await client.post(
        "/v1/auth/pair",
        json={"pairing_code": ch.json()["pairing_code"], "device_name": "Revoke Test"},
    )
    access_token = pair.json()["access_token"]

    # Validar que funciona inicialmente
    valid_res = await client.get(
        "/v1/auth/me",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert valid_res.status_code == 200

    # Revocar el token
    rev_res = await client.post(
        "/v1/auth/revoke",
        json={"token": access_token},
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert rev_res.status_code == 200
    assert rev_res.json()["success"] is True

    # Petición inmediata con el token revocado debe ser rechazada con 401
    post_rev = await client.get(
        "/v1/auth/me",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert post_rev.status_code == 401


@pytest.mark.asyncio
async def test_device_revocation_invalidates_all_tokens(client, db_session):
    # Generar dispositivo y tokens
    ch = await client.post("/v1/auth/challenge")
    pair = await client.post(
        "/v1/auth/pair",
        json={"pairing_code": ch.json()["pairing_code"], "device_name": "Device To Kill"},
    )
    device_id = pair.json()["device_id"]
    access_token = pair.json()["access_token"]
    refresh_token = pair.json()["refresh_token"]

    # Revocar por device_id
    rev_res = await client.post(
        "/v1/auth/revoke",
        json={"device_id": device_id},
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert rev_res.status_code == 200

    # El access_token falla
    me_res = await client.get(
        "/v1/auth/me",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert me_res.status_code == 401

    # El refresh_token también falla
    ref_res = await client.post(
        "/v1/auth/refresh",
        json={"refresh_token": refresh_token},
    )
    assert ref_res.status_code == 401

    # Verificar en base de datos que el dispositivo está inactivo
    dev_res = await db_session.execute(select(Device).where(Device.id == device_id))
    dev = dev_res.scalar_one()
    assert dev.is_active is False


@pytest.mark.asyncio
async def test_scope_enforcement(client):
    ch = await client.post("/v1/auth/challenge")
    pair = await client.post(
        "/v1/auth/pair",
        json={"pairing_code": ch.json()["pairing_code"], "device_name": "Scope Test"},
    )
    access_token = pair.json()["access_token"]

    # 1. Ruta que requiere agenda:read -> Permite (200)
    agenda_res = await client.get(
        "/test/scope-agenda",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert agenda_res.status_code == 200
    assert agenda_res.json()["allowed"] is True

    # 2. Ruta que requiere admin:restricted -> Deniega (403 Forbidden)
    admin_res = await client.get(
        "/test/scope-admin",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert admin_res.status_code == 403
    assert "Permiso insuficiente" in admin_res.json()["detail"]


@pytest.mark.asyncio
async def test_expired_token_rejected(client, db_session):
    # Insertar token expirado manualmente
    expired_raw = "expired_raw_token_xyz"
    expired_hash = hash_token(expired_raw)
    past_time = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=2)

    tok = AuthToken(
        id="tok-expired-1",
        user_id="default_user",
        token_hash=expired_hash,
        scopes=["agenda:read"],
        expires_at=past_time,
    )
    db_session.add(tok)
    await db_session.commit()

    res = await client.get(
        "/v1/auth/me",
        headers={"Authorization": f"Bearer {expired_raw}"},
    )
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_automatic_fallback_local_network(client):
    # Sin Authorization header pero desde red local/testclient -> permite fallback transparente (Opción B)
    res = await client.get("/test/scope-agenda")
    assert res.status_code == 200
    assert res.json()["allowed"] is True
    assert res.json()["user_id"] == "default_user"


@pytest.mark.asyncio
async def test_automatic_fallback_blocked_on_public_network(client):
    # The transport supplies the peer address; XFF must not grant trust.
    async with AsyncClient(transport=ASGITransport(app=app, client=("8.8.8.8", 40000)), base_url="http://test") as external:
        res = await external.get("/test/scope-agenda", headers={"X-Forwarded-For": "127.0.0.1"})
    # Debe rechazar con 401 para evitar brechas de seguridad en internet
    assert res.status_code == 401
    assert "Acceso directo anónimo denegado desde red pública" in res.json()["detail"]


@pytest.mark.asyncio
async def test_automatic_fallback_with_pre_shared_secret_on_public_network(client):
    from app.config import settings

    # Si viene de IP pública pero trae la clave de compilación (X-App-Key), se autoriza
    async with AsyncClient(transport=ASGITransport(app=app, client=("8.8.8.8", 40000)), base_url="http://test") as external:
        res = await external.get("/test/scope-agenda", headers={"X-App-Key": settings.secret_key})
    assert res.status_code == 200
    assert res.json()["allowed"] is True


@pytest.mark.asyncio
async def test_pairing_challenge_requires_auth_when_fallback_disabled(client, monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, 'allow_anonymous_fallback', False)
    res = await client.post('/v1/auth/challenge')
    assert res.status_code == 401
    res = await client.post('/v1/auth/challenge', headers={'X-App-Key': settings.secret_key})
    assert res.status_code == 401
