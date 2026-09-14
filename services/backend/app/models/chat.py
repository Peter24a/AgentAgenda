from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field
from app.models.proposal import AgentProposalModel

class ChatMessageModel(BaseModel):
    text: str
    is_user: bool
    timestamp: datetime = Field(default_factory=datetime.utcnow)

class ChatRequest(BaseModel):
    message: str
    date: Optional[str] = None  # Format YYYY-MM-DD
    history: List[ChatMessageModel] = Field(default_factory=list)

class ChatStreamChunk(BaseModel):
    event: str  # 'token', 'proposal', 'done', 'error'
    data: str
