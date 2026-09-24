import pytest
from sqlalchemy import select
from app.config import settings
from app.models.canonical import DocumentOrigin, DocumentRevision
from app.services.file_delivery import file_delivery_response, file_query

@pytest.mark.asyncio
async def test_photo_roundtrip_catalog_and_chat(client, db_session, monkeypatch, tmp_path):
    monkeypatch.setattr(settings, 'storage_path', str(tmp_path))
    content = b'\x89PNG\r\n\x1a\nsynthetic-image-fixture'
    response = await client.post('/v1/documents/uploads', json={
        'filename': 'foto_prueba.png', 'title': 'Foto prueba',
        'mime_type': 'image/png', 'expected_size_bytes': len(content),
    })
    upload_id = response.json()['upload_id']
    assert (await client.put(f'/v1/documents/uploads/{upload_id}/content', content=content)).status_code == 200
    response = await client.post(f'/v1/documents/uploads/{upload_id}/complete')
    assert response.status_code == 200
    doc_id, user_id = response.json()['id'], response.json()['user_id']
    rev = (await db_session.execute(select(DocumentRevision).where(DocumentRevision.document_id == doc_id))).scalar_one()
    rev.extracted_text = 'private body not needed in a catalogue'
    await db_session.commit()
    listing = await client.get('/v1/documents?include_text=false')
    assert listing.status_code == 200
    assert 'private body' not in listing.text
    answer = await file_delivery_response(db_session, user_id, 'Dame la foto prueba')
    assert f'/v1/documents/{doc_id}/versions/1/download' in answer
    assert 'private body' not in answer
    assert (await client.get(f'/v1/documents/{doc_id}/versions/1/download')).content == content
    assert 'No encontré' in await file_delivery_response(db_session, 'different-user', 'Dame la foto prueba')
    db_session.add(DocumentOrigin(document_id=doc_id, source_collection='test', source_path='not-opened', privacy_class='NEVER_UPLOAD', source_kind='test'))
    await db_session.commit()
    assert 'No encontré' in await file_delivery_response(db_session, user_id, 'Dame la foto prueba')

def test_file_intent_does_not_hijack_agenda_or_questions():
    assert file_query('Dame mi calendario de mañana') is None
    assert file_query('¿Qué dice mi documento?') is None
    assert file_query('Mueve la reunión a mañana') is None
    assert file_query('/archivo cv') == 'cv'

@pytest.mark.asyncio
async def test_confirm_move_across_midnight_and_cancel(client):
    event = (await client.post('/v1/agenda/events', json={
        'title': 'Evento sintético', 'start_time': '2026-10-01T22:00:00-06:00',
        'end_time': '2026-10-01T23:00:00-06:00',
    })).json()
    item = {'id': event['id'], 'title': 'Evento sintético',
            'start_time': '2026-10-02T23:30:00-06:00', 'end_time': '2026-10-03T00:30:00-06:00'}
    for proposal_id, action in [('move-synthetic', 'upsert'), ('cancel-synthetic', 'delete')]:
        response = await client.post('/v1/proposals', json={
            'id': proposal_id, 'summary': 'Prueba', 'reason': 'Prueba',
            'resulting_items': [{**item, 'action': action}],
        })
        assert response.status_code == 200
        assert response.json()['resulting_items'][0]['action'] == action
        response = await client.post(f'/v1/proposals/{proposal_id}/confirm')
        assert response.json()['success']
        events = (await client.get('/v1/agenda/events?date=2026-10-02&timezone=America/Mexico_City')).json()
        found = [e for e in events if e['id'] == event['id']]
        assert len(found) == (1 if action == 'upsert' else 0)
        if found:
            assert found[0]['start_time'].startswith('2026-10-03T05:30:00')
        old = (await client.get('/v1/agenda/events?date=2026-10-01')).json()
        assert all(e['id'] != event['id'] for e in old)

@pytest.mark.asyncio
async def test_fast_reply_cannot_finish_between_snapshot_and_subscription(test_engine, monkeypatch):
    import asyncio
    from datetime import datetime
    from app.models.chat import ChatTurnResponse
    from app.services.chat_orchestrator import ChatOrchestrator
    orchestrator = ChatOrchestrator()
    async def snapshot(*args):
        await orchestrator._broadcast('fast', {'type': 'token', 'content': 'archivo'})
        await orchestrator._broadcast('fast', {'type': 'done'})
        return ChatTurnResponse(turn_id='fast', user_id='owner', status='running', user_message='file', created_at=datetime.now())
    monkeypatch.setattr(orchestrator, 'get_turn_response', snapshot)
    async def collect():
        return [chunk async for chunk in orchestrator.subscribe_turn_sse('fast', 'owner')]
    events = await asyncio.wait_for(collect(), timeout=2)
    assert any('archivo' in event for event in events)
    assert any('done' in event for event in events)
    assert not orchestrator._subscribers
