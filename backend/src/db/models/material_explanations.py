from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID as UUIDType
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class MaterialExplanations(Base):
    __tablename__ = 'material_explanations'
    __table_args__ = {'schema': 'mvp'}

    user_id: Mapped[UUID] = mapped_column(UUIDType, ForeignKey('mvp.users.id', ondelete='RESTRICT'), primary_key=True)
    material_id: Mapped[UUID] = mapped_column(UUIDType, ForeignKey('mvp.materials.id', ondelete='RESTRICT'), primary_key=True)
    explanation: Mapped[str | None] = mapped_column(Text)
    offer_text: Mapped[str | None] = mapped_column(Text)
    profile_hash: Mapped[str | None] = mapped_column(Text)
    context_hash: Mapped[str | None] = mapped_column(Text)
    source_version: Mapped[str | None] = mapped_column(Text)
    generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lease_id: Mapped[UUID | None] = mapped_column(UUIDType)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
