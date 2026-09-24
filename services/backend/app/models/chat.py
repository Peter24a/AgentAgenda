from datetime import datetime
from typing import Any, Dict, List, Literal, Optional
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


class CreateTurnRequest(BaseModel):
    message: str = Field(..., description="Mensaje del usuario")
    client_message_id: Optional[str] = Field(None, description="ID único para deduplicación idempotente")
    date: Optional[str] = Field(None, description="Fecha de consulta YYYY-MM-DD (view_date)")
    timezone: Optional[str] = Field("America/Mexico_City", description="Zona horaria IANA del cliente")
    history: Optional[List[ChatMessageModel]] = Field(default_factory=list, description="Historial reciente opcional")


class ChatMessageResponse(BaseModel):
    id: str
    turn_id: Optional[str] = None
    role: Literal["user", "assistant", "system"]
    content: str
    client_created_at: Optional[datetime] = None
    received_at: datetime
    created_at: datetime

    class Config:
        from_attributes = True


class ChatTurnResponse(BaseModel):
    turn_id: str
    user_id: str
    client_message_id: Optional[str] = None
    status: Literal["queued", "running", "completed", "failed", "cancelled"]
    user_message: str
    assistant_message: Optional[str] = None
    proposal: Optional[AgentProposalModel] = None
    error_message: Optional[str] = None
    created_at: datetime
    completed_at: Optional[datetime] = None


class ChatWindowResponse(BaseModel):
    messages: List[ChatMessageResponse]
    window_start: datetime
    window_end: datetime
    next_cursor: Optional[str] = None
    has_older: bool = False


class CheckInRequest(BaseModel):
    notification_key: str = Field(..., min_length=1, max_length=160)
    event_id: Optional[str] = Field(None, max_length=64)
    scheduled_at: Optional[datetime] = None
    kind: Literal["check_in", "reminder"] = "check_in"
