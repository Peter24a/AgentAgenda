import asyncio
from copy import deepcopy
from datetime import date, datetime
import json
import sys

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.importing import schedule as schedule_module
from app.importing.schedule import apply_schedule, prepare_events, reconcile_schedule
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


def dated_plan(*days, collection='synthetic-study', start='19:00', end='21:00'):
    schedule = plan()
    template = schedule['dated_events'][0]
    schedule['collection'] = collection
    schedule['dated_events'] = [dict(template, id=day, date=day,
        iso_weekday=date.fromisoformat(day).isoweekday(), start_time=start, end_time=end)
        for day in days]
    return schedule


async def snapshot(session):
    session.expire_all()
    events = list((await session.execute(select(Event).order_by(Event.id))).scalars())
    heads = list((await session.execute(select(SyncHead).order_by(SyncHead.user_id))).scalars())
    changes = list((await session.execute(select(ChangeBatch).order_by(ChangeBatch.commit_seq))).scalars())
    return {
        'events': [tuple(getattr(event, column.name) for column in Event.__table__.columns)
                   for event in events],
        'heads': [tuple(getattr(head, column.name) for column in SyncHead.__table__.columns)
                  for head in heads],
        'changes': [tuple(getattr(change, column.name) for column in ChangeBatch.__table__.columns)
                    for change in changes],
    }


@pytest.mark.asyncio
async def test_reconcile_future_preview_apply_and_replay_preserve_history(test_engine, db_session):
    old = dated_plan('2026-09-14', '2026-09-15', '2026-09-16')
    new = dated_plan('2026-09-14', '2026-09-15', '2026-09-16',
                     collection='synthetic-corrected', start='20:00', end='22:00')
    await apply_schedule(old, 'owner', not_before='2026-09-14')
    before = await snapshot(db_session)
    preview = await reconcile_schedule(old, new, 'owner', cutoff='2026-09-15', dry_run=True)
    assert preview['retired'] == preview['created'] == 2
    assert preview['old_skipped_past'] == preview['skipped_past'] == 1
    assert preview['commit_seq'] is None
    assert await snapshot(db_session) == before
    report = await reconcile_schedule(old, new, 'owner', cutoff='2026-09-15')
    assert report['retired_event_ids'] == preview['retired_event_ids']
    assert report['created_event_ids'] == preview['created_event_ids']
    assert report['old_plan_fingerprint'] == preview['old_plan_fingerprint']
    assert report['commit_seq'] == 7
    _, prepared_old = prepare_events(old, 'owner')
    for expected in prepared_old:
        event = await db_session.get(Event, expected['id'], populate_existing=True)
        assert event.is_deleted == (expected['local_date'] >= date(2026, 9, 15))
        assert event.version == (2 if event.is_deleted else 1)
        assert event.title == expected['title']
    changes = list((await db_session.execute(select(ChangeBatch).order_by(ChangeBatch.commit_seq))).scalars())
    assert [change.commit_seq for change in changes] == list(range(1, 8))
    tombstones = [change for change in changes if change.change_type == 'delete']
    assert len(tombstones) == 2
    assert all(change.entity_version == 2 and change.payload_json['is_deleted']
               and change.payload_json['version'] == 2 for change in tombstones)
    assert all(change.payload_json['start_time'].endswith('Z') for change in tombstones)
    after = await snapshot(db_session)
    replay = await reconcile_schedule(old, new, 'owner', cutoff=date(2026, 9, 15))
    assert replay['created'] == replay['retired'] == 0
    assert replay['old_already_deleted'] == replay['unchanged'] == 2
    assert replay['commit_seq'] is None
    assert await snapshot(db_session) == after


