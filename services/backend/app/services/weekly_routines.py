"""Materialize rolling weekly routines while preserving edited/deleted occurrences."""
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from sqlalchemy import select
from app.db.session import get_db_context
from app.models.canonical import WeeklyRoutine
from app.importing.schedule import (
    prepare_events, _schedule_transaction, _plan_additions, _record_change,
)

HORIZON_DAYS = 28


def expand_routine(routine, start, end):
    zone = ZoneInfo(routine.timezone)
    start = max(start, date.fromisoformat(routine.starts_on))
    if routine.ends_on:
        end = min(end, date.fromisoformat(routine.ends_on))
    if (end - start).days > 366:
        raise ValueError('Routine expansion exceeds one year')
    rows, ids = [], set()
    templates = routine.template_json
    if not isinstance(templates, list) or not 0 < len(templates) <= 150:
        raise ValueError('Invalid weekly template')
    for row in templates:
        if not isinstance(row, dict) or not isinstance(row.get('id'), str) or row['id'] in ids:
            raise ValueError('Weekly template ids must be unique')
        ids.add(row['id'])
        if type(row.get('iso_weekday')) is not int or not 1 <= row['iso_weekday'] <= 7:
            raise ValueError('Invalid weekly day')
    day = start
    while day <= end:
        for template in templates:
            if template['iso_weekday'] != day.isoweekday():
                continue
            if template.get('until') and day > date.fromisoformat(template['until']):
                continue
            if template.get('from') and day < date.fromisoformat(template['from']):
                continue
            rows.append({**template, 'id': day.isoformat()+':'+template['id'], 'date': day.isoformat()})
        day += timedelta(days=1)
    plan = {'schema_version': 1, 'timezone': zone.key,
            'collection': f'weekly:{routine.id}:g{routine.generation}', 'dated_events': rows}
    if rows:
        _, prepared = prepare_events(plan, routine.user_id)
        for left, right in zip(prepared, prepared[1:]):
            if left['end_time'] > right['start_time']:
                raise ValueError('Weekly routine contains overlapping blocks')
    return plan


def _report():
    return dict(created=0, unchanged=0, preserved_existing=0, deleted_not_restored=0,
                skipped_past=0, skipped_conflict=0, conflict_event_ids=[])


async def materialize_routine(routine_id, user_id, *, now=None):
    instant = now or datetime.now(timezone.utc)
    async with _schedule_transaction(user_id, False, persist_metadata=True) as (session, head, existing, clock):
        routine = await session.get(WeeklyRoutine, routine_id)
        if not routine or routine.user_id != user_id or not routine.enabled:
            return {'created': 0}
        today = instant.astimezone(ZoneInfo(routine.timezone)).date()
        through = today + timedelta(days=HORIZON_DAYS - 1)
        plan = expand_routine(routine, today, through)
        report = _report()
        if plan['dated_events']:
            _, prepared = prepare_events(plan, user_id)
            for event in _plan_additions(prepared, existing, user_id, today, clock, report):
                session.add(event)
                _record_change(session, head, event, 'create', clock)
        routine.materialized_through = through.isoformat()
        routine.last_materialized_at = clock
        routine.updated_at = clock
        return report


async def set_routine_enabled(routine_id, user_id, enabled, *, now=None):
    # This switch controls future materialization, preserving the calendar.
    # In particular, enabling never revives a user's deleted occurrence.
    async with _schedule_transaction(user_id, False, persist_metadata=True) as (session, head, existing, clock):
        routine = await session.get(WeeklyRoutine, routine_id)
        if not routine or routine.user_id != user_id:
            return None
        routine.enabled = enabled
        routine.updated_at = clock
    if enabled:
        await materialize_routine(routine_id, user_id, now=now)
    return {'enabled': enabled, 'existing_events_preserved': True}


async def maintain_weekly_routines(*, now=None):
    instant = now or datetime.now(timezone.utc)
    async with get_db_context() as session:
        rows = (await session.scalars(select(WeeklyRoutine).where(WeeklyRoutine.enabled.is_(True)))).all()
        due = [(r.id, r.user_id) for r in rows if not r.materialized_through or
               date.fromisoformat(r.materialized_through) < instant.astimezone(ZoneInfo(r.timezone)).date()+timedelta(days=HORIZON_DAYS-1)]
    for routine_id, user_id in due:
        await materialize_routine(routine_id, user_id, now=instant)
    return len(due)
