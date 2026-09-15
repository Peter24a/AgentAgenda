import hashlib
from datetime import datetime, timedelta, timezone
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
            "device_name": "Pixel Prep Test",
            "platform": "android",
        },
    )
    token = pair.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_event_preparation_lifecycle(client, auth_headers):
    # 1. Crear evento
    now = datetime.now(timezone.utc)
    ev_payload = {
        "title": "Cita en el Consulado",
        "description": "Renovación de visado",
        "start_time": (now + timedelta(days=5)).isoformat(),
        "end_time": (now + timedelta(days=5, hours=1)).isoformat(),
        "timezone": "America/Mexico_City",
    }
    ev_res = await client.post("/v1/agenda/events", json=ev_payload, headers=auth_headers)
    assert ev_res.status_code == 200
    event_id = ev_res.json()["id"]

    # 2. Consultar preparación sin requisitos iniciales
    prep_res1 = await client.get(f"/v1/events/{event_id}/preparation", headers=auth_headers)
    assert prep_res1.status_code == 200
    prep1 = prep_res1.json()
    assert prep1["event_id"] == event_id
    assert prep1["total_requirements"] == 0
    assert prep1["readiness_status"] == "ready"

    # 3. Añadir requisito documental
    req_payload = {
        "title": "Pasaporte Vigente",
        "description": "Original con vigencia mínima de 6 meses",
        "rule_source": "consulate_requirements",
    }
    add_res = await client.post(
        f"/v1/events/{event_id}/requirements",
        json=req_payload,
        headers=auth_headers,
    )
    assert add_res.status_code == 201
    req_data = add_res.json()
    req_id = req_data["id"]
    assert req_data["title"] == "Pasaporte Vigente"
    assert req_data["status"] == "missing"

    # 4. Consultar preparación: debe marcar missing y attention_required
    prep_res2 = await client.get(f"/v1/events/{event_id}/preparation", headers=auth_headers)
    assert prep_res2.status_code == 200
    prep2 = prep_res2.json()
    assert prep2["total_requirements"] == 1
    assert prep2["missing_count"] == 1
    assert prep2["readiness_status"] == "attention_required"
    assert len(prep2["missing_requirements"]) == 1

    # 5. Cargar documento a la bóveda privada
    content = b"%PDF-1.4 Pasaporte Oficial de Prueba"
    c_hash = hashlib.sha256(content).hexdigest()
    init_res = await client.post(
        "/v1/documents/uploads",
        json={
            "filename": "pasaporte_titular.pdf",
            "mime_type": "application/pdf",
            "expected_size_bytes": len(content),
            "expected_sha256": c_hash,
            "title": "Pasaporte Ordinario",
            "doc_type": "identificacion",
        },
        headers=auth_headers,
    )
    assert init_res.status_code in (200, 201)
    upl_id = init_res.json()["upload_id"]

    await client.put(
        f"/v1/documents/uploads/{upl_id}/content",
        content=content,
        headers={**auth_headers, "Content-Type": "application/octet-stream"},
    )
    comp_res = await client.post(f"/v1/documents/uploads/{upl_id}/complete", headers=auth_headers)
    assert comp_res.status_code == 200
    doc_id = comp_res.json()["id"]

    # 6. Vincular documento como candidato
    link_res = await client.post(
        f"/v1/events/{event_id}/requirements/{req_id}/link",
        json={"document_id": doc_id, "status": "candidate"},
        headers=auth_headers,
    )
    assert link_res.status_code == 200

    # 7. Consultar preparación: candidato cargado -> in_progress
    prep_res3 = await client.get(f"/v1/events/{event_id}/preparation", headers=auth_headers)
    prep3 = prep_res3.json()
    assert prep3["candidate_count"] == 1
    assert prep3["missing_count"] == 0
    assert prep3["readiness_status"] == "in_progress"

    # 8. Verificar requisito
    verify_res = await client.post(
        f"/v1/events/{event_id}/requirements/{req_id}/verify",
        json={"status": "verified", "verified_by": "user"},
        headers=auth_headers,
    )
    assert verify_res.status_code == 200
    assert verify_res.json()["status"] == "verified"

    # 9. Consultar preparación: verificado -> ready
    prep_res4 = await client.get(f"/v1/events/{event_id}/preparation", headers=auth_headers)
    prep4 = prep_res4.json()
    assert prep4["verified_count"] == 1
    assert prep4["readiness_status"] == "ready"


