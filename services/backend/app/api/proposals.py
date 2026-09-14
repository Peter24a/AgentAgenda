from typing import Optional
from fastapi import APIRouter, HTTPException
from app.models.proposal import AgentProposalModel, ProposalStatus, ProposalActionResponse
from app.db.database import get_proposal, get_latest_pending_proposal, save_proposal, upsert_event

router = APIRouter(prefix="/v1/proposals", tags=["Proposals"])

@router.get("/pending", response_model=Optional[AgentProposalModel])
async def get_pending_proposal():
    return await get_latest_pending_proposal()

@router.get("/{proposal_id}", response_model=AgentProposalModel)
async def get_single_proposal(proposal_id: str):
    proposal = await get_proposal(proposal_id)
    if not proposal:
        raise HTTPException(status_code=404, detail="Propuesta no encontrada")
    return proposal

@router.post("/{proposal_id}/confirm", response_model=ProposalActionResponse)
async def confirm_proposal(proposal_id: str):
    proposal = await get_proposal(proposal_id)
    if not proposal:
        raise HTTPException(status_code=404, detail="Propuesta no encontrada")

    if proposal.status != ProposalStatus.pending:
        return ProposalActionResponse(
            success=False,
            proposal_id=proposal_id,
            status=proposal.status,
            message=f"La propuesta ya fue procesada anteriormente ({proposal.status.value})"
        )

    # 1. Apply resulting items directly into SQLite events
    for item in proposal.resulting_items:
        await upsert_event(item)

    # 2. Mark proposal as accepted
    updated = proposal.model_copy(update={"status": ProposalStatus.accepted})
    await save_proposal(updated)

    return ProposalActionResponse(
        success=True,
        proposal_id=proposal_id,
        status=ProposalStatus.accepted,
        message="Propuesta aceptada e integrada en tu agenda con éxito."
    )

@router.post("/{proposal_id}/reject", response_model=ProposalActionResponse)
async def reject_proposal(proposal_id: str):
    proposal = await get_proposal(proposal_id)
    if not proposal:
        raise HTTPException(status_code=404, detail="Propuesta no encontrada")

    updated = proposal.model_copy(update={"status": ProposalStatus.rejected})
    await save_proposal(updated)

    return ProposalActionResponse(
        success=True,
        proposal_id=proposal_id,
        status=ProposalStatus.rejected,
        message="Propuesta descartada."
    )
