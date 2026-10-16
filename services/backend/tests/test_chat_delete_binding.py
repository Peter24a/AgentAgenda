"""Installed-client cancellation previews identify the exact canonical commitment."""
import json
from datetime import datetime, timezone
from unittest.mock import patch

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.models.canonical import Event


class Clock(datetime):
    @classmethod
    def now(cls, tz=None):
        instant = datetime(2026, 10, 15, 16, tzinfo=timezone.utc)
        return instant.astimezone(tz) if tz else instant.replace(tzinfo=None)


@pytest_asyncio.fixture
async def delete_owner(client):
    challenge = (await client.post('/v1/auth/challenge')).json()
    credentials = (await client.post('/v1/auth/pair', json={
        'pairing_code': challenge['pairing_code'], 'device_name': 'Installed client', 'platform': 'android',
    })).json()
    return {'Authorization': 'Bearer ' + credentials['access_token']}


def fabricated_delete(target_id):
    async def generate(messages):
        yield '```proposal\n' + json.dumps({
            'summary': 'Invented summary', 'reason': 'Invented details',
            'items': [{'id': target_id, 'action': 'delete', 'title': 'Título incorrecto',
                       'start_time': '2026-10-23T09:00:00', 'end_time': '2026-10-23T09:30:00',
                       'category': 'leisure'}],
        }) + '\n```'
    return generate


async def cancel(client, headers, message, target_id):
    with patch('app.services.chat_orchestrator.datetime', Clock), patch(
            'app.services.chat_orchestrator.stream_chat_completion', fabricated_delete(target_id)):
        response = await client.post('/v1/chat/stream', headers=headers, json={
            'message': message, 'date': '2026-10-15', 'history': [],
        })
    assert response.status_code == 200
    events = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith('data: ')]
    assert not [event for event in events if event['type'] == 'error'], events
    return (''.join(event.get('content', '') for event in events if event['type'] == 'token'),
            next((event['proposal'] for event in events if event['type'] == 'proposal'), None))


@pytest.mark.asyncio
async def test_wrong_date_existing_id_cannot_cancel_another_weeks_activity(client, delete_owner, db_session):
    db_session.add(Event(id='today-call', user_id='default_user', title='Llamada con Miguel',
                         start_time=datetime(2026, 10, 15, 23), end_time=datetime(2026, 10, 15, 23, 30)))
    await db_session.commit()
    answer, proposal = await cancel(client, delete_owner, 'Cancela la llamada con Miguel el viernes de la próxima semana', 'today-call')
    assert proposal is None and 'fecha que pediste cancelar' in answer
    await db_session.refresh(await db_session.get(Event, 'today-call'))
    assert not (await db_session.get(Event, 'today-call')).is_deleted


@pytest.mark.asyncio
async def test_delete_preview_replaces_all_model_fields_with_canonical_event(client, delete_owner, db_session):
    db_session.add(Event(id='actual-call', user_id='default_user', title='Llamada con Miguel',
                         description='Descripción original', category='work',
                         start_time=datetime(2026, 10, 23, 23), end_time=datetime(2026, 10, 23, 23, 30)))
    await db_session.commit()
    answer, proposal = await cancel(client, delete_owner, 'Cancela la llamada con Miguel el viernes de la próxima semana', 'actual-call')
    assert proposal, answer
    reviewed = proposal['resulting_items'][0]
    assert reviewed['title'] == 'Llamada con Miguel'
    assert reviewed['description'] == 'Descripción original' and reviewed['category'] == 'work'
    assert reviewed['start_time'] == '2026-10-23T17:00:00-06:00'
    assert reviewed['end_time'] == '2026-10-23T17:30:00-06:00'
    assert 'Título incorrecto' not in answer
    result = await client.post('/v1/proposals/' + proposal['id'] + '/confirm', headers=delete_owner)
    assert result.status_code == 200 and result.json()['success']
    event = await db_session.get(Event, 'actual-call')
    await db_session.refresh(event)
    assert event.is_deleted


@pytest.mark.asyncio
async def test_same_title_same_date_needs_exact_hour_before_cancellation(client, delete_owner, db_session):
    for id, hour in [('first-call', 23), ('second-call', 22)]:
        db_session.add(Event(id=id, user_id='default_user', title='Llamada con Miguel',
                             start_time=datetime(2026, 10, 23, hour), end_time=datetime(2026, 10, 23, hour, 30)))
    await db_session.commit()
    answer, proposal = await cancel(client, delete_owner, 'Cancela la llamada con Miguel el viernes de la próxima semana', 'first-call')
    assert proposal is None and 'varias actividades' in answer
    answer, proposal = await cancel(client, delete_owner, 'A las 17:00', 'first-call')
    assert proposal, answer
    assert [item['id'] for item in proposal['resulting_items']] == ['first-call']
    assert all(not event.is_deleted for event in (await db_session.scalars(select(Event))).all())


@pytest.mark.asyncio
async def test_finite_repeated_delete_expands_one_model_template_to_all_requested_dates(client, delete_owner, db_session):
    days = (19, 21, 23, 26, 28, 30)
    for day in days:
        db_session.add(Event(id=f'study-{day}', user_id='default_user', title='Estudio',
                             start_time=datetime(2026, 10, day, 23), end_time=datetime(2026, 10, day, 23, 30)))
    await db_session.commit()
    answer, proposal = await cancel(client, delete_owner,
        'Cancela estudio lunes, miércoles y viernes desde 2026-10-19 hasta 2026-10-30', 'study-19')
    assert proposal, answer
    assert {item['id'] for item in proposal['resulting_items']} == {f'study-{day}' for day in days}
    result = await client.post('/v1/proposals/' + proposal['id'] + '/confirm', headers=delete_owner)
    assert result.status_code == 200 and result.json()['success']
    db_session.expire_all()
    assert all(event.is_deleted for event in (await db_session.scalars(select(Event))).all())


@pytest.mark.asyncio
async def test_finite_repeated_delete_does_not_silently_apply_partial_scope(client, delete_owner, db_session):
    for day in (19, 21, 23, 26, 28):  # Friday 30 cannot be resolved.
        db_session.add(Event(id=f'study-{day}', user_id='default_user', title='Estudio',
                             start_time=datetime(2026, 10, day, 23), end_time=datetime(2026, 10, day, 23, 30)))
    await db_session.commit()
    answer, proposal = await cancel(client, delete_owner,
        'Cancela estudio lunes, miércoles y viernes desde 2026-10-19 hasta 2026-10-30', 'study-19')
    assert proposal is None and 'cancelación parcial' in answer
    assert all(not event.is_deleted for event in (await db_session.scalars(select(Event))).all())
