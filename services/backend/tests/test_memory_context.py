from datetime import datetime, timedelta, timezone
import pytest
import pytest_asyncio
from app.models.memory import ContextAssembleRequest


@pytest_asyncio.fixture
async def auth_headers(client):
    ch = await client.post("/v1/auth/challenge")
    code = ch.json()["pairing_code"]
    pair = await client.post(
        "/v1/auth/pair",
        json={
            "pairing_code": code,
            "device_name": "Pixel Memory Test",
            "platform": "android",
        },
    )
    token = pair.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_memory_creation_and_search(client, auth_headers):
    # 1. Crear memoria semántica
    req1 = {
        "memory_type": "semantic",
        "predicate": "alergias_medicamentos",
        "value": "Alergia confirmada a la penicilina y amoxicilina",
        "context_text": "Mencionado durante la consulta de valoración médica",
        "source_kind": "chat",
        "source_id": "turn-test-101",
    }
    res1 = await client.post("/v1/memory", json=req1, headers=auth_headers)
    assert res1.status_code == 201
    mem1 = res1.json()
    assert mem1["predicate"] == "alergias_medicamentos"
    assert mem1["status"] == "active"
    assert mem1["version"] == 1
    assert len(mem1["sources"]) == 1
    assert mem1["sources"][0]["source_id"] == "turn-test-101"

    # 2. Crear memoria episódica
    req2 = {
        "memory_type": "episodic",
        "predicate": "visita_taller_mecanico",
        "value": "Cambio de frenos delanteros y afinación mayor",
        "source_kind": "manual",
    }
    res2 = await client.post("/v1/memory", json=req2, headers=auth_headers)
    assert res2.status_code == 201

    # 3. Búsqueda por texto (query)
    search_res = await client.post(
        "/v1/memory/search",
        json={"query": "penicilina"},
        headers=auth_headers,
    )
    assert search_res.status_code == 200
    data = search_res.json()
    assert data["total"] >= 1
    assert any("penicilina" in m["value"] for m in data["memories"])

    # 4. Búsqueda por tipo
    search_type = await client.post(
        "/v1/memory/search",
        json={"memory_type": "episodic"},
        headers=auth_headers,
    )
    assert search_type.status_code == 200
    assert all(m["memory_type"] == "episodic" for m in search_type.json()["memories"])


@pytest.mark.asyncio
async def test_memory_correction_and_lineage(client, auth_headers):
    # 1. Crear hecho inicial (versión 1)
    res_init = await client.post(
        "/v1/memory",
        json={
            "memory_type": "semantic",
            "predicate": "direccion_fiscal_sat",
            "value": "Av. Paseo de la Reforma 222, CDMX",
        },
        headers=auth_headers,
    )
    assert res_init.status_code == 201
    mem_v1 = res_init.json()
    v1_id = mem_v1["id"]

    # 2. Corregir hecho mediante endpoint /correct
    corr_res = await client.post(
        "/v1/memory/correct",
        json={
            "memory_id": v1_id,
            "new_value": "Av. Insurgentes Sur 1602, Crédito Constructor, Benito Juárez, CDMX",
            "reason": "Cambio de domicilio fiscal registrado ante el SAT",
        },
        headers=auth_headers,
    )
    assert corr_res.status_code == 200
    mem_v2 = corr_res.json()
    assert mem_v2["version"] == 2
    assert mem_v2["supersedes_id"] == v1_id
    assert mem_v2["status"] == "active"
    assert "Insurgentes Sur" in mem_v2["value"]

    # 3. Comprobar que versión 1 ahora está marcada como 'superseded'
    v1_check = await client.get(f"/v1/memory/{v1_id}", headers=auth_headers)
    assert v1_check.status_code == 200
    assert v1_check.json()["status"] == "superseded"

    # 4. Comprobar que en búsqueda activa solo aparece la versión 2
    search_res = await client.post(
        "/v1/memory/search",
        json={"predicate": "direccion_fiscal_sat", "status": "active"},
        headers=auth_headers,
    )
    assert search_res.status_code == 200
    active_mems = search_res.json()["memories"]
    assert len(active_mems) == 1
    assert active_mems[0]["id"] == mem_v2["id"]
    assert active_mems[0]["version"] == 2


