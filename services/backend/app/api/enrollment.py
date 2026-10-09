"""Private, idempotent enrollment for the space control plane."""
import asyncio
import base64
import hashlib
import hmac
import json
import uuid
from datetime import datetime, timedelta

from cryptography.fernet import Fernet
from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db_session
from app.config import settings
from app.models.auth import PairRequest, PairResponse
from app.models.canonical import Device, Document, DocumentOrigin, DocumentRevision, DocumentContextGrant, EnrollmentReceipt
from app.services.auth_service import auth_service

router = APIRouter(prefix="/internal", include_in_schema=False)
_sqlite_lock = asyncio.Lock()

class EnrollmentRequest(BaseModel):
    operation_id: str = Field(min_length=1, max_length=128)
    user_id: str = Field(min_length=1, max_length=64)
    device_name: str = Field(min_length=1, max_length=128)
    platform: str = Field(default="android", max_length=32)
    client_device_id: str | None = Field(default=None, max_length=64)
    replace_device_id: str | None = Field(default=None, max_length=64)

async def enroll(session, req, secret):
    body_hash = hashlib.sha256(json.dumps(req.model_dump(), sort_keys=True).encode()).hexdigest()
    cipher = Fernet(base64.urlsafe_b64encode(hashlib.sha256(secret.encode()).digest()))
    now = datetime.utcnow()
    if session.bind.dialect.name == "postgresql":
        lock_id = int.from_bytes(hashlib.sha256(req.operation_id.encode()).digest()[:8], "big", signed=True)
        await session.execute(text("SELECT pg_advisory_xact_lock(:id)"), {"id": lock_id})
    old = await session.get(EnrollmentReceipt, req.operation_id)
    if old:
        if old.request_hash != body_hash:
            raise HTTPException(409, "La operación ya está vinculada a otra solicitud")
        if old.expires_at <= now:
            raise HTTPException(410, "El recibo de activación expiró")
        return PairResponse.model_validate_json(cipher.decrypt(old.response_ciphertext.encode()))
    if req.replace_device_id:
        device = await session.get(Device, req.replace_device_id)
        if not device or device.user_id != req.user_id:
            raise HTTPException(400, "Dispositivo de reconexión no válido")
    try:
        response = await auth_service.enroll_device(session, req.user_id, PairRequest(
            pairing_code="internal", device_name=req.device_name, platform=req.platform,
            client_device_id=req.client_device_id), commit=False)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    if req.replace_device_id:
        grants = (await session.execute(select(DocumentContextGrant).join(Document,
            Document.id == DocumentContextGrant.document_id).join(DocumentOrigin,
            DocumentOrigin.document_id == Document.id).join(DocumentRevision,
            DocumentRevision.id == DocumentContextGrant.revision_id).where(
            DocumentContextGrant.user_id == req.user_id, Document.user_id == req.user_id,
            DocumentContextGrant.recipient_id == "device:" + req.replace_device_id,
            DocumentContextGrant.revoked_at.is_(None), Document.is_deleted.is_(False),
            DocumentRevision.document_id == Document.id,
            DocumentOrigin.privacy_class.in_(("SAFE", "OPT_IN"))
        ))).scalars().all()
        for grant in grants:
            session.add(DocumentContextGrant(id="grant-"+uuid.uuid4().hex,
                user_id=req.user_id, document_id=grant.document_id, revision_id=grant.revision_id,
                recipient_id="device:"+response.device_id, reason="Reconexión autorizada del mismo titular"))
    session.add(EnrollmentReceipt(operation_id=req.operation_id, user_id=req.user_id,
        device_id=response.device_id, request_hash=body_hash,
        response_ciphertext=cipher.encrypt(response.model_dump_json().encode()).decode(),
        created_at=now, expires_at=now+timedelta(hours=24)))
    await session.commit()
    return response

@router.post("/enroll", response_model=PairResponse)
async def internal_enroll(req: EnrollmentRequest, session: AsyncSession = Depends(get_db_session), x_enrollment_key: str | None = Header(default=None)):
    secret = settings.platform_enrollment_key.get_secret_value()
    if not secret or not x_enrollment_key or not hmac.compare_digest(secret.encode(), x_enrollment_key.encode()):
        raise HTTPException(403, "Acceso interno denegado")
    if session.bind.dialect.name == "sqlite":
        async with _sqlite_lock:
            return await enroll(session, req, secret)
    return await enroll(session, req, secret)


@router.get("/metrics")
async def metrics(x_enrollment_key: str | None = Header(default=None), session: AsyncSession = Depends(get_db_session)):
    secret = settings.platform_enrollment_key.get_secret_value()
    if not secret or not x_enrollment_key or not hmac.compare_digest(secret.encode(), x_enrollment_key.encode()):
        raise HTTPException(403, "Acceso interno denegado")
    from app.services.document_storage import document_storage
    from app.models.canonical import ChatResponseReport
    usage = await asyncio.to_thread(document_storage.storage_usage_bytes)
    pending_reports = await session.scalar(select(func.count(ChatResponseReport.id)).where(ChatResponseReport.status == "received"))
    return {"usage_bytes": usage, "quota_bytes": settings.storage_quota_bytes, "health": "ready", "pending_ai_reports": pending_reports or 0}
