from datetime import datetime
from enum import Enum
from typing import Literal, Optional
from pydantic import BaseModel, Field

class ActivityCategory(str, Enum):
    sleep = "sleep"
    work = "work"
    food = "food"
    exercise = "exercise"
    study = "study"
    leisure = "leisure"
    general = "general"

class AgendaItemModel(BaseModel):
    id: str
    action: Literal["upsert", "delete"] = "upsert"
    title: str
    description: Optional[str] = None
    start_time: datetime
    end_time: Optional[datetime] = None
    category: ActivityCategory = ActivityCategory.general
    is_completed: bool = False

    class Config:
        from_attributes = True

class AgendaItemCreate(BaseModel):
    id: Optional[str] = None
    title: str
    description: Optional[str] = None
    start_time: datetime
    end_time: Optional[datetime] = None
    category: ActivityCategory = ActivityCategory.general
    is_completed: bool = False
