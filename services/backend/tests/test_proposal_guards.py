from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.models.agenda import AgendaItemModel
from app.models.canonical import Event, Proposal, WeeklyRoutine, ChangeBatch
from app.models.proposal import AgentProposalModel, WeeklyRoutineProposal
from app.services.proposal_service import proposal_service
from app.services.weekly_routines import materialize_routine

USER = "proposal-guard-owner"
NOW = datetime(2027, 1, 4, 6, tzinfo=timezone.utc)  # Monday local midnight


def item(id, title="Reunión de equipo", start="2027-01-04T10:00:00", end="2027-01-04T11:00:00", **extra):
    return AgendaItemModel(id=id, title=title, start_time=start, end_time=end, **extra)


def proposal(id, items=None, **extra):
    return AgentProposalModel(id=id, summary="Propuesta de prueba", reason="Petición explícita", resulting_items=items or [], created_at=NOW, **extra)


async def confirm(session, model):
    await proposal_service.save_proposal(session, USER, model)
    return await proposal_service.confirm_proposal(session, USER, model.id)


async def events(session):
    return list((await session.scalars(select(Event).where(Event.user_id == USER, Event.is_deleted.is_(False)))).all())


@pytest.mark.asyncio
async def test_independent_duplicate_preserves_existing_metadata_and_no_new_sync_change(db_session):
    first = proposal("dup-1", [item("event-first", description="Original", category="work")])
    await confirm(db_session, first)
    original = (await events(db_session))[0]
    count_before = len((await db_session.scalars(select(ChangeBatch))).all())
    second = proposal("dup-2", [item("event-second", title="  reunion   DE EQUIPO  ", description="Do not overwrite", category="general")])
    result = await confirm(db_session, second)
    assert result.success and "duplicado" in result.message
    rows = await events(db_session)
    assert len(rows) == 1 and rows[0].id == "event-first"
    assert rows[0].description == "Original" and rows[0].category == "work"
    assert len((await db_session.scalars(select(ChangeBatch))).all()) == count_before
    repeated = await proposal_service.confirm_proposal(db_session, USER, second.id)
    assert not repeated.success and repeated.status.value == "accepted"
    await proposal_service.reject_proposal(db_session, USER, second.id)
    await proposal_service.save_proposal(db_session, USER, second)
    assert (await db_session.get(Proposal, second.id)).status == "accepted"
    assert rows[0].version == 1


@pytest.mark.asyncio
async def test_conflict_is_atomic_and_keeps_pending_proposal(db_session):
    await confirm(db_session, proposal("base", [item("busy")]))
    next_proposal = proposal("conflicting", [
        item("free", title="Free", start="2027-01-04T08:00:00", end="2027-01-04T09:00:00"),
        item("collision", title="Other", start="2027-01-04T10:30:00", end="2027-01-04T11:30:00"),
    ])
    with pytest.raises(ValueError, match="se cruza"):
        await proposal_service.validate_proposal(db_session, USER, next_proposal)
    await proposal_service.save_proposal(db_session, USER, next_proposal)
    with pytest.raises(ValueError, match="Reunión de equipo"):
        await proposal_service.confirm_proposal(db_session, USER, next_proposal.id)
    await db_session.rollback()
    assert [row.id for row in await events(db_session)] == ["busy"]
    assert (await db_session.get(Proposal, next_proposal.id)).status == "pending"


@pytest.mark.asyncio
async def test_moving_self_adjacent_and_separate_same_title_allowed(db_session):
    await confirm(db_session, proposal("first", [item("moving")]))
    await confirm(db_session, proposal("move", [item("moving", start="2027-01-04T10:30:00", end="2027-01-04T11:30:00")]))
    await confirm(db_session, proposal("adjacent", [item("separate", start="2027-01-04T11:30:00", end="2027-01-04T12:30:00")]))
    rows = await events(db_session)
    assert len(rows) == 2
    moved = next(row for row in rows if row.id == "moving")
    assert moved.version == 2 and moved.start_time == datetime(2027, 1, 4, 16, 30)


@pytest.mark.asyncio
async def test_intra_batch_duplicate_and_conflict(db_session):
    await confirm(db_session, proposal("same-batch", [item("first"), item("second")]))
    assert len(await events(db_session)) == 1
    conflicting = proposal("batch-overlap", [
        item("one", title="One", start="2027-01-05T09:00:00", end="2027-01-05T10:00:00"),
        item("two", title="Two", start="2027-01-05T09:30:00", end="2027-01-05T10:30:00"),
    ])
    with pytest.raises(ValueError, match="se cruza"):
        await proposal_service.validate_proposal(db_session, USER, conflicting)
    assert len(await events(db_session)) == 1


def routine(**extra):
    values = dict(title="Leer novela", starts_on="2027-01-04", ends_on=None, iso_weekdays=[1, 3, 5],
                  start_time="14:00", end_time="14:30", category="leisure", timezone="America/Mexico_City")
    values.update(extra)
    return WeeklyRoutineProposal(**values)


