"""Sync accepts offset-bearing instants without changing command identity."""

import os
import uuid
from datetime import datetime

import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.canonical import Base, ChangeBatch, Event, Memory, OperationReceipt, SyncHead, Task
from app.models.sync import SyncPushRequest
from app.services.sync_service import sync_service


ENTITIES = [
    ("event", Event, ("start_time", "end_time"), "events"),
    ("task", Task, ("due_date",), "tasks"),
    ("memory", Memory, ("valid_from", "valid_to"), "memories"),
]

# Expected values are explicit UTC instants, including a date boundary and a
# fractional-hour offset. The last case protects legacy timezone-free input.
INSTANTS = [
    (
        ("2026-10-09T21:49:11-06:00", "2026-10-09T23:49:11-06:00"),
        ("2026-10-10T03:49:11", "2026-10-10T05:49:11"),
        ("2026-10-11T06:30:00+05:30", "2026-10-11T07:45:00+05:30"),
        ("2026-10-11T01:00:00", "2026-10-11T02:15:00"),
    ),
    (
        ("2026-10-09T05:30:00+05:30", "2026-10-09T06:15:00+05:30"),
        ("2026-10-09T00:00:00", "2026-10-09T00:45:00"),
        ("2026-10-10T01:15:00Z", "2026-10-10T02:45:00Z"),
        ("2026-10-10T01:15:00", "2026-10-10T02:45:00"),
    ),
    (
        ("2026-10-09T12:00:00Z", "2026-10-09T13:00:00Z"),
        ("2026-10-09T12:00:00", "2026-10-09T13:00:00"),
        ("2026-10-09T21:00:00-06:00", "2026-10-09T22:00:00-06:00"),
        ("2026-10-10T03:00:00", "2026-10-10T04:00:00"),
    ),
    (
        ("2026-10-09T12:00:00", "2026-10-09T13:00:00"),
        ("2026-10-09T12:00:00", "2026-10-09T13:00:00"),
        ("2026-10-09T14:00:00", "2026-10-09T15:00:00"),
        ("2026-10-09T14:00:00", "2026-10-09T15:00:00"),
    ),
]


async def verify_instants(session, entity_spec, instants, user_id):
    kind, model, fields, bootstrap_key = entity_spec
    create_input, create_utc, update_input, update_utc = instants
    entity_id = f"ts-{uuid.uuid4().hex}"
    create_payload = {"title": "Timestamp regression", "predicate": "sync_instant", "value": "expected"}
    create_payload.update(dict(zip(fields, create_input)))
    create = SyncPushRequest(operations=[{
        "operation_id": f"create-{uuid.uuid4().hex}", "operation_epoch": "timestamp-test",
        "entity_type": kind, "entity_id": entity_id, "action": "create",
        "base_version": 0, "payload": create_payload,
    }])
    first = await sync_service.push_operations(session, user_id, None, create)
    assert first.results[0].status == "applied"
    starting_seq = first.commit_seq

    async def check_storage(values, version):
        entity = await session.scalar(select(model).where(model.id == entity_id, model.user_id == user_id))
        await session.refresh(entity)
        assert entity.version == version
        for field, expected in zip(fields, values):
            stored = getattr(entity, field)
            assert stored == datetime.fromisoformat(expected)
            assert stored.tzinfo is None
        bootstrap = await sync_service.get_bootstrap(session, user_id)
        row = next(row for row in getattr(bootstrap, bootstrap_key) if row["id"] == entity_id)
        for field, expected in zip(fields, values):
            assert row[field] == expected

    await check_storage(create_utc, 1)

    update_payload = dict(zip(fields, update_input))
    update = SyncPushRequest(operations=[{
        "operation_id": f"update-{uuid.uuid4().hex}", "operation_epoch": "timestamp-test",
        "entity_type": kind, "entity_id": entity_id, "action": "update",
        "base_version": 1, "payload": update_payload,
    }])
    updated = await sync_service.push_operations(session, user_id, None, update)
    assert updated.results[0].status == "applied"
    assert updated.commit_seq == starting_seq + 1
    await check_storage(update_utc, 2)

    # Replaying the exact commands remains a duplicate even after later edits.
    for request, original_payload in ((create, create_payload), (update, update_payload)):
        op = request.operations[0]
        assert op.payload == original_payload
        receipt = await session.scalar(select(OperationReceipt).where(
            OperationReceipt.operation_id == op.operation_id,
            OperationReceipt.user_id == user_id,
        ))
        assert receipt.canonical_hash == op.get_canonical_hash()
        replayed = await sync_service.push_operations(session, user_id, None, request)
        assert replayed.results[0].status == "duplicate"
        assert replayed.commit_seq == starting_seq + 1

    # The change log preserves the original offset representation for clients.
    changes = await sync_service.pull_changes(session, user_id, starting_seq - 1)
    assert [change.payload for change in changes.changes] == [create_payload, update_payload]

    # Equivalent instants with different command bytes must still conflict.
    reformatted = update.model_copy(deep=True)
    reformatted.operations[0].payload[fields[0]] = update_utc[0] + "+00:00"
    assert reformatted.operations[0].get_canonical_hash() != update.operations[0].get_canonical_hash()
    conflicted = await sync_service.push_operations(session, user_id, None, reformatted)
    assert conflicted.results[0].status == "conflict"
    assert conflicted.commit_seq == starting_seq + 1
    await check_storage(update_utc, 2)


