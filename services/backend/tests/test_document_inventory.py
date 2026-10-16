import hashlib
from unittest.mock import patch

import pytest
from sqlalchemy import select
from app.models.canonical import Document, DocumentRevision, DocumentOrigin, Device
from app.services.document_consent import set_context_access
from app.services.document_inventory import inventory_query, inventory_response


TEXT = 'La Universidad Ejemplo otorga el reconocimiento a Pedro Ibarra por su participación en el concurso de innovación educativa celebrado el 15 de octubre de 2026, folio A123. Este diploma acredita la participación y dedicación del alumno.'

async def seed(s, key, title='Reconocimiento innovación', text=TEXT, privacy=None, user='owner', version=1, digest=None):
    if not await s.get(Document, key):
        s.add(Document(id=key, user_id=user, title=title))
        await s.flush()
        if privacy:
            s.add(DocumentOrigin(document_id=key, source_collection='test', source_path=key, source_kind='manual', privacy_class=privacy))
    s.add(DocumentRevision(id=f'{key}-v{version}', document_id=key, version=version,
        storage_path='/never-open', original_filename=key+'.pdf', mime_type='application/pdf',
        file_size_bytes=100, sha256_hash=digest or hashlib.sha256(key.encode()).hexdigest(),
        extraction_status='ready', extracted_text=text))
    await s.commit()

async def answer(s, message='¿Cuántos reconocimientos he obtenido?', recipient='device:phone'):
    return await inventory_response(s, 'owner', recipient, message)

@pytest.mark.parametrize('message,keywords,compare', [
    ('¿Cuántos reconocimientos he obtenido?', ('reconocimiento',), True),
    ('Cuenta mis documentos', (), False),
    ('Cuántos documentos con título agenda tengo', ('agenda',), False),
    ('Puedes buscar mis documentos con título reconocimientos', ('reconocimiento',), False),
    ('Busca documentos por título que digan reconocimientos', ('reconocimiento',), False),
    ('¿Tengo reconocimientos repetidos?', ('reconocimiento',), True),
    ('Compara mis documentos duplicados', (), True),
    ('Lista documentos con título "Curso de física"', ('curso','de','fisica'), False),
])
def test_queries(message,keywords,compare):
    q=inventory_query(message)
    assert q and q.keywords == keywords and q.compare == compare

@pytest.mark.parametrize('message', ['/autorizar reconocimiento','/revocar reconocimiento','/archivo reconocimiento','Analiza el documento reconocimiento','Agenda revisar documentos mañana','¿Cuántas reuniones tengo?','sí, autorizo'])
def test_unrelated_routes(message):
    assert inventory_query(message) is None

@pytest.mark.asyncio
async def test_complete_count_metadata_only_latest_revision_deleted_and_owner(db_session):
    for i in range(25):
        await seed(db_session, f'd{i}')
    await seed(db_session,'d0',version=2)
    await seed(db_session,'alien',user='other')
    await seed(db_session,'hidden',privacy='NEVER_UPLOAD')
    await seed(db_session,'deleted')
    (await db_session.get(Document,'deleted')).is_deleted=True
    # Filename and alias alone are intentionally not title matches.
    await seed(db_session,'reconocimiento-file',title='Factura')
    (await db_session.get(Document,'reconocimiento-file')).alias='Reconocimiento'
    await db_session.commit()
    statements=[]
    from sqlalchemy import event
    engine=db_session.bind.sync_engine
    def record(conn,cursor,statement,parameters,context,executemany): statements.append(statement)
    event.listen(engine,'before_cursor_execute',record)
    try:
        result=await answer(db_session,'Cuenta los documentos con título reconocimientos')
    finally:
        event.remove(engine,'before_cursor_execute',record)
    assert '**25 documentos**' in result and '20 de 25' in result
    assert '/d0/versions/2/download' in result
    assert not any('extracted_text' in sql or 'sha256_hash' in sql for sql in statements)
    assert 'alien' not in result and 'hidden' not in result

@pytest.mark.asyncio
async def test_no_grant_no_content_no_duplicate_claim(db_session):
    await seed(db_session,'one')
    await seed(db_session,'two')
    result=await answer(db_session)
    assert '**2 documentos**' in result and '**0 de 2 documentos autorizados**' in result
    assert '0 grupos; 0 copias adicionales' in result
    assert '/autorizar one' in result and 'No leí su contenido' in result
    assert 'Pedro Ibarra' not in result

