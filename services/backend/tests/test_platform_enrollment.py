import asyncio
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from pydantic import SecretStr
from sqlalchemy import select
from app.config import settings
from app.models.canonical import Device, AuthToken, EnrollmentReceipt, Document, DocumentRevision, DocumentContextGrant, DocumentOrigin
from app.models.document import UploadInitRequest
from app.services.document_storage import DocumentStorageService

@pytest.fixture
def enrollment(monkeypatch):
    monkeypatch.setattr(settings, "platform_enrollment_key", SecretStr("private-test-enrollment-key"))
    monkeypatch.setattr(settings, "allow_anonymous_fallback", False)
    return {"X-Enrollment-Key": "private-test-enrollment-key"}

@pytest.mark.asyncio
async def test_enrollment_secret_and_durable_retry(client, db_session, enrollment):
    body = {"operation_id":"retry-operation", "user_id":"owner", "device_name":"Phone"}
    assert (await client.post("/internal/enroll",json=body)).status_code == 403
    first = await client.post("/internal/enroll",json=body,headers=enrollment)
    assert first.status_code == 200
    assert (await client.post("/internal/enroll",json=body,headers=enrollment)).json() == first.json()
    conflict = await client.post("/internal/enroll",json={**body,"user_id":"other"},headers=enrollment)
    assert conflict.status_code == 409
    receipt = await db_session.get(EnrollmentReceipt,body["operation_id"])
    assert first.json()["access_token"] not in receipt.response_ciphertext
    assert len((await db_session.execute(select(Device))).scalars().all()) == 1
    assert len((await db_session.execute(select(AuthToken))).scalars().all()) == 2
    me = await client.get("/v1/auth/me",headers={"Authorization":"Bearer "+first.json()["access_token"]})
    assert me.json()["user_id"] == "owner"

@pytest.mark.asyncio
async def test_device_reconnection_and_revocation_require_same_owner(client,db_session,enrollment):
    first = (await client.post("/internal/enroll",headers=enrollment,json={"operation_id":"first", "user_id":"alice", "device_name":"Alice"})).json()
    second = (await client.post("/internal/enroll",headers=enrollment,json={"operation_id":"second", "user_id":"bob", "device_name":"Bob"})).json()
    forbidden = await client.post("/internal/enroll",headers=enrollment,json={"operation_id":"wrong", "user_id":"alice", "device_name":"New", "replace_device_id":second["device_id"]})
    assert forbidden.status_code == 400
    auth={"Authorization":"Bearer "+first["access_token"]}
    devices=await client.get("/v1/devices",headers=auth)
    assert [x["id"] for x in devices.json()["devices"]] == [first["device_id"]]
    assert (await client.post("/v1/auth/revoke",headers=auth,json={"device_id":second["device_id"]})).status_code == 400
    assert (await db_session.get(Device,second["device_id"])).is_active

@pytest.mark.asyncio
async def test_master_secret_is_not_a_pairing_code(client,enrollment):
    response=await client.post("/v1/auth/pair",json={"pairing_code":settings.secret_key,"device_name":"Phone"})
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_concurrent_receipt_retries_create_exactly_one_device(client, db_session, enrollment):
    body = {"operation_id": "concurrent-retry", "user_id": "owner", "device_name": "Synthetic phone"}
    responses = await asyncio.gather(*(client.post("/internal/enroll", json=body, headers=enrollment) for _ in range(4)))
    assert all(response.status_code == 200 for response in responses)
    assert all(response.json() == responses[0].json() for response in responses)
    assert len((await db_session.execute(select(Device))).scalars().all()) == 1
    assert len((await db_session.execute(select(AuthToken))).scalars().all()) == 2
    assert len((await db_session.execute(select(EnrollmentReceipt))).scalars().all()) == 1


@pytest.mark.asyncio
async def test_expired_receipt_does_not_reenroll_or_emit_new_credentials(client, db_session, enrollment):
    body = {"operation_id": "expired-retry", "user_id": "owner", "device_name": "Synthetic phone"}
    assert (await client.post("/internal/enroll", json=body, headers=enrollment)).status_code == 200
    receipt = await db_session.get(EnrollmentReceipt, body["operation_id"])
    receipt.expires_at = datetime.utcnow() - timedelta(seconds=1)
    await db_session.commit()
    assert (await client.post("/internal/enroll", json=body, headers=enrollment)).status_code == 410
    assert len((await db_session.execute(select(AuthToken))).scalars().all()) == 2


@pytest.mark.asyncio
async def test_refresh_credential_cannot_be_used_as_access_or_revoke_devices(client, enrollment):
    activation = (await client.post("/internal/enroll", headers=enrollment, json={"operation_id": "refresh-only", "user_id": "owner", "device_name": "Phone"})).json()
    refresh_headers = {"Authorization": "Bearer " + activation["refresh_token"]}
    assert (await client.get("/v1/auth/me", headers=refresh_headers)).status_code == 401
    assert (await client.get("/v1/devices", headers=refresh_headers)).status_code == 401
    assert (await client.post("/v1/auth/revoke", headers=refresh_headers, json={"device_id": activation["device_id"]})).status_code == 401
    assert (await client.post("/v1/auth/refresh", json={"refresh_token": activation["refresh_token"]})).status_code == 200


