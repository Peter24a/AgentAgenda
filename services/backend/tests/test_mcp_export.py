import hashlib
import json
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
            "device_name": "Pixel MCP Test",
            "platform": "android",
        },
    )
    token = pair.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_mcp_protocol_handshake_and_tools_list(client, auth_headers):
    # 1. Initialize
    init_req = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "Codex-Agent", "version": "1.0"},
        },
    }
    init_res = await client.post("/v1/mcp", json=init_req, headers=auth_headers)
    assert init_res.status_code == 200
    res_data = init_res.json()
    assert res_data["jsonrpc"] == "2.0"
    assert res_data["id"] == 1
    assert res_data["result"]["serverInfo"]["name"] == "agentagenda-mcp"

    # 2. List tools
    tools_req = {
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/list",
        "params": {},
    }
    tools_res = await client.post("/v1/mcp", json=tools_req, headers=auth_headers)
    assert tools_res.status_code == 200
    tools_data = tools_res.json()
    tool_names = [t["name"] for t in tools_data["result"]["tools"]]
    assert "get_personal_context" in tool_names
    assert "query_agenda" in tool_names
    assert "search" in tool_names
    assert "search_documents" in tool_names
    assert "get_event_preparation" in tool_names


@pytest.mark.asyncio
async def test_mcp_tools_call_execution(client, auth_headers):
    # 1. Crear datos de prueba
    now = datetime.now(timezone.utc)
    await client.post(
        "/v1/agenda/events",
        json={
            "title": "Audiencia en Juzgado Cívico",
            "start_time": (now + timedelta(days=1)).isoformat(),
            "end_time": (now + timedelta(days=1, hours=2)).isoformat(),
            "description": "Juzgado 12 de lo Familiar",
        },
        headers=auth_headers,
    )

    await client.post(
        "/v1/memory",
        json={
            "memory_type": "semantic",
            "predicate": "abogado_contacto",
            "value": "Lic. Roberto Garza (Tel: 55-1234-5678)",
        },
        headers=auth_headers,
    )

    # 2. Invocar tool 'search'
    call_search = {
        "jsonrpc": "2.0",
        "id": 10,
        "method": "tools/call",
        "params": {
            "name": "search",
            "arguments": {"query": "Audiencia"},
        },
    }
    res_s = await client.post("/v1/mcp", json=call_search, headers=auth_headers)
    assert res_s.status_code == 200
    s_content = res_s.json()["result"]["content"][0]["text"]
    assert "Audiencia en Juzgado Cívico" in s_content

    # 3. Invocar tool 'query_agenda'
    call_agenda = {
        "jsonrpc": "2.0",
        "id": 11,
        "method": "tools/call",
        "params": {
            "name": "query_agenda",
            "arguments": {},
        },
    }
    res_a = await client.post("/v1/mcp", json=call_agenda, headers=auth_headers)
    assert res_a.status_code == 200
    a_content = res_a.json()["result"]["content"][0]["text"]
    assert "Audiencia en Juzgado Cívico" in a_content

    # 4. Invocar tool 'get_personal_context'
    call_ctx = {
        "jsonrpc": "2.0",
        "id": 12,
        "method": "tools/call",
        "params": {
            "name": "get_personal_context",
            "arguments": {"purpose": "legal_consultation", "token_budget": 1024},
        },
    }
    res_c = await client.post("/v1/mcp", json=call_ctx, headers=auth_headers)
    assert res_c.status_code == 200
    c_content = res_c.json()["result"]["content"][0]["text"]
    assert "CONTEXTO PERSONAL" in c_content
    assert "abogado_contacto" in c_content or "Roberto Garza" in c_content


@pytest.mark.asyncio
async def test_canonical_context_export(client, auth_headers):
    # 1. Exportación en JSON
    json_res = await client.post(
        "/v1/context/export",
        json={"format": "json", "include_documents": True},
        headers=auth_headers,
    )
    assert json_res.status_code == 200
    json_data = json_res.json()
    assert json_data["format"] == "json"
    assert "sha256" in json_data
    assert len(json_data["sha256"]) == 64
    assert "events" in json_data["data"]
    assert "memories" in json_data["data"]

    # 2. Exportación en Markdown
    md_res = await client.post(
        "/v1/context/export",
        json={"format": "markdown", "include_documents": True},
        headers=auth_headers,
    )
    assert md_res.status_code == 200
    md_data = md_res.json()
    assert md_data["format"] == "markdown"
    assert "DOSSIER DE CONTEXTO CANÓNICO" in md_data["content"]
    assert hashlib.sha256(md_data["content"].encode("utf-8")).hexdigest() == md_data["sha256"]
