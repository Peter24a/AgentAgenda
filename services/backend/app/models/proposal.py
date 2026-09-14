from datetime import datetime
from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field
from app.models.agenda import AgendaItemModel

class ProposalStatus(str, Enum):
    pending = "pending"
    accepted = "accepted"
    rejected = "rejected"

class AgentProposalModel(BaseModel):
    id: str
    summary: str
    reason: str
    resulting_items: List[AgendaItemModel] = Field(default_factory=list)
    status: ProposalStatus = ProposalStatus.pending
    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        from_attributes = True

class ProposalActionResponse(BaseModel):
    success: bool
    proposal_id: str
    status: ProposalStatus
    message: str
