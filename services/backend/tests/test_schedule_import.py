from datetime import datetime

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.importing.schedule import apply_schedule, prepare_events
from app.models.canonical import ChangeBatch, Event, SyncHead


def plan():
    return {'schema_version': 1, 'timezone': 'America/Mexico_City', 'collection': 'synthetic-study',
            'dated_events': [{'id': 'day-1', 'date': '2026-09-15', 'iso_weekday': 2,
                'start_time': '19:00', 'end_time': '21:00', 'duration_minutes': 120,
                'title': 'Synthetic study', 'category': 'study', 'description': 'Synthetic exercises only.',
                'source_path': 'PersonalLLM/STUDY.md', 'source_updated': '2026-08-31'}]}


async def count(session, model):
    return await session.scalar(select(func.count()).select_from(model))


@pytest.mark.asyncio
async def test_schedule_utc_sync_replay_and_manual_edits_are_preserved(test_engine, db_session):
    schedule = plan()
    preview = await apply_schedule(schedule, 'owner', not_before='2026-09-15', dry_run=True)
    assert preview['created'] == 1
    assert await count(db_session, Event) == await count(db_session, SyncHead) == 0
    first = await apply_schedule(schedule, 'owner', not_before='2026-09-15')
    assert first['created'] == 1 and first['commit_seq'] == 1
    event = (await db_session.execute(select(Event))).scalar_one()
    change = (await db_session.execute(select(ChangeBatch))).scalar_one()
    assert event.start_time == datetime(2026, 9, 16, 1)
    assert event.end_time == datetime(2026, 9, 16, 3)
    assert 'Horario provisional' in event.description and 'Fuente: STUDY.md' in event.description
    assert '[AgentAgenda schedule source]' not in event.description
    assert change.payload_json['start_time'] == '2026-09-16T01:00:00Z'
    replay = await apply_schedule(schedule, 'owner', not_before='2026-09-15')
    assert replay['unchanged'] == 1 and replay['created'] == 0
    event.title = 'Manually adjusted'
    event.start_time = datetime(2026, 9, 16, 2)
    event.is_completed = True
    event.version = 2
    await db_session.commit()
    replay = await apply_schedule(schedule, 'owner', not_before='2026-09-15')
    assert replay['preserved_existing'] == 1
    await db_session.refresh(event)
    assert event.title == 'Manually adjusted' and event.is_completed and event.version == 2
    event.is_deleted = True
    await db_session.commit()
    replay = await apply_schedule(schedule, 'owner', not_before='2026-09-15')
    assert replay['deleted_not_restored'] == 1
    assert await count(db_session, Event) == await count(db_session, ChangeBatch) == 1


@pytest.mark.asyncio
async def test_schedule_preserves_conflicting_commitments_and_ignores_other_owners(test_engine, db_session):
    schedule = plan()
    db_session.add(Event(id='existing-food', user_id='owner', title='Existing meal', category='food',
                         start_time=datetime(2026, 9, 16, 2), end_time=datetime(2026, 9, 16, 2, 30)))
    await db_session.commit()
    result = await apply_schedule(schedule, 'owner', not_before='2026-09-15')
    assert result['created'] == 0 and result['skipped_conflict'] == 1
    assert 'Synthetic' not in str(result) and 'Existing meal' not in str(result)
    other = await apply_schedule(schedule, 'other-owner', not_before='2026-09-15')
    assert other['created'] == 1


@pytest.mark.asyncio
async def test_schedule_failure_rolls_back_events_changes_and_sync_head(test_engine, db_session, monkeypatch):
    original_flush = AsyncSession.flush
    async def fail_flush(session, *args, **kwargs):
        await original_flush(session, *args, **kwargs)
        if any(isinstance(item, Event) for item in session.identity_map.values()):
            raise RuntimeError('Synthetic transaction failure')
    monkeypatch.setattr(AsyncSession, 'flush', fail_flush)
    with pytest.raises(RuntimeError):
        await apply_schedule(plan(), 'owner', not_before='2026-09-15')
    assert await count(db_session, Event) == 0
    assert await count(db_session, ChangeBatch) == 0
    assert await count(db_session, SyncHead) == 0


def test_schedule_validates_durations_and_rejects_ambiguous_time_before_writes():
    schedule = plan()
    schedule['dated_events'][0]['duration_minutes'] = 60
    with pytest.raises(ValueError, match='duration'):
        prepare_events(schedule, 'owner')
    schedule = plan()
    schedule['timezone'] = 'America/New_York'
    schedule['dated_events'][0].update(date='2026-11-01', iso_weekday=7, start_time='01:00', end_time='03:00')
    with pytest.raises(ValueError, match='Ambiguous'):
        prepare_events(schedule, 'owner')
