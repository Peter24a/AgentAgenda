import pytest
import pytest_asyncio
from datetime import datetime, timezone

from app.models.canonical import SyncHead


@pytest_asyncio.fixture
async def auth_headers(client):
    """Genera credenciales válidas con alcances de sync completos."""
    ch = await client.post("/v1/auth/challenge")
    code = ch.json()["pairing_code"]
    pair = await client.post(
        "/v1/auth/pair",
        json={
            "pairing_code": code,
            "device_name": "Pixel Test Sync",
            "platform": "android",
        },
    )
    token = pair.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_sync_bootstrap_empty(client, auth_headers):
    res = await client.post("/v1/sync/bootstrap", headers=auth_headers)
    assert res.status_code == 200
    data = res.json()
    assert data["sync_schema_version"] == 1
    assert data["watermark_seq"] == 0
    assert data["events"] == []
    assert data["tasks"] == []
    assert data["proposals"] == []


@pytest.mark.asyncio
async def test_sync_push_create_event_and_task(client, auth_headers):
    ops = [
        {
            "operation_id": "op-evt-001",
            "operation_epoch": "epoch-1",
            "entity_type": "event",
            "entity_id": "evt-100",
            "base_version": 0,
            "action": "create",
            "payload": {
                "title": "Reunión de Sincronización",
                "start_time": "2026-09-15T10:00:00",
                "timezone": "America/Mexico_City",
                "category": "work",
            },
        },
        {
            "operation_id": "op-tsk-001",
            "operation_epoch": "epoch-1",
            "entity_type": "task",
            "entity_id": "tsk-100",
            "base_version": 0,
            "action": "create",
            "payload": {
                "title": "Enviar reporte",
                "priority": "high",
                "status": "pending",
            },
        },
    ]

    push_res = await client.post(
        "/v1/sync/push",
        json={"sync_schema_version": 1, "operations": ops},
        headers=auth_headers,
    )
    assert push_res.status_code == 200
    data = push_res.json()
    assert data["commit_seq"] == 2
    assert len(data["results"]) == 2

    r1, r2 = data["results"]
    assert r1["operation_id"] == "op-evt-001"
    assert r1["status"] == "applied"
    assert r1["new_version"] == 1

    assert r2["operation_id"] == "op-tsk-001"
    assert r2["status"] == "applied"
    assert r2["new_version"] == 1

    # Verificar que el bootstrap ahora incluye estas entidades
    boot_res = await client.post("/v1/sync/bootstrap", headers=auth_headers)
    boot_data = boot_res.json()
    assert boot_data["watermark_seq"] == 2
    assert len(boot_data["events"]) == 1
    assert boot_data["events"][0]["title"] == "Reunión de Sincronización"
    assert len(boot_data["tasks"]) == 1
    assert boot_data["tasks"][0]["title"] == "Enviar reporte"


@pytest.mark.asyncio
async def test_sync_push_idempotency_duplicate_and_conflict(client, auth_headers):
    op = {
        "operation_id": "op-idempotent-01",
        "operation_epoch": "epoch-1",
        "entity_type": "event",
        "entity_id": "evt-idem-01",
        "base_version": 0,
        "action": "create",
        "payload": {"title": "Evento Único"},
    }

    # 1. Primer envío -> applied
    res1 = await client.post(
        "/v1/sync/push",
        json={"sync_schema_version": 1, "operations": [op]},
        headers=auth_headers,
    )
    assert res1.status_code == 200
    assert res1.json()["results"][0]["status"] == "applied"
    assert res1.json()["commit_seq"] == 1

    # 2. Reintento idéntico (mismo ID + mismo hash) -> duplicate (no incrementa commit_seq)
    res2 = await client.post(
        "/v1/sync/push",
        json={"sync_schema_version": 1, "operations": [op]},
        headers=auth_headers,
    )
    assert res2.status_code == 200
    r2 = res2.json()["results"][0]
    assert r2["status"] == "duplicate"
    assert r2["new_version"] == 1
    assert res2.json()["commit_seq"] == 1  # No se alteró la secuencia

    # 3. Mismo operation_id con DIFERENTE payload -> conflict
    modified_op = dict(op)
    modified_op["payload"] = {"title": "Título completamente alterado"}
    res3 = await client.post(
        "/v1/sync/push",
        json={"sync_schema_version": 1, "operations": [modified_op]},
        headers=auth_headers,
    )
    assert res3.status_code == 200
    r3 = res3.json()["results"][0]
    assert r3["status"] == "conflict"
    assert "Conflicto de idempotencia" in r3["error_message"]


