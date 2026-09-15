import asyncio
from datetime import datetime, timezone
import pytest
import pytest_asyncio


@pytest_asyncio.fixture
async def auth_headers(client):
    ch = await client.post("/v1/auth/challenge")
    code = ch.json()["pairing_code"]
    pair = await client.post(
        "/v1/auth/pair",
        json={
            "pairing_code": code,
            "device_name": "Pixel DeviceRequest Test",
            "platform": "android",
        },
    )
    token = pair.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_device_request_complete_flow(client, auth_headers):
    # 1. Servidor/Agente solicita ubicación al móvil
    create_payload = {
        "capability": "location",
        "purpose": "Calcular tiempo de traslado a la notaría",
        "ttl_seconds": 60,
    }
    create_res = await client.post("/v1/device-requests", json=create_payload, headers=auth_headers)
    assert create_res.status_code == 201
    req_data = create_res.json()
    req_id = req_data["id"]
    assert req_data["capability"] == "location"
    assert req_data["status"] == "pending"

    # 2. El móvil consulta solicitudes pendientes
    pending_res = await client.get("/v1/device-requests/pending", headers=auth_headers)
    assert pending_res.status_code == 200
    pending = pending_res.json()
    assert any(r["id"] == req_id for r in pending)

    # 3. El móvil responde con observación del sensor GPS
    obs_payload = {
        "status": "completed",
        "payload": {
            "latitude": 19.432608,
            "longitude": -99.133209,
            "accuracy_meters": 4.5,
        },
        "observed_at": datetime.now(timezone.utc).isoformat(),
    }
    resp_res = await client.post(
        f"/v1/device-requests/{req_id}/response",
        json=obs_payload,
        headers=auth_headers,
    )
    assert resp_res.status_code == 200
    assert resp_res.json()["status"] == "completed"

    # 4. Consultar la observación persistida
    obs_res = await client.get(f"/v1/device-requests/{req_id}/observation", headers=auth_headers)
    assert obs_res.status_code == 200
    obs_data = obs_res.json()
    assert obs_data["capability"] == "location"
    assert obs_data["payload_json"]["latitude"] == 19.432608

    # 5. Ya no debe figurar en pendientes
    after_pending = await client.get("/v1/device-requests/pending", headers=auth_headers)
    assert not any(r["id"] == req_id for r in after_pending.json())


@pytest.mark.asyncio
async def test_device_request_denial(client, auth_headers):
    # Crear solicitud de calendario
    create_res = await client.post(
        "/v1/device-requests",
        json={
            "capability": "calendar_snapshot",
            "purpose": "Verificar empalmes con el calendario nativo",
            "ttl_seconds": 60,
        },
        headers=auth_headers,
    )
    req_id = create_res.json()["id"]

    # El usuario deniega el permiso en el teléfono
    deny_res = await client.post(
        f"/v1/device-requests/{req_id}/response",
        json={"status": "denied", "payload": {}},
        headers=auth_headers,
    )
    assert deny_res.status_code == 200
    assert deny_res.json()["status"] == "denied"

    # Verificar estado final
    check_res = await client.get(f"/v1/device-requests/{req_id}", headers=auth_headers)
    assert check_res.json()["status"] == "denied"


@pytest.mark.asyncio
async def test_device_request_ttl_expiration(client, auth_headers):
    # Crear solicitud con TTL de 1 segundo
    create_res = await client.post(
        "/v1/device-requests",
        json={
            "capability": "timezone",
            "purpose": "Confirmar cambio de huso horario",
            "ttl_seconds": 10,
        },
        headers=auth_headers,
    )
    req_id = create_res.json()["id"]

    # Simular expiración de fecha
    from app.db.session import async_session_factory
    from app.models.canonical import DeviceRequest
    from datetime import timedelta
    from sqlalchemy import update

    async with async_session_factory() as session:
        past = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=10)
        await session.execute(
            update(DeviceRequest).where(DeviceRequest.id == req_id).values(expires_at=past)
        )
        await session.commit()

    # Intentar responder tardíamente debe ser rechazado
    late_res = await client.post(
        f"/v1/device-requests/{req_id}/response",
        json={"status": "completed", "payload": {"timezone": "America/Cancun"}},
        headers=auth_headers,
    )
    assert late_res.status_code == 400
    assert "expirado" in late_res.json()["detail"]

    # Consultar estado: debe estar marcado como expired
    check_res = await client.get(f"/v1/device-requests/{req_id}", headers=auth_headers)
    assert check_res.json()["status"] == "expired"
