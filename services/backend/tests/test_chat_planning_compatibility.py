"""End-to-end server behavior through the payload understood by installed Android."""
import json
from datetime import datetime, timezone
from unittest.mock import patch

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.models.canonical import Document, DocumentRevision, Event, WeeklyRoutine


class Clock(datetime):
    @classmethod
    def now(cls, tz=None):
        value = datetime(2026, 10, 15, 16, tzinfo=timezone.utc)
        return value.astimezone(tz) if tz else value.replace(tzinfo=None)


@pytest_asyncio.fixture
async def owner(client):
    challenge = (await client.post('/v1/auth/challenge')).json()
    pair = (await client.post('/v1/auth/pair', json={
        'pairing_code': challenge['pairing_code'], 'device_name': 'Installed Android', 'platform': 'android',
    })).json()
    return {'Authorization': 'Bearer ' + pair['access_token']}


async def legacy(client, owner, message, date='2026-10-29'):
    response = await client.post('/v1/chat/stream', headers=owner,
                                json={'message': message, 'date': date, 'history': []})
    assert response.status_code == 200
    events = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith('data: ')]
    assert not [event for event in events if event['type'] == 'error'], events
    return ''.join(e.get('content', '') for e in events if e['type'] == 'token'), next((e['proposal'] for e in events if e['type'] == 'proposal'), None)


def fake_model(captured, title='Sesión sintética'):
    async def generate(messages):
        captured.append(messages)
        yield 'Fecha del modelo deliberadamente equivocada.\n```proposal\n' + json.dumps({
            'summary': 'Viernes 24 incorrecto', 'reason': 'Fixture', 'items': [{
                'id': 'invented', 'title': title, 'start_time': '2026-10-24T12:00:00',
                'end_time': '2026-10-24T13:00:00', 'category': 'general',
            }],
        }) + '\n```'
    return generate


@pytest.mark.asyncio
async def test_legacy_requires_clarification_then_uses_exact_server_dates(client, owner):
    captured = []
    with patch('app.services.chat_orchestrator.datetime', Clock), patch('app.services.chat_orchestrator.stream_chat_completion', fake_model(captured)):
        answer, proposal = await legacy(client, owner, 'Agenda una llamada con Miguel')
        assert proposal is None and 'fecha' in answer and not captured
        answer, proposal = await legacy(client, owner, 'El viernes de la próxima semana de 17:00 a 17:30')
        assert proposal and len(proposal['resulting_items']) == 1
        assert proposal['resulting_items'][0]['start_time'] == '2026-10-23T17:00:00-06:00'
        assert '24/10' not in answer and '23/10/2026' in answer


@pytest.mark.asyncio
async def test_week_context_and_conflict_preflight(client, owner, db_session):
    db_session.add(Event(id='existing-nextweek', user_id='default_user', title='Compromiso existente',
        start_time=datetime(2026, 10, 23, 23), end_time=datetime(2026, 10, 23, 23, 30)))
    await db_session.commit()
    captured = []
    with patch('app.services.chat_orchestrator.datetime', Clock), patch('app.services.chat_orchestrator.stream_chat_completion', fake_model(captured)):
        answer, proposal = await legacy(client, owner, 'Agenda estudio el viernes de la próxima semana de 17:00 a 17:30')
    assert 'Compromiso existente' in str(captured)
    assert proposal is None and 'cruza' in answer
    assert len((await db_session.scalars(select(Event))).all()) == 1


@pytest.mark.asyncio
async def test_separate_chat_requests_and_retries_do_not_duplicate(client, owner, db_session):
    with patch('app.services.chat_orchestrator.datetime', Clock), patch('app.services.chat_orchestrator.stream_chat_completion', fake_model([])):
        for _ in range(2):
            _, proposal = await legacy(client, owner, 'Agenda sesión el 2026-10-23 de 17:00 a 17:30')
            assert proposal
            response = await client.post('/v1/proposals/' + proposal['id'] + '/confirm', headers=owner)
            assert response.status_code == 200 and response.json()['success']
            await client.post('/v1/proposals/' + proposal['id'] + '/confirm', headers=owner)
    assert len((await db_session.scalars(select(Event))).all()) == 1


@pytest.mark.asyncio
async def test_existing_mobile_confirms_real_weekly_routine(client, owner, db_session):
    captured = []
    with patch('app.services.chat_orchestrator.datetime', Clock), patch('app.services.chat_orchestrator.stream_chat_completion', fake_model(captured)):
        answer, proposal = await legacy(client, owner, 'Agenda estudio todos los lunes, miércoles y viernes desde el 19 de octubre de 2026 hasta el 30 de octubre de 2026 de 17:00 a 17:30')
    assert proposal and len(proposal['resulting_items']) == 6, answer
    assert not (await db_session.scalars(select(WeeklyRoutine))).all()
    assert not (await db_session.scalars(select(Event))).all()
    result = await client.post('/v1/proposals/' + proposal['id'] + '/confirm', headers=owner)
    assert result.status_code == 200 and result.json()['success'], result.text
    assert len((await db_session.scalars(select(WeeklyRoutine))).all()) == 1
    assert len((await db_session.scalars(select(Event))).all()) == 6
    recovered = (await client.get('/v1/proposals/' + proposal['id'], headers=owner)).json()
    assert recovered['status'] == 'accepted'


@pytest.mark.asyncio
async def test_document_consent_and_revocation_through_installed_chat(client, owner, db_session):
    db_session.add(Document(id='chat-file', user_id='default_user', title='Factura sintética'))
    await db_session.flush()
    db_session.add(DocumentRevision(id='chat-file-v1', document_id='chat-file', version=1,
        storage_path='/unused', original_filename='factura.pdf', mime_type='application/pdf',
        file_size_bytes=10, sha256_hash='a'*64, extraction_status='ready', extracted_text='Importe reservado 1847 pesos.'))
    await db_session.commit()
    captured = []
    async def analyze(messages):
        captured.append(messages)
        yield 'El importe es 1847 pesos.'
    with patch('app.services.chat_orchestrator.stream_chat_completion', analyze):
        answer, proposal = await legacy(client, owner, 'Lee el documento Factura sintética e indica su importe')
        assert '¿Autorizas' in answer and proposal is None and not captured
        answer, _ = await legacy(client, owner, 'sí, autorizo')
        assert 'Importe reservado 1847' in str(captured[-1]) and '1847' in answer
        answer, _ = await legacy(client, owner, '/revocar chat-file')
        assert 'Revoqué' in answer
        count = len(captured)
        answer, _ = await legacy(client, owner, 'Lee el documento Factura sintética')
        assert '¿Autorizas' in answer and len(captured) == count