async def synthetic_document(session, key, *, user="alice", privacy="OPT_IN", deleted=False):
    doc = Document(id=key, user_id=user, title="Synthetic private document", is_deleted=deleted)
    session.add(doc)
    await session.flush()
    revision = DocumentRevision(id=key + "-v1", document_id=key, version=1, storage_path="/unused", original_filename="test.txt", mime_type="text/plain", file_size_bytes=1, sha256_hash="a" * 64, extraction_status="ready", extracted_text="astrofísica sintética")
    session.add(revision)
    if privacy:
        session.add(DocumentOrigin(document_id=key, source_collection="synthetic", source_path="synthetic.txt", privacy_class=privacy, source_kind="reference"))
    await session.commit()
    return doc, revision


@pytest.mark.asyncio
async def test_reconnection_copies_only_authorized_original_revisions(client, db_session, enrollment):
    first = (await client.post("/internal/enroll", headers=enrollment, json={"operation_id": "old-phone", "user_id": "alice", "device_name": "Old"})).json()
    old_id = first["device_id"]
    for key, kwargs in [
        ("allowed", {}), ("never", {"privacy": "NEVER_UPLOAD"}),
        ("unclassified", {"privacy": None}), ("unknown", {"privacy": "UNKNOWN"}),
        ("deleted", {"deleted": True}), ("foreign", {"user": "bob"}),
        ("revoked", {}), ("wrong-recipient", {}), ("invalid-revision", {}),
    ]:
        doc, revision = await synthetic_document(db_session, key, **kwargs)
        db_session.add(DocumentContextGrant(
            id="grant-" + key, user_id="alice", document_id=doc.id,
            revision_id="allowed-v1" if key == "invalid-revision" else revision.id,
            recipient_id="device:somebody-else" if key == "wrong-recipient" else "device:" + old_id,
            reason="Synthetic explicit grant", revoked_at=datetime.utcnow() if key == "revoked" else None))
    await db_session.commit()
    response = await client.post("/internal/enroll", headers=enrollment, json={"operation_id": "reconnect-phone", "user_id": "alice", "device_name": "New", "replace_device_id": old_id})
    assert response.status_code == 200
    new_id = response.json()["device_id"]
    grants = (await db_session.execute(select(DocumentContextGrant).where(DocumentContextGrant.recipient_id == "device:" + new_id))).scalars().all()
    assert [(grant.document_id, grant.revision_id, grant.user_id) for grant in grants] == [("allowed", "allowed-v1", "alice")]
    assert (await db_session.get(Device, old_id)).is_active  # The caller verifies the new session before revoking the old phone.
    from app.services.document_retrieval import document_retrieval
    assert await document_retrieval.search(db_session, "alice", "astrofísica", recipient_id="device:" + new_id)
    db_session.add(DocumentRevision(id="allowed-v2", document_id="allowed", version=2, storage_path="/unused", original_filename="new.txt", mime_type="text/plain", file_size_bytes=1, sha256_hash="b" * 64, extraction_status="ready", extracted_text="astrofísica versión futura"))
    await db_session.commit()
    assert not await document_retrieval.search(db_session, "alice", "astrofísica", recipient_id="device:" + new_id)


def test_quota_accounts_for_active_reservations_and_orphaned_partial_files(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "storage_path", str(tmp_path))
    monkeypatch.setattr(settings, "storage_quota_bytes", 10)
    store = DocumentStorageService()
    (tmp_path / "documents" / "existing").write_bytes(b"123")
    store.start_upload_session("alice", UploadInitRequest(filename="reserved.txt", mime_type="text/plain", expected_size_bytes=7))
    with pytest.raises(ValueError, match="cuota"):
        store.start_upload_session("alice", UploadInitRequest(filename="extra.txt", mime_type="text/plain", expected_size_bytes=1))
    # Restart loses in-memory reservation metadata, but the remaining partial file still consumes capacity.
    (tmp_path / "temp" / "upl-orphan.part").write_bytes(b"1234567")
    restarted = DocumentStorageService()
    with pytest.raises(ValueError, match="cuota"):
        restarted.start_upload_session("alice", UploadInitRequest(filename="extra.txt", mime_type="text/plain", expected_size_bytes=1))


@pytest.mark.asyncio
async def test_expired_upload_reservation_is_released_and_excess_chunk_is_discarded(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "storage_path", str(tmp_path))
    monkeypatch.setattr(settings, "storage_quota_bytes", 10)
    store = DocumentStorageService()
    initial = store.start_upload_session("alice", UploadInitRequest(filename="abandoned.txt", mime_type="text/plain", expected_size_bytes=10))
    store._sessions[initial.upload_id]["created_at"] = datetime.utcnow() - timedelta(days=2)
    replacement = store.start_upload_session("alice", UploadInitRequest(filename="replacement.txt", mime_type="text/plain", expected_size_bytes=10))
    assert initial.upload_id not in store._sessions
    assert not (tmp_path / "temp" / (initial.upload_id + ".part")).exists()
    with pytest.raises(ValueError, match="reservado"):
        await store.append_chunk(replacement.upload_id, "alice", b"x" * 11)
    assert not (tmp_path / "temp" / (replacement.upload_id + ".part")).exists()
    assert store.start_upload_session("alice", UploadInitRequest(filename="new.txt", mime_type="text/plain", expected_size_bytes=10))
