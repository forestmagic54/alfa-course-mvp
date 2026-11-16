from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, Text, text
from sqlalchemy.dialects.postgresql import UUID as UUIDType
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class DiscountGrants(Base):
    __tablename__ = 'discount_grants'
    __table_args__ = (
        CheckConstraint('(discount_percent IS NOT NULL AND discount_percent > 0 AND discount_percent <= 100 AND discount_amount_minor IS NULL) OR (discount_percent IS NULL AND discount_amount_minor IS NOT NULL AND discount_amount_minor > 0)', name='discount_one_valid_amount'),
        Index('uq_discount_grants_onboarding', 'user_id', unique=True, postgresql_where=text("reason = 'onboarding'")),
        {'schema': 'mvp'},
    )
    id: Mapped[UUID] = mapped_column('id', UUIDType, primary_key=True, nullable=False, server_default=text('gen_random_uuid()'))
    user_id: Mapped[UUID] = mapped_column('user_id', UUIDType, ForeignKey('mvp.users.id', ondelete="RESTRICT"), nullable=False)
    reason: Mapped[str] = mapped_column('reason', Text, nullable=False)
    granted_at: Mapped[datetime] = mapped_column('granted_at', DateTime(timezone=True), nullable=False, server_default=text('now()'))
    expires_at: Mapped[datetime | None] = mapped_column('expires_at', DateTime(timezone=True), nullable=True)
    redeemed_at: Mapped[datetime | None] = mapped_column('redeemed_at', DateTime(timezone=True), nullable=True)
    discount_percent: Mapped[int | None] = mapped_column('discount_percent', Integer, nullable=True)
    discount_amount_minor: Mapped[int | None] = mapped_column('discount_amount_minor', Integer, nullable=True)


class SubscriptionAccess(Base):
    __tablename__ = 'subscription_access'
    __table_args__ = (
        Index('ix_subscription_access_user_id_subscription_id', 'user_id', 'subscription_id'),
        {'schema': 'mvp'},
    )
    id: Mapped[UUID] = mapped_column('id', UUIDType, primary_key=True, nullable=False, server_default=text('gen_random_uuid()'))
    user_id: Mapped[UUID] = mapped_column('user_id', UUIDType, ForeignKey('mvp.users.id', ondelete="RESTRICT"), nullable=False)
    subscription_id: Mapped[UUID] = mapped_column('subscription_id', UUIDType, ForeignKey('public.Subscription.Id', ondelete="RESTRICT"), nullable=False)
    valid_from: Mapped[datetime] = mapped_column('valid_from', DateTime(timezone=True), nullable=False)
    valid_until: Mapped[datetime | None] = mapped_column('valid_until', DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column('revoked_at', DateTime(timezone=True), nullable=True)
    source: Mapped[str] = mapped_column('source', Text, nullable=False)
    source_reference: Mapped[str | None] = mapped_column('source_reference', Text, nullable=True)


class Purchases(Base):
    __tablename__ = 'purchases'
    __table_args__ = (
        CheckConstraint('(course_id IS NOT NULL) <> (subscription_tariff_id IS NOT NULL)', name='purchase_one_target'),
        CheckConstraint('amount_minor >= 0', name='purchases_amount_minor_check'),
        {'schema': 'mvp'},
    )
    id: Mapped[UUID] = mapped_column('id', UUIDType, primary_key=True, nullable=False, server_default=text('gen_random_uuid()'))
    user_id: Mapped[UUID] = mapped_column('user_id', UUIDType, ForeignKey('mvp.users.id', ondelete="RESTRICT"), nullable=False)
    course_id: Mapped[UUID | None] = mapped_column('course_id', UUIDType, ForeignKey('public.Courses.Id', ondelete="RESTRICT"), nullable=True)
    subscription_tariff_id: Mapped[UUID | None] = mapped_column('subscription_tariff_id', UUIDType, ForeignKey('public.SubscriptionTariffs.Id', ondelete="RESTRICT"), nullable=True)
    amount_minor: Mapped[int | None] = mapped_column('amount_minor', Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column('created_at', DateTime(timezone=True), nullable=False, server_default=text('now()'))