@pytest.mark.asyncio
@pytest.mark.parametrize("ends_on, expected", [(None, 12), ("2027-01-15", 6)])
async def test_weekly_routine_only_after_confirm_stable_occurrences_and_retries(db_session, ends_on, expected):
    model = proposal_service.prepare_recurring_proposal(USER, proposal("routine-one"), routine(ends_on=ends_on), now=NOW)
    assert len(model.resulting_items) == expected
    assert model.resulting_items[0].start_time.isoformat() == "2027-01-04T14:00:00-06:00"
    await proposal_service.save_proposal(db_session, USER, model)
    assert not await events(db_session)
    assert not (await db_session.scalars(select(WeeklyRoutine))).all()
    result = await proposal_service.confirm_proposal(db_session, USER, model.id)
    assert result.success
    rows = await events(db_session)
    assert {row.id for row in rows} == {row.id for row in model.resulting_items}
    series = (await db_session.scalars(select(WeeklyRoutine))).one()
    assert series.ends_on == ends_on
    await db_session.commit()
    # Rolling maintenance uses exactly the same IDs as the confirmed preview.
    await materialize_routine(series.id, USER, now=NOW)
    assert len(await events(db_session)) == expected
    repeat = proposal_service.prepare_recurring_proposal(USER, proposal("routine-two"), routine(ends_on=ends_on))
    assert (await confirm(db_session, repeat)).success
    assert len((await db_session.scalars(select(WeeklyRoutine))).all()) == 1
    assert len(await events(db_session)) == expected
    await proposal_service.confirm_proposal(db_session, USER, repeat.id)
    assert len(await events(db_session)) == expected


@pytest.mark.asyncio
async def test_repeated_routine_preserves_deleted_and_edited_occurrences(db_session):
    model = proposal_service.prepare_recurring_proposal(USER, proposal("routine-one"), routine())
    await confirm(db_session, model)
    rows = await events(db_session)
    removed, edited = rows[:2]
    removed.is_deleted = True
    edited.title = "Título editado por su propietario"
    edited.version = 2
    await db_session.commit()
    await confirm(db_session, proposal("routine-again", routine=routine(description="Different description")))
    assert (await db_session.get(Event, removed.id)).is_deleted
    assert (await db_session.get(Event, edited.id)).title == "Título editado por su propietario"
    assert len(await events(db_session)) == 11


@pytest.mark.asyncio
async def test_new_routine_conflict_does_not_persist_series_or_partial_dates(db_session):
    await confirm(db_session, proposal("existing", [item("busy", title="Compromiso", start="2027-01-08T14:00:00", end="2027-01-08T15:00:00")]))
    model = proposal("routine-conflicting", routine=routine())
    await proposal_service.save_proposal(db_session, USER, model)
    with pytest.raises(ValueError, match="Compromiso"):
        await proposal_service.confirm_proposal(db_session, USER, model.id)
    await db_session.rollback()
    assert len(await events(db_session)) == 1
    assert not (await db_session.scalars(select(WeeklyRoutine))).all()


@pytest.mark.asyncio
async def test_overlapping_routine_period_requires_clarification(db_session):
    await confirm(db_session, proposal("existing-routine", routine=routine()))
    model = proposal("another-routine", routine=routine(starts_on="2027-01-11"))
    with pytest.raises(ValueError, match="rutina igual"):
        await proposal_service.validate_proposal(db_session, USER, model)


@pytest.mark.asyncio
async def test_weekly_maintenance_extends_indefinite_and_stops_at_finite_end(db_session):
    model = proposal("long-routine", routine=routine(ends_on="2027-02-05"))
    await confirm(db_session, model)
    series = (await db_session.scalars(select(WeeklyRoutine))).one()
    assert len(await events(db_session)) == 12
    first = (await events(db_session))[0]
    first.is_deleted = True
    await db_session.commit()
    await materialize_routine(series.id, USER, now=NOW + timedelta(days=14))
    rows = await events(db_session)
    assert len(rows) == 14  # 15 occurrences in five weeks, one explicitly deleted
    assert all(row.start_time <= datetime(2027, 2, 5, 20) for row in rows)
    assert (await db_session.get(Event, first.id)).is_deleted
    await db_session.commit()
    await materialize_routine(series.id, USER, now=NOW + timedelta(days=60))
    assert len(await events(db_session)) == 14


@pytest.mark.asyncio
async def test_routine_parent_is_flushed_before_context_with_foreign_keys_enabled(db_session):
    from sqlalchemy import text
    from app.models.canonical import ProposalContext
    await db_session.execute(text("PRAGMA foreign_keys=ON"))
    assert await db_session.scalar(text("PRAGMA foreign_keys")) == 1
    model = proposal("fk-routine", routine=routine())
    await proposal_service.save_proposal(db_session, USER, model)
    context = await db_session.get(ProposalContext, model.id)
    assert context is not None and context.payload["routine"]["title"] == "Leer novela"
    assert (await proposal_service.confirm_proposal(db_session, USER, model.id)).success


@pytest.mark.asyncio
async def test_delete_requires_new_review_if_other_device_moved_target(db_session):
    original = item("moved-after-preview")
    await confirm(db_session, proposal("create-before-delete", [original]))
    pending = proposal("pending-delete", [original.model_copy(update={"action": "delete"})])
    await proposal_service.save_proposal(db_session, USER, pending)
    await confirm(db_session, proposal("other-device-moved", [original.model_copy(update={
        "start_time": datetime(2027, 1, 4, 12), "end_time": datetime(2027, 1, 4, 13),
    })]))
    with pytest.raises(ValueError, match="cambió desde"):
        await proposal_service.confirm_proposal(db_session, USER, pending.id)
    await db_session.rollback()
    event = await db_session.get(Event, original.id)
    assert not event.is_deleted and event.start_time == datetime(2027, 1, 4, 18)
    assert (await db_session.get(Proposal, pending.id)).status == "pending"
