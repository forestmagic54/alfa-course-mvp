from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel


class PercentValue(BaseModel):
    kind: Literal['percent']
    percent: int


class FixedValue(BaseModel):
    kind: Literal['fixed']
    amount_minor: int


class DiscountGrant(BaseModel):
    id: UUID
    reason: str
    status: Literal['available', 'redeemed', 'expired']
    granted_at: datetime
    expires_at: datetime | None
    redeemed_at: datetime | None
    value: PercentValue | FixedValue
