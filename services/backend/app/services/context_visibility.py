"""Visibility for model context, distinct from the owner's document catalogue.

An imported OPT_IN classification is not a grant to every model/client. Until
recipient-specific grants exist, model/export paths only use explicitly SAFE
document origins. Unknown origins are excluded, including manually uploaded
originals which have not been classified.
"""

from sqlalchemy import and_, exists, or_, select
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


def memory_source_visibility(user_id):
    # A source may identify an original document or one of its revisions.
    safe_document_ids = select(Document.id).where(*safe_document_filters(user_id))
    safe_revision_ids = select(DocumentRevision.id).join(Document).where(*safe_document_filters(user_id))
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
    grant = exists(select(DocumentContextGrant.id).where(
        DocumentContextGrant.user_id == user_id,
        DocumentContextGrant.document_id == Document.id,
        DocumentContextGrant.revision_id == DocumentRevision.id,
        DocumentContextGrant.recipient_id == recipient_id,
        DocumentContextGrant.revoked_at.is_(None),
    ).correlate(Document, DocumentRevision))
    return (Document.user_id == user_id, Document.is_deleted.is_(False),
            or_(and_(*safe_document_filters(user_id)), and_(permitted_origin, grant)))
