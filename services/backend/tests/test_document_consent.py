from datetime import datetime, timedelta
from unittest.mock import patch

import pytest
from sqlalchemy import select

from app.core.security import hash_token
from app.models.canonical import (
    AuthToken, ChatPendingAction, Device, Document, DocumentContextGrant,
    DocumentOrigin, DocumentRevision, Memory, MemorySource,
)
from app.services.document_consent import (
    DocumentConsentError, context_access_state, handle_document_consent,
    set_context_access,
)
from app.services.document_retrieval import document_retrieval
from app.services.context_engine import context_engine


async def seed(session, *, privacy=None, title="Factura octubre", key="invoice", user="owner", device="phone"):
    if not await session.get(Device, device):
        session.add(Device(id=device, user_id=user, device_name="Synthetic phone"))
    session.add(Document(id=key, user_id=user, title=title))
    await session.flush()
    session.add(DocumentRevision(
        id=f"{key}-v1", document_id=key, version=1, storage_path="/not-read",
        original_filename=f"{key}.pdf", mime_type="application/pdf",
        file_size_bytes=10, sha256_hash="a" * 64,
        extracted_text="La factura tiene un importe de 1847 pesos.", extraction_status="ready",
    ))
    if privacy:
        session.add(DocumentOrigin(document_id=key, source_collection="synthetic",
                                   source_path="unused", source_kind="manual", privacy_class=privacy))
    await session.commit()


async def read(session, *, device="phone", user="owner"):
    return await document_retrieval.search(session, user, "factura importe pesos", recipient_id=f"device:{device}")


@pytest.mark.asyncio
async def test_chat_consent_is_explicit_durable_and_scoped_to_revision_device_owner(db_session):
    await seed(db_session)
    await seed(db_session, key="other", title="Otro documento")
    await seed(db_session, key="foreign", title="Factura octubre", user="other-owner", device="foreign-phone")
    assert not await read(db_session)
    prompt = await handle_document_consent(db_session, "owner", "phone", "analiza el documento Factura octubre")
    assert "¿Autorizas" in prompt.reply
    assert prompt.retrieval_query is None
    assert not await read(db_session)
    assert not (await db_session.scalars(select(DocumentContextGrant))).all()
    assert await db_session.scalar(select(ChatPendingAction.id))
    # Another device cannot consume the first device's question.
    db_session.add(Device(id="other-phone", user_id="owner", device_name="Other"))
    await db_session.commit()
    assert (await handle_document_consent(db_session, "owner", "other-phone", "sí, autorizo")).retrieval_query is None
    approved = await handle_document_consent(db_session, "owner", "phone", "sí, autorizo")
    assert approved.authorized_document_id == "invoice"
    assert "Factura octubre" in approved.retrieval_query
    assert {p.document_id for p in await read(db_session)} == {"invoice"}
    assert not await read(db_session, device="other-phone")
    assert not await read(db_session, user="other-owner")
    assert (await db_session.get(DocumentOrigin, "invoice")).privacy_class == "OPT_IN"
    assert not await db_session.get(DocumentOrigin, "other")
    # Upgrading the original creates a new consent boundary.
    db_session.add(DocumentRevision(id="invoice-v2", document_id="invoice", version=2,
        storage_path="/not-read", original_filename="invoice.pdf", mime_type="application/pdf",
        file_size_bytes=10, sha256_hash="b" * 64, extracted_text="factura nueva 999", extraction_status="ready"))
    await db_session.commit()
    assert not await read(db_session)
    assert "¿Autorizas" in (await handle_document_consent(db_session, "owner", "phone", "lee el documento Factura octubre")).reply


@pytest.mark.asyncio
async def test_direct_grant_revoke_regrant_keeps_revocation_barrier(db_session):
    await seed(db_session)
    t0 = datetime(2026, 10, 15, 12)
    result = await handle_document_consent(db_session, "owner", "phone", "/autorizar invoice", now=t0)
    assert result.authorized_document_id == "invoice"
    assert await read(db_session)
    revoked = await handle_document_consent(db_session, "owner", "phone", "/revocar invoice", now=t0 + timedelta(minutes=1))
    assert revoked.revoked
    assert not await read(db_session)
    await handle_document_consent(db_session, "owner", "phone", "autorizo analizar el documento invoice", now=t0 + timedelta(minutes=2))
    assert await read(db_session)
    grants = (await db_session.scalars(select(DocumentContextGrant))).all()
    assert len(grants) == 2
    assert sum(g.revoked_at is not None for g in grants) == 1


@pytest.mark.asyncio
async def test_safe_origin_can_be_revoked_for_one_device_and_never_upload_always_wins(db_session):
    await seed(db_session, privacy="SAFE")
    assert await read(db_session)
    await set_context_access(db_session, "owner", "phone", "invoice", "invoice-v1", False)
    assert not await read(db_session)
    assert await read(db_session, device="another")  # SAFE remains available to other recipients.
    await set_context_access(db_session, "owner", "phone", "invoice", "invoice-v1", True)
    assert await read(db_session)
    origin = await db_session.get(DocumentOrigin, "invoice")
    origin.privacy_class = "NEVER_UPLOAD"
    await db_session.commit()
    assert not await read(db_session)
    blocked = await handle_document_consent(db_session, "owner", "phone", "/autorizar invoice")
    assert "NEVER_UPLOAD" in blocked.reply
    with pytest.raises(DocumentConsentError):
        await set_context_access(db_session, "owner", "phone", "invoice", "invoice-v1", True)


