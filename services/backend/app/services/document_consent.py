"""Explicit per-revision document consent, usable from already installed chat clients.

Only catalogue metadata is inspected before consent. The model never decides
whether a document may enter its context or interprets the consent answer.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import re
import unicodedata
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.models.canonical import (
    ChatPendingAction, Device, Document, DocumentContextGrant, DocumentOrigin,
    DocumentRevision,
)
from app.services.context_visibility import document_context_filters


@dataclass(frozen=True)
class DocumentConsentResult:
    reply: str | None = None
    retrieval_query: str | None = None
    authorized_document_id: str | None = None
    revoked: bool = False


class DocumentConsentError(ValueError):
    def __init__(self, message: str, status_code: int = 403):
        super().__init__(message)
        self.status_code = status_code


def _now(value=None):
    value = value or datetime.now(timezone.utc)
    return value.astimezone(timezone.utc).replace(tzinfo=None) if value.tzinfo else value


def _normal(value):
    return "".join(c for c in unicodedata.normalize("NFKD", value.casefold())
                   if not unicodedata.combining(c))


def _label(value):
    return re.sub(r"[`<>\[\]]", "", " ".join(str(value or "").split()))[:180]


def _pending_id(user_id, device_id):
    return hashlib.sha256(f"{user_id}\0{device_id}\0document".encode()).hexdigest()


async def _registered_device(session, user_id, device_id):
    if not device_id:
        return False
    return bool(await session.scalar(select(Device.id).where(
        Device.id == device_id, Device.user_id == user_id, Device.is_active.is_(True),
    )))


async def _catalogue(session, user_id, document_id=None):
    # Deliberately select columns: loading Document's selectin relationship would
    # fetch extracted_text before consent, even when only names were needed.
    latest = aliased(DocumentRevision)
    latest_id = (select(latest.id).where(latest.document_id == Document.id)
                 .order_by(latest.version.desc(), latest.created_at.desc(), latest.id.desc())
                 .limit(1).correlate(Document).scalar_subquery())
    stmt = select(
        Document.id.label("document_id"), Document.title, Document.alias,
        DocumentRevision.id.label("revision_id"), DocumentRevision.version,
        DocumentRevision.original_filename, DocumentRevision.extraction_status,
        DocumentOrigin.privacy_class,
    ).select_from(Document).join(DocumentRevision, DocumentRevision.id == latest_id).outerjoin(
        DocumentOrigin, DocumentOrigin.document_id == Document.id,
    ).where(Document.user_id == user_id, Document.is_deleted.is_(False))
    if document_id:
        stmt = stmt.where(Document.id == document_id)
    rows = (await session.execute(stmt.order_by(
        DocumentRevision.created_at.desc(), Document.created_at.desc(), Document.id,
    ))).mappings()
    return [dict(row) for row in rows]


async def context_access_state(session, user_id, device_id, document_id):
    if not await _registered_device(session, user_id, device_id):
        raise DocumentConsentError("Se requiere un dispositivo registrado y activo.")
    rows = await _catalogue(session, user_id, document_id)
    if not rows:
        raise DocumentConsentError("Documento no encontrado.", 404)
    row = rows[0]
    allowed = await session.scalar(select(DocumentRevision.id).join(Document).where(
        *document_context_filters(user_id, f"device:{device_id}"),
        DocumentRevision.id == row["revision_id"],
    ))
    return {
        "document_id": row["document_id"], "title": row["title"],
        "revision_id": row["revision_id"], "version": row["version"],
        "recipient_id": f"device:{device_id}", "authorized": bool(allowed),
        "blocked": row["privacy_class"] == "NEVER_UPLOAD",
        "extraction_status": row["extraction_status"],
    }


async def set_context_access(session, user_id, device_id, document_id, revision_id,
                             authorized, *, now=None):
    state = await context_access_state(session, user_id, device_id, document_id)
    if state["revision_id"] != revision_id:
        raise DocumentConsentError(
            "El documento tiene otra versión. Revisa la versión actual antes de autorizarla.", 409)
    timestamp = _now(now)
    recipient = f"device:{device_id}"
    if authorized:
        if state["blocked"]:
            raise DocumentConsentError("Este documento está marcado como NEVER_UPLOAD y no se puede usar en el asistente.")
        origin = await session.get(DocumentOrigin, document_id)
        if origin and origin.privacy_class not in ("SAFE", "OPT_IN"):
            raise DocumentConsentError("La clasificación del documento no permite autorizar su análisis.")
        if not origin:
            session.add(DocumentOrigin(
                document_id=document_id, source_collection="owner-upload",
                source_path="", privacy_class="OPT_IN", source_kind="manual",
                metadata_json={"classified_by": "explicit_owner_consent"},
            ))
        if not state["authorized"]:
            # A fresh row retains older revocation timestamps used as the chat
            # history barrier. Re-authorizing must never restore previous context.
            session.add(DocumentContextGrant(
                id=str(uuid4()), user_id=user_id, document_id=document_id,
                revision_id=revision_id, recipient_id=recipient,
                reason="Explicit owner authorization for this revision and device",
                created_at=timestamp,
            ))
    else:
        active = (await session.scalars(select(DocumentContextGrant).where(
            DocumentContextGrant.user_id == user_id,
            DocumentContextGrant.document_id == document_id,
            DocumentContextGrant.recipient_id == recipient,
            DocumentContextGrant.revoked_at.is_(None),
        ))).all()
        for grant in active:
            grant.revoked_at = timestamp
        if not active:
            # Also denies the SAFE default for this recipient and establishes a
            # history barrier when it had never required an explicit grant.
            session.add(DocumentContextGrant(
                id=str(uuid4()), user_id=user_id, document_id=document_id,
                revision_id=revision_id, recipient_id=recipient,
                reason="Explicit owner revocation for this document and device",
                created_at=timestamp, revoked_at=timestamp,
            ))
    await session.commit()
    return await context_access_state(session, user_id, device_id, document_id)


_DIRECT = re.compile(r"^(?:/autorizar\b|autorizo\b|doy\s+(?:mi\s+)?(?:permiso|consentimiento)\b)")
_REVOKE = re.compile(r"^(?:/revocar\b|revoca(?:r)?\b|retiro\s+(?:mi\s+)?(?:permiso|consentimiento)\b|deja\s+de\s+(?:analizar|leer|usar)\b)")
_REQUEST = re.compile(r"\b(?:analiz(?:a|ame|ar)|lee|leeme|leer|resum(?:e|eme|ir)|revisa|revisame|revisar|explica|explicame|explicar|autoriza(?:r)?|que\s+(?:dice|contiene))\b")
_DOC = re.compile(r"\b(?:documentos?|archivos?|pdf|contrato|factura|informe|reporte|constancia|certificado|comprobante)\b")
_YES = re.compile(r"^(?:si(?:,?\s+(?:autorizo|doy\s+(?:mi\s+)?permiso|adelante))?|autorizo|de\s+acuerdo|acepto)(?:\s+(?:el\s+)?(?:analisis|uso))?[.!]?$", re.I)
_NO = re.compile(r"^(?:no|no\s+autorizo|cancelar?|mejor\s+no)[.!]?$", re.I)
_GENERIC = {"a", "el", "la", "los", "las", "un", "una", "de", "del", "mi", "mis", "para", "por", "favor", "que", "lo", "me", "puedes", "puede", "podrias", "documento", "archivo", "pdf", "analiza", "analizar", "lee", "leer", "resume", "resumir", "revisa", "revisar", "explica", "explicar", "autoriza", "autorizar", "autorizo", "revoca", "revocar", "deja", "usar", "y", "dime", "contenido"}


def _candidates(rows, message):
    normal = _normal(message)
    explicit = [r for r in rows if re.search(r"(?<![\w-])" + re.escape(_normal(r["document_id"])) + r"(?![\w-])", normal)]
    if explicit:
        return explicit
    if re.search(r"\b(?:ultimo\s+(?:documento|archivo)|(?:documento|archivo)\s+(?:mas\s+reciente|que\s+acabo\s+de\s+subir|recien\s+subido))\b", normal):
        return rows[:1]
    quoted = re.findall(r'["“](.+?)["”]', normal)
    terms = set(re.findall(r"[\w.-]+", normal)) - _GENERIC
    matches = []
    for row in rows:
        names = [_normal(str(row[k] or "")).strip() for k in ("title", "alias", "original_filename")]
        if any(name and (name in quoted or re.search(r"(?<!\w)" + re.escape(name) + r"(?!\w)", normal)) for name in names):
            matches.append(row)
            continue
        name_terms = set(re.findall(r"[\w.-]+", " ".join(names))) - _GENERIC
        if terms and terms <= name_terms:
            matches.append(row)
    return matches


async def _save_pending(session, user_id, device_id, payload, timestamp):
    key = _pending_id(user_id, device_id)
    pending = await session.get(ChatPendingAction, key)
    if not pending:
        pending = ChatPendingAction(id=key, user_id=user_id, device_id=device_id, kind="document")
        session.add(pending)
    pending.payload = payload
    pending.updated_at = timestamp
    pending.expires_at = timestamp + timedelta(minutes=15)
    await session.commit()


async def _clear_pending(session, pending):
    if pending:
        await session.delete(pending)
        await session.commit()


def _ready_result(row, query):
    status = row["extraction_status"]
    if status == "pending":
        return DocumentConsentResult(reply=f'Autorizaste «{_label(row["title"])}», versión {row["version"]}, para este dispositivo. El texto todavía se está procesando; vuelve a pedir el análisis cuando termine.')
    if status not in ("ready", "needs_review"):
        return DocumentConsentResult(reply=f'«{_label(row["title"])}» está autorizado para este dispositivo, pero su texto no se pudo extraer. Puedes descargar el original o subir una versión con texto legible.')
    return DocumentConsentResult(
        retrieval_query=f'{query} — Documento: {row["title"]}',
        authorized_document_id=row["document_id"],
    )


async def handle_document_consent(session: AsyncSession, user_id: str, device_id: str | None,
                                  message: str, *, now=None, can_authorize=True):
    """Return a deterministic reply, or a scoped retrieval request after consent.

    Callers must have documents:read; can_authorize must reflect documents:write.
    This function additionally verifies the active registered device itself.
    """
    timestamp = _now(now)
    normal = _normal(message.strip())
    if re.search(r"\b(?:como|donde)\b.*\b(?:autorizar?|autorizo|permiso)\b", normal) and _DOC.search(normal):
        return DocumentConsentResult(reply=(
            'Escribe «analiza el documento NOMBRE» y te pediré autorización para su versión actual. '
            'Responde «sí, autorizo» para permitir su análisis en este dispositivo. '
            'También puedes usar «/autorizar NOMBRE» directamente y «/revocar NOMBRE» para retirar el permiso.'
        ))
    pending = await session.get(ChatPendingAction, _pending_id(user_id, device_id))
    if pending and pending.expires_at <= timestamp:
        await _clear_pending(session, pending)
        pending = None
    operation = "revoke" if _REVOKE.search(normal) else "authorize" if _DIRECT.search(normal) else "request"
    doc_request = operation != "request" or bool(_REQUEST.search(normal) and _DOC.search(normal))
    if not pending and not doc_request:
        return DocumentConsentResult()
    if not await _registered_device(session, user_id, device_id):
        return DocumentConsentResult(reply="Para autorizar documentos necesitas una sesión de un dispositivo registrado y activo.")
    if pending and _NO.fullmatch(normal):
        await _clear_pending(session, pending)
        return DocumentConsentResult(reply="De acuerdo, no autoricé el documento.")
    if pending and pending.payload.get("stage") == "consent" and _YES.fullmatch(normal):
        if not can_authorize:
            return DocumentConsentResult(reply="Esta sesión no tiene permiso para cambiar la autorización de documentos.")
        payload = pending.payload
        await _clear_pending(session, pending)
        try:
            await set_context_access(session, user_id, device_id, payload["document_id"], payload["revision_id"], True, now=timestamp)
        except DocumentConsentError as error:
            return DocumentConsentResult(reply=str(error))
        row = (await _catalogue(session, user_id, payload["document_id"]))[0]
        return _ready_result(row, payload["original_query"])
    rows = await _catalogue(session, user_id)
    candidates = _candidates(rows, message)
    if pending and pending.payload.get("stage") == "selection" and not doc_request:
        candidate_ids = pending.payload.get("candidates", [])
        if normal.isdigit() and 1 <= int(normal) <= len(candidate_ids):
            candidates = [row for row in rows if row["document_id"] == candidate_ids[int(normal) - 1]]
        else:
            candidates = [row for row in candidates if row["document_id"] in candidate_ids]
        if candidates:
            operation = pending.payload.get("operation", "request")
            # Selecting a title/number is not itself consent to model use.
            if operation == "authorize":
                operation = "request"
            message = pending.payload.get("original_query", message)
            doc_request = True
    if pending:
        await _clear_pending(session, pending)
    if not doc_request:
        return DocumentConsentResult()
    if len(candidates) != 1:
        options = (candidates or rows)[:5]
        if not options:
            return DocumentConsentResult(reply="No encuentro documentos en tu catálogo. Sube el archivo y después pide analizarlo por su nombre.")
        await _save_pending(session, user_id, device_id, {
            "stage": "selection", "candidates": [row["document_id"] for row in options],
            "operation": operation, "original_query": message,
        }, timestamp)
        listing = "\n".join(f'{i}. {_label(row["title"])} (versión {row["version"]}, id {row["document_id"]})' for i, row in enumerate(options, 1))
        return DocumentConsentResult(reply=f"¿A cuál documento te refieres? Responde con su número o nombre exacto.\n{listing}")
    row = candidates[0]
    if operation in ("revoke", "authorize") and not can_authorize:
        return DocumentConsentResult(reply="Esta sesión no tiene permiso para cambiar la autorización de documentos.")
    if operation == "revoke":
        await set_context_access(session, user_id, device_id, row["document_id"], row["revision_id"], False, now=timestamp)
        return DocumentConsentResult(reply=f'Revoqué el uso de «{_label(row["title"])}» en el contexto del asistente de este dispositivo. El archivo sigue en tu catálogo. Las respuestas anteriores siguen visibles en el historial.', revoked=True)
    if row["privacy_class"] == "NEVER_UPLOAD":
        return DocumentConsentResult(reply="Este documento está marcado como NEVER_UPLOAD y no se puede usar en el asistente. Puedes consultar su ficha en el catálogo.")
    state = await context_access_state(session, user_id, device_id, row["document_id"])
    if state["authorized"]:
        return _ready_result(row, message)
    if not can_authorize:
        return DocumentConsentResult(reply="Esta sesión no tiene permiso para cambiar la autorización de documentos.")
    if operation == "authorize":
        try:
            await set_context_access(session, user_id, device_id, row["document_id"], row["revision_id"], True, now=timestamp)
        except DocumentConsentError as error:
            return DocumentConsentResult(reply=str(error))
        return _ready_result(row, message)
    await _save_pending(session, user_id, device_id, {
        "stage": "consent", "document_id": row["document_id"],
        "revision_id": row["revision_id"], "original_query": message,
    }, timestamp)
    return DocumentConsentResult(reply=(
        f'¿Autorizas usar el texto de «{_label(row["title"])}» (versión {row["version"]}) '
        'en el contexto del asistente de este dispositivo? Responde «sí, autorizo» o «no». '
        'El permiso aplica sólo a esta versión; una nueva versión necesitará otra autorización. '
        f'Puedes retirarlo con «/revocar {row["document_id"]}».'
    ))
