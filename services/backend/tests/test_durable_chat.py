import pytest
import pytest_asyncio
import json
from unittest.mock import patch

@pytest_asyncio.fixture
async def auth_headers(client):
    ch = await client.post("/v1/auth/challenge")
    code = ch.json()["pairing_code"]
    pair = await client.post(
        "/v1/auth/pair",
        json={
            "pairing_code": code,
            "device_name": "Pixel Chat Test",
            "platform": "android",
        },
    )
    token = pair.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}

async def mock_stream_llm(messages, temperature=0.7, max_tokens=1024):
    chunks = ["Hola, ", "puedo ayudarte ", "con tu agenda. "]
    for ch in chunks:
        yield ch

@pytest.mark.asyncio
async def test_durable_turn_creation_and_idempotency(client, auth_headers):
    with patch("app.services.chat_orchestrator.stream_chat_completion", side_effect=mock_stream_llm):
        # 1. Crear turno durable
        turn_payload = {
            "message": "¿Qué actividades tengo hoy?",
            "client_message_id": "client-msg-alpha-1",
            "date": "2026-09-15",
            "timezone": "America/Mexico_City"
        }
        res = await client.post("/v1/chat/turns", json=turn_payload, headers=auth_headers)
        assert res.status_code == 200
        data = res.json()
        turn_id = data["turn_id"]
        assert data["user_message"] == "¿Qué actividades tengo hoy?"
        assert data["status"] in ("queued", "running", "completed")

        # 2. Reenviar con el mismo client_message_id (Idempotencia)
        res_dup = await client.post("/v1/chat/turns", json=turn_payload, headers=auth_headers)
        assert res_dup.status_code == 200
        assert res_dup.json()["turn_id"] == turn_id

        # 3. Consultar estado del turno
        res_get = await client.get(f"/v1/chat/turns/{turn_id}", headers=auth_headers)
        assert res_get.status_code == 200
        assert res_get.json()["turn_id"] == turn_id

@pytest.mark.asyncio
async def test_durable_chat_messages_history(client, auth_headers):
    with patch("app.services.chat_orchestrator.stream_chat_completion", side_effect=mock_stream_llm):
        # Crear turno
        await client.post(
            "/v1/chat/turns",
            json={"message": "Mensaje para el historial durable"},
            headers=auth_headers
        )

        # Consultar historial
        res = await client.get("/v1/chat/messages", headers=auth_headers)
        assert res.status_code == 200
        messages = res.json()
        assert len(messages) >= 1
        found = any("Mensaje para el historial durable" in m["content"] for m in messages)
        assert found is True

@pytest.mark.asyncio
async def test_chat_stream_legacy_compatibility(client, auth_headers):
    with patch("app.services.chat_orchestrator.stream_chat_completion", side_effect=mock_stream_llm):
        legacy_req = {
            "message": "Hola asistente",
            "date": "2026-09-15",
            "history": []
        }
        res = await client.post("/v1/chat/stream", json=legacy_req, headers=auth_headers)
        assert res.status_code == 200
        assert "text/event-stream" in res.headers["content-type"]
