from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models.commerce import DiscountGrants, Purchases, SubscriptionAccess
from src.db.models.public import CourseSubscriptions, Subscription, SubscriptionTariffs


class CommerceCRUD:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def tariffs(self, course_ids, tariff_ids):
        query = (select(CourseSubscriptions.CourseId, Subscription, SubscriptionTariffs)
                 .join(Subscription, Subscription.Id == CourseSubscriptions.SubscriptionId)
                 .join(SubscriptionTariffs, SubscriptionTariffs.SubscriptionId == Subscription.Id)
                 .where(CourseSubscriptions.CourseId.in_(course_ids), Subscription.IsDeleted.is_(False),
                        SubscriptionTariffs.Id.in_(tariff_ids)))
        return (await self.session.execute(query)).all()

    async def subscription_links(self, course_ids):
        query = select(CourseSubscriptions.CourseId, CourseSubscriptions.SubscriptionId).where(
            CourseSubscriptions.CourseId.in_(course_ids))
        return (await self.session.execute(query)).all()

    async def user_state(self, user_id):
        purchases = list((await self.session.scalars(select(Purchases).where(Purchases.user_id == user_id))).all())
        subscriptions = list((await self.session.scalars(select(SubscriptionAccess).where(SubscriptionAccess.user_id == user_id))).all())
        discounts = list((await self.session.scalars(select(DiscountGrants).where(DiscountGrants.user_id == user_id))).all())
        return purchases, subscriptions, discounts

    async def has_onboarding_grant(self, user_id):
        from sqlalchemy import exists

        return bool(await self.session.scalar(select(exists().where(
            DiscountGrants.user_id == user_id, DiscountGrants.reason == 'onboarding',
        ))))

    async def has_course_purchase(self, user_id):
        from sqlalchemy import exists

        return bool(await self.session.scalar(select(exists().where(
            Purchases.user_id == user_id, Purchases.course_id.is_not(None),
        ))))

    async def create_onboarding_grant(self, user_id, now, percent, duration_days):
        from datetime import timedelta

        self.session.add(DiscountGrants(user_id=user_id, reason='onboarding', granted_at=now,
                                        expires_at=now + timedelta(days=duration_days), discount_percent=percent))

    async def purchase(self, request_id):
        return await self.session.get(Purchases, request_id)

    async def purchases(self, user_id):
        query = select(Purchases).where(Purchases.user_id == user_id).order_by(Purchases.created_at.desc(), Purchases.id.desc())
        return list((await self.session.scalars(query)).all())

    async def discounts(self, user_id):
        query = select(DiscountGrants).where(DiscountGrants.user_id == user_id).order_by(DiscountGrants.granted_at.desc(), DiscountGrants.id.desc())
        return list((await self.session.scalars(query)).all())

    async def active_subscriptions(self, user_id, now):
        from sqlalchemy import or_

        query = (select(SubscriptionAccess, Subscription.Title).join(Subscription, Subscription.Id == SubscriptionAccess.subscription_id)
                 .where(SubscriptionAccess.user_id == user_id, SubscriptionAccess.valid_from <= now,
                        or_(SubscriptionAccess.valid_until.is_(None), SubscriptionAccess.valid_until > now),
                        SubscriptionAccess.revoked_at.is_(None))
                 .order_by(SubscriptionAccess.valid_from.desc(), SubscriptionAccess.id.desc()))
        return (await self.session.execute(query)).all()

    async def all_tariffs(self, tariff_ids):
        query = (select(Subscription, SubscriptionTariffs).join(SubscriptionTariffs, SubscriptionTariffs.SubscriptionId == Subscription.Id)
                 .where(SubscriptionTariffs.Id.in_(tariff_ids), Subscription.IsDeleted.is_(False))
                 .order_by(SubscriptionTariffs.Id))
        return (await self.session.execute(query)).all()

    async def create_purchase(self, **values):
        purchase = Purchases(**values)
        self.session.add(purchase)
        await self.session.flush()
        return purchase

    async def create_access(self, **values):
        self.session.add(SubscriptionAccess(**values))
        await self.session.flush()

    async def redeem(self, grant, now):
        grant.redeemed_at = now
        await self.session.flush()

    async def tariff(self, tariff_id):
        query = (select(Subscription, SubscriptionTariffs).join(SubscriptionTariffs, SubscriptionTariffs.SubscriptionId == Subscription.Id)
                 .where(SubscriptionTariffs.Id == tariff_id))
        return (await self.session.execute(query)).first()