@pytest.mark.asyncio
async def test_ambiguous_catalogue_selection_still_needs_consent_and_cancel_does_not_grant(db_session):
    await seed(db_session)
    await seed(db_session, key="second", title="Factura noviembre")
    ask = await handle_document_consent(db_session, "owner", "phone", "analiza la factura")
    assert "¿A cuál" in ask.reply
    selected = await handle_document_consent(db_session, "owner", "phone", "Factura octubre")
    assert "¿Autorizas" in selected.reply
    assert not await read(db_session)
    declined = await handle_document_consent(db_session, "owner", "phone", "no")
    assert "no autoricé" in declined.reply
    assert not await read(db_session)


@pytest.mark.asyncio
async def test_expired_or_interrupted_question_and_changed_revision_cannot_be_approved(db_session):
    await seed(db_session)
    t0 = datetime(2026, 10, 15, 12)
    await handle_document_consent(db_session, "owner", "phone", "analiza documento invoice", now=t0)
    expired = await handle_document_consent(db_session, "owner", "phone", "sí, autorizo", now=t0 + timedelta(minutes=16))
    assert not expired.retrieval_query
    assert not await read(db_session)
    await handle_document_consent(db_session, "owner", "phone", "analiza documento invoice", now=t0)
    await handle_document_consent(db_session, "owner", "phone", "agenda una llamada mañana", now=t0)
    assert not (await handle_document_consent(db_session, "owner", "phone", "sí, autorizo", now=t0)).retrieval_query
    await handle_document_consent(db_session, "owner", "phone", "analiza documento invoice", now=t0)
    db_session.add(DocumentRevision(id="invoice-v2", document_id="invoice", version=2,
        storage_path="/unused", original_filename="invoice.pdf", mime_type="application/pdf",
        file_size_bytes=10, sha256_hash="b" * 64, extraction_status="pending"))
    await db_session.commit()
    changed = await handle_document_consent(db_session, "owner", "phone", "sí, autorizo", now=t0)
    assert "otra versión" in changed.reply
    assert not (await db_session.scalars(select(DocumentContextGrant))).all()


@pytest.mark.asyncio
@pytest.mark.parametrize("device,can_authorize", [(None, True), ("missing", True), ("phone", False), ("foreign", True)])
async def test_cannot_authorize_without_registered_owned_device_and_write_scope(db_session, device, can_authorize):
    await seed(db_session)
    db_session.add(Device(id="foreign", user_id="someone-else", device_name="Other"))
    await db_session.commit()
    denied = await handle_document_consent(db_session, "owner", device, "/autorizar invoice", can_authorize=can_authorize)
    assert denied.reply and not denied.retrieval_query
    assert not (await db_session.scalars(select(DocumentContextGrant))).all()


@pytest.mark.asyncio
async def test_inactive_device_is_denied_and_pending_extraction_is_explained(db_session):
    await seed(db_session)
    revision = await db_session.get(DocumentRevision, "invoice-v1")
    revision.extraction_status = "pending"
    await db_session.commit()
    result = await handle_document_consent(db_session, "owner", "phone", "/autorizar invoice")
    assert "todavía se está procesando" in result.reply
    device = await db_session.get(Device, "phone")
    device.is_active = False
    await db_session.commit()
    assert "activo" in (await handle_document_consent(db_session, "owner", "phone", "/autorizar invoice")).reply


@pytest.mark.asyncio
async def test_context_access_api_requires_explicit_auth_scope_device_and_owned_revision(client, db_session):
    await seed(db_session)
    await seed(db_session, key="foreign", user="someone-else", device="foreign-phone")
    tokens = {"full": ["documents:read", "documents:write"], "read": ["documents:read"], "write": ["documents:write"]}
    for name, scopes in tokens.items():
        db_session.add(AuthToken(id=name, device_id="phone", user_id="owner", token_hash=hash_token(name),
            scopes=scopes, expires_at=datetime.utcnow() + timedelta(hours=1)))
    await db_session.commit()
    path = "/v1/documents/invoice/context-access"
    body = {"revision_id": "invoice-v1", "authorized": True}
    assert (await client.put(path, json=body)).status_code == 401
    for token in ("read", "write"):
        assert (await client.put(path, json=body, headers={"Authorization": f"Bearer {token}"})).status_code == 403
    headers = {"Authorization": "Bearer full"}
    assert not (await client.get(path, headers=headers)).json()["authorized"]
    assert (await client.put(path, json={**body, "revision_id": "foreign-v1"}, headers=headers)).status_code == 409
    assert (await client.put("/v1/documents/foreign/context-access", json={**body, "revision_id": "foreign-v1"}, headers=headers)).status_code == 404
    authorized = await client.put(path, json=body, headers=headers)
    assert authorized.status_code == 200 and authorized.json()["authorized"]
    revoked = await client.put(path, json={**body, "authorized": False}, headers=headers)
    assert revoked.status_code == 200 and not revoked.json()["authorized"]


