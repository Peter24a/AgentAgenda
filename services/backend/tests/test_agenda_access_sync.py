from datetime import datetime

import pytest
from sqlalchemy import select

from app.config import settings
from app.models.auth import AuthContext
from app.models.canonical import ChangeBatch, Event, SyncHead
from app.services.auth_service import auth_service


@pytest.mark.asyncio
async def test_all_agenda_routes_reject_missing_or_invalid_identity(client, monkeypatch):
    monkeypatch.setattr(settings, "allow_anonymous_fallback", False)
    for method, path, body in [
        ("GET", "/v1/agenda/events?date=2026-09-15", None),
        ("GET", "/v1/agenda/tasks", None),
        ("POST", "/v1/agenda/events", {"title": "Synthetic", "start_time": "2026-09-15T10:00:00-06:00"}),
        ("DELETE", "/v1/agenda/events/synthetic", None),
        ("POST", "/v1/agenda/events/synthetic/toggle", None),
        ("POST", "/v1/agenda/tasks/synthetic/toggle", None),
        ("GET", "/v1/proposals/pending", None),
        ("GET", "/v1/proposals/synthetic", None),
        ("POST", "/v1/proposals/synthetic/confirm", None),
        ("POST", "/v1/proposals/synthetic/reject", None),
    ]:
        for headers in ({}, {"Authorization": "Bearer not-a-valid-token"}):
            response = await client.request(method, path, json=body, headers=headers)
            assert response.status_code == 401


@pytest.mark.asyncio
async def test_read_scope_cannot_mutate_or_fall_back_to_another_owner(client, db_session, monkeypatch):
    async def auth(session, token):
        return AuthContext(user_id="reader", device_id=None, token_id="synthetic", scopes=["agenda:read"])
    monkeypatch.setattr(auth_service, "authenticate_token", auth)
    db_session.add(Event(id="private-event", user_id="default_user", title="Synthetic other owner", start_time=datetime(2026, 9, 15, 16)))
    await db_session.commit()
    headers = {"Authorization": "Bearer synthetic-reader"}
    read = await client.get("/v1/agenda/events?date=2026-09-15", headers=headers)
    assert read.status_code == 200 and read.json() == []
    changed = await client.post("/v1/agenda/events/private-event/toggle", headers=headers)
    assert changed.status_code == 403


@pytest.mark.asyncio
async def test_rest_changes_are_visible_to_sync_with_utc_times(client, db_session, monkeypatch):
    monkeypatch.setattr(settings, "allow_anonymous_fallback", True)
    created = await client.post("/v1/agenda/events", json={
        "id": "synthetic-sync-event", "title": "Synthetic schedule",
        "start_time": "2026-09-15T07:00:00", "end_time": "2026-09-15T08:00:00",
    })
    assert created.status_code == 200
    assert created.json()["start_time"] == "2026-09-15T13:00:00Z"
    assert (await client.post("/v1/agenda/events/synthetic-sync-event/toggle")).status_code == 200
    assert (await client.delete("/v1/agenda/events/synthetic-sync-event")).status_code == 200
    changes = (await db_session.scalars(select(ChangeBatch).order_by(ChangeBatch.commit_seq))).all()
    assert [c.change_type for c in changes] == ["create", "update", "delete"]
    assert [c.entity_version for c in changes] == [1, 2, 3]
    assert changes[0].payload_json["start_time"] == "2026-09-15T13:00:00Z"
    assert changes[1].payload_json["is_completed"] is True
    assert changes[2].payload_json["is_deleted"] is True
    head = await db_session.get(SyncHead, "default_user")
    assert head.current_seq == 3
    pulled = await client.get("/v1/sync/pull?since_seq=0")
    assert pulled.status_code == 200
    assert len(pulled.json()["changes"]) == 3


@pytest.mark.asyncio
async def test_invalid_schedule_input_does_not_commit(client, db_session, monkeypatch):
    monkeypatch.setattr(settings, "allow_anonymous_fallback", True)
    response = await client.post("/v1/agenda/events", json={
        "title": "Synthetic backwards", "start_time": "2026-09-15T10:00:00-06:00",
        "end_time": "2026-09-15T09:00:00-06:00",
    })
    assert response.status_code == 422
    response = await client.get("/v1/agenda/events?date=not-a-date")
    assert response.status_code == 422
    response = await client.get("/v1/agenda/events?date=2026-09-15&timezone=not-a-zone")
    assert response.status_code == 422
    assert (await db_session.scalars(select(Event))).all() == []
    assert (await db_session.scalars(select(ChangeBatch))).all() == []
