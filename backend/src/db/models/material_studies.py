from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Index, text
from sqlalchemy.dialects.postgresql import UUID as UUIDType
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class UserMaterialStudies(Base):
    __tablename__ = 'user_material_studies'
    __table_args__ = (
        Index('ix_user_material_studies_material_id', 'material_id'),
        {'schema': 'mvp'},
    )
    user_id: Mapped[UUID] = mapped_column('user_id', UUIDType, ForeignKey('mvp.users.id', ondelete='RESTRICT'), primary_key=True, nullable=False)
    material_id: Mapped[UUID] = mapped_column('material_id', UUIDType, ForeignKey('mvp.materials.id', ondelete='RESTRICT'), primary_key=True, nullable=False)
    marked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text('now()'))
