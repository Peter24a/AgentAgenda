from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db_session, require_scope
from app.models.auth import AuthContext
from app.models.preparation import (
    CreateRequirementRequest,
    DocumentLinkDetail,
    EventPreparationResponse,
    LinkDocumentRequest,
    RequirementDetail,
    VerifyRequirementRequest,
)
from app.services.preparation_service import preparation_service

router = APIRouter(tags=["Document Requirements & Event Preparation"])


@router.get(
    "/v1/events/{event_id}/preparation",
    response_model=EventPreparationResponse,
    summary="Consultar preparación documental completa de un evento o compromiso",
)
@router.get(
    "/v1/agenda/events/{event_id}/preparation",
    response_model=EventPreparationResponse,
    include_in_schema=False,
)
async def get_event_preparation(
    event_id: str,
    session: AsyncSession = Depends(get_db_session),
    auth: AuthContext = Depends(require_scope("agenda:read")),
):
    prep = await preparation_service.get_event_preparation(
        session=session,
        user_id=auth.user_id,
        event_id=event_id,
    )
    if not prep:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Evento '{event_id}' no encontrado o eliminado",
        )
    return prep


@router.post(
    "/v1/events/{event_id}/requirements",
    response_model=RequirementDetail,
    status_code=status.HTTP_201_CREATED,
    summary="Añadir un requisito documental a un evento",
)
@router.post(
    "/v1/agenda/events/{event_id}/requirements",
    response_model=RequirementDetail,
    status_code=status.HTTP_201_CREATED,
    include_in_schema=False,
)
async def add_event_requirement(
    event_id: str,
    req: CreateRequirementRequest,
    session: AsyncSession = Depends(get_db_session),
    auth: AuthContext = Depends(require_scope("agenda:write")),
):
    try:
        doc_req = await preparation_service.add_requirement(
            session=session,
            user_id=auth.user_id,
            event_id=event_id,
            req=req,
        )
        return RequirementDetail(
            id=doc_req.id,
            event_id=doc_req.event_id,
            task_id=doc_req.task_id,
            title=doc_req.title,
            description=doc_req.description,
            rule_source=doc_req.rule_source,
            status=doc_req.status,
            links=[],
            created_at=doc_req.created_at,
            updated_at=doc_req.updated_at,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.post(
    "/v1/events/{event_id}/requirements/{req_id}/link",
    response_model=DocumentLinkDetail,
    summary="Vincular un documento específico de la bóveda a un requisito de cita",
)
@router.post(
    "/v1/agenda/events/{event_id}/requirements/{req_id}/link",
    response_model=DocumentLinkDetail,
    include_in_schema=False,
)
async def link_document_to_requirement(
    event_id: str,
    req_id: str,
    link_req: LinkDocumentRequest,
    session: AsyncSession = Depends(get_db_session),
    auth: AuthContext = Depends(require_scope("agenda:write")),
):
    try:
        link_obj = await preparation_service.link_document(
            session=session,
            user_id=auth.user_id,
            event_id=event_id,
            requirement_id=req_id,
            link_req=link_req,
        )
        # Consultar la preparación para devolver el detalle enriquecido
        prep = await preparation_service.get_event_preparation(session, auth.user_id, event_id)
        if prep:
            for r in prep.requirements:
                if r.id == req_id:
                    for l in r.links:
                        if l.id == link_obj.id:
                            return l

        return DocumentLinkDetail(
            id=link_obj.id,
            requirement_id=link_obj.requirement_id,
            document_id=link_obj.document_id,
            document_title="Documento Vinculado",
            revision_id=link_obj.revision_id,
            status=link_obj.status,
            created_at=link_obj.created_at,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post(
    "/v1/events/{event_id}/requirements/{req_id}/verify",
    response_model=RequirementDetail,
    summary="Confirmar y verificar la validez de un documento vinculado para un compromiso",
)
@router.post(
    "/v1/agenda/events/{event_id}/requirements/{req_id}/verify",
    response_model=RequirementDetail,
    include_in_schema=False,
)
async def verify_requirement(
    event_id: str,
    req_id: str,
    verify_req: VerifyRequirementRequest,
    session: AsyncSession = Depends(get_db_session),
    auth: AuthContext = Depends(require_scope("agenda:write")),
):
    try:
        await preparation_service.verify_requirement(
            session=session,
            user_id=auth.user_id,
            event_id=event_id,
            requirement_id=req_id,
            verify_req=verify_req,
        )
        prep = await preparation_service.get_event_preparation(session, auth.user_id, event_id)
        if prep:
            for r in prep.requirements:
                if r.id == req_id:
                    return r

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Requisito '{req_id}' no encontrado",
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
