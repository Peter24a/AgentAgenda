import pytest
import pytest_asyncio
from datetime import datetime, timedelta

from app.models.canonical import Event, Proposal

@pytest_asyncio.fixture
async def auth_headers(client):
    ch = await client.post("/v1/auth/challenge")
    code = ch.json()["pairing_code"]
    pair = await client.post(
        "/v1/auth/pair",
        json={
            "pairing_code": code,
            "device_name": "Pixel Agenda Test",
            "platform": "android",
        },
    )
    token = pair.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}

@pytest.mark.asyncio
async def test_agenda_events_crud_and_timezone(client, auth_headers):
    # 1. Crear evento
    now_str = "2026-09-15T14:30:00"
    create_payload = {
        "title": "Reunión de Arquitectura",
        "description": "Definir contratos de sincronización",
        "start_time": now_str,
        "category": "work",
        "is_completed": False
    }
    res_create = await client.post("/v1/agenda/events", json=create_payload, headers=auth_headers)
    assert res_create.status_code == 200
    event_data = res_create.json()
    event_id = event_data["id"]
    assert event_data["title"] == "Reunión de Arquitectura"
    assert event_data["is_completed"] is False

    # 2. Listar eventos para la fecha
    res_list = await client.get("/v1/agenda/events?date=2026-09-15&timezone=America/Mexico_City", headers=auth_headers)
    assert res_list.status_code == 200
    events = res_list.json()
    assert len(events) >= 1
    assert any(e["id"] == event_id for e in events)

    # 3. Toggle completed
    res_toggle = await client.post(f"/v1/agenda/events/{event_id}/toggle", headers=auth_headers)
    assert res_toggle.status_code == 200
    assert res_toggle.json()["is_completed"] is True

    # 4. Eliminar evento
    res_del = await client.delete(f"/v1/agenda/events/{event_id}", headers=auth_headers)
    assert res_del.status_code == 200
    assert res_del.json()["success"] is True

    # 5. Verificar que ya no aparece en el listado activo
    res_list_after = await client.get("/v1/agenda/events?date=2026-09-15", headers=auth_headers)
    events_after = res_list_after.json()
    assert not any(e["id"] == event_id for e in events_after)

@pytest.mark.asyncio
async def test_canonical_proposals_atomic_confirm_and_reject(client, auth_headers):
    # 1. Crear propuesta
    prop_payload = {
        "id": "prop-canon-01",
        "summary": "Optimización del descanso nocturno",
        "reason": "Mejora del rendimiento matutino",
        "resulting_items": [
            {
                "id": "evt-prop-1",
                "title": "Lectura previa al sueño",
                "start_time": "2026-09-15T22:00:00",
                "end_time": "2026-09-15T22:45:00",
                "category": "leisure",
                "is_completed": False
            },
            {
                "id": "evt-prop-2",
                "title": "Meditación y apagado de pantallas",
                "start_time": "2026-09-15T22:45:00",
                "end_time": "2026-09-15T23:00:00",
                "category": "sleep",
                "is_completed": False
            }
        ],
        "status": "pending"
    }
    res_create_prop = await client.post("/v1/proposals", json=prop_payload, headers=auth_headers)
    assert res_create_prop.status_code == 200

    # 2. Consultar propuesta pendiente
    res_pending = await client.get("/v1/proposals/pending", headers=auth_headers)
    assert res_pending.status_code == 200
    pending_prop = res_pending.json()
    assert pending_prop["id"] == "prop-canon-01"

    # 3. Confirmar propuesta de forma atómica
    res_confirm = await client.post("/v1/proposals/prop-canon-01/confirm", headers=auth_headers)
    assert res_confirm.status_code == 200
    confirm_data = res_confirm.json()
    assert confirm_data["success"] is True
    assert confirm_data["status"] == "accepted"

    # 4. Verificar que ambos eventos existen ahora en la agenda
    res_events = await client.get("/v1/agenda/events?date=2026-09-15", headers=auth_headers)
    agenda_events = res_events.json()
    evt_ids = [e["id"] for e in agenda_events]
    assert "evt-prop-1" in evt_ids
    assert "evt-prop-2" in evt_ids

    # 5. Reintentar confirmar propuesta (idempotencia en el confirm)
    res_reconfirm = await client.post("/v1/proposals/prop-canon-01/confirm", headers=auth_headers)
    assert res_reconfirm.status_code == 200
    assert res_reconfirm.json()["success"] is False
    assert "ya fue procesada" in res_reconfirm.json()["message"]

    # 6. Crear segunda propuesta y rechazarla
    prop_reject_payload = {
        "id": "prop-canon-02",
        "summary": "Actividad descartable",
        "reason": "No necesaria",
        "resulting_items": [
            {
                "id": "evt-prop-3",
                "title": "Actividad que no se debe aplicar",
                "start_time": "2026-09-16T11:00:00",
                "category": "general"
            }
        ],
        "status": "pending"
    }
    await client.post("/v1/proposals", json=prop_reject_payload, headers=auth_headers)
    res_reject = await client.post("/v1/proposals/prop-canon-02/reject", headers=auth_headers)
    assert res_reject.status_code == 200
    assert res_reject.json()["status"] == "rejected"

    # Verificar que el evento evt-prop-3 NO existe en la agenda
    res_check = await client.get("/v1/agenda/events?date=2026-09-16", headers=auth_headers)
    assert not any(e["id"] == "evt-prop-3" for e in res_check.json())
