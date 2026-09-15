from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db_session, require_scope
from app.models.auth import AuthContext
from app.models.proposal import AgentProposalModel, ProposalStatus, ProposalActionResponse
from app.models.agenda import AgendaItemModel
from app.services.proposal_service import proposal_service


router = APIRouter(prefix="/v1/proposals", tags=["Proposals"])


def _proposal_to_model(p) -> AgentProposalModel:
    raw_items = p.resulting_items or []
    resulting_items = []
    for it in raw_items:
        if isinstance(it, dict):
            resulting_items.append(AgendaItemModel.model_validate(it))
        elif isinstance(it, AgendaItemModel):
            resulting_items.append(it)

    return AgentProposalModel(
        id=p.id,
        summary=p.summary,
        reason=p.reason,
        resulting_items=resulting_items,
        status=ProposalStatus(p.status),
        created_at=p.created_at,
    )


@router.get("/pending", response_model=Optional[AgentProposalModel])
async def get_pending_proposal(
    session: AsyncSession = Depends(get_db_session),
    auth: AuthContext = Depends(require_scope("agenda:read")),
):
    user_id = auth.user_id
    # 1. Buscar en BD canónica
    prop = await proposal_service.get_latest_pending(session, user_id)
    if prop:
        return _proposal_to_model(prop)
    return None


@router.get("/{proposal_id}", response_model=AgentProposalModel)
async def get_single_proposal(
    proposal_id: str,
    session: AsyncSession = Depends(get_db_session),
    auth: AuthContext = Depends(require_scope("agenda:read")),
):
    user_id = auth.user_id
    prop = await proposal_service.get_proposal(session, user_id, proposal_id)
    if prop:
        return _proposal_to_model(prop)

    raise HTTPException(status_code=404, detail="Propuesta no encontrada")


@router.post("", response_model=AgentProposalModel)
async def create_proposal(
    proposal: AgentProposalModel,
    session: AsyncSession = Depends(get_db_session),
    auth: AuthContext = Depends(require_scope("agenda:write")),
):
    user_id = auth.user_id
    saved = await proposal_service.save_proposal(session, user_id, proposal)
    return _proposal_to_model(saved)


@router.post("/{proposal_id}/confirm", response_model=ProposalActionResponse)
async def confirm_proposal(
    proposal_id: str,
    session: AsyncSession = Depends(get_db_session),
    auth: AuthContext = Depends(require_scope("agenda:write")),
):
    user_id = auth.user_id
    # 1. Si existe en la base canónica, aplicar con transacción atómica estricta
    canonical_prop = await proposal_service.get_proposal(session, user_id, proposal_id)
    if canonical_prop:
        return await proposal_service.confirm_proposal(session, user_id, proposal_id)

    raise HTTPException(status_code=404, detail="Propuesta no encontrada")


@router.post("/{proposal_id}/reject", response_model=ProposalActionResponse)
async def reject_proposal(
    proposal_id: str,
    session: AsyncSession = Depends(get_db_session),
    auth: AuthContext = Depends(require_scope("agenda:write")),
):
    user_id = auth.user_id
    canonical_prop = await proposal_service.get_proposal(session, user_id, proposal_id)
    if canonical_prop:
        return await proposal_service.reject_proposal(session, user_id, proposal_id)

    raise HTTPException(status_code=404, detail="Propuesta no encontrada")
