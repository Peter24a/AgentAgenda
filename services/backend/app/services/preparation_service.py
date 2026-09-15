import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.canonical import Document, DocumentLink, DocumentRequirement, DocumentRevision, Event
from app.models.preparation import (
    CreateRequirementRequest,
    DocumentLinkDetail,
    EventPreparationResponse,
    LinkDocumentRequest,
    RequirementDetail,
    VerifyRequirementRequest,
)


class PreparationService:
    async def get_event_preparation(
        self, session: AsyncSession, user_id: str, event_id: str
    ) -> Optional[EventPreparationResponse]:
        # 1. Verificar existencia del evento
        event_res = await session.execute(
            select(Event).where(
                Event.id == event_id,
                Event.user_id == user_id,
                Event.is_deleted.is_(False),
            )
        )
        event = event_res.scalar_one_or_none()
        if not event:
            return None

        # 2. Obtener requisitos del evento
        req_res = await session.execute(
            select(DocumentRequirement)
            .where(
                DocumentRequirement.event_id == event_id,
                DocumentRequirement.user_id == user_id,
            )
            .order_by(DocumentRequirement.created_at.asc())
        )
        requirements = list(req_res.scalars().all())

        if not requirements:
            return EventPreparationResponse(
                event_id=event.id,
                event_title=event.title,
                event_start_time=event.start_time,
                readiness_status="ready",
                total_requirements=0,
                verified_count=0,
                candidate_count=0,
                missing_count=0,
                expired_count=0,
                requirements=[],
                missing_requirements=[],
                verified_requirements=[],
                attention_required=[],
            )

        req_ids = [r.id for r in requirements]

        # 3. Obtener enlaces asociados
        links_res = await session.execute(
            select(DocumentLink)
            .where(DocumentLink.requirement_id.in_(req_ids))
            .order_by(DocumentLink.created_at.asc())
        )
        all_links = list(links_res.scalars().all())

        # 4. Obtener documentos y revisiones involucradas
        doc_ids = list({l.document_id for l in all_links})
        rev_ids = list({l.revision_id for l in all_links if l.revision_id})

        docs_map: Dict[str, Document] = {}
        if doc_ids:
            d_res = await session.execute(
                select(Document).where(Document.id.in_(doc_ids), Document.is_deleted.is_(False))
            )
            for d in d_res.scalars().all():
                docs_map[d.id] = d

        revs_map: Dict[str, DocumentRevision] = {}
        if rev_ids:
            r_res = await session.execute(
                select(DocumentRevision).where(DocumentRevision.id.in_(rev_ids))
            )
            for r in r_res.scalars().all():
                revs_map[r.id] = r

        links_by_req: Dict[str, List[DocumentLinkDetail]] = {r.id: [] for r in requirements}

        for l in all_links:
            doc = docs_map.get(l.document_id)
            if not doc:
                continue

            rev = revs_map.get(l.revision_id) if l.revision_id else None

            # Evaluar vencimiento documental con respecto al evento o a la fecha actual
            is_expired = False
            if doc.expiry_date:
                compare_time = event.start_time or datetime.now(timezone.utc).replace(tzinfo=None)
                if doc.expiry_date < compare_time:
                    is_expired = True

            link_detail = DocumentLinkDetail(
                id=l.id,
                requirement_id=l.requirement_id,
                document_id=doc.id,
                document_title=doc.title,
                revision_id=rev.id if rev else None,
                version=rev.version if rev else None,
                status="expired" if is_expired else l.status,
                mime_type=rev.mime_type if rev else None,
                sha256_hash=rev.sha256_hash if rev else None,
                is_expired=is_expired,
                expiry_date=doc.expiry_date,
                verified_at=l.verified_at,
                verified_by=l.verified_by,
                created_at=l.created_at,
            )
            links_by_req[l.requirement_id].append(link_detail)

        # 5. Estructurar detalles y estados de cada requisito
        req_details: List[RequirementDetail] = []
        verified_reqs: List[RequirementDetail] = []
        missing_reqs: List[RequirementDetail] = []
        attention_reqs: List[RequirementDetail] = []

        verified_cnt = 0
        candidate_cnt = 0
        missing_cnt = 0
        expired_cnt = 0

        for r in requirements:
            r_links = links_by_req.get(r.id, [])

            # Calcular estado dinámico del requisito
            has_verified = any(l.status == "verified" and not l.is_expired for l in r_links)
            has_expired = any(l.is_expired for l in r_links)
            has_candidate = any(l.status == "candidate" and not l.is_expired for l in r_links)

            if has_verified:
                effective_status = "verified"
                verified_cnt += 1
            elif has_expired:
                effective_status = "expired"
                expired_cnt += 1
            elif has_candidate:
                effective_status = "candidate"
                candidate_cnt += 1
            else:
                effective_status = "missing"
                missing_cnt += 1

            detail = RequirementDetail(
                id=r.id,
                event_id=r.event_id,
                task_id=r.task_id,
                title=r.title,
                description=r.description,
                rule_source=r.rule_source,
                status=effective_status,
                links=r_links,
                created_at=r.created_at,
                updated_at=r.updated_at,
            )
            req_details.append(detail)

            if effective_status == "verified":
                verified_reqs.append(detail)
            elif effective_status == "missing":
                missing_reqs.append(detail)
                attention_reqs.append(detail)
            elif effective_status == "expired":
                attention_reqs.append(detail)
            elif effective_status == "candidate":
                pass

        total = len(requirements)
        if verified_cnt == total:
            readiness_status = "ready"
        elif expired_cnt > 0 or (missing_cnt > 0 and candidate_cnt == 0):
            readiness_status = "attention_required"
        else:
            readiness_status = "in_progress"

        return EventPreparationResponse(
            event_id=event.id,
            event_title=event.title,
            event_start_time=event.start_time,
            readiness_status=readiness_status,
            total_requirements=total,
            verified_count=verified_cnt,
            candidate_count=candidate_cnt,
            missing_count=missing_cnt,
            expired_count=expired_cnt,
            requirements=req_details,
            missing_requirements=missing_reqs,
            verified_requirements=verified_reqs,
            attention_required=attention_reqs,
        )

    async def add_requirement(
        self, session: AsyncSession, user_id: str, event_id: str, req: CreateRequirementRequest
    ) -> DocumentRequirement:
        event_res = await session.execute(
            select(Event).where(
                Event.id == event_id,
                Event.user_id == user_id,
                Event.is_deleted.is_(False),
            )
        )
        event = event_res.scalar_one_or_none()
        if not event:
            raise ValueError(f"Evento '{event_id}' no encontrado")

        now = datetime.now(timezone.utc).replace(tzinfo=None)
        doc_req = DocumentRequirement(
            id=f"req-{uuid.uuid4().hex[:12]}",
            user_id=user_id,
            event_id=event_id,
            task_id=req.task_id,
            title=req.title,
            description=req.description,
            rule_source=req.rule_source,
            status="missing",
            created_at=now,
            updated_at=now,
        )
        session.add(doc_req)
        await session.commit()
        await session.refresh(doc_req)
        return doc_req

    async def link_document(
        self,
        session: AsyncSession,
        user_id: str,
        event_id: str,
        requirement_id: str,
        link_req: LinkDocumentRequest,
    ) -> DocumentLink:
        # Validar requisito
        req_res = await session.execute(
            select(DocumentRequirement).where(
                DocumentRequirement.id == requirement_id,
                DocumentRequirement.event_id == event_id,
                DocumentRequirement.user_id == user_id,
            )
        )
        requirement = req_res.scalar_one_or_none()
        if not requirement:
            raise ValueError(f"Requisito '{requirement_id}' no encontrado para este evento")

        # Validar documento
        doc_res = await session.execute(
            select(Document).where(
                Document.id == link_req.document_id,
                Document.user_id == user_id,
                Document.is_deleted.is_(False),
            )
        )
        doc = doc_res.scalar_one_or_none()
        if not doc:
            raise ValueError(f"Documento '{link_req.document_id}' no encontrado o fue eliminado")

        # Determinar revisión
        rev_id = link_req.revision_id
        if not rev_id:
            latest_rev_res = await session.execute(
                select(DocumentRevision)
                .where(DocumentRevision.document_id == doc.id)
                .order_by(DocumentRevision.version.desc())
                .limit(1)
            )
            latest_rev = latest_rev_res.scalar_one_or_none()
            if latest_rev:
                rev_id = latest_rev.id

        now = datetime.now(timezone.utc).replace(tzinfo=None)

        # Comprobar si ya existe un link para este documento y requisito
        existing_res = await session.execute(
            select(DocumentLink).where(
                DocumentLink.requirement_id == requirement_id,
                DocumentLink.document_id == doc.id,
            )
        )
        existing_link = existing_res.scalar_one_or_none()

        if existing_link:
            existing_link.revision_id = rev_id
            existing_link.status = link_req.status
            link_obj = existing_link
        else:
            link_obj = DocumentLink(
                id=f"link-{uuid.uuid4().hex[:12]}",
                requirement_id=requirement_id,
                document_id=doc.id,
                revision_id=rev_id,
                status=link_req.status,
                created_at=now,
            )
            session.add(link_obj)

        requirement.status = link_req.status
        requirement.updated_at = now

        await session.commit()
        await session.refresh(link_obj)
        return link_obj

    async def verify_requirement(
        self,
        session: AsyncSession,
        user_id: str,
        event_id: str,
        requirement_id: str,
        verify_req: VerifyRequirementRequest,
    ) -> DocumentRequirement:
        req_res = await session.execute(
            select(DocumentRequirement).where(
                DocumentRequirement.id == requirement_id,
                DocumentRequirement.event_id == event_id,
                DocumentRequirement.user_id == user_id,
            )
        )
        requirement = req_res.scalar_one_or_none()
        if not requirement:
            raise ValueError(f"Requisito '{requirement_id}' no encontrado para este evento")

        now = datetime.now(timezone.utc).replace(tzinfo=None)

        # Buscar el link a actualizar
        if verify_req.link_id:
            link_stmt = select(DocumentLink).where(
                DocumentLink.id == verify_req.link_id,
                DocumentLink.requirement_id == requirement_id,
            )
        else:
            link_stmt = (
                select(DocumentLink)
                .where(DocumentLink.requirement_id == requirement_id)
                .order_by(DocumentLink.created_at.desc())
                .limit(1)
            )

        link_res = await session.execute(link_stmt)
        link = link_res.scalar_one_or_none()

        if link:
            link.status = verify_req.status
            if verify_req.status == "verified":
                link.verified_at = now
                link.verified_by = verify_req.verified_by
            else:
                link.verified_at = None
                link.verified_by = None

        requirement.status = verify_req.status
        requirement.updated_at = now

        await session.commit()
        await session.refresh(requirement)
        return requirement


preparation_service = PreparationService()
