import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select

from app.api import status as status_api
from app.models.canonical import Job
from app.worker import runner


@pytest.mark.asyncio
async def test_recovery_only_requeues_expired_processing_claims(db_session):
    now = datetime(2026, 9, 15, 12, 0)
    rows = [
        ("expired", "processing", now - timedelta(minutes=31)),
        ("recent", "processing", now - timedelta(minutes=10)),
        ("boundary", "processing", now - timedelta(minutes=30)),
        ("completed", "completed", now - timedelta(days=1)),
        ("failed", "failed", now - timedelta(days=1)),
        ("pending", "pending", now - timedelta(days=1)),
    ]
    for job_id, state, updated_at in rows:
        db_session.add(Job(id=job_id, job_type="document_extraction", payload_json={},
                           status=state, updated_at=updated_at, attempts=1))
    await db_session.commit()
    assert await runner.recover_expired_jobs(db_session, now=now) == 1
    jobs = {job.id: job for job in (await db_session.execute(select(Job))).scalars()}
    assert jobs["expired"].status == "pending"
    assert jobs["expired"].updated_at == now
    assert jobs["recent"].status == jobs["boundary"].status == "processing"
    assert jobs["completed"].status == "completed"
    assert jobs["failed"].status == "failed"
    assert jobs["pending"].status == "pending"
    assert all(job.attempts == 1 for job in jobs.values())
    # Jobs that were fresh at startup become eligible during a later sweep.
    assert await runner.recover_expired_jobs(db_session, now=now + timedelta(minutes=21)) == 2
    for job in jobs.values():
        await db_session.refresh(job)
    assert jobs["recent"].status == jobs["boundary"].status == "pending"
    assert await runner.recover_expired_jobs(db_session, now=now + timedelta(hours=1)) == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("processed_count, pause", [(0, 2), (2, 0.1)])
async def test_runner_sweeps_leases_each_iteration_and_cleans_heartbeat(tmp_path, monkeypatch, processed_count, pause):
    session = object()

    @asynccontextmanager
    async def fake_context():
        yield session

    fake_engine = SimpleNamespace(dialect=SimpleNamespace(name="sqlite"), connect=fake_context)
    monkeypatch.setattr(runner, "engine", fake_engine)
    monkeypatch.setattr(runner, "get_db_context", fake_context)
    monkeypatch.setattr(runner.settings, "storage_path", str(tmp_path))
    recover = AsyncMock()
    process = AsyncMock(return_value=(processed_count, processed_count, 0, []))
    monkeypatch.setattr(runner, "recover_expired_jobs", recover)
    monkeypatch.setattr(runner.background_worker, "process_pending_jobs", process)
    pulse_file = tmp_path / "worker-heartbeat.json"
    pulse_file.write_text("{}")

    async def idle_heartbeat():
        await asyncio.Event().wait()

    monkeypatch.setattr(runner, "heartbeat", idle_heartbeat)
    pauses = []

    async def stop_after_second_cycle(seconds):
        pauses.append(seconds)
        if len(pauses) == 2:
            raise asyncio.CancelledError

    monkeypatch.setattr(runner.asyncio, "sleep", stop_after_second_cycle)
    with pytest.raises(asyncio.CancelledError):
        await runner.run()
    assert recover.await_count == process.await_count == 2
    assert all(call.args == (session,) for call in recover.await_args_list)
    assert pauses == [pause, pause]
    assert not pulse_file.exists()


@pytest.mark.asyncio
async def test_heartbeat_writes_atomic_current_timestamp(tmp_path, monkeypatch):
    monkeypatch.setattr(runner.settings, "storage_path", str(tmp_path))

    async def stop_after_write(_):
        raise asyncio.CancelledError

    monkeypatch.setattr(runner.asyncio, "sleep", stop_after_write)
    with pytest.raises(asyncio.CancelledError):
        await runner.heartbeat()
    stamp = json.loads((tmp_path / "worker-heartbeat.json").read_text())["timestamp"]
    assert abs((datetime.now(timezone.utc) - datetime.fromisoformat(stamp)).total_seconds()) < 5
    assert not (tmp_path / "worker-heartbeat.tmp").exists()


@pytest.mark.asyncio
@pytest.mark.parametrize("heartbeat_kind", ["fresh", "missing", "stale", "future", "malformed", "naive"])
async def test_status_requires_recent_valid_worker_heartbeat(tmp_path, db_session, monkeypatch, heartbeat_kind):
    monkeypatch.setattr(status_api.settings, "storage_path", str(tmp_path))

    class OnlineLLM:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def get(self, *args):
            return SimpleNamespace(status_code=200)

    monkeypatch.setattr(status_api.httpx, "AsyncClient", OnlineLLM)
    now = datetime.now(timezone.utc)
    if heartbeat_kind != "missing":
        stamp = {
            "fresh": now.isoformat(),
            "stale": (now - timedelta(seconds=40)).isoformat(),
            "future": (now + timedelta(minutes=10)).isoformat(),
            "malformed": "invalid timestamp",
            "naive": now.replace(tzinfo=None).isoformat(),
        }[heartbeat_kind]
        (tmp_path / "worker-heartbeat.json").write_text(json.dumps({"timestamp": stamp}))
    result = await status_api.get_system_status(db_session)
    assert result["database"]["status"] == "connected"
    assert result["llm"]["status"] == "online"
    assert result["worker"]["status"] == ("active" if heartbeat_kind == "fresh" else "offline")
    assert result["status"] == ("healthy" if heartbeat_kind == "fresh" else "degraded")
