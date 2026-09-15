"""Synthetic regressions for context visibility, MCP transport and auth."""
import asyncio
import hashlib
from datetime import datetime, timedelta, timezone

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.config import settings
from app.core.security import hash_token
from app.models.canonical import AuthToken, ChatMessage, ChatTurn, Document, DocumentOrigin, Memory, MemorySource
from app.models.memory import ContextAssembleRequest, MemoryCreateRequest
from app.services.context_engine import context_engine
from app.services.context_export import context_export_service
from app.services.memory_service import memory_service


async def headers_for(session, scopes):
    key = "synthetic-" + "-".join(scopes)
    session.add(AuthToken(id=key, user_id="default_user", device_id=None,
                          token_hash=hash_token(key), scopes=scopes,
                          expires_at=datetime.utcnow() + timedelta(days=1)))
    await session.commit()
    return {"Authorization": f"Bearer {key}"}


def rpc(method, arguments=None, name=None):
    return {"jsonrpc": "2.0", "id": 1, "method": method,
            "params": {"name": name, "arguments": arguments or {}} if name else arguments or {}}


@pytest.mark.asyncio
async def test_forwarded_header_cannot_enable_anonymous_pairing(client, monkeypatch):
    from app.main import app
    monkeypatch.setattr(settings, "allow_anonymous_fallback", True)
    transport = ASGITransport(app=app, client=("8.8.8.8", 41000))
    async with AsyncClient(transport=transport, base_url="http://review") as external:
        response = await external.post("/v1/auth/challenge", headers={"X-Forwarded-For": "127.0.0.1"})
        assert response.status_code == 401
    # Explicit local bootstrap remains usable only when enabled.
    assert (await client.post("/v1/auth/challenge")).status_code == 200
    monkeypatch.setattr(settings, "allow_anonymous_fallback", False)
    assert (await client.post("/v1/auth/challenge")).status_code == 401


@pytest.mark.asyncio
async def test_mcp_requires_bearer_and_enforces_transport(client, db_session):
    assert (await client.post("/v1/mcp", json=rpc("ping"))).status_code == 401
    headers = await headers_for(db_session, ["mcp:read"])
    initialized = await client.post("/v1/mcp", headers=headers, json=rpc("initialize", {
        "protocolVersion": "2025-06-18", "capabilities": {},
        "clientInfo": {"name": "synthetic-review", "version": "1"},
    }))
    assert initialized.json()["result"]["protocolVersion"] == "2025-06-18"
    notification = await client.post("/v1/mcp", headers=headers,
                                    json={"jsonrpc": "2.0", "method": "notifications/initialized"})
    assert notification.status_code == 202 and notification.content == b""
    assert (await client.get("/v1/mcp", headers=headers)).status_code == 405
    invalid_version = await client.post("/v1/mcp", headers={**headers, "MCP-Protocol-Version": "unsupported"}, json=rpc("ping"))
    assert invalid_version.status_code == 400
    bad_origin = await client.post("/v1/mcp", headers={**headers, "Origin": "https://untrusted.invalid"}, json=rpc("ping"))
    assert bad_origin.status_code == 403
    bad_body = await client.post("/v1/mcp", headers=headers, json=[])
    assert bad_body.json()["error"]["code"] == -32600
    parse_error = await client.post("/v1/mcp", headers=headers, content="{")
    assert parse_error.status_code == 400 and parse_error.json()["error"]["code"] == -32700


@pytest.mark.asyncio
async def test_mcp_scope_does_not_imply_memory_or_document_access(client, db_session):
    headers = await headers_for(db_session, ["mcp:read"])
    listing = await client.post("/v1/mcp", headers=headers, json=rpc("tools/list"))
    assert listing.json()["result"]["tools"] == []
    denied = await client.post("/v1/mcp", headers=headers, json=rpc("tools/call", {"query": "anything"}, "search_documents"))
    assert denied.json()["result"]["isError"] is True
    export = await client.post("/v1/context/export", headers=headers, json={})
    assert export.status_code == 403


@pytest.mark.asyncio
async def test_mcp_rejects_invalid_arguments_without_500(client, db_session):
    headers = await headers_for(db_session, ["mcp:read", "memory:read", "agenda:read", "tasks:read"])
    for name, arguments in [
        ("search", {"query": "test", "limit": -1}),
        ("query_agenda", {"from_date": "not-a-date"}),
        ("get_personal_context", {"token_budget": 1}),
        ("query_agenda", {"timezone": "No/SuchZone"}),
    ]:
        response = await client.post("/v1/mcp", headers=headers, json=rpc("tools/call", arguments, name))
        assert response.status_code == 200
        assert response.json()["error"]["code"] == -32602