@pytest.mark.asyncio
async def test_expired_document_detected_in_preparation(client, auth_headers):
    # 1. Crear evento
    now = datetime.now(timezone.utc)
    ev_payload = {
        "title": "Cita Bancaria Hipoteca",
        "start_time": (now + timedelta(days=2)).isoformat(),
        "end_time": (now + timedelta(days=2, hours=1)).isoformat(),
    }
    ev_res = await client.post("/v1/agenda/events", json=ev_payload, headers=auth_headers)
    event_id = ev_res.json()["id"]

    # 2. Requisito
    req_res = await client.post(
        f"/v1/events/{event_id}/requirements",
        json={"title": "Comprobante de Domicilio Vigente (máx 3 meses)"},
        headers=auth_headers,
    )
    req_id = req_res.json()["id"]

    # 3. Documento vencido (expiry_date en el pasado)
    content = b"Comprobante CFE Antiguo"
    init_res = await client.post(
        "/v1/documents/uploads",
        json={
            "filename": "recibo_cfe_vencido.pdf",
            "mime_type": "application/pdf",
            "expected_size_bytes": len(content),
            "title": "Recibo CFE 2023",
        },
        headers=auth_headers,
    )
    upl_id = init_res.json()["upload_id"]
    await client.put(f"/v1/documents/uploads/{upl_id}/content", content=content, headers=auth_headers)
    comp_res = await client.post(f"/v1/documents/uploads/{upl_id}/complete", headers=auth_headers)
    doc_id = comp_res.json()["id"]

    # Asignar fecha de expiración en el pasado
    past_date = (now - timedelta(days=30)).isoformat()
    await client.patch(
        f"/v1/documents/{doc_id}",
        json={"expiry_date": past_date},
        headers=auth_headers,
    )

    # 4. Vincular a requisito
    await client.post(
        f"/v1/events/{event_id}/requirements/{req_id}/link",
        json={"document_id": doc_id, "status": "candidate"},
        headers=auth_headers,
    )

    # 5. Verificar que se detecta como expired y attention_required
    prep_res = await client.get(f"/v1/events/{event_id}/preparation", headers=auth_headers)
    prep = prep_res.json()
    assert prep["expired_count"] == 1
    assert prep["readiness_status"] == "attention_required"
    assert len(prep["attention_required"]) >= 1


@pytest.mark.asyncio
async def test_event_deletion_preserves_vault_documents(client, auth_headers):
    # 1. Crear evento y documento
    now = datetime.now(timezone.utc)
    ev_res = await client.post(
        "/v1/agenda/events",
        json={"title": "Evento Temporal", "start_time": now.isoformat(), "end_time": (now + timedelta(hours=1)).isoformat()},
        headers=auth_headers,
    )
    event_id = ev_res.json()["id"]

    content = b"Documento Inmune a la eliminacion de eventos"
    init_res = await client.post(
        "/v1/documents/uploads",
        json={"filename": "doc_permanente.pdf", "mime_type": "application/pdf", "expected_size_bytes": len(content)},
        headers=auth_headers,
    )
    upl_id = init_res.json()["upload_id"]
    await client.put(f"/v1/documents/uploads/{upl_id}/content", content=content, headers=auth_headers)
    doc_id = (await client.post(f"/v1/documents/uploads/{upl_id}/complete", headers=auth_headers)).json()["id"]

    # 2. Requisito y vínculo
    req_res = await client.post(
        f"/v1/events/{event_id}/requirements",
        json={"title": "Requisito Temporal"},
        headers=auth_headers,
    )
    req_id = req_res.json()["id"]
    await client.post(
        f"/v1/events/{event_id}/requirements/{req_id}/link",
        json={"document_id": doc_id},
        headers=auth_headers,
    )

    # 3. Eliminar evento
    del_res = await client.delete(f"/v1/agenda/events/{event_id}", headers=auth_headers)
    assert del_res.status_code == 200

    # 4. El documento sigue existiendo intacto en la bóveda
    doc_check = await client.get(f"/v1/documents/{doc_id}", headers=auth_headers)
    assert doc_check.status_code == 200
    assert doc_check.json()["id"] == doc_id
