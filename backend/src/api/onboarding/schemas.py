from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

FormType = Literal['simple', 'advanced']
Status = Literal['partial', 'completed', 'skipped']


class Option(BaseModel):
    value: str
    label: str


class Question(BaseModel):
    key: str
    label: str
    type: Literal['single_select', 'multi_select', 'text']
    required: bool
    options: list[Option] | None = None
    max_length: int | None = None


class Questionnaire(BaseModel):
    form_type: FormType
    questionnaire_version: str
    questions: list[Question]


class OnboardingInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    form_type: FormType
    questionnaire_version: str = Field(min_length=1)
    status: Status = 'completed'
    answers: dict[str, object]


class OnboardingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    form_type: FormType
    questionnaire_version: str
    status: Status
    answers: dict[str, object]
    created_at: datetime
    submitted_at: datetime
    completed_at: datetime | None