@pytest.mark.asyncio
async def test_safe_origin_and_source_revocation_apply_to_model_and_export(db_session):
    for key, privacy, deleted in [
        ("safe", "SAFE", False), ("optin", "OPT_IN", False),
        ("never", "NEVER_UPLOAD", False), ("unknown", None, False),
        ("deleted", "SAFE", True),
    ]:
        db_session.add(Document(id=key, user_id="default_user", title=f"doc-{key}", is_deleted=deleted))
        await db_session.flush()
        if privacy:
            db_session.add(DocumentOrigin(document_id=key, source_collection="synthetic",
                                          source_path=f"{key}.txt", source_kind="reference", privacy_class=privacy))
        db_session.add(Memory(id=f"memory-{key}", user_id="default_user", memory_type="semantic",
                              predicate="favorite_color", value=f"value-{key}", source_kind="document", status="active"))
        await db_session.flush()
        db_session.add(MemorySource(id=f"source-{key}", memory_id=f"memory-{key}", source_kind="document", source_id=key))
    db_session.add(Memory(id="expired", user_id="default_user", memory_type="semantic", predicate="old",
                          value="expired-value", status="active", valid_to=datetime.utcnow()-timedelta(days=1)))
    await db_session.commit()
    context = await context_engine.memory_context(db_session, "default_user", token_budget=3000)
    assert "value-safe" in context
    assert all(f"value-{key}" not in context for key in ("optin", "never", "unknown", "deleted"))
    assert "expired-value" not in context
    exported = await context_export_service.export_canonical_context(db_session, "default_user", include_documents=True)
    assert [doc["id"] for doc in exported["data"]["documents"]] == ["safe"]
    assert [memory["id"] for memory in exported["data"]["memories"]] == ["memory-safe"]
    safe_doc = await db_session.get(Document, "safe")
    safe_doc.is_deleted = True
    await db_session.commit()
    assert "value-safe" not in await context_engine.memory_context(db_session, "default_user", token_budget=3000)


@pytest.mark.asyncio
async def test_context_budget_counts_only_whole_included_records(db_session):
    await memory_service.create_memory(db_session, "default_user", MemoryCreateRequest(
        predicate="oversized", value="contenido sintético " * 2000,
    ))
    response = await context_engine.assemble_context(db_session, "default_user", ContextAssembleRequest(
        token_budget=256, include_agenda=False,
    ))
    assert response.estimated_tokens <= 256
    assert response.memories_count == 0
    assert response.items_included_count == 0
    assert "omitidos" in response.assembled_context


@pytest.mark.asyncio
async def test_semantic_memory_reaches_chat_only_with_scope(client, db_session, monkeypatch):
    from app.services import chat_orchestrator as module
    from app.services.chat_orchestrator import chat_orchestrator
    await memory_service.create_memory(db_session, "default_user", MemoryCreateRequest(
        predicate="preferred_study_method", value="SYNTHETIC_SEMANTIC_FACT",
    ))
    captured = []
    async def fake_stream(messages):
        captured.append(messages)
        yield "Respuesta sintética."
    monkeypatch.setattr(module, "stream_chat_completion", fake_stream)
    for scopes in (["chat:write", "memory:read"], ["chat:write"]):
        headers = await headers_for(db_session, scopes)
        response = await client.post("/v1/chat/turns", headers=headers, json={"message": "¿Qué método prefiero?"})
        assert response.status_code == 200
        tasks = list(chat_orchestrator._active_tasks.values())
        if tasks:
            await asyncio.wait_for(asyncio.gather(*tasks), timeout=3)
    assert "SYNTHETIC_SEMANTIC_FACT" in str(captured[0])
    assert "SYNTHETIC_SEMANTIC_FACT" not in str(captured[1])


@pytest.mark.asyncio
async def test_revoked_memory_does_not_return_through_chat_history(client, db_session, monkeypatch):
    from app.services import chat_orchestrator as module
    from app.services.chat_orchestrator import chat_orchestrator
    old_time = datetime.utcnow() - timedelta(hours=1)
    db_session.add(ChatTurn(id="old-turn", user_id="default_user", status="completed", created_at=old_time))
    await db_session.flush()
    db_session.add(ChatMessage(id="old-response", turn_id="old-turn", user_id="default_user", role="assistant",
                               content="REVOKED_SYNTHETIC_FACT", created_at=old_time, received_at=old_time))
    db_session.add(Memory(id="revoked-fact", user_id="default_user", memory_type="semantic", predicate="old",
                          value="REVOKED_SYNTHETIC_FACT", status="revoked", updated_at=datetime.utcnow()))
    await db_session.commit()
    captured = []
    async def fake_stream(messages):
        captured.append(messages)
        yield "Respuesta sintética."
    monkeypatch.setattr(module, "stream_chat_completion", fake_stream)
    headers = await headers_for(db_session, ["chat:write", "memory:read", "documents:read"])
    response = await client.post("/v1/chat/turns", headers=headers, json={"message": "Revisemos el día"})
    assert response.status_code == 200
    tasks = list(chat_orchestrator._active_tasks.values())
    if tasks:
        await asyncio.wait_for(asyncio.gather(*tasks), timeout=3)
    assert captured and "REVOKED_SYNTHETIC_FACT" not in str(captured)