@pytest.mark.asyncio
async def test_read_only_session_can_read_existing_permission_but_not_grant(db_session):
    await seed(db_session, privacy="SAFE")
    result = await handle_document_consent(db_session, "owner", "phone", "lee documento invoice", can_authorize=False)
    assert result.authorized_document_id == "invoice"
    await seed(db_session, key="private", title="Privado")
    denied = await handle_document_consent(db_session, "owner", "phone", "lee documento private", can_authorize=False)
    assert "no tiene permiso" in denied.reply
    assert not await db_session.scalar(select(DocumentContextGrant.id))


@pytest.mark.asyncio
async def test_document_revocation_removes_derived_memories_for_recipient(db_session):
    await seed(db_session, privacy="SAFE")
    for key, source_id in (("doc-fact", "invoice"), ("rev-fact", "invoice-v1")):
        db_session.add(Memory(id=key, user_id="owner", memory_type="semantic", predicate="importe",
                             value=f"Dato documental {key}", source_kind="document", status="active"))
        await db_session.flush()
        db_session.add(MemorySource(id=f"source-{key}", memory_id=key, source_kind="document", source_id=source_id))
    await db_session.commit()
    async def context(recipient="device:phone"):
        return await context_engine.memory_context(db_session, "owner", recipient_id=recipient)
    before = await context()
    assert "doc-fact" in before and "rev-fact" in before
    await set_context_access(db_session, "owner", "phone", "invoice", "invoice-v1", False)
    assert not await context()
    assert "doc-fact" in await context("device:another")
    assert "rev-fact" in await context("device:another")
    # Exports with no recipient preserve their SAFE-only policy.
    assert "doc-fact" in await context(None)
    await set_context_access(db_session, "owner", "phone", "invoice", "invoice-v1", True)
    after = await context()
    assert "rev-fact" in after
    # An ID without the source revision cannot prove the reauthorized version.
    assert "doc-fact" not in after


@pytest.mark.asyncio
async def test_opt_in_memory_requires_exact_source_revision_and_recipient(db_session):
    await seed(db_session, privacy="OPT_IN")
    for key, source_id in (("unknown-version", "invoice"), ("exact-version", "invoice-v1")):
        db_session.add(Memory(id=key, user_id="owner", memory_type="semantic", predicate="importe",
                             value=key, source_kind="document", status="active"))
        await db_session.flush()
        db_session.add(MemorySource(id=f"source-{key}", memory_id=key, source_kind="document", source_id=source_id))
    await db_session.commit()
    await set_context_access(db_session, "owner", "phone", "invoice", "invoice-v1", True)
    allowed = await context_engine.memory_context(db_session, "owner", recipient_id="device:phone")
    assert "exact-version" in allowed and "unknown-version" not in allowed
    assert not await context_engine.memory_context(db_session, "owner", recipient_id="device:another")
    assert not await context_engine.memory_context(db_session, "owner")


@pytest.mark.asyncio
async def test_installed_chat_protocol_asks_before_model_then_analyzes_and_revokes(client, db_session):
    await seed(db_session)
    db_session.add(AuthToken(
        id="chat-consent-token", user_id="owner", device_id="phone",
        token_hash=hash_token("chat-consent-token"),
        scopes=["chat:write", "chat:read", "agenda:read", "memory:read", "documents:read", "documents:write"],
        expires_at=datetime.utcnow() + timedelta(hours=1),
    ))
    await db_session.commit()
    headers = {"Authorization": "Bearer chat-consent-token"}
    model_inputs = []

    async def model(messages, **kwargs):
        model_inputs.append(str(messages))
        yield "Respuesta sintética del asistente."

    async def chat(message, key):
        created = await client.post("/v1/chat/turns", headers=headers,
                                    json={"message": message, "client_message_id": key})
        assert created.status_code == 200
        turn_id = created.json()["turn_id"]
        stream = await client.get(f"/v1/chat/turns/{turn_id}/stream", headers=headers)
        assert stream.status_code == 200
        result = (await client.get(f"/v1/chat/turns/{turn_id}", headers=headers)).json()
        assert result["status"] == "completed", result
        return result

    with patch("app.services.chat_orchestrator.stream_chat_completion", side_effect=model):
        requested = await chat("analiza el documento invoice", "consent-request")
        assert "¿Autorizas" in requested["assistant_message"]
        assert not model_inputs
        approved = await chat("sí, autorizo", "consent-approved")
        assert "Respuesta sintética" in approved["assistant_message"]
        assert len(model_inputs) == 1 and "1847" in model_inputs[0]
        await chat("/revocar invoice", "consent-revoked")
        assert len(model_inputs) == 1
        await chat("¿Cuál es el importe de la factura?", "consent-after-revoke")
        assert len(model_inputs) == 2 and "1847" not in model_inputs[-1]
