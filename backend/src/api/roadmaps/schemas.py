from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic.json_schema import SkipJsonSchema

from src.api.onboarding.schemas import OnboardingInput
from src.api.recommendations.schemas import RecommendationItem


class RoadmapInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    onboarding: OnboardingInput | SkipJsonSchema[None] = None

    @field_validator('onboarding')
    @classmethod
    def reject_null(cls, value):
        if value is None:
            raise ValueError('Omit the field instead of passing null')
        return value


class RoadmapStep(RecommendationItem):
    explanation: str = Field(min_length=1)
    step_role: Literal['intro', 'practice', 'advanced']
    transition_text: str | None
    is_studied: bool

    @model_validator(mode='after')
    def validate_transition(self):
        if (self.position == 1 and self.transition_text is not None or
                self.position != 1 and (not self.transition_text or not self.transition_text.strip())):
            raise ValueError('Invalid transition')
        return self


class Roadmap(BaseModel):
    id: UUID | None
    title: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    saved_at: datetime | None
    steps: list[RoadmapStep] = Field(min_length=1)
