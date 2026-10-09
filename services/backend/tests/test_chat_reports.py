"""AI feedback is durable, explicitly authenticated, and private to its owner."""
import asyncio
import json
from unittest.mock import patch

import pytest
from pydantic import SecretStr
from sqlalchemy import select

from app.config import settings
from app.core.security import hash_token
from app.models.auth import PairRequest
from app.models.canonical import AuthToken, ChatMessage, ChatResponseReport, ChatTurn, Device
from app.services.auth_service import auth_service
from app.services.chat_orchestrator import chat_orchestrator


async def enroll(session, *, user="alice", scopes=None, device_bound=True):
    pair = await auth_service.enroll_device(session, user, PairRequest(
        pairing_code="synthetic", device_name="Synthetic review phone", platform="android",
    ))
    token = await session.scalar(select(AuthToken).where(AuthToken.token_hash == hash_token(pair.access_token)))
    if scopes is not None:
        token.scopes = scopes
    if not device_bound:
        token.device_id = None
    await session.commit()
    return pair, {"Authorization": "Bearer " + pair.access_token}


async def assistant_message(session, *, message_id="assistant-1", user="alice", device="old-phone", role="assistant", standalone=False):
    turn_id = None if standalone else "turn-" + message_id
    if turn_id:
        session.add(ChatTurn(id=turn_id, user_id=user, device_id=device, status="completed"))
        await session.flush()
    message = ChatMessage(id=message_id, turn_id=turn_id, user_id=user, role=role, content="Synthetic private response")
    session.add(message)
    await session.commit()
    return message


@pytest.mark.asyncio
@pytest.mark.parametrize("standalone", [False, True])
async def test_report_persists_without_copying_assistant_text(client, db_session, standalone):
    pair, headers = await enroll(db_session)
    message = await assistant_message(db_session, standalone=standalone)
    result = await client.post("/v1/chat/reports", headers=headers, json={
        "message_id": message.id, "reason": "harmful", "details": "  Please review this response  ",
    })
    assert result.status_code == 201
    receipt = result.json()
    assert set(receipt) == {"id", "message_id", "reason", "status", "created_at"}
    assert receipt["status"] == "received"
    assert receipt["created_at"].endswith("Z")
    report = await db_session.get(ChatResponseReport, receipt["id"])
    assert (report.user_id, report.device_id, report.message_id) == ("alice", pair.device_id, message.id)
    assert report.details == "Please review this response"
    assert report.status == "received"
    assert "Synthetic private response" not in result.text
    assert "Please review" not in result.text
    # Historical messages from the owner's prior device remain reportable.
    assert message.turn_id is None or pair.device_id != "old-phone"


@pytest.mark.asyncio
async def test_identical_retry_reuses_receipt_and_conflicting_report_is_rejected(client, db_session):
    _, headers = await enroll(db_session)
    await assistant_message(db_session)
    body = {"message_id": "assistant-1", "reason": "privacy", "details": "Synthetic concern"}
    first = await client.post("/v1/chat/reports", headers=headers, json=body)
    retry = await client.post("/v1/chat/reports", headers=headers, json=body)
    assert first.status_code == 201
    assert retry.status_code == 200
    assert retry.json() == first.json()
    conflict = await client.post("/v1/chat/reports", headers=headers, json={**body, "reason": "other"})
    assert conflict.status_code == 409
    reports = (await db_session.scalars(select(ChatResponseReport))).all()
    assert len(reports) == 1
    assert reports[0].reason == "privacy"


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["missing", "foreign", "user", "system"])
async def test_foreign_missing_and_non_assistant_messages_have_same_rejection(client, db_session, kind):
    _, headers = await enroll(db_session)
    if kind != "missing":
        await assistant_message(db_session, user="bob" if kind == "foreign" else "alice",
                                role=kind if kind in {"user", "system"} else "assistant")
    result = await client.post("/v1/chat/reports", headers=headers, json={"message_id": "assistant-1", "reason": "other"})
    assert result.status_code == 404
    assert result.json() == {"detail": "Respuesta del asistente no encontrada"}
    assert not (await db_session.scalars(select(ChatResponseReport))).all()


@pytest.mark.asyncio
async def test_reports_require_explicit_access_token_even_with_local_fallback(client, db_session):
    pair, _ = await enroll(db_session)
    await assistant_message(db_session)
    body = {"message_id": "assistant-1", "reason": "other"}
    for headers in ({}, {"Authorization": "Bearer invalid"}, {"Authorization": "Bearer " + pair.refresh_token}):
        assert (await client.post("/v1/chat/reports", headers=headers, json=body)).status_code == 401
    assert not (await db_session.scalars(select(ChatResponseReport))).all()


