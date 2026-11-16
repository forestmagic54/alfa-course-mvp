from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, Text, text
from sqlalchemy.dialects.postgresql import UUID as UUIDType
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class EmailPreferences(Base):
    __tablename__ = 'email_preferences'
    __table_args__ = (
        {'schema': 'mvp'},
    )
    user_id: Mapped[UUID] = mapped_column('user_id', UUIDType, ForeignKey('mvp.users.id', ondelete="RESTRICT"), primary_key=True, nullable=False)
    marketing_consent: Mapped[bool] = mapped_column('marketing_consent', Boolean, nullable=False, server_default=text('false'))
    consent_updated_at: Mapped[datetime] = mapped_column('consent_updated_at', DateTime(timezone=True), nullable=False)
    consent_version: Mapped[str | None] = mapped_column('consent_version', Text, nullable=True)
    unsubscribed_at: Mapped[datetime | None] = mapped_column('unsubscribed_at', DateTime(timezone=True), nullable=True)
    max_emails_per_week: Mapped[int | None] = mapped_column('max_emails_per_week', Integer, nullable=True)


class EmailMessages(Base):
    __tablename__ = 'email_messages'
    __table_args__ = (
        Index('ix_email_messages_user_id_sent_at', 'user_id', 'sent_at'),
        {'schema': 'mvp'},
    )
    id: Mapped[UUID] = mapped_column('id', UUIDType, primary_key=True, nullable=False, server_default=text('gen_random_uuid()'))
    user_id: Mapped[UUID] = mapped_column('user_id', UUIDType, ForeignKey('mvp.users.id', ondelete="RESTRICT"), nullable=False)
    list_id: Mapped[UUID | None] = mapped_column('list_id', UUIDType, ForeignKey('mvp.recommendation_lists.id', ondelete="RESTRICT"), nullable=True)
    kind: Mapped[str] = mapped_column('kind', Text, nullable=False)
    status: Mapped[str] = mapped_column('status', Text, nullable=False)
    provider_message_id: Mapped[str | None] = mapped_column('provider_message_id', Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column('created_at', DateTime(timezone=True), nullable=False, server_default=text('now()'))
    sent_at: Mapped[datetime | None] = mapped_column('sent_at', DateTime(timezone=True), nullable=True)


