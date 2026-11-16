from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


class Preferences(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    stage_code: str | None
    industry_code: str | None
    goal_code: str | None
    learning_mode: Literal['quick', 'practical', 'trajectory'] | None
    profile_config_version: str
    updated_at: datetime
