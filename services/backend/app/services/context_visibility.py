"""Visibility for model context, distinct from the owner's document catalogue.

An imported OPT_IN classification is not a grant to every model/client.
Recipient-specific context can use an explicitly authorized original revision;
exports without a recipient remain SAFE-only. Unknown origins are excluded.
"""

from sqlalchemy import and_, exists, or_, select
from sqlalchemy.orm import aliased
from app.models.canonical import Document, DocumentOrigin, DocumentRevision, Memory, MemorySource


def safe_document_filters(user_id):
    safe_origin = exists(select(DocumentOrigin.document_id).where(
        DocumentOrigin.document_id == Document.id,
        DocumentOrigin.privacy_class == "SAFE",
    ).correlate(Document))
    unsafe_origin = exists(select(DocumentOrigin.document_id).where(
        DocumentOrigin.document_id == Document.id,
        or_(DocumentOrigin.privacy_class != "SAFE", DocumentOrigin.privacy_class.is_(None)),
    ).correlate(Document))
    return (Document.user_id == user_id, Document.is_deleted.is_(False), safe_origin, ~unsafe_origin)


def memory_source_visibility(user_id, recipient_id=None):
    # A source may identify an original document or one of its revisions.
    safe_document_ids = select(Document.id).where(*safe_document_filters(user_id))
    safe_revision_ids = select(DocumentRevision.id).join(Document).where(*safe_document_filters(user_id))
    if recipient_id:
        from app.models.canonical import DocumentContextGrant
        revoked = exists(select(DocumentContextGrant.id).where(
            DocumentContextGrant.user_id == user_id,
            DocumentContextGrant.document_id == Document.id,
            DocumentContextGrant.recipient_id == recipient_id,
            DocumentContextGrant.revoked_at.is_not(None),
        ).correlate(Document))
        # A source containing only the document ID cannot prove which revision
        # supplied the fact. Per-revision consent must not authorize that unknown
        # version; retain only SAFE defaults without recipient revocations.
        safe_document_ids = safe_document_ids.where(~revoked)
        safe_revision_ids = select(DocumentRevision.id).join(Document).where(
            *document_context_filters(user_id, recipient_id),
        )
    document_source = MemorySource.source_kind == "document"
    has_document_source = exists(select(MemorySource.id).where(
        MemorySource.memory_id == Memory.id, document_source,
    ))
    unsafe_source = exists(select(MemorySource.id).where(
        MemorySource.memory_id == Memory.id, document_source,
        ~MemorySource.source_id.in_(safe_document_ids),
        ~MemorySource.source_id.in_(safe_revision_ids),
    ))
    return and_(
        ~unsafe_source,
        or_(Memory.source_kind != "document", has_document_source),
    )


def document_context_filters(user_id, recipient_id=None):
    """SAFE by default; an explicit grant is restricted to one original revision and recipient."""
    if not recipient_id:
        return safe_document_filters(user_id)
    from app.models.canonical import DocumentContextGrant
    permitted_origin = exists(select(DocumentOrigin.document_id).where(
        DocumentOrigin.document_id == Document.id,
        DocumentOrigin.privacy_class.in_(("SAFE", "OPT_IN")),
    ).correlate(Document))
    never_upload = exists(select(DocumentOrigin.document_id).where(
        DocumentOrigin.document_id == Document.id,
        DocumentOrigin.privacy_class == "NEVER_UPLOAD",
    ).correlate(Document))
    revoked = aliased(DocumentContextGrant)
    revoked_for_recipient = exists(select(revoked.id).where(
        revoked.user_id == user_id, revoked.document_id == Document.id,
        revoked.recipient_id == recipient_id, revoked.revoked_at.is_not(None),
    ).correlate(Document))
    revoked_after_grant = exists(select(revoked.id).where(
        revoked.user_id == user_id, revoked.document_id == Document.id,
        revoked.recipient_id == recipient_id,
        revoked.revoked_at > DocumentContextGrant.created_at,
    ).correlate(Document, DocumentContextGrant))
    grant = exists(select(DocumentContextGrant.id).where(
        DocumentContextGrant.user_id == user_id,
        DocumentContextGrant.document_id == Document.id,
        DocumentContextGrant.revision_id == DocumentRevision.id,
        DocumentContextGrant.recipient_id == recipient_id,
        DocumentContextGrant.revoked_at.is_(None),
        ~revoked_after_grant,
    ).correlate(Document, DocumentRevision))
    return (Document.user_id == user_id, Document.is_deleted.is_(False),
            ~never_upload,
            or_(and_(*safe_document_filters(user_id), ~revoked_for_recipient),
                and_(permitted_origin, grant)))