@pytest.mark.asyncio
@pytest.mark.parametrize("entity_spec", ENTITIES, ids=[item[0] for item in ENTITIES])
@pytest.mark.parametrize("instants", INSTANTS, ids=["negative-offset", "half-hour-offset", "zulu", "legacy-naive"])
async def test_sync_instants_create_update_and_replay(db_session, entity_spec, instants):
    await verify_instants(db_session, entity_spec, instants, "sync-timestamp-owner")


@pytest.mark.asyncio
@pytest.mark.parametrize("entity_spec", ENTITIES, ids=[item[0] for item in ENTITIES])
async def test_sync_optional_instants_can_be_cleared(db_session, entity_spec):
    kind, model, fields, _ = entity_spec
    await verify_instants(db_session, entity_spec, INSTANTS[0], "sync-timestamp-owner")
    entity = await db_session.scalar(select(model).where(model.user_id == "sync-timestamp-owner"))
    optional_fields = fields[1:] if kind == "event" else fields
    cleared = await sync_service.push_operations(db_session, "sync-timestamp-owner", None, SyncPushRequest(operations=[{
        "operation_id": f"clear-{uuid.uuid4().hex}", "operation_epoch": "timestamp-test",
        "entity_type": kind, "entity_id": entity.id, "action": "update",
        "base_version": 2, "payload": dict.fromkeys(optional_fields),
    }]))
    assert cleared.results[0].status == "applied"
    await db_session.refresh(entity)
    assert all(getattr(entity, field) is None for field in optional_fields)


@pytest.mark.asyncio
@pytest.mark.skipif(not os.getenv("TEST_PG_URL"), reason="TEST_PG_URL not provided")
async def test_sync_instants_live_postgres():
    """Exercises the actual asyncpg TIMESTAMP WITHOUT TIME ZONE boundary."""
    engine = create_async_engine(os.environ["TEST_PG_URL"], echo=False)
    user_id = f"sync-ts-{uuid.uuid4().hex}"
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as session:
            try:
                for entity_spec in ENTITIES:
                    for instants in INSTANTS:
                        await verify_instants(session, entity_spec, instants, user_id)
            finally:
                await session.rollback()
                for model in (ChangeBatch, OperationReceipt, Event, Task, Memory, SyncHead):
                    await session.execute(delete(model).where(model.user_id == user_id))
                await session.commit()
    finally:
        await engine.dispose()
