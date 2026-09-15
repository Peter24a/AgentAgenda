import pytest
from datetime import datetime, timedelta
from sqlalchemy import select
from app.models.canonical import (
    SyncHead, Device, AuthToken, AccessGrant, Event, Task, Reminder,
    Proposal, ChatTurn, ChatMessage, Document, DocumentRevision,
    DocumentRequirement, DocumentLink, Entity, Memory, MemorySource,
    OperationReceipt, ChangeBatch, DeviceRequest, DeviceObservation,
    Job, AuditEvent
)

@pytest.mark.asyncio
async def test_canonical_models_crud(db_session):
    # 1. SyncHead
    head = SyncHead(user_id="user-1", current_seq=42)
    db_session.add(head)
    await db_session.commit()
    
    res = await db_session.execute(select(SyncHead).where(SyncHead.user_id == "user-1"))
    stored_head = res.scalar_one()
    assert stored_head.current_seq == 42

    # 2. Device & AuthToken
    device = Device(id="dev-1", user_id="user-1", device_name="Pixel 9 Pro", platform="android", capabilities=["location", "calendar"])
    db_session.add(device)
    await db_session.flush()

    token = AuthToken(id="tok-1", device_id="dev-1", user_id="user-1", token_hash="hash123", scopes=["agenda:read", "agenda:write"], expires_at=datetime.utcnow() + timedelta(days=30))
    db_session.add(token)
    await db_session.commit()

    res = await db_session.execute(select(Device).where(Device.id == "dev-1"))
    assert res.scalar_one().device_name == "Pixel 9 Pro"

    # 3. Events & Tasks
    now = datetime.utcnow()
    event = Event(id="evt-1", user_id="user-1", title="Reunión de equipo", start_time=now, timezone="America/Mexico_City", category="work")
    task = Task(id="tsk-1", user_id="user-1", title="Preparar reporte", priority="high", due_date=now + timedelta(days=1))
    db_session.add_all([event, task])
    await db_session.commit()

    res_evt = await db_session.execute(select(Event).where(Event.id == "evt-1"))
    assert res_evt.scalar_one().timezone == "America/Mexico_City"

    # 4. Reminders & Proposals
    reminder = Reminder(id="rem-1", user_id="user-1", event_id="evt-1", remind_at=now - timedelta(minutes=30), offset_minutes=30)
    proposal = Proposal(id="prop-1", user_id="user-1", summary="Ajustar agenda", reason="Optimizar descanso", resulting_items=[{"title": "Descanso", "start_time": now.isoformat()}])
    db_session.add_all([reminder, proposal])
    await db_session.commit()

    # 5. Chat Turns & Messages
    turn = ChatTurn(id="turn-1", user_id="user-1", client_message_id="msg-client-1", status="completed")
    db_session.add(turn)
    await db_session.flush()

    msg1 = ChatMessage(id="msg-1", turn_id="turn-1", user_id="user-1", role="user", content="¿Qué tengo para hoy?", received_at=now)
    msg2 = ChatMessage(id="msg-2", turn_id="turn-1", user_id="user-1", role="assistant", content="Tienes una reunión.", received_at=now)
    db_session.add_all([msg1, msg2])
    await db_session.commit()

    # 6. Documents & Revisions
    doc = Document(id="doc-1", user_id="user-1", title="Constancia de Curso", doc_type="constancia")
    db_session.add(doc)
    await db_session.flush()

    rev = DocumentRevision(id="rev-1", document_id="doc-1", version=1, storage_path="/storage/doc-1-v1.pdf", original_filename="curso.pdf", mime_type="application/pdf", file_size_bytes=1024, sha256_hash="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855")
    db_session.add(rev)
    await db_session.commit()

    # 7. Document Requirements & Links
    req = DocumentRequirement(id="req-1", user_id="user-1", event_id="evt-1", title="Constancia requerida", status="candidate")
    db_session.add(req)
    await db_session.flush()

    link = DocumentLink(id="lnk-1", requirement_id="req-1", document_id="doc-1", revision_id="rev-1", status="verified")
    db_session.add(link)
    await db_session.commit()

    # 8. Entities, Memories & Memory Sources
    entity = Entity(id="ent-1", user_id="user-1", name="Proyecto Alpha", entity_type="project")
    db_session.add(entity)
    await db_session.flush()

    memory = Memory(id="mem-1", user_id="user-1", memory_type="semantic", subject_id="ent-1", predicate="status", value="activo")
    db_session.add(memory)
    await db_session.flush()

    mem_src = MemorySource(id="ms-1", memory_id="mem-1", source_kind="message", source_id="msg-1")
    db_session.add(mem_src)
    await db_session.commit()

    # 9. Receipts & Change Batches (Sync)
    receipt = OperationReceipt(operation_id="op-1", user_id="user-1", operation_epoch="epoch-1", canonical_hash="hash-abc", status="applied")
    batch = ChangeBatch(id="cb-1", user_id="user-1", commit_seq=1, entity_type="event", entity_id="evt-1", change_type="create", payload_json={"title": "Reunión"})
    db_session.add_all([receipt, batch])
    await db_session.commit()

    # 10. Device Requests & Observations
    dev_req = DeviceRequest(id="dreq-1", user_id="user-1", device_id="dev-1", capability="location", purpose="Contexto", expires_at=now + timedelta(minutes=5))
    obs = DeviceObservation(id="obs-1", user_id="user-1", device_id="dev-1", request_id="dreq-1", capability="location", payload_json={"lat": 19.43, "lng": -99.13}, observed_at=now)
    db_session.add_all([dev_req, obs])
    await db_session.commit()

    # 11. Jobs & Audit Events
    job = Job(id="job-1", job_type="reminder_dispatch", payload_json={"reminder_id": "rem-1"}, status="pending")
    audit = AuditEvent(id="aud-1", user_id="user-1", event_type="login", details_json={"ip": "127.0.0.1"})
    db_session.add_all([job, audit])
    await db_session.commit()

    # Verify counts
    res_jobs = await db_session.execute(select(Job).where(Job.id == "job-1"))
    assert res_jobs.scalar_one().status == "pending"

@pytest.mark.asyncio
async def test_transactional_rollback(db_session):
    event = Event(id="evt-rollback", user_id="user-1", title="Test Rollback", start_time=datetime.utcnow(), timezone="America/Mexico_City")
    db_session.add(event)
    await db_session.flush()

    # Intentionally trigger rollback
    await db_session.rollback()

    res = await db_session.execute(select(Event).where(Event.id == "evt-rollback"))
    assert res.scalar_one_or_none() is None
