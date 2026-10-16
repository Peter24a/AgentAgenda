import asyncio
from unittest.mock import patch
import pytest
import pytest_asyncio
from sqlalchemy import select

from app.models.canonical import ChatMessage, ChatTurn


@pytest_asyncio.fixture
async def auth_headers(client):
    ch = await client.post("/v1/auth/challenge")
    code = ch.json()["pairing_code"]
    pair = await client.post(
        "/v1/auth/pair",
        json={
            "pairing_code": code,
            "device_name": "Pixel Chat Test",
            "platform": "android",
        },
    )
    token = pair.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


async def mock_stream_chat_completion(messages, temperature=0.7, max_tokens=1024):
    """Simulador de inferencia LLM para pruebas deterministas rápidas."""
    tokens = ["Hola, ", "te ", "ayudo ", "a ", "organizar ", "tu ", "agenda."]
    for tok in tokens:
        await asyncio.sleep(0.01)
        yield tok

    # Si el usuario pide agendar o propuesta, incluir bloque ```proposal ... ```
    last_msg = messages[-1]["content"] if messages else ""
    if "reunión" in last_msg.lower() or "cita" in last_msg.lower():
        yield "\n\n```proposal\n"
        yield '{\n  "summary": "Reunión de prueba",\n  "reason": "Coordinación",\n  "items": [\n'
        yield '    {\n      "id": "evt-mock-01",\n      "title": "Reunión de prueba",\n      "category": "work",\n'
        yield '      "start_time": "2026-09-15T15:00:00",\n      "end_time": "2026-09-15T16:00:00"\n    }\n'
        yield '  ]\n}\n```'


@pytest.mark.asyncio
async def test_create_chat_turn_persists_immediately(client, auth_headers):
    with patch("app.services.chat_orchestrator.stream_chat_completion", side_effect=mock_stream_chat_completion):
        res = await client.post(
            "/v1/chat/turns",
            json={"message": "¿Qué actividades tengo programadas?", "client_message_id": "client-msg-101"},
            headers=auth_headers,
        )
        assert res.status_code == 200
        data = res.json()
        assert "turn_id" in data
        assert data["client_message_id"] == "client-msg-101"
        assert data["user_message"] == "¿Qué actividades tengo programadas?"
        turn_id = data["turn_id"]

        # Consultar estado inmediato del turno
        get_res = await client.get(f"/v1/chat/turns/{turn_id}", headers=auth_headers)
        assert get_res.status_code == 200
        turn_data = get_res.json()
        assert turn_data["turn_id"] == turn_id
        assert turn_data["status"] in ("queued", "running", "completed")


@pytest.mark.asyncio
async def test_idempotent_turn_creation(client, auth_headers):
    with patch("app.services.chat_orchestrator.stream_chat_completion", side_effect=mock_stream_chat_completion):
        # 1. Primer envío con client_message_id
        res1 = await client.post(
            "/v1/chat/turns",
            json={"message": "Recordar comprar café", "client_message_id": "idem-coffee-99"},
            headers=auth_headers,
        )
        assert res1.status_code == 200
        turn_id_1 = res1.json()["turn_id"]

        # 2. Reintento con el mismo client_message_id -> debe devolver el MISMO turn_id sin duplicar
        res2 = await client.post(
            "/v1/chat/turns",
            json={"message": "Recordar comprar café", "client_message_id": "idem-coffee-99"},
            headers=auth_headers,
        )
        assert res2.status_code == 200
        turn_id_2 = res2.json()["turn_id"]
        assert turn_id_1 == turn_id_2


@pytest.mark.asyncio
async def test_turn_generation_and_sse_streaming(client, auth_headers):
    with patch("app.services.chat_orchestrator.stream_chat_completion", side_effect=mock_stream_chat_completion):
        # Crear turno que dispara propuesta
        create_res = await client.post(
            "/v1/chat/turns",
            json={"message": "Agenda una reunión mañana a las 3pm", "client_message_id": "client-meet-01"},
            headers=auth_headers,
        )
        turn_id = create_res.json()["turn_id"]

        # Conectar al stream SSE
        stream_res = await client.get(f"/v1/chat/turns/{turn_id}/stream", headers=auth_headers)
        assert stream_res.status_code == 200

        content_lines = stream_res.text.split("\n")
        data_lines = [line[6:] for line in content_lines if line.startswith("data: ")]
        import json
        events = [json.loads(d) for d in data_lines]

        event_types = [e["type"] for e in events]
        assert "status" in event_types
        assert "token" in event_types
        assert "proposal" in event_types
        assert "done" in event_types

        # Esperar a que la tarea en segundo plano termine de persistir
        await asyncio.sleep(0.1)

        # Consultar turno terminado
        done_turn = await client.get(f"/v1/chat/turns/{turn_id}", headers=auth_headers)
        done_data = done_turn.json()
        assert done_data["status"] == "completed"
        assert done_data["assistant_message"] is not None
        assert done_data["proposal"] is not None
        assert done_data["proposal"]["summary"] == "Reunión de prueba"


