from datetime import datetime, timedelta, timezone
import pytest
from sqlalchemy import select
from app.models.canonical import ChatMessage, DocumentContextGrant, DocumentOrigin, DocumentRevision, Memory
from app.services.document_retrieval import document_retrieval
from app.services.context_engine import context_engine
from test_document_retrieval import add_document

@pytest.mark.asyncio
async def test_twelve_hour_windows_boundaries_ties_and_cross_user_cursor(client, db_session):
    end = datetime(2026,9,22,12)
    for key, hours, user in [('a',1,'default_user'),('b',1,'default_user'),('boundary',12,'default_user'),('older',13,'default_user'),('foreign',1,'someone')]:
        at=end-timedelta(hours=hours)
        db_session.add(ChatMessage(id=key,user_id=user,role='user',content=key,created_at=at,received_at=at))
    await db_session.commit()
    response=await client.get('/v1/chat/history',params={'before':end.isoformat()+'Z','limit':1})
    assert response.status_code==200
    page=response.json(); assert [m['id'] for m in page['messages']]==['b']
    response=await client.get('/v1/chat/history',params={'before':page['window_end'],'limit':1,'cursor':page['next_cursor']})
    assert [m['id'] for m in response.json()['messages']]==['a']
    response=await client.get('/v1/chat/history',params={'before':page['window_end'],'limit':1,'cursor':'a'})
    assert [m['id'] for m in response.json()['messages']]==['boundary']
    assert response.json()['next_cursor'] is None and response.json()['has_older']
    older=await client.get('/v1/chat/history',params={'before':page['window_start']})
    assert [m['id'] for m in older.json()['messages']]==['older']
    assert not older.json()['has_older']
    assert (await client.get('/v1/chat/history',params={'before':page['window_end'],'cursor':'foreign'})).status_code==400

@pytest.mark.asyncio
async def test_check_in_is_durable_and_idempotent_without_marking_done(client,db_session):
    now=datetime.now(timezone.utc)
    event=(await client.post('/v1/agenda/events',json={'title':'Actividad sintética','start_time':(now-timedelta(hours=1)).isoformat(),'end_time':(now-timedelta(minutes=10)).isoformat()})).json()
    payload={'notification_key':'test-slot-1','event_id':event['id'],'kind':'check_in','scheduled_at':now.isoformat()}
    first=await client.post('/v1/chat/check-ins',json=payload)
    second=await client.post('/v1/chat/check-ins',json=payload)
    assert first.status_code==200 and second.json()['id']==first.json()['id']
    assert 'Actividad sintética' in first.json()['content']
    assert first.json()['role']=='assistant'
    assert 'completed' not in first.json()['content']

@pytest.mark.asyncio
async def test_private_grant_is_revision_and_recipient_bound(db_session):
    doc,rev=await add_document(db_session,'private','Preferencia sintética: estudiar astrofísica.',privacy='OPT_IN')
    db_session.add(DocumentContextGrant(id='grant',user_id='default_user',document_id=doc.id,revision_id=rev.id,recipient_id='device:pixel',reason='Explicit synthetic authorization'))
    await db_session.commit()
    async def search(recipient=None):
        return await document_retrieval.search(db_session,'default_user','astrofísica',recipient_id=recipient)
    assert not await search()
    assert not await search('device:other')
    assert await search('device:pixel')
    origin=await db_session.get(DocumentOrigin,doc.id)
    origin.privacy_class='NEVER_UPLOAD';await db_session.commit()
    assert not await search('device:pixel')
    origin.privacy_class='OPT_IN'
    db_session.add(DocumentRevision(id='private-v2',document_id=doc.id,version=2,storage_path='/unused',original_filename='test.txt',mime_type='text/plain',file_size_bytes=1,sha256_hash='b'*64,extraction_status='ready',extracted_text='astrofísica nueva'))
    await db_session.commit()
    assert not await search('device:pixel')

@pytest.mark.asyncio
async def test_older_memories_and_user_conversations_survive_many_updates(db_session):
    old=datetime(2020,1,1)
    db_session.add(Memory(id='old',user_id='default_user',memory_type='semantic',predicate='preferencia',value='Disfruto estudiar astronomía',source_kind='chat',status='active',created_at=old,updated_at=old))
    for i in range(205):
        db_session.add(Memory(id=f'recent-{i}',user_id='default_user',memory_type='episodic',predicate='activity_check_in',value='Actividad sintética reciente',source_kind='phone',status='active',created_at=datetime(2026,1,1),updated_at=datetime(2026,1,1)))
    db_session.add(ChatMessage(id='old-chat',user_id='default_user',role='user',content='Hablé de astronomía hace años.',created_at=old,received_at=old))
    db_session.add(ChatMessage(id='other-chat',user_id='other',role='user',content='Astronomía de otro usuario.',created_at=old,received_at=old))
    await db_session.commit()
    result=await context_engine.memory_context(db_session,'default_user',query='¿Qué dije sobre astronomía?')
    assert 'Disfruto estudiar astronomía' in result
    recall=await context_engine.past_conversation_context(db_session,'default_user','astronomía')
    assert 'hace años' in recall and '2020' in recall and 'otro usuario' not in recall
