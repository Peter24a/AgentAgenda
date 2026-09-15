"""Import an explicitly authorized private schedule without replacing existing events.

Input uses schema_version=1, timezone, and dated_events. Each event has a stable
id, date, start_time/end_time (HH:MM), title, category, and optional provenance.
Clock times are local to the named timezone. No document instructions execute.
Reconciliation retires only pristine events from the explicitly supplied old
plan, on or after the activation date. Shared IDs are never replaced in place.
"""
import argparse
import asyncio
from contextlib import asynccontextmanager
from datetime import date, datetime, time, timedelta, timezone
import hashlib
import json
from pathlib import Path
import re
from weakref import WeakKeyDictionary
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select, text

from app.db.session import get_db_context
from app.models.canonical import ChangeBatch, Event, SyncHead

CATEGORIES = {'sleep', 'work', 'food', 'exercise', 'study', 'leisure', 'general'}
MAX_EVENTS = 1000
EVENT_FIELDS = ('title', 'description', 'start_time', 'end_time', 'timezone', 'category')
# StaticPool-backed SQLite tests can share a connection across sessions. SQLite's
# BEGIN IMMEDIATE handles separate connections/processes; this guards that case.
_SQLITE_LOCKS = WeakKeyDictionary()


def _stable_id(prefix, *parts):
    return prefix + hashlib.sha256('\0'.join(parts).encode()).hexdigest()[:48]


def _clock(value):
    if not isinstance(value, str) or not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d', value):
        raise ValueError('Schedule times must use HH:MM')
    return time.fromisoformat(value)


def _local_to_utc(day, clock, tz):
    local = datetime.combine(day, clock)
    candidates = {local.replace(tzinfo=tz, fold=fold).astimezone(timezone.utc) for fold in (0, 1)}
    valid = [candidate for candidate in candidates if candidate.astimezone(tz).replace(tzinfo=None) == local]
    if len(valid) != 1:
        raise ValueError('Ambiguous or nonexistent local schedule time')
    return valid[0].replace(tzinfo=None)


