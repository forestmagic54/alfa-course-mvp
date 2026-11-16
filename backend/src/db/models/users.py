from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as UUIDType
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class Users(Base):
    __tablename__ = 'users'
    __table_args__ = (
        Index('uq_users_email_lower', text('lower(email)'), unique=True),
        {'schema': 'mvp'},
    )
    id: Mapped[UUID] = mapped_column('id', UUIDType, primary_key=True, nullable=False, server_default=text('gen_random_uuid()'))
    email: Mapped[str] = mapped_column('email', Text, unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column('password_hash', Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column('created_at', DateTime(timezone=True), nullable=False, server_default=text('now()'))


class OnboardingResponses(Base):
    __tablename__ = 'onboarding_responses'
    __table_args__ = (
        CheckConstraint("(status = 'completed' AND completed_at IS NOT NULL) OR (status <> 'completed' AND completed_at IS NULL)", name='onboarding_completion_state'),
        CheckConstraint('submitted_at >= created_at', name='onboarding_time_order'),
        CheckConstraint("form_type IN ('simple', 'advanced')", name='onboarding_responses_form_type_check'),
        CheckConstraint("status IN ('partial', 'completed', 'skipped')", name='onboarding_responses_status_check'),
        Index('ix_onboarding_responses_user_id_submitted_at', 'user_id', 'submitted_at'),
        {'schema': 'mvp'},
    )
    id: Mapped[UUID] = mapped_column('id', UUIDType, primary_key=True, nullable=False, server_default=text('gen_random_uuid()'))
    user_id: Mapped[UUID] = mapped_column('user_id', UUIDType, ForeignKey('mvp.users.id', ondelete="RESTRICT"), nullable=False)
    answers: Mapped[dict] = mapped_column('answers', JSONB, nullable=False)
    form_type: Mapped[str] = mapped_column('form_type', Text, nullable=False)
    questionnaire_version: Mapped[str] = mapped_column('questionnaire_version', Text, nullable=False)
    status: Mapped[str] = mapped_column('status', Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column('created_at', DateTime(timezone=True), nullable=False, server_default=text('now()'))
    submitted_at: Mapped[datetime] = mapped_column('submitted_at', DateTime(timezone=True), nullable=False, server_default=text('now()'))
    completed_at: Mapped[datetime | None] = mapped_column('completed_at', DateTime(timezone=True), nullable=True)


class UserProfiles(Base):
    __tablename__ = 'user_profiles'
    __table_args__ = (
        CheckConstraint("learning_mode IN ('quick', 'practical', 'trajectory')", name='user_profiles_learning_mode_check'),
        {'schema': 'mvp'},
    )
    user_id: Mapped[UUID] = mapped_column('user_id', UUIDType, ForeignKey('mvp.users.id', ondelete="RESTRICT"), primary_key=True, nullable=False)
    stage_code: Mapped[str | None] = mapped_column('stage_code', Text, nullable=True)
    industry_code: Mapped[str | None] = mapped_column('industry_code', Text, nullable=True)
    goal_code: Mapped[str | None] = mapped_column('goal_code', Text, nullable=True)
    learning_mode: Mapped[str | None] = mapped_column('learning_mode', Text, nullable=True)
    profile_config_version: Mapped[str] = mapped_column('profile_config_version', Text, nullable=False)
    source_onboarding_response_id: Mapped[UUID | None] = mapped_column('source_onboarding_response_id', UUIDType, ForeignKey('mvp.onboarding_responses.id', ondelete="RESTRICT"), nullable=True)
    updated_at: Mapped[datetime] = mapped_column('updated_at', DateTime(timezone=True), nullable=False, server_default=text('now()'))