@pytest.mark.asyncio
async def test_stdio_uses_fixed_readonly_identity_and_skips_notifications(db_session):
    import io
    import json
    from app.mcp.stdio import serve
    inputs = [rpc("initialize", {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {}}),
              {"jsonrpc": "2.0", "method": "notifications/initialized"},
              rpc("tools/list"), rpc("tools/call", {}, "delete_everything")]
    incoming = io.BytesIO(b"\n".join(json.dumps(item).encode() for item in inputs) + b"\n")
    outgoing = io.BytesIO()
    await serve(incoming, outgoing)
    responses = [json.loads(line) for line in outgoing.getvalue().splitlines()]
    assert len(responses) == 3
    assert responses[0]["result"]["protocolVersion"] == "2025-06-18"
    assert all(tool["annotations"]["readOnlyHint"] for tool in responses[1]["result"]["tools"])
    assert responses[2]["error"]["code"] == -32602


@pytest.mark.asyncio
async def test_stdio_oversized_and_bad_json_recover_for_next_request(db_session, monkeypatch):
    import io
    import json
    import app.mcp.stdio as module
    monkeypatch.setattr(module, "MAX_MESSAGE_BYTES", 512)
    incoming = io.BytesIO(b"x" * 1000 + b"\n{\n" + json.dumps(rpc("ping")).encode() + b"\n")
    outgoing = io.BytesIO()
    await module.serve(incoming, outgoing)
    responses = [json.loads(line) for line in outgoing.getvalue().splitlines()]
    assert [response.get("error", {}).get("code") for response in responses] == [-32600, -32700, None]
    assert responses[-1]["result"] == {}


@pytest.mark.asyncio
async def test_memory_scope_cannot_read_agenda_through_context(client, db_session):
    headers = await headers_for(db_session, ["memory:read"])
    assert (await client.get("/v1/context", headers=headers)).status_code == 403
    assert (await client.get("/v1/context?include_agenda=false", headers=headers)).status_code == 200


@pytest.mark.asyncio
async def test_past_activity_is_retained_as_dated_episode(db_session):
    observed = datetime.utcnow() - timedelta(days=1)
    db_session.add(Memory(id="episode", user_id="default_user", memory_type="episodic",
                          predicate="activity_check_in", value="SYNTHETIC_PAST_EPISODE",
                          valid_from=observed, valid_to=observed, status="active"))
    await db_session.commit()
    context = await context_engine.memory_context(db_session, "default_user")
    assert "SYNTHETIC_PAST_EPISODE" in context
    assert observed.isoformat() in context


@pytest.mark.asyncio
async def test_correction_preserves_source_privacy_and_timezone(db_session):
    from app.models.memory import MemoryCorrectRequest
    db_session.add(Document(id="restricted-source", user_id="default_user", title="Synthetic restricted source"))
    await db_session.flush()
    db_session.add(DocumentOrigin(document_id="restricted-source", source_collection="synthetic",
                                  source_path="fiction.txt", source_kind="reference", privacy_class="OPT_IN"))
    await db_session.commit()
    original = await memory_service.create_memory(db_session, "default_user", MemoryCreateRequest(
        predicate="synthetic_fact", value="old value", source_kind="document", source_id="restricted-source",
        valid_from=datetime(2026, 1, 1, 6, tzinfo=timezone(timedelta(hours=-6))),
    ))
    assert original.valid_from == datetime(2026, 1, 1, 12)
    corrected = await memory_service.correct_memory(db_session, "default_user", MemoryCorrectRequest(
        memory_id=original.id, new_value="CORRECTED_RESTRICTED_SYNTHETIC_VALUE",
    ))
    assert any(source.source_id == "restricted-source" for source in corrected.sources)
    assert "CORRECTED_RESTRICTED_SYNTHETIC_VALUE" not in await context_engine.memory_context(db_session, "default_user")