@pytest.mark.asyncio
async def test_client_disconnect_preserves_durable_persistence(client, auth_headers, db_session):
    with patch("app.services.chat_orchestrator.stream_chat_completion", side_effect=mock_stream_chat_completion):
        create_res = await client.post(
            "/v1/chat/turns",
            json={"message": "Pregunta de desconexión", "client_message_id": "disc-test-01"},
            headers=auth_headers,
        )
        turn_id = create_res.json()["turn_id"]

        # El cliente NO abre o corta de inmediato el stream SSE...
        # Esperamos a que el orquestador termine la generación en segundo plano
        for _ in range(50):
            await asyncio.sleep(0.05)
            check_res = await client.get(f"/v1/chat/turns/{turn_id}", headers=auth_headers)
            if check_res.json()["status"] == "completed":
                break

        final_turn = await client.get(f"/v1/chat/turns/{turn_id}", headers=auth_headers)
        assert final_turn.json()["status"] == "completed"
        assert "organizar tu agenda" in final_turn.json()["assistant_message"]

        # Verificar en base de datos que el mensaje del asistente existe
        res_msgs = await db_session.execute(
            select(ChatMessage).where(ChatMessage.turn_id == turn_id, ChatMessage.role == "assistant")
        )
        asst_msg = res_msgs.scalar_one_or_none()
        assert asst_msg is not None
        assert "organizar tu agenda" in asst_msg.content


@pytest.mark.asyncio
async def test_chat_messages_history_pagination(client, auth_headers):
    with patch("app.services.chat_orchestrator.stream_chat_completion", side_effect=mock_stream_chat_completion):
        # Crear 2 turnos
        await client.post(
            "/v1/chat/turns",
            json={"message": "Mensaje histórico 1", "client_message_id": "hist-1"},
            headers=auth_headers,
        )
        await client.post(
            "/v1/chat/turns",
            json={"message": "Mensaje histórico 2", "client_message_id": "hist-2"},
            headers=auth_headers,
        )

        # Esperar finalización
        await asyncio.sleep(0.1)

        # Consultar historial
        hist_res = await client.get("/v1/chat/messages?limit=10", headers=auth_headers)
        assert hist_res.status_code == 200
        msgs = hist_res.json()
        assert len(msgs) >= 2
        user_texts = [m["content"] for m in msgs if m["role"] == "user"]
        assert "Mensaje histórico 1" in user_texts
        assert "Mensaje histórico 2" in user_texts


@pytest.mark.asyncio
async def test_legacy_chat_stream_compatibility(client, auth_headers):
    with patch("app.services.chat_orchestrator.stream_chat_completion", side_effect=mock_stream_chat_completion):
        legacy_res = await client.post(
            "/v1/chat/stream",
            json={"message": "Hola agente", "date": "2026-09-15"},
            headers=auth_headers,
        )
        assert legacy_res.status_code == 200
        text = legacy_res.text
        assert "data: " in text
        assert "done" in text


@pytest.mark.asyncio
async def test_llm_failure_is_failed_turn_without_assistant_message(client, auth_headers):
    from app.services.llm_service import LLMError
    from app.services.chat_orchestrator import chat_orchestrator

    async def broken_stream(*args, **kwargs):
        yield 'partial'
        raise LLMError('Servicio no disponible')

    with patch('app.services.chat_orchestrator.stream_chat_completion', side_effect=broken_stream):
        res = await client.post('/v1/chat/turns', json={'message': 'test failure'}, headers=auth_headers)
        turn_id = res.json()['turn_id']
        task = chat_orchestrator._active_tasks.get(turn_id)
        if task:
            await task
        turn = (await client.get(f'/v1/chat/turns/{turn_id}', headers=auth_headers)).json()
        assert turn['status'] == 'failed'
        assert turn['assistant_message'] is None
        assert turn['error_message'] == 'Servicio no disponible'


