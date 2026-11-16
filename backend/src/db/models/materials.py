from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as UUIDType
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class Materials(Base):
    __tablename__ = 'materials'
    __table_args__ = (
        CheckConstraint("(source_table = 'Courses' AND kind = 'course' AND verified_course_id IS NOT NULL AND source_id = verified_course_id) OR (source_table = 'Articles' AND kind = 'article' AND verified_course_id IS NULL) OR (source_table = 'Documents' AND kind = 'document' AND verified_course_id IS NULL)", name='material_source_matches_kind'),
        CheckConstraint('(metadata IS NULL OR metadata_schema_version IS NOT NULL) AND ((metadata IS NULL AND learning_role IS NULL AND difficulty_level IS NULL) OR (annotation_source IS NOT NULL AND annotation_version IS NOT NULL))', name='material_annotation_provenance'),
        CheckConstraint("source_table IN ('Courses', 'Articles', 'Documents')", name='materials_source_table_check'),
        CheckConstraint("kind IN ('course', 'article', 'document')", name='materials_kind_check'),
        CheckConstraint('duration_minutes > 0', name='materials_duration_minutes_check'),
        CheckConstraint("access_type IN ('free', 'paid', 'unknown')", name='materials_access_type_check'),
        CheckConstraint("learning_role IN ('intro', 'practice', 'advanced')", name='materials_learning_role_check'),
        CheckConstraint("difficulty_level IN ('beginner', 'intermediate', 'advanced')", name='materials_difficulty_level_check'),
        CheckConstraint("annotation_source IN ('import', 'manual', 'model')", name='materials_annotation_source_check'),
        UniqueConstraint('source_table', 'source_id', name='ix_materials_source_table_source_id'),
        Index('ix_materials_verified_course_id', 'verified_course_id'),
        Index('ix_materials_kind_is_recommendable', 'kind', 'is_recommendable'),
        {'schema': 'mvp'},
    )
    id: Mapped[UUID] = mapped_column('id', UUIDType, primary_key=True, nullable=False, server_default=text('gen_random_uuid()'))
    source_table: Mapped[str] = mapped_column('source_table', Text, nullable=False)
    source_id: Mapped[UUID] = mapped_column('source_id', UUIDType, nullable=False)
    kind: Mapped[str] = mapped_column('kind', Text, nullable=False)
    title: Mapped[str] = mapped_column('title', Text, nullable=False)
    public_description: Mapped[str | None] = mapped_column('public_description', Text, nullable=True)
    default_offer_text: Mapped[str | None] = mapped_column('default_offer_text', Text, nullable=True)
    url: Mapped[str | None] = mapped_column('url', Text, nullable=True)
    duration_minutes: Mapped[int | None] = mapped_column('duration_minutes', Integer, nullable=True)
    access_type: Mapped[str] = mapped_column('access_type', Text, nullable=False, server_default=text("'unknown'"))
    is_recommendable: Mapped[bool] = mapped_column('is_recommendable', Boolean, nullable=False, server_default=text('false'))
    source_version: Mapped[str] = mapped_column('source_version', Text, nullable=False)
    synced_at: Mapped[datetime] = mapped_column('synced_at', DateTime(timezone=True), nullable=False, server_default=text('now()'))
    verified_course_id: Mapped[UUID | None] = mapped_column('verified_course_id', UUIDType, ForeignKey('public.Courses.Id', ondelete="RESTRICT"), nullable=True)
    learning_role: Mapped[str | None] = mapped_column('learning_role', Text, nullable=True)
    difficulty_level: Mapped[str | None] = mapped_column('difficulty_level', Text, nullable=True)
    metadata_: Mapped[dict | None] = mapped_column('metadata', JSONB(none_as_null=True), nullable=True)
    metadata_schema_version: Mapped[str | None] = mapped_column('metadata_schema_version', Text, nullable=True)
    annotation_source: Mapped[str | None] = mapped_column('annotation_source', Text, nullable=True)
    annotation_version: Mapped[str | None] = mapped_column('annotation_version', Text, nullable=True)
    metadata_reviewed_at: Mapped[datetime | None] = mapped_column('metadata_reviewed_at', DateTime(timezone=True), nullable=True)


