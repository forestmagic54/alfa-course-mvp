from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, StringConstraints

from src.api.materials.schemas import MaterialCard


class FavoriteFolderInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]


class FavoriteFolder(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    name: str
    is_default: bool
    created_at: datetime


class FavoriteMaterial(BaseModel):
    material_id: UUID
    created_at: datetime
    material: MaterialCard | None