@pytest.mark.asyncio
async def test_memory_forget_revocation(client, auth_headers):
    # 1. Crear memoria
    res = await client.post(
        "/v1/memory",
        json={
            "memory_type": "semantic",
            "predicate": "clave_acceso_antigua",
            "value": "Contraseña provisoria expirada",
        },
        headers=auth_headers,
    )
    mem_id = res.json()["id"]

    # 2. Revocar (forget)
    f_res = await client.post(
        "/v1/memory/forget",
        json={"memory_id": mem_id, "reason": "Revocación por seguridad"},
        headers=auth_headers,
    )
    assert f_res.status_code == 200
    assert f_res.json()["status"] == "revoked"

    # 3. Verificar estado revoked
    check_res = await client.get(f"/v1/memory/{mem_id}", headers=auth_headers)
    assert check_res.json()["status"] == "revoked"

    # 4. En búsqueda de activas no debe aparecer
    search_res = await client.post(
        "/v1/memory/search",
        json={"query": "clave_acceso_antigua", "status": "active"},
        headers=auth_headers,
    )
    assert len(search_res.json()["memories"]) == 0


@pytest.mark.asyncio
async def test_context_engine_assembly_and_budget(client, auth_headers):
    now = datetime.now(timezone.utc)

    # 1. Crear evento para hoy
    await client.post(
        "/v1/agenda/events",
        json={
            "title": "Reunión con Notario Público 14",
            "description": "Notaría 14, CDMX",
            "start_time": (now + timedelta(hours=2)).isoformat(),
            "end_time": (now + timedelta(hours=3)).isoformat(),
        },
        headers=auth_headers,
    )

    # 2. Crear hecho activo
    await client.post(
        "/v1/memory",
        json={
            "memory_type": "semantic",
            "predicate": "preferencia_idioma",
            "value": "Español formal con terminología jurídica mexicana",
        },
        headers=auth_headers,
    )

    # 3. Crear hecho revocado (no debe aparecer en contexto)
    rev_mem = await client.post(
        "/v1/memory",
        json={
            "memory_type": "semantic",
            "predicate": "hecho_secreto_olvidado",
            "value": "Dato secreto que fue revocado completamente",
        },
        headers=auth_headers,
    )
    await client.post(
        "/v1/memory/forget",
        json={"memory_id": rev_mem.json()["id"]},
        headers=auth_headers,
    )

    # 4. Ensamblar contexto
    ctx_res = await client.get("/v1/context?purpose=agenda_review", headers=auth_headers)
    assert ctx_res.status_code == 200
    ctx = ctx_res.json()
    assembled = ctx["assembled_context"]

    # Debe incluir evento activo de hoy
    assert "Reunión con Notario Público 14" in assembled
    assert "Notaría 14" in assembled

    # Debe incluir memoria semántica activa
    assert "preferencia_idioma" in assembled
    assert "Español formal" in assembled

    # NO debe incluir el hecho revocado
    assert "Dato secreto que fue revocado completamente" not in assembled

    # 5. Presupuesto estricto de tokens
    assert ctx["estimated_tokens"] <= ctx["token_budget"]
    assert ctx["token_budget"] == 6144


@pytest.mark.asyncio
async def test_tripled_token_budget_defaults_and_limits(client, auth_headers):
    # ContextAssembleRequest default
    req = ContextAssembleRequest(purpose="check_budget")
    assert req.token_budget == 6144

    # GET /v1/context default
    res = await client.get("/v1/context?purpose=test_budget", headers=auth_headers)
    assert res.status_code == 200
    assert res.json()["token_budget"] == 6144

    # Upper bound accepts up to 24576
    large_req = ContextAssembleRequest(purpose="large", token_budget=24576)
    assert large_req.token_budget == 24576

