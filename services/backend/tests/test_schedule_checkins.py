from datetime import datetime

import pytest
from sqlalchemy import func, select

from app.models.canonical import Memory
from app.services.document_retrieval import estimate_tokens, MESSAGE_OVERHEAD_TOKENS, PROMPT_TOKEN_BUDGET
from app.services.prompt_builder import build_llm_messages


@pytest.mark.asyncio
async def test_activity_check_in_replay_and_conflict(client, db_session):
    payload = {'request_id': 'check-in-one', 'activity': 'Estoy leyendo',
               'observed_at': '2026-09-15T10:00:00-06:00'}
    first = await client.post('/v1/agenda/check-ins', json=payload)
    assert first.status_code == 200
    again = await client.post('/v1/agenda/check-ins', json=payload)
    assert again.json() == first.json()
    assert await db_session.scalar(select(func.count(Memory.id))) == 1
    memory = await db_session.get(Memory, first.json()['memory_id'])
    assert memory.valid_from == datetime(2026, 9, 15, 16)
    assert memory.valid_to == memory.valid_from  # observation, not a permanent habit
    changed = await client.post('/v1/agenda/check-ins', json={**payload, 'activity': 'Otra actividad'})
    assert changed.status_code == 409
    invalid = await client.post('/v1/agenda/check-ins', json={**payload, 'activity': '  '})
    assert invalid.status_code == 422


@pytest.mark.asyncio
async def test_agenda_local_midnight_overlap_and_explicit_utc(client):
    created = await client.post('/v1/agenda/events', json={
        'id': 'night-block', 'title': 'Descanso', 'category': 'sleep',
        'start_time': '2026-09-14T23:00:00-06:00',
        'end_time': '2026-09-15T07:00:00-06:00',
    })
    assert created.status_code == 200
    assert created.json()['start_time'] == '2026-09-15T05:00:00Z'
    day = await client.get('/v1/agenda/events?date=2026-09-15')
    assert any(event['id'] == 'night-block' for event in day.json())
    following = await client.get('/v1/agenda/events?date=2026-09-16')
    assert not any(event['id'] == 'night-block' for event in following.json())


def test_activity_context_stays_within_prompt_budget():
    messages = build_llm_messages('2026-09-15', [], 'Ayúdame a organizar el día', [],
                                  memory_context='REGISTROS DE ACTIVIDAD\n' + 'observación ' * 10000)
    assert any('REGISTROS DE ACTIVIDAD' in message['content'] for message in messages)
    assert sum(estimate_tokens(message['content']) + MESSAGE_OVERHEAD_TOKENS for message in messages) <= PROMPT_TOKEN_BUDGET


@pytest.mark.asyncio
async def test_confirm_proposal_preserves_local_time(client):
    response = await client.post('/v1/proposals', json={
        'id': 'proposal-local-clock', 'summary': 'Bloque de lectura', 'reason': 'Horario local',
        'resulting_items': [{'id': 'reading-local', 'title': 'Lectura',
                             'start_time': '2026-09-15T19:00:00-06:00',
                             'end_time': '2026-09-15T20:00:00-06:00'}],
    })
    assert response.status_code == 200
    confirmed = await client.post('/v1/proposals/proposal-local-clock/confirm')
    assert confirmed.status_code == 200 and confirmed.json()['success']
    events = (await client.get('/v1/agenda/events?date=2026-09-15')).json()
    event = next(event for event in events if event['id'] == 'reading-local')
    assert event['start_time'] == '2026-09-16T01:00:00Z'
