"""Import an explicitly authorized private schedule without replacing existing events.

Input uses schema_version=1, timezone, and dated_events. Each event has a stable
id, date, start_time/end_time (HH:MM), title, category, and optional provenance.
Clock times are local to the named timezone. No document instructions execute.
"""
import argparse
import asyncio
from datetime import date, datetime, time, timedelta, timezone
import hashlib
import json
from pathlib import Path
import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select, text

from app.db.session import get_db_context
from app.models.canonical import ChangeBatch, Event, SyncHead

CATEGORIES = {'sleep', 'work', 'food', 'exercise', 'study', 'leisure', 'general'}
MAX_EVENTS = 1000


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


async def apply_schedule(plan, user_id, *, not_before=None, dry_run=False):
    collection, prepared = prepare_events(plan, user_id)
    cutoff = date.fromisoformat(not_before) if isinstance(not_before, str) else not_before
    if cutoff is None:
        cutoff = datetime.now(ZoneInfo(plan['timezone'])).date()
    if not isinstance(cutoff, date):
        raise ValueError('Invalid schedule activation date')
    report = {'dry_run': dry_run, 'planned': len(prepared), 'created': 0,
              'unchanged': 0, 'preserved_existing': 0, 'deleted_not_restored': 0,
              'skipped_past': 0, 'skipped_conflict': 0, 'conflict_event_ids': [],
              'commit_seq': None}
    async with get_db_context() as session:
        async with session.begin():
            if session.bind.dialect.name == 'postgresql':
                lock_key = int.from_bytes(hashlib.sha256(('schedule\0' + user_id).encode()).digest()[:8], 'big', signed=True)
                await session.execute(text('SELECT pg_advisory_xact_lock(:key)'), {'key': lock_key})
            existing_stmt = select(Event).where(Event.user_id == user_id)
            if session.bind.dialect.name == 'postgresql':
                existing_stmt = existing_stmt.with_for_update()
            existing = list((await session.execute(existing_stmt)).scalars().all())
            by_id = {event.id: event for event in existing}
            busy = [event for event in existing if not event.is_deleted]
            created = []
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            for event in prepared:
                if event['local_date'] < cutoff:
                    report['skipped_past'] += 1
                    continue
                old = by_id.get(event['id'])
                if old is not None:
                    if old.is_deleted:
                        report['deleted_not_restored'] += 1
                    elif all(getattr(old, key) == event[key] for key in ('title', 'description', 'start_time', 'end_time', 'timezone', 'category')) and not old.is_completed:
                        report['unchanged'] += 1
                    else:
                        report['preserved_existing'] += 1
                    continue
                if any(_overlaps(event, other) for other in busy):
                    report['skipped_conflict'] += 1
                    report['conflict_event_ids'].append(event['id'])
                    continue
                model = Event(**{key: value for key, value in event.items() if key != 'local_date'},
                              user_id=user_id, is_completed=False, is_deleted=False,
                              version=1, created_at=now, updated_at=now)
                busy.append(model)
                created.append(model)
                report['created'] += 1
            if not dry_run and created:
                head_stmt = select(SyncHead).where(SyncHead.user_id == user_id)
                if session.bind.dialect.name == 'postgresql':
                    head_stmt = head_stmt.with_for_update()
                head = (await session.execute(head_stmt)).scalar_one_or_none()
                if head is None:
                    head = SyncHead(user_id=user_id, current_seq=0, updated_at=now)
                    session.add(head)
                for event in created:
                    session.add(event)
                    head.current_seq += 1
                    payload = {
                        'id': event.id, 'title': event.title, 'description': event.description,
                        'start_time': event.start_time.isoformat() + 'Z',
                        'end_time': event.end_time.isoformat() + 'Z',
                        'timezone': event.timezone, 'category': event.category,
                        'is_completed': False, 'is_deleted': False, 'version': 1,
                    }
                    session.add(ChangeBatch(id=_stable_id('cb-plan-', event.id), user_id=user_id,
                        commit_seq=head.current_seq, entity_type='event', entity_id=event.id,
                        change_type='create', entity_version=1, payload_json=payload, created_at=now))
                head.updated_at = now
                report['commit_seq'] = head.current_seq
                await session.flush()
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('preview', 'apply'))
    parser.add_argument('plan')
    parser.add_argument('--user-id', required=True)
    parser.add_argument('--not-before')
    args = parser.parse_args()
    try:
        path = Path(args.plan)
        if path.stat().st_size > 10 * 1024 * 1024:
            raise ValueError('Schedule plan exceeds maximum size')
        plan = json.loads(path.read_text())
        report = asyncio.run(apply_schedule(plan, args.user_id, not_before=args.not_before,
                                           dry_run=args.command == 'preview'))
    except Exception as exc:
        # Database errors can contain bound titles/descriptions; never echo them.
        print(json.dumps({'status': 'failed', 'error_type': type(exc).__name__, 'rolled_back': True}))
        raise SystemExit(1) from None
    print(json.dumps(report))


if __name__ == '__main__':
    main()
