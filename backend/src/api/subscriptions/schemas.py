from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class SubscriptionAccess(BaseModel):
    id: UUID
    subscription_id: UUID
    title: str
    valid_from: datetime
    valid_until: datetime | None
