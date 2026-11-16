from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Text, text
from sqlalchemy.dialects.postgresql import UUID as UUIDType
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class FavoriteFolders(Base):
    __tablename__ = 'favorite_folders'
    __table_args__ = (
        Index('ix_favorite_folders_user_id', 'user_id'),
        Index('uq_favorite_folders_default', 'user_id', unique=True, postgresql_where=text('is_default = true')),
        {'schema': 'mvp'},
    )
    id: Mapped[UUID] = mapped_column('id', UUIDType, primary_key=True, nullable=False, server_default=text('gen_random_uuid()'))
    user_id: Mapped[UUID] = mapped_column('user_id', UUIDType, ForeignKey('mvp.users.id', ondelete="RESTRICT"), nullable=False)
    name: Mapped[str] = mapped_column('name', Text, nullable=False)
    is_default: Mapped[bool] = mapped_column('is_default', Boolean, nullable=False, server_default=text('false'))
    created_at: Mapped[datetime] = mapped_column('created_at', DateTime(timezone=True), nullable=False, server_default=text('now()'))


class Favorites(Base):
    __tablename__ = 'favorites'
    __table_args__ = (
        Index('ix_favorites_material_id', 'material_id'),
        {'schema': 'mvp'},
    )
    folder_id: Mapped[UUID] = mapped_column('folder_id', UUIDType, ForeignKey('mvp.favorite_folders.id', ondelete="RESTRICT"), primary_key=True, nullable=False)
    material_id: Mapped[UUID] = mapped_column('material_id', UUIDType, ForeignKey('mvp.materials.id', ondelete="RESTRICT"), primary_key=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column('created_at', DateTime(timezone=True), nullable=False, server_default=text('now()'))