@pytest.mark.asyncio
async def test_sync_update_and_version_conflict(client, auth_headers):
    # 1. Crear evento
    create_op = {
        "operation_id": "op-evt-v0",
        "operation_epoch": "epoch-1",
        "entity_type": "event",
        "entity_id": "evt-versioned",
        "base_version": 0,
        "action": "create",
        "payload": {"title": "Versión Inicial"},
    }
    await client.post(
        "/v1/sync/push",
        json={"sync_schema_version": 1, "operations": [create_op]},
        headers=auth_headers,
    )

    # 2. Actualizar con base_version correcta (1) -> applied, new_version=2
    update_op = {
        "operation_id": "op-evt-v1",
        "operation_epoch": "epoch-1",
        "entity_type": "event",
        "entity_id": "evt-versioned",
        "base_version": 1,
        "action": "update",
        "payload": {"title": "Versión Modificada"},
    }
    up_res = await client.post(
        "/v1/sync/push",
        json={"sync_schema_version": 1, "operations": [update_op]},
        headers=auth_headers,
    )
    assert up_res.json()["results"][0]["status"] == "applied"
    assert up_res.json()["results"][0]["new_version"] == 2

    # 3. Intentar actualizar de nuevo usando base_version=1 (cuando el servidor ya está en 2) -> conflict
    stale_op = {
        "operation_id": "op-evt-v1-stale",
        "operation_epoch": "epoch-1",
        "entity_type": "event",
        "entity_id": "evt-versioned",
        "base_version": 1,
        "action": "update",
        "payload": {"title": "Edición desfasada"},
    }
    conflict_res = await client.post(
        "/v1/sync/push",
        json={"sync_schema_version": 1, "operations": [stale_op]},
        headers=auth_headers,
    )
    r_conflict = conflict_res.json()["results"][0]
    assert r_conflict["status"] == "conflict"
    assert "servidor=2, cliente=1" in r_conflict["error_message"]
    assert r_conflict["current_server_state"]["title"] == "Versión Modificada"


@pytest.mark.asyncio
async def test_sync_delete_tombstone(client, auth_headers):
    # 1. Crear tarea
    create_op = {
        "operation_id": "op-tsk-del-01",
        "operation_epoch": "epoch-1",
        "entity_type": "task",
        "entity_id": "tsk-to-delete",
        "base_version": 0,
        "action": "create",
        "payload": {"title": "Tarea efímera"},
    }
    await client.post(
        "/v1/sync/push",
        json={"sync_schema_version": 1, "operations": [create_op]},
        headers=auth_headers,
    )

    # 2. Borrar tarea con base_version=1 -> applied, version=2
    del_op = {
        "operation_id": "op-tsk-del-02",
        "operation_epoch": "epoch-1",
        "entity_type": "task",
        "entity_id": "tsk-to-delete",
        "base_version": 1,
        "action": "delete",
        "payload": {},
    }
    del_res = await client.post(
        "/v1/sync/push",
        json={"sync_schema_version": 1, "operations": [del_op]},
        headers=auth_headers,
    )
    assert del_res.json()["results"][0]["status"] == "applied"
    assert del_res.json()["results"][0]["new_version"] == 2

    # 3. El bootstrap no debe contener la tarea borrada
    boot = await client.post("/v1/sync/bootstrap", headers=auth_headers)
    assert not any(t["id"] == "tsk-to-delete" for t in boot.json()["tasks"])

    # 4. El pull debe reportar el ChangeBatch tipo 'delete'
    pull = await client.get("/v1/sync/pull?since_seq=0", headers=auth_headers)
    del_change = next(
        c for c in pull.json()["changes"] if c["entity_id"] == "tsk-to-delete" and c["change_type"] == "delete"
    )
    assert del_change["entity_version"] == 2


@pytest.mark.asyncio
async def test_sync_pull_pagination(client, auth_headers):
    # Crear 3 eventos secuenciales
    ops = [
        {
            "operation_id": f"op-seq-{i}",
            "operation_epoch": "epoch-1",
            "entity_type": "event",
            "entity_id": f"evt-seq-{i}",
            "base_version": 0,
            "action": "create",
            "payload": {"title": f"Evento {i}"},
        }
        for i in range(1, 4)
    ]
    await client.post(
        "/v1/sync/push",
        json={"sync_schema_version": 1, "operations": ops},
        headers=auth_headers,
    )

    # Pull con límite 2
    pull1 = await client.get("/v1/sync/pull?since_seq=0&limit=2", headers=auth_headers)
    p1_data = pull1.json()
    assert len(p1_data["changes"]) == 2
    assert p1_data["has_more"] is True
    cursor = p1_data["changes"][-1]["commit_seq"]

    # Pull subsecuente desde cursor
    pull2 = await client.get(f"/v1/sync/pull?since_seq={cursor}&limit=2", headers=auth_headers)
    p2_data = pull2.json()
    assert len(p2_data["changes"]) == 1
    assert p2_data["has_more"] is False
    assert p2_data["changes"][0]["entity_id"] == "evt-seq-3"


@pytest.mark.asyncio
async def test_operation_receipt_recovery_and_ack(client, auth_headers):
    op = {
        "operation_id": "op-recover-01",
        "operation_epoch": "epoch-1",
        "entity_type": "event",
        "entity_id": "evt-recover",
        "base_version": 0,
        "action": "create",
        "payload": {"title": "Evento con timeout simulado"},
    }
    await client.post(
        "/v1/sync/push",
        json={"sync_schema_version": 1, "operations": [op]},
        headers=auth_headers,
    )

    # 1. Recuperar recibo por ID
    rcpt = await client.get("/v1/operations/op-recover-01", headers=auth_headers)
    assert rcpt.status_code == 200
    rcpt_data = rcpt.json()
    assert rcpt_data["operation_id"] == "op-recover-01"
    assert rcpt_data["status"] == "applied"
    assert rcpt_data["canonical_hash"] != ""

    # 2. Recibo inexistente -> 404
    not_found = await client.get("/v1/operations/op-inexistente", headers=auth_headers)
    assert not_found.status_code == 404

    # 3. ACK
    ack_res = await client.post(
        "/v1/sync/ack",
        json={"device_id": "dev-test", "last_applied_seq": 5},
        headers=auth_headers,
    )
    assert ack_res.status_code == 200
    assert ack_res.json()["acknowledged_seq"] == 5