@pytest.mark.asyncio
async def test_recovered_and_replayed_chat_proposal_remains_confirmable(client, auth_headers, db_session):
    import json
    from app.services.chat_orchestrator import ChatOrchestrator
    with patch('app.services.chat_orchestrator.stream_chat_completion', side_effect=mock_stream_chat_completion):
        payload = {'message': 'Agenda una reunión', 'client_message_id': 'recover-confirmable', 'timezone': 'America/Mexico_City'}
        created = (await client.post('/v1/chat/turns', json=payload, headers=auth_headers)).json()
        turn_id = created['turn_id']
        stream = await client.get(f'/v1/chat/turns/{turn_id}/stream', headers=auth_headers)
        events = [json.loads(line[6:]) for line in stream.text.splitlines() if line.startswith('data: ')]
        streamed = next(item['proposal'] for item in events if item['type'] == 'proposal')
        first = (await client.get(f'/v1/chat/turns/{turn_id}', headers=auth_headers)).json()
        second = (await client.get(f'/v1/chat/turns/{turn_id}', headers=auth_headers)).json()
        duplicate = (await client.post('/v1/chat/turns', json=payload, headers=auth_headers)).json()
        restarted = await ChatOrchestrator().get_turn_response(db_session, first['user_id'], turn_id)
        assert first['proposal'] == second['proposal'] == duplicate['proposal'] == streamed
        assert restarted.proposal.id == streamed['id']
        replay = await client.get(f'/v1/chat/turns/{turn_id}/stream', headers=auth_headers)
        replay_events = [json.loads(line[6:]) for line in replay.text.splitlines() if line.startswith('data: ')]
        assert next(item['proposal'] for item in replay_events if item['type'] == 'proposal')['id'] == streamed['id']
        confirmed = await client.post('/v1/proposals/'+streamed['id']+'/confirm', headers=auth_headers)
        assert confirmed.status_code == 200 and confirmed.json()['success']
        recovered = (await client.get(f'/v1/chat/turns/{turn_id}', headers=auth_headers)).json()
        assert recovered['proposal']['status'] == 'accepted'
        assert recovered['proposal']['id'] == streamed['id']
        agenda = (await client.get('/v1/agenda/events?date=2026-09-15', headers=auth_headers)).json()
        assert len([item for item in agenda if item['id'] == 'evt-mock-01']) == 1
        assert next(item for item in agenda if item['id'] == 'evt-mock-01')['start_time'].startswith('2026-09-15T21:00:00')


@pytest.mark.asyncio
@pytest.mark.parametrize('candidate_count', [0, 1, 2])
async def test_legacy_turn_recovers_only_unambiguous_persisted_proposal(client, auth_headers, db_session, candidate_count):
    import json
    from datetime import datetime, timedelta
    from app.models.canonical import Proposal
    owner = (await client.get('/v1/auth/me', headers=auth_headers)).json()['user_id']
    now = datetime.utcnow()
    raw_item = {'id': 'legacy-event', 'title': 'Legacy meeting', 'start_time': '2026-10-20T14:00:00', 'end_time': '2026-10-20T15:00:00', 'category': 'work'}
    content = '```proposal\n'+json.dumps({'summary': 'Legacy', 'reason': 'Test', 'items': [raw_item]})+'\n```'
    turn_id = 'legacy-turn'
    db_session.add(ChatTurn(id=turn_id, user_id=owner, status='completed', created_at=now-timedelta(seconds=2), completed_at=now))
    await db_session.flush()
    db_session.add(ChatMessage(id='legacy-message', turn_id=turn_id, user_id=owner, role='assistant', content=content, created_at=now, received_at=now))
    for index in range(candidate_count):
        db_session.add(Proposal(id=f'legacy-persisted-{index}', user_id=owner, summary='Legacy', reason='Test', resulting_items=[{**raw_item, 'start_time': '2026-10-20T14:00:00-06:00', 'end_time': '2026-10-20T15:00:00-06:00'}], status='pending', created_at=now-timedelta(seconds=1), updated_at=now))
    await db_session.commit()
    response = (await client.get(f'/v1/chat/turns/{turn_id}', headers=auth_headers)).json()
    if candidate_count == 1:
        assert response['proposal']['id'] == 'legacy-persisted-0'
        confirmed = await client.post('/v1/proposals/legacy-persisted-0/confirm', headers=auth_headers)
        assert confirmed.status_code == 200 and confirmed.json()['success']
    else:
        assert response['proposal'] is None
