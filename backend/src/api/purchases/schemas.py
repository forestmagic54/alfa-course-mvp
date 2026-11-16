from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, model_validator


class PurchaseInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    request_id: UUID
    kind: Literal['course', 'subscription']
    course_id: UUID | None = None
    subscription_tariff_id: UUID | None = None

    @model_validator(mode='after')
    def validate_target(self):
        required = 'course_id' if self.kind == 'course' else 'subscription_tariff_id'
        forbidden = 'subscription_tariff_id' if self.kind == 'course' else 'course_id'
        if getattr(self, required) is None or forbidden in self.model_fields_set:
            raise ValueError('Exactly one matching target is required')
        return self


class Purchase(BaseModel):
    id: UUID
    kind: Literal['course', 'subscription']
    course_id: UUID | None = None
    subscription_tariff_id: UUID | None = None
    amount_minor: int | None
    currency: Literal['RUB']
    created_at: datetime
    mode: Literal['demo']