@pytest.mark.asyncio
@pytest.mark.parametrize('field,value', [
    ('title', 'Manual title'), ('description', 'Manual notes'),
    ('start_time', datetime(2026, 9, 16, 1, 30)),
    ('end_time', datetime(2026, 9, 16, 2, 30)),
    ('timezone', 'UTC'), ('category', 'work'),
    ('version', 2), ('is_completed', True), ('is_deleted', True),
])
async def test_reconcile_preserves_every_manual_field_completed_and_deleted(
        test_engine, db_session, field, value):
    old = plan()
    new = deepcopy(old)
    new['collection'] = 'synthetic-corrected'
    await apply_schedule(old, 'owner', not_before='2026-09-15')
    event = (await db_session.execute(select(Event))).scalar_one()
    setattr(event, field, value)
    await db_session.commit()
    report = await reconcile_schedule(old, new, 'owner', cutoff='2026-09-15')
    await db_session.refresh(event)
    assert getattr(event, field) == value
    assert report['retired'] == 0
    if field == 'is_deleted':
        assert report['old_already_deleted'] == 1
    else:
        assert report['preserved_old'] == report['skipped_conflict'] == 1
        assert report['created'] == 0


@pytest.mark.asyncio
async def test_reconcile_never_replaces_shared_ids_or_restores_deleted_new_ids(test_engine, db_session):
    old = plan()
    await apply_schedule(old, 'owner', not_before='2026-09-15')
    new = deepcopy(old)
    new['dated_events'][0]['title'] = 'Changed in new plan'
    before = await snapshot(db_session)
    report = await reconcile_schedule(old, new, 'owner', cutoff='2026-09-15')
    assert report['retired'] == report['created'] == 0
    assert report['preserved_existing'] == 1
    assert len(report['retained_shared_ids']) == 1
    assert await snapshot(db_session) == before
    event = (await db_session.execute(select(Event))).scalar_one()
    event.is_deleted = True
    event.version = 2
    await db_session.commit()
    before = await snapshot(db_session)
    report = await reconcile_schedule(old, new, 'owner', cutoff='2026-09-15')
    assert report['deleted_not_restored'] == 1
    assert await snapshot(db_session) == before


@pytest.mark.asyncio
async def test_reconcile_scopes_retirement_to_exact_old_plan_and_respects_manual_conflicts(test_engine, db_session):
    old = dated_plan('2026-09-15')
    unrelated = dated_plan('2026-09-17', collection='another-import')
    new = dated_plan('2026-09-15', collection='synthetic-corrected', start='20:00', end='22:00')
    await apply_schedule(old, 'owner', not_before='2026-09-15')
    await apply_schedule(unrelated, 'owner', not_before='2026-09-15')
    await apply_schedule(old, 'other-owner', not_before='2026-09-15')
    db_session.add(Event(id='manual-commitment', user_id='owner', title='Manual commitment',
        start_time=datetime(2026, 9, 16, 3), end_time=datetime(2026, 9, 16, 4)))
    await db_session.commit()
    report = await reconcile_schedule(old, new, 'owner', cutoff='2026-09-15')
    assert report['retired'] == report['skipped_conflict'] == 1
    assert report['created'] == 0
    assert 'Manual commitment' not in str(report)
    preserved_ids = [prepare_events(unrelated, 'owner')[1][0]['id'],
                     prepare_events(old, 'other-owner')[1][0]['id'], 'manual-commitment']
    for event_id in preserved_ids:
        assert not (await db_session.get(Event, event_id, populate_existing=True)).is_deleted


@pytest.mark.asyncio
async def test_reconcile_mismatching_old_plan_cannot_retire_its_ids(test_engine, db_session):
    old = plan()
    await apply_schedule(old, 'owner', not_before='2026-09-15')
    claimed_old = deepcopy(old)
    claimed_old['dated_events'][0]['description'] = 'Different source fingerprint'
    new = deepcopy(old)
    new['collection'] = 'synthetic-corrected'
    before = await snapshot(db_session)
    result = await reconcile_schedule(claimed_old, new, 'owner', cutoff='2026-09-15')
    assert result['preserved_old'] == result['skipped_conflict'] == 1
    assert result['created'] == result['retired'] == 0
    assert await snapshot(db_session) == before


