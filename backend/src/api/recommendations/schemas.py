from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic.json_schema import SkipJsonSchema

from src.api.materials.schemas import MaterialCard
from src.api.onboarding.schemas import OnboardingInput

FeedFormat = Literal['quick', 'medium']


class FeedInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    format: FeedFormat | SkipJsonSchema[None] = None
    onboarding: OnboardingInput | SkipJsonSchema[None] = None

    @field_validator('format', 'onboarding')
    @classmethod
    def reject_null(cls, value):
        if value is None:
            raise ValueError('Omit the field instead of passing null')
        return value


class RecommendationItem(BaseModel):
    position: int = Field(ge=1)
    material: MaterialCard
    explanation: str | None
    offer_text: str | None


class RecommendationList(BaseModel):
    id: UUID | None
    mode: Literal['popular', 'personalized']
    format: FeedFormat | None
    saved_at: datetime | None
    items: list[RecommendationItem] = Field(max_length=6)
