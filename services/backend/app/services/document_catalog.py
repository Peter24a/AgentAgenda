from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import defer, noload

from app.models.canonical import Document, DocumentRevision
from app.models.document import (
    DocumentListResponse,
    DocumentResponse,
    DocumentRevisionResponse,
)


class DocumentCatalogService:
    async def list_documents(
        self,
        session: AsyncSession,
        user_id: str,
        query: Optional[str] = None,
        doc_type: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
        include_text: bool = True,
    ) -> DocumentListResponse:
        filters = [
            Document.user_id == user_id,
            Document.is_deleted.is_(False),
        ]

        if doc_type and doc_type.strip():
            filters.append(Document.doc_type == doc_type.strip())

        if query and query.strip():
            pattern = f"%{query.strip().lower()}%"
            filters.append(
                or_(
                    func.lower(Document.title).like(pattern),
                    func.lower(Document.alias).like(pattern),
                    func.lower(Document.issuer).like(pattern),
                    func.lower(Document.holder).like(pattern),
                )
            )

        # Contar total
        count_stmt = select(func.count(Document.id)).where(*filters)
        count_res = await session.execute(count_stmt)
        total = count_res.scalar() or 0

        # Obtener documentos paginados
        stmt = (
            select(Document)
            .options(noload(Document.revisions))
            .where(*filters)
            .order_by(Document.updated_at.desc(), Document.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        res = await session.execute(stmt)
        docs = list(res.scalars().all())

        if not docs:
            return DocumentListResponse(total=total, documents=[])

        doc_ids = [d.id for d in docs]
        rev_stmt = (
            select(DocumentRevision)
            .where(DocumentRevision.document_id.in_(doc_ids))
            .order_by(DocumentRevision.version.asc())
        )
        if not include_text:
            rev_stmt = rev_stmt.options(defer(DocumentRevision.extracted_text))
        rev_res = await session.execute(rev_stmt)
        all_revisions = list(rev_res.scalars().all())

        rev_map = {d.id: [] for d in docs}
        for r in all_revisions:
            if r.document_id in rev_map:
                rev_map[r.document_id].append(
                    DocumentRevisionResponse.model_validate(r) if include_text else
                    DocumentRevisionResponse(**{
                        field: getattr(r, field) for field in DocumentRevisionResponse.model_fields
                        if field != "extracted_text"
                    })
                )

        doc_responses = []
        for d in docs:
            resp = DocumentResponse(
                id=d.id,
                user_id=d.user_id,
                title=d.title,
                alias=d.alias,
                doc_type=d.doc_type,
                issuer=d.issuer,
                holder=d.holder,
                issue_date=d.issue_date,
                expiry_date=d.expiry_date,
                revisions=rev_map.get(d.id, []),
                created_at=d.created_at,
                updated_at=d.updated_at,
            )
            doc_responses.append(resp)

        return DocumentListResponse(total=total, documents=doc_responses)

    async def get_document(
        self, session: AsyncSession, user_id: str, document_id: str
    ) -> Optional[DocumentResponse]:
        stmt = select(Document).where(
            Document.id == document_id,
            Document.user_id == user_id,
            Document.is_deleted.is_(False),
        )
        res = await session.execute(stmt)
        doc = res.scalar_one_or_none()
        if not doc:
            return None

        rev_stmt = (
            select(DocumentRevision)
            .where(DocumentRevision.document_id == doc.id)
            .order_by(DocumentRevision.version.asc())
        )
        rev_res = await session.execute(rev_stmt)
        revisions = list(rev_res.scalars().all())

        return DocumentResponse(
            id=doc.id,
            user_id=doc.user_id,
            title=doc.title,
            alias=doc.alias,
            doc_type=doc.doc_type,
            issuer=doc.issuer,
            holder=doc.holder,
            issue_date=doc.issue_date,
            expiry_date=doc.expiry_date,
            revisions=[DocumentRevisionResponse.model_validate(r) for r in revisions],
            created_at=doc.created_at,
            updated_at=doc.updated_at,
        )

    async def get_document_by_id(
        self, session: AsyncSession, user_id: str, document_id: str
    ) -> Optional[Document]:
        stmt = select(Document).where(
            Document.id == document_id,
            Document.user_id == user_id,
            Document.is_deleted.is_(False),
        )
        res = await session.execute(stmt)
        return res.scalar_one_or_none()

    async def get_revision_for_download(
        self,
        session: AsyncSession,
        user_id: str,
        document_id: str,
        version: Optional[int] = None,
    ) -> Optional[DocumentRevision]:
        stmt = select(Document).where(
            Document.id == document_id,
            Document.user_id == user_id,
            Document.is_deleted.is_(False),
        )
        res = await session.execute(stmt)
        doc = res.scalar_one_or_none()
        if not doc:
            return None

        if version is not None:
            rev_stmt = select(DocumentRevision).where(
                DocumentRevision.document_id == doc.id,
                DocumentRevision.version == version,
            )
        else:
            rev_stmt = (
                select(DocumentRevision)
                .where(DocumentRevision.document_id == doc.id)
                .order_by(DocumentRevision.version.desc())
                .limit(1)
            )

        rev_res = await session.execute(rev_stmt)
        return rev_res.scalar_one_or_none()

    async def delete_document(
        self, session: AsyncSession, user_id: str, document_id: str
    ) -> bool:
        stmt = select(Document).where(
            Document.id == document_id,
            Document.user_id == user_id,
            Document.is_deleted.is_(False),
        )
        res = await session.execute(stmt)
        doc = res.scalar_one_or_none()
        if not doc:
            return False

        doc.is_deleted = True
        doc.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
        await session.commit()
        return True


document_catalog = DocumentCatalogService()