def prepare_events(plan, user_id):
    """Validate the entire private input before opening a database transaction."""
    if not isinstance(plan, dict) or plan.get('schema_version') != 1:
        raise ValueError('Unsupported schedule schema')
    if not isinstance(user_id, str) or not 0 < len(user_id) <= 64:
        raise ValueError('Invalid schedule owner')
    collection = plan.get('collection', 'personal-study-2026')
    if not isinstance(collection, str) or not 0 < len(collection) <= 128:
        raise ValueError('Invalid schedule collection')
    rows = plan.get('dated_events')
    if not isinstance(rows, list) or not 0 < len(rows) <= MAX_EVENTS:
        raise ValueError('Schedule must contain between 1 and 1000 dated events')
    prepared, seen = [], set()
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError('Invalid schedule event')
        source_id = row.get('id')
        if not isinstance(source_id, str) or not source_id or len(source_id) > 256 or source_id in seen:
            raise ValueError('Schedule event ids must be unique and stable')
        seen.add(source_id)
        try:
            local_date = date.fromisoformat(row['date'])
            tz_name = row.get('timezone') or plan['timezone']
            tz = ZoneInfo(tz_name)
        except (KeyError, TypeError, ValueError, ZoneInfoNotFoundError) as exc:
            raise ValueError('Invalid schedule date or timezone') from exc
        if row.get('iso_weekday', local_date.isoweekday()) != local_date.isoweekday():
            raise ValueError('Schedule date and weekday disagree')
        begin, end = _clock(row.get('start_time')), _clock(row.get('end_time'))
        end_day = local_date + timedelta(days=1) if end < begin else local_date
        start_utc = _local_to_utc(local_date, begin, tz)
        end_utc = _local_to_utc(end_day, end, tz)
        duration = int((end_utc - start_utc).total_seconds() // 60)
        if not 0 < duration <= 24 * 60 or row.get('duration_minutes', duration) != duration:
            raise ValueError('Schedule duration does not match its clock times')
        title, category = row.get('title'), row.get('category', 'study')
        if not isinstance(title, str) or not title.strip() or len(title) > 256 or category not in CATEGORIES:
            raise ValueError('Invalid schedule title or category')
        description = row.get('description', '')
        source_path = row.get('source_path', '')
        if not isinstance(description, str) or len(description) > 20000 or not isinstance(source_path, str):
            raise ValueError('Invalid schedule description or provenance')
        condition = row.get('condition')
        if condition is not None and (not isinstance(condition, str) or not condition.strip()):
            raise ValueError('Invalid schedule condition')
        if 'condition_confirmed' in row and not isinstance(row['condition_confirmed'], bool):
            raise ValueError('Schedule condition confirmation must be boolean')
        if row.get('clock_time_origin', 'operational_assumption') == 'operational_assumption':
            description = 'Horario provisional. Ajustable según disponibilidad y compromisos reales.\n\n' + description
        if source_path:
            citation = Path(source_path).name
            if row.get('source_section'):
                citation += ' · ' + str(row['source_section']).lstrip('# ')
            source_updated = row.get('source_updated') or plan.get('source_plan_updated')
            if source_updated:
                citation += ' · actualizado ' + str(source_updated)
            description += '\n\nFuente: ' + citation
        if condition is not None and row.get('condition_confirmed') is not True:
            continue
        prepared.append({
            'id': _stable_id('evt-plan-', user_id, collection, source_id),
            'local_date': local_date, 'title': title, 'description': description,
            'start_time': start_utc, 'end_time': end_utc, 'timezone': tz_name,
            'category': category,
        })
    prepared.sort(key=lambda event: (event['start_time'], event['id']))
    return collection, prepared


def _overlaps(event, other):
    # Events without an end still reserve their start instant.
    other_end = other.end_time or other.start_time + timedelta(microseconds=1)
    return event['start_time'] < other_end and other.start_time < event['end_time']


def _activation_date(value):
    cutoff = date.fromisoformat(value) if isinstance(value, str) else value
    if not isinstance(cutoff, date) or isinstance(cutoff, datetime):
        raise ValueError('Invalid schedule activation date')
    return cutoff


def _matches(event, prepared):
    return event.id == prepared['id'] and all(
        getattr(event, field) == prepared[field] for field in EVENT_FIELDS)


def _fingerprint(collection, prepared):
    return hashlib.sha256(json.dumps(
        {'collection': collection, 'events': prepared}, sort_keys=True,
        separators=(',', ':'), default=lambda value: value.isoformat()).encode()).hexdigest()


@asynccontextmanager
async def _schedule_transaction(user_id, dry_run):
    async with get_db_context() as session:
        dialect = session.bind.dialect.name
        sqlite_lock = _SQLITE_LOCKS.setdefault(session.bind, asyncio.Lock()) if dialect == 'sqlite' else None
        if sqlite_lock is not None:
            await sqlite_lock.acquire()
        try:
            async with session.begin():
                now = datetime.now(timezone.utc).replace(tzinfo=None)
                if dialect == 'postgresql':
                    from sqlalchemy.dialects.postgresql import insert
                    lock_key = int.from_bytes(hashlib.sha256(('schedule\0' + user_id).encode()).digest()[:8], 'big', signed=True)
                    await session.execute(text('SELECT pg_advisory_xact_lock(:key)'), {'key': lock_key})
                    # Head first, matching SyncService's lock order. The upsert
                    # also serializes first-use creation with other writers.
                    await session.execute(insert(SyncHead).values(
                        user_id=user_id, current_seq=0, updated_at=now
                    ).on_conflict_do_nothing(index_elements=['user_id']))
                elif dialect == 'sqlite':
                    await session.execute(text('BEGIN IMMEDIATE'))
                else:
                    raise ValueError('Unsupported schedule database dialect')
                head_stmt = select(SyncHead).where(SyncHead.user_id == user_id)
                if dialect == 'postgresql':
                    head_stmt = head_stmt.with_for_update()
                head = (await session.execute(head_stmt)).scalar_one_or_none()
                if head is None:
                    head = SyncHead(user_id=user_id, current_seq=0, updated_at=now)
                    session.add(head)
                    await session.flush()
                initial_seq = head.current_seq
                existing_stmt = select(Event).where(Event.user_id == user_id).order_by(Event.id)
                if dialect == 'postgresql':
                    existing_stmt = existing_stmt.with_for_update()
                existing = list((await session.execute(existing_stmt)).scalars().all())
                yield session, head, existing, now
                if dry_run or head.current_seq == initial_seq:
                    # Previews and no-ops do not even persist an empty sync head.
                    await session.rollback()
                else:
                    await session.flush()
        finally:
            if sqlite_lock is not None:
                sqlite_lock.release()


def _new_event(prepared, user_id, now):
    return Event(**{key: value for key, value in prepared.items() if key != 'local_date'},
                 user_id=user_id, is_completed=False, is_deleted=False,
                 version=1, created_at=now, updated_at=now)


def _record_change(session, head, event, change_type, now):
    head.current_seq += 1
    head.updated_at = now
    payload = {field: getattr(event, field) for field in EVENT_FIELDS}
    for field in ('start_time', 'end_time'):
        payload[field] = payload[field].isoformat() + 'Z' if payload[field] is not None else None
    payload.update(id=event.id, is_completed=event.is_completed,
                   is_deleted=event.is_deleted, version=event.version)
    change_id = (_stable_id('cb-plan-', event.id) if change_type == 'create'
                 else _stable_id('cb-plan-retire-', event.id, str(event.version)))
    session.add(ChangeBatch(id=change_id, user_id=event.user_id,
        commit_seq=head.current_seq, entity_type='event', entity_id=event.id,
        change_type=change_type, entity_version=event.version, payload_json=payload, created_at=now))


async def apply_schedule(plan, user_id, *, not_before=None, dry_run=False):
    _, prepared = prepare_events(plan, user_id)
    cutoff = _activation_date(not_before if not_before is not None else
                              datetime.now(ZoneInfo(plan['timezone'])).date())
    report = {'dry_run': dry_run, 'planned': len(prepared), 'created': 0,
              'unchanged': 0, 'preserved_existing': 0, 'deleted_not_restored': 0,
              'skipped_past': 0, 'skipped_conflict': 0, 'conflict_event_ids': [],
              'commit_seq': None}
    async with _schedule_transaction(user_id, dry_run) as (session, head, existing, now):
        created = _plan_additions(prepared, existing, user_id, cutoff, now, report)
        if not dry_run:
            for event in created:
                session.add(event)
                _record_change(session, head, event, 'create', now)
            if created:
                report['commit_seq'] = head.current_seq
    return report


def _plan_additions(prepared, existing, user_id, cutoff, now, report, retiring_ids=frozenset()):
    by_id = {event.id: event for event in existing}
    busy = [event for event in existing if not event.is_deleted and event.id not in retiring_ids]
    created = []
    for event in prepared:
        if event['local_date'] < cutoff:
            report['skipped_past'] += 1
            continue
        old = by_id.get(event['id'])
        if old is not None:
            if old.is_deleted:
                report['deleted_not_restored'] += 1
            elif _matches(old, event) and not old.is_completed:
                report['unchanged'] += 1
            else:
                report['preserved_existing'] += 1
            continue
        if any(_overlaps(event, other) for other in busy):
            report['skipped_conflict'] += 1
            report['conflict_event_ids'].append(event['id'])
            continue
        model = _new_event(event, user_id, now)
        busy.append(model)
        created.append(model)
        report['created'] += 1
    return created


async def reconcile_schedule(old_plan, new_plan, user_id, *, cutoff, dry_run=False):
    """Replace pristine, future imports from an exact old plan in one transaction.

    The cutoff is an inclusive local calendar date, using each row's timezone.
    All imported fields, owner, id, version=1 and completion/deletion flags must
    match before retiring an old event. Timestamps are retained as audit history.
    A shared ID is preserved even when its new payload differs: use new source
    IDs or a new collection for a replacement. Deleted events are never restored.
    Distinct IDs are distinct events: no semantic equivalence is inferred from
    titles or source-row names. Manual tombstones remain intact, but do not
    reserve time against different new IDs; live manual events do reserve time.
    """
    old_collection, old_events = prepare_events(old_plan, user_id)
    new_collection, new_events = prepare_events(new_plan, user_id)
    cutoff = _activation_date(cutoff)
    report = {'dry_run': dry_run, 'cutoff': cutoff.isoformat(),
              'old_plan_fingerprint': _fingerprint(old_collection, old_events),
              'new_plan_fingerprint': _fingerprint(new_collection, new_events),
              'planned': len(new_events), 'created': 0, 'retired': 0,
              'unchanged': 0, 'preserved_existing': 0, 'deleted_not_restored': 0,
              'skipped_past': 0, 'skipped_conflict': 0, 'conflict_event_ids': [],
              'old_skipped_past': 0, 'old_missing': 0, 'old_already_deleted': 0,
              'preserved_old': 0, 'retained_shared_ids': [],
              'retired_event_ids': [], 'created_event_ids': [], 'commit_seq': None}
    # Only IDs actually prepared from this old plan can be retired. No prefix
    # search or assumptions about other imported collections are used.
    # Even an unconfirmed conditional row retains its declared identity.
    new_ids = {_stable_id('evt-plan-', user_id, new_collection, row['id'])
               for row in new_plan['dated_events']}
    async with _schedule_transaction(user_id, dry_run) as (session, head, existing, now):
        by_id = {event.id: event for event in existing}
        retired = []
        for event in old_events:
            if event['local_date'] < cutoff:
                report['old_skipped_past'] += 1
                continue
            if event['id'] in new_ids:
                report['retained_shared_ids'].append(event['id'])
                continue
            old = by_id.get(event['id'])
            if old is None:
                report['old_missing'] += 1
            elif old.is_deleted:
                report['old_already_deleted'] += 1
            elif (old.user_id == user_id and old.version == 1 and not old.is_completed
                  and _matches(old, event)):
                retired.append(old)
            else:
                report['preserved_old'] += 1
        retiring_ids = {event.id for event in retired}
        created = _plan_additions(new_events, existing, user_id, cutoff, now, report, retiring_ids)
        report['retired'] = len(retired)
        report['retired_event_ids'] = [event.id for event in retired]
        report['created_event_ids'] = [event.id for event in created]
        if not dry_run:
            for event in retired:
                event.is_deleted = True
                event.version += 1
                event.updated_at = now
                _record_change(session, head, event, 'delete', now)
            for event in created:
                session.add(event)
                _record_change(session, head, event, 'create', now)
            if retired or created:
                report['commit_seq'] = head.current_seq
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('preview', 'apply', 'reconcile-preview', 'reconcile-apply'))
    parser.add_argument('plan')
    parser.add_argument('new_plan', nargs='?')
    parser.add_argument('--user-id', required=True)
    parser.add_argument('--not-before', '--cutoff', dest='cutoff')
    args = parser.parse_args()
    reconciling = args.command.startswith('reconcile-')
    if reconciling and (args.new_plan is None or args.cutoff is None):
        parser.error('Reconciliation requires old/new plans and --cutoff YYYY-MM-DD')
    if not reconciling and args.new_plan is not None:
        parser.error('A second plan is only accepted for reconciliation')

    def read_plan(filename):
        path = Path(filename)
        if path.stat().st_size > 10 * 1024 * 1024:
            raise ValueError('Schedule plan exceeds maximum size')
        return json.loads(path.read_text())

    try:
        plan = read_plan(args.plan)
        if reconciling:
            report = asyncio.run(reconcile_schedule(plan, read_plan(args.new_plan), args.user_id,
                cutoff=args.cutoff, dry_run=args.command == 'reconcile-preview'))
        else:
            report = asyncio.run(apply_schedule(plan, args.user_id, not_before=args.cutoff,
                                               dry_run=args.command == 'preview'))
    except Exception as exc:
        # Database errors can contain bound titles/descriptions; never echo them.
        print(json.dumps({'status': 'failed', 'error_type': type(exc).__name__, 'rolled_back': True}))
        raise SystemExit(1) from None
    print(json.dumps(report))


if __name__ == '__main__':
    main()