@pytest.mark.asyncio
async def test_exact_text_copies_similarity_and_distinct_awards(db_session):
    await seed(db_session,'one',privacy='SAFE')
    await seed(db_session,'scan',text=TEXT.upper().replace(' ', '\n'),privacy='SAFE')
    await seed(db_session,'different-person',text=TEXT.replace('Pedro Ibarra','Miguel Pérez').replace('A123','A124'),privacy='SAFE')
    await seed(db_session,'unrelated',text='Un documento completamente distinto acerca del aprendizaje, la tecnología y una conferencia de física, con otro propósito y distinta evidencia.',privacy='SAFE')
    result=await answer(db_session)
    assert '**4 de 4 documentos autorizados**' in result
    assert '1 grupos; 1 copias adicionales' in result
    assert 'sin confirmar como duplicados' in result
    assert 'No eliminé ni fusioné' in result
    assert 'no acredita cuántos reconocimientos distintos' in result

@pytest.mark.asyncio
async def test_binary_copies_without_text(db_session):
    for key in ('one','two'):
        await seed(db_session,key,text=None,privacy='SAFE',digest='a'*64)
    result=await answer(db_session)
    assert '1 grupos; 1 copias adicionales' in result
    assert '2 documentos autorizados no tienen suficiente texto' in result

@pytest.mark.asyncio
async def test_invalid_empty_hash_never_merges(db_session):
    await seed(db_session,'one',text=None,privacy='SAFE',digest='invalid')
    await seed(db_session,'two',text=None,privacy='SAFE',digest='invalid')
    assert '0 grupos; 0 copias adicionales' in await answer(db_session)

@pytest.mark.asyncio
async def test_grants_device_revision_revocation_and_never_upload(db_session):
    db_session.add(Device(id='phone',user_id='owner',device_name='test'))
    await db_session.commit()
    for key in ('one','two'):
        await seed(db_session,key)
        await set_context_access(db_session,'owner','phone',key,key+'-v1',True)
    await db_session.commit()
    assert '1 grupos; 1 copias adicionales' in await answer(db_session)
    assert '**0 de 2 documentos autorizados**' in await answer(db_session,recipient='device:other')
    await seed(db_session,'two',version=2)
    assert '**1 de 2 documentos autorizados**' in await answer(db_session)
    await set_context_access(db_session,'owner','phone','one','one-v1',False)
    await db_session.commit()
    assert '**0 de 2 documentos autorizados**' in await answer(db_session)
    (await db_session.get(DocumentOrigin,'two')).privacy_class='NEVER_UPLOAD'
    await db_session.commit()
    assert '**1 documentos**' in await answer(db_session)

@pytest.mark.asyncio
async def test_no_revision_count_and_zero_matches(db_session):
    db_session.add(Document(id='draft',user_id='owner',title='Reconocimiento sin versión'))
    await db_session.commit()
    assert '**1 documentos**' in await answer(db_session)
    assert 'sin versión descargable' in await answer(db_session)
    assert '**0 documentos**' in await answer(db_session,'Cuántos documentos con título facturas tengo')

@pytest.mark.asyncio
async def test_installed_mobile_sse_count_does_not_call_model(client,db_session):
    import json
    pair=(await client.post('/v1/auth/pair',json={
        'pairing_code':(await client.post('/v1/auth/challenge')).json()['pairing_code'],
        'device_name':'Installed Android','platform':'android'})).json()
    await seed(db_session,'mobile',user='default_user')
    with patch('app.services.chat_orchestrator.stream_chat_completion') as model:
        response=await client.post('/v1/chat/stream',headers={'Authorization':'Bearer '+pair['access_token']},json={
            'message':'Cuántos reconocimientos he obtenido','date':'2026-10-15','history':[]})
    assert response.status_code==200
    events=[json.loads(line[6:]) for line in response.text.splitlines() if line.startswith('data: ')]
    text=''.join(e.get('content','') for e in events if e['type']=='token')
    assert '**1 documentos**' in text and '**0 de 1 documentos autorizados**' in text
    assert any(e['type']=='done' for e in events)
    assert not any(e['type'] in ('error','proposal') for e in events)
    model.assert_not_called()