@pytest.mark.asyncio
async def test_reconcile_failure_rolls_back_retirement_additions_and_sync(test_engine, db_session, monkeypatch):
    old = plan()
    new = deepcopy(old)
    new['collection'] = 'synthetic-corrected'
    await apply_schedule(old, 'owner', not_before='2026-09-15')
    before = await snapshot(db_session)
    original_flush = AsyncSession.flush

    async def fail_after_flush(session, *args, **kwargs):
        await original_flush(session, *args, **kwargs)
        if any(isinstance(item, Event) and item.is_deleted for item in session.identity_map.values()):
            raise RuntimeError('Synthetic failure after retirement and insertion')

    monkeypatch.setattr(AsyncSession, 'flush', fail_after_flush)
    with pytest.raises(RuntimeError):
        await reconcile_schedule(old, new, 'owner', cutoff='2026-09-15')
    assert await snapshot(db_session) == before


@pytest.mark.asyncio
async def test_concurrent_reconcile_is_serialized_and_idempotent(test_engine, db_session):
    old = plan()
    new = deepcopy(old)
    new['collection'] = 'synthetic-corrected'
    await apply_schedule(old, 'owner', not_before='2026-09-15')
    reports = await asyncio.gather(*[
        reconcile_schedule(old, new, 'owner', cutoff='2026-09-15') for _ in range(2)])
    assert sum(report['created'] for report in reports) == 1
    assert sum(report['retired'] for report in reports) == 1
    assert await count(db_session, ChangeBatch) == 3
    assert (await db_session.get(SyncHead, 'owner')).current_seq == 3


@pytest.mark.asyncio
async def test_conditional_windows_require_explicit_boolean_confirmation(test_engine, db_session):
    conditional = plan()
    conditional['dated_events'][0]['condition'] = 'Only if the synthetic exercise is approved'
    assert prepare_events(conditional, 'owner')[1] == []
    result = await apply_schedule(conditional, 'owner', not_before='2026-09-15')
    assert result['created'] == 0
    assert await count(db_session, Event) == await count(db_session, SyncHead) == 0
    conditional['dated_events'][0]['condition_confirmed'] = 'true'
    with pytest.raises(ValueError, match='boolean'):
        prepare_events(conditional, 'owner')
    conditional['dated_events'][0]['condition_confirmed'] = True
    assert len(prepare_events(conditional, 'owner')[1]) == 1
    await apply_schedule(conditional, 'owner', not_before='2026-09-15')
    unconfirmed = deepcopy(conditional)
    unconfirmed['dated_events'][0]['condition_confirmed'] = False
    result = await reconcile_schedule(conditional, unconfirmed, 'owner', cutoff='2026-09-15')
    assert result['created'] == result['retired'] == 0
    assert len(result['retained_shared_ids']) == 1


@pytest.mark.parametrize('command', ['preview', 'apply', 'reconcile-preview', 'reconcile-apply'])
def test_schedule_cli_dispatches_explicit_plans_and_cutoff(command, tmp_path, monkeypatch, capsys):
    old = plan()
    new = deepcopy(old)
    new['collection'] = 'synthetic-corrected'
    old_path, new_path = tmp_path / 'old.json', tmp_path / 'new.json'
    old_path.write_text(json.dumps(old))
    new_path.write_text(json.dumps(new))
    calls = []

    async def capture(*args, **kwargs):
        calls.append((args, kwargs))
        return {'created': 0}

    monkeypatch.setattr(schedule_module, 'reconcile_schedule', capture)
    monkeypatch.setattr(schedule_module, 'apply_schedule', capture)
    reconciling = command.startswith('reconcile-')
    argv = ['schedule', command, str(old_path)]
    if reconciling:
        argv.append(str(new_path))
    argv.extend(['--user-id', 'owner', '--cutoff', '2026-09-15'])
    monkeypatch.setattr(sys, 'argv', argv)
    schedule_module.main()
    args, kwargs = calls[0]
    assert args == ((old, new, 'owner') if reconciling else (old, 'owner'))
    assert kwargs == {'cutoff' if reconciling else 'not_before': '2026-09-15',
                      'dry_run': command.endswith('preview')}
    assert json.loads(capsys.readouterr().out) == {'created': 0}
