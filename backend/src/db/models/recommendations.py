from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
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


class RecommendationLists(Base):
    __tablename__ = 'recommendation_lists'
    __table_args__ = (
        CheckConstraint("(mode = 'popular' AND list_type = 'feed' AND recommendation_format IS NULL) OR (mode = 'personalized' AND ((list_type = 'feed' AND recommendation_format IN ('quick', 'medium')) OR (list_type = 'trajectory' AND recommendation_format = 'deep')) AND recommendation_format IS NOT NULL)", name='recommendation_mode_format'),
        CheckConstraint("list_type IN ('feed', 'trajectory')", name='recommendation_lists_list_type_check'),
        CheckConstraint("mode IN ('popular', 'personalized')", name='recommendation_lists_mode_check'),
        CheckConstraint("recommendation_format IN ('quick', 'medium', 'deep')", name='recommendation_lists_recommendation_format_check'),
        Index('ix_recommendation_lists_user_id_created_at', 'user_id', 'created_at'),
        {'schema': 'mvp'},
    )
    id: Mapped[UUID] = mapped_column('id', UUIDType, primary_key=True, nullable=False, server_default=text('gen_random_uuid()'))
    user_id: Mapped[UUID] = mapped_column('user_id', UUIDType, ForeignKey('mvp.users.id', ondelete="RESTRICT"), nullable=False)
    onboarding_response_id: Mapped[UUID | None] = mapped_column('onboarding_response_id', UUIDType, ForeignKey('mvp.onboarding_responses.id', ondelete="RESTRICT"), nullable=True)
    list_type: Mapped[str] = mapped_column('list_type', Text, nullable=False, server_default=text("'feed'"))
    mode: Mapped[str] = mapped_column('mode', Text, nullable=False)
    recommendation_format: Mapped[str | None] = mapped_column('recommendation_format', Text, nullable=True)
    context_snapshot: Mapped[dict] = mapped_column('context_snapshot', JSONB, nullable=False)
    ranking_version: Mapped[str] = mapped_column('ranking_version', Text, nullable=False)
    ranking_config: Mapped[dict] = mapped_column('ranking_config', JSONB, nullable=False)
    title: Mapped[str | None] = mapped_column('title', Text, nullable=True)
    summary: Mapped[str | None] = mapped_column('summary', Text, nullable=True)
    saved_at: Mapped[datetime | None] = mapped_column('saved_at', DateTime(timezone=True), nullable=True)
    generation_run_id: Mapped[UUID | None] = mapped_column('generation_run_id', UUIDType, ForeignKey('mvp.generation_runs.id', ondelete="RESTRICT"), nullable=True)
    created_at: Mapped[datetime] = mapped_column('created_at', DateTime(timezone=True), nullable=False, server_default=text('now()'))


class RecommendationItems(Base):
    __tablename__ = 'recommendation_items'
    __table_args__ = (
        CheckConstraint('position > 0', name='recommendation_items_position_check'),
        CheckConstraint("selection_kind IN ('relevance', 'exploration', 'fallback')", name='recommendation_items_selection_kind_check'),
        CheckConstraint("step_role IN ('intro', 'practice', 'advanced')", name='recommendation_items_step_role_check'),
        UniqueConstraint('list_id', 'material_id', name='ix_recommendation_items_list_id_material_id'),
        UniqueConstraint('list_id', 'position', name='ix_recommendation_items_list_id_position'),
        Index('ix_recommendation_items_material_id', 'material_id'),
        {'schema': 'mvp'},
    )
    id: Mapped[UUID] = mapped_column('id', UUIDType, primary_key=True, nullable=False, server_default=text('gen_random_uuid()'))
    list_id: Mapped[UUID] = mapped_column('list_id', UUIDType, ForeignKey('mvp.recommendation_lists.id', ondelete="RESTRICT"), nullable=False)
    material_id: Mapped[UUID] = mapped_column('material_id', UUIDType, ForeignKey('mvp.materials.id', ondelete="RESTRICT"), nullable=False)
    position: Mapped[int] = mapped_column('position', Integer, nullable=False)
    explanation: Mapped[str | None] = mapped_column('explanation', Text, nullable=True)
    offer_text: Mapped[str | None] = mapped_column('offer_text', Text, nullable=True)
    selection_kind: Mapped[str] = mapped_column('selection_kind', Text, nullable=False)
    score: Mapped[float | None] = mapped_column('score', Float, nullable=True)
    step_role: Mapped[str | None] = mapped_column('step_role', Text, nullable=True)
    transition_text: Mapped[str | None] = mapped_column('transition_text', Text, nullable=True)
    generation_run_id: Mapped[UUID | None] = mapped_column('generation_run_id', UUIDType, ForeignKey('mvp.generation_runs.id', ondelete="RESTRICT"), nullable=True)


class GenerationRuns(Base):
    __tablename__ = 'generation_runs'
    __table_args__ = (
        CheckConstraint("status NOT IN ('succeeded', 'fallback') OR output_json IS NOT NULL", name='generation_result_required'),
        CheckConstraint("status IN ('pending', 'succeeded', 'failed', 'fallback')", name='generation_runs_status_check'),
        CheckConstraint('latency_ms >= 0', name='generation_runs_latency_ms_check'),
        Index('ix_generation_runs_input_hash_created_at', 'input_hash', 'created_at'),
        Index('ix_generation_runs_created_at', 'created_at'),
        {'schema': 'mvp'},
    )
    id: Mapped[UUID] = mapped_column('id', UUIDType, primary_key=True, nullable=False, server_default=text('gen_random_uuid()'))
    model_name: Mapped[str] = mapped_column('model_name', Text, nullable=False)
    model_revision: Mapped[str] = mapped_column('model_revision', Text, nullable=False)
    prompt_version: Mapped[str] = mapped_column('prompt_version', Text, nullable=False)
    generation_parameters: Mapped[dict] = mapped_column('generation_parameters', JSONB, nullable=False)
    input_snapshot: Mapped[dict] = mapped_column('input_snapshot', JSONB, nullable=False)
    input_hash: Mapped[str] = mapped_column('input_hash', Text, nullable=False)
    output_json: Mapped[dict | None] = mapped_column('output_json', JSONB(none_as_null=True), nullable=True)
    status: Mapped[str] = mapped_column('status', Text, nullable=False, server_default=text("'pending'"))
    validation_errors: Mapped[dict | None] = mapped_column('validation_errors', JSONB(none_as_null=True), nullable=True)
    latency_ms: Mapped[int | None] = mapped_column('latency_ms', Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column('created_at', DateTime(timezone=True), nullable=False, server_default=text('now()'))


