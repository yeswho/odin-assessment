from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from app.workflow.states import Status


class APIModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        from_attributes=True,
        extra="forbid",
        str_strip_whitespace=True,
    )


class WorkItemCreate(APIModel):
    external_id: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=10000)


class Category(StrEnum):
    DOCUMENT_REQUEST = "DOCUMENT_REQUEST"
    BILLING = "BILLING"
    TECHNICAL_SUPPORT = "TECHNICAL_SUPPORT"
    GENERAL = "GENERAL"


class Priority(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class Analysis(APIModel):
    category: Category
    priority: Priority
    summary: str = Field(min_length=1, max_length=2000)
    recommended_action: str = Field(min_length=1, max_length=2000)


class WorkItemRead(WorkItemCreate):
    id: UUID
    status: Status
    analysis: Analysis | None
    ai_provider: str | None
    attempts: int
    error_code: str | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime


class StatusUpdate(APIModel):
    status: Status


class WorkItemList(APIModel):
    items: list[WorkItemRead]
    total: int
    limit: int
    offset: int
    counts: dict[Status, int]


class CreateResult(APIModel):
    item: WorkItemRead
    created: bool
