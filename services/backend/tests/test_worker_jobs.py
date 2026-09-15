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
            "device_name": "Pixel Worker Test",
            "platform": "android",
        },
    )
    token = pair.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_job_document_extraction_flow(client, auth_headers):
    # 1. Cargar un documento a la bóveda (esto encola un job document_extraction)
    content = b"%PDF-1.4 Extracted Text: Certificado Medico de Aptitud Fisica para el Paciente Pedro"
    init_res = await client.post(
        "/v1/documents/uploads",
        json={
            "filename": "certificado_medico.pdf",
            "mime_type": "application/pdf",
            "expected_size_bytes": len(content),
            "title": "Certificado Médico",
        },
        headers=auth_headers,
    )
    assert init_res.status_code in (200, 201)
    upl_id = init_res.json()["upload_id"]
    await client.put(f"/v1/documents/uploads/{upl_id}/content", content=content, headers=auth_headers)
    comp_res = await client.post(f"/v1/documents/uploads/{upl_id}/complete", headers=auth_headers)
    assert comp_res.status_code == 200
    doc_id = comp_res.json()["id"]

    # 2. Ejecutar worker sobre trabajos pendientes
    proc_res = await client.post("/v1/jobs/process-pending", headers=auth_headers)
    assert proc_res.status_code == 200
    batch = proc_res.json()
    assert batch["processed_count"] >= 1
    assert batch["succeeded_count"] >= 1

    # 3. Comprobar que la revisión del documento tiene ahora texto extraído
    doc_res = await client.get(f"/v1/documents/{doc_id}", headers=auth_headers)
    doc_data = doc_res.json()
    rev = doc_data["revisions"][0]
    assert rev["extraction_status"] == "ready"
    assert rev["extracted_text"] is not None
    assert "Certificado Medico" in rev["extracted_text"] or "Pedro" in rev["extracted_text"]


@pytest.mark.asyncio
async def test_job_generate_reminders_and_dismiss(client, auth_headers):
    now = datetime.now(timezone.utc)

    # 1. Crear evento próximo (en 3 horas)
    ev_res = await client.post(
        "/v1/agenda/events",
        json={
            "title": "Vuelo a Guadalajara",
            "start_time": (now + timedelta(hours=3)).isoformat(),
            "end_time": (now + timedelta(hours=4)).isoformat(),
        },
        headers=auth_headers,
    )
    assert ev_res.status_code == 200
    event_id = ev_res.json()["id"]

    # 2. Encolar job para generar recordatorios
    job_res = await client.post(
        "/v1/jobs",
        json={
            "job_type": "generate_reminders",
            "payload": {"user_id": "default_user", "hours_ahead": 24},
        },
        headers=auth_headers,
    )
    assert job_res.status_code == 201
    job_id = job_res.json()["id"]

    # 3. Procesar trabajo
    proc_res = await client.post("/v1/jobs/process-pending", headers=auth_headers)
    assert proc_res.status_code == 200
    assert proc_res.json()["succeeded_count"] >= 1

    # Comprobar que el trabajo terminó con éxito
    check_job = await client.get(f"/v1/jobs/{job_id}", headers=auth_headers)
    assert check_job.json()["status"] == "completed"

    # 4. Crear evento con fecha pasada para probar recordatorio 'due'
    past_ev_res = await client.post(
        "/v1/agenda/events",
        json={
            "title": "Evento Inmediato",
            "start_time": (now + timedelta(minutes=10)).isoformat(),
            "end_time": (now + timedelta(hours=1)).isoformat(),
        },
        headers=auth_headers,
    )
    await client.post(
        "/v1/jobs",
        json={"job_type": "generate_reminders", "payload": {"user_id": "default_user", "hours_ahead": 24}},
        headers=auth_headers,
    )
    await client.post("/v1/jobs/process-pending", headers=auth_headers)

    # 5. Consultar recordatorios pendientes
    rem_res = await client.get("/v1/agenda/reminders/pending", headers=auth_headers)
    assert rem_res.status_code == 200
    reminders = rem_res.json()
    assert len(reminders) >= 1
    rem_id = reminders[0]["id"]

    # 6. Descartar recordatorio
    dismiss_res = await client.post(f"/v1/agenda/reminders/{rem_id}/dismiss", headers=auth_headers)
    assert dismiss_res.status_code == 200
    assert dismiss_res.json()["status"] == "dismissed"


@pytest.mark.asyncio
async def test_job_failure_retry_and_error_capture(client, auth_headers):
    # Encolar trabajo con tipo inválido o error deliberado
    job_res = await client.post(
        "/v1/jobs",
        json={
            "job_type": "document_extraction",
            "payload": {"revision_id": "rev-inexistente-12345"},
            "max_attempts": 2,
        },
        headers=auth_headers,
    )
    assert job_res.status_code == 201
    job_id = job_res.json()["id"]

    # Intento 1: falla y debe quedar en pending para reintento
    await client.post("/v1/jobs/process-pending", headers=auth_headers)
    j1 = (await client.get(f"/v1/jobs/{job_id}", headers=auth_headers)).json()
    assert j1["attempts"] == 1
    assert j1["status"] == "pending"
    assert "no encontrada" in j1["error_message"]

    # Intento 2: alcanza max_attempts (2) y debe marcar failed
    await client.post("/v1/jobs/process-pending", headers=auth_headers)
    j2 = (await client.get(f"/v1/jobs/{job_id}", headers=auth_headers)).json()
    assert j2["attempts"] == 2
    assert j2["status"] == "failed"
