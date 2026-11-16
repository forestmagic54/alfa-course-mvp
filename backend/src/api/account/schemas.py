from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr


class Account(BaseModel):
    id: UUID
    email: EmailStr
    created_at: datetime
    onboarding_completed: bool
