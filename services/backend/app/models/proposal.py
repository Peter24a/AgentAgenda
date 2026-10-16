from datetime import date, datetime
from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field, field_validator, model_validator
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from app.models.agenda import AgendaItemModel, ActivityCategory

class ProposalStatus(str, Enum):
    pending = "pending"
    accepted = "accepted"
    rejected = "rejected"


class WeeklyRoutineProposal(BaseModel):
    """An explicit recurrence, confirmed through the existing proposal button."""
    title: str = Field(min_length=1, max_length=256)
    description: Optional[str] = None
    category: ActivityCategory = ActivityCategory.general
    timezone: str = "America/Mexico_City"
    starts_on: date
    # A missing end means explicitly indefinite; the chat resolves that choice
    # before building this model, never by guessing from an incomplete request.
    ends_on: Optional[date] = None
    iso_weekdays: List[int] = Field(min_length=1, max_length=7)
    start_time: str
    end_time: str

    @field_validator("iso_weekdays")
    @classmethod
    def valid_weekdays(cls, values):
        if any(value not in range(1, 8) for value in values):
            raise ValueError("Los días de la rutina deben estar entre lunes y domingo")
        return sorted(set(values))

    @field_validator("title")
    @classmethod
    def valid_title(cls, value):
        if not value.strip():
            raise ValueError("La rutina necesita un título")
        return value.strip()

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value):
        try:
            ZoneInfo(value)
        except (ValueError, ZoneInfoNotFoundError):
            raise ValueError("Zona horaria inválida") from None
        return value

    @field_validator("start_time", "end_time")
    @classmethod
    def valid_clock(cls, value):
        import re
        if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", value):
            raise ValueError("Las horas de la rutina deben usar HH:MM")
        return value

    @model_validator(mode="after")
    def valid_interval(self):
        if self.ends_on is not None and self.ends_on < self.starts_on:
            raise ValueError("El final de la rutina debe ser posterior al inicio")
        if self.start_time == self.end_time:
            raise ValueError("La rutina necesita una duración positiva")
        return self


class AgentProposalModel(BaseModel):
    id: str
    summary: str
    reason: str
    resulting_items: List[AgendaItemModel] = Field(default_factory=list)
    routine: Optional[WeeklyRoutineProposal] = None
    status: ProposalStatus = ProposalStatus.pending
    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        from_attributes = True

class ProposalActionResponse(BaseModel):
    success: bool
    proposal_id: str
    status: ProposalStatus
    message: str