@pytest.mark.asyncio
@pytest.mark.parametrize("scopes,device_bound", [(["chat:read"], True), (["chat:write"], True), (["agenda:write"], True), (["chat:*"], False)])
async def test_reports_require_chat_read_write_and_registered_device(client, db_session, scopes, device_bound):
    _, headers = await enroll(db_session, scopes=scopes, device_bound=device_bound)
    await assistant_message(db_session)
    result = await client.post("/v1/chat/reports", headers=headers, json={"message_id": "assistant-1", "reason": "other"})
    assert result.status_code == 403
    assert not (await db_session.scalars(select(ChatResponseReport))).all()


@pytest.mark.asyncio
async def test_revoked_device_cannot_submit_feedback(client, db_session):
    pair, headers = await enroll(db_session)
    await assistant_message(db_session)
    device = await db_session.get(Device, pair.device_id)
    device.is_active = False
    await db_session.commit()
    assert (await client.post("/v1/chat/reports", headers=headers, json={"message_id": "assistant-1", "reason": "other"})).status_code == 401
    assert not (await db_session.scalars(select(ChatResponseReport))).all()


@pytest.mark.asyncio
@pytest.mark.parametrize("bad_body", [
    {"message_id": "assistant-1", "reason": "unsupported"},
    {"message_id": "assistant-1", "reason": "other", "details": "x" * 2001},
    {"message_id": "assistant-1", "reason": "other", "status": "reviewed"},
    {"message_id": "   ", "reason": "other"},
])
async def test_report_payload_is_bounded_and_cannot_set_status(client, db_session, bad_body):
    _, headers = await enroll(db_session)
    assert (await client.post("/v1/chat/reports", headers=headers, json=bad_body)).status_code == 422
    assert not (await db_session.scalars(select(ChatResponseReport))).all()


@pytest.mark.asyncio
async def test_internal_metrics_expose_report_count_only(client, db_session, monkeypatch):
    monkeypatch.setattr(settings, "platform_enrollment_key", SecretStr("synthetic-internal-key"))
    _, headers = await enroll(db_session)
    await assistant_message(db_session)
    await client.post("/v1/chat/reports", headers=headers, json={"message_id": "assistant-1", "reason": "harmful", "details": "Sensitive synthetic details"})
    assert (await client.get("/internal/metrics", headers=headers)).status_code == 403
    result = await client.get("/internal/metrics", headers={"X-Enrollment-Key": "synthetic-internal-key"})
    assert result.status_code == 200
    assert result.json()["pending_ai_reports"] == 1
    assert set(result.json()) == {"usage_bytes", "quota_bytes", "health", "pending_ai_reports"}
    assert "Sensitive" not in result.text
    assert "assistant-1" not in result.text


@pytest.mark.asyncio
async def test_live_and_replayed_done_include_exact_reportable_assistant_id(client, db_session):
    _, headers = await enroll(db_session)

    async def synthetic_completion(*args, **kwargs):
        await asyncio.sleep(0.01)
        yield "Synthetic generated answer"

    with patch("app.services.chat_orchestrator.stream_chat_completion", side_effect=synthetic_completion):
        created = await client.post("/v1/chat/turns", headers=headers, json={"message": "Synthetic question"})
        turn_id = created.json()["turn_id"]
        stream = await client.get(f"/v1/chat/turns/{turn_id}/stream", headers=headers)
        task = chat_orchestrator._active_tasks.get(turn_id)
        if task:
            await task
    done = [json.loads(line[6:]) for line in stream.text.splitlines() if line.startswith("data: ")]
    message_id = next(event["assistant_message_id"] for event in done if event["type"] == "done")
    stored = await db_session.get(ChatMessage, message_id)
    assert stored.role == "assistant"
    assert stored.turn_id == turn_id
    turn = (await client.get(f"/v1/chat/turns/{turn_id}", headers=headers)).json()
    assert turn["assistant_message_id"] == message_id
    replay = await client.get(f"/v1/chat/turns/{turn_id}/stream", headers=headers)
    replay_events = [json.loads(line[6:]) for line in replay.text.splitlines() if line.startswith("data: ")]
    assert next(event["assistant_message_id"] for event in replay_events if event["type"] == "done") == message_id
    assert (await client.post("/v1/chat/reports", headers=headers, json={"message_id": message_id, "reason": "inaccurate"})).status_code == 201
