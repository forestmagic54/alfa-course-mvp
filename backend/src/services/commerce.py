from calendar import monthrange
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy.exc import IntegrityError

from src.services.access import card_access, discounted_amount, select_discount


class CommerceError(Exception):
    def __init__(self, code: str):
        self.code = code


def add_months(now: datetime, months: int) -> datetime:
    year, month = divmod(now.year * 12 + now.month - 1 + months, 12)
    return now.replace(year=year, month=month + 1, day=min(now.day, monthrange(year, month + 1)[1]))


def purchase_data(purchase: Any) -> dict:
    course = purchase.course_id is not None
    return {'id': purchase.id, 'kind': 'course' if course else 'subscription',
            ('course_id' if course else 'subscription_tariff_id'): purchase.course_id if course else purchase.subscription_tariff_id,
            'amount_minor': purchase.amount_minor, 'currency': 'RUB', 'created_at': purchase.created_at, 'mode': 'demo'}


def active(entry: Any, now: datetime) -> bool:
    return entry.valid_from <= now and (entry.valid_until is None or entry.valid_until > now) and entry.revoked_at is None


def purchase_pk_conflict(exc: IntegrityError) -> bool:
    cause = exc.orig
    while cause is not None:
        name = getattr(cause, 'constraint_name', None) or getattr(getattr(cause, 'diag', None), 'constraint_name', None)
        if name == 'purchases_pkey' and getattr(cause, 'sqlstate', getattr(exc.orig, 'sqlstate', None)) == '23505':
            return True
        cause = cause.__cause__
    return False


class CommerceService:
    def __init__(self, session, users, commerce, catalog, config):
        self.session, self.users, self.commerce, self.catalog, self.config = session, users, commerce, catalog, config

    def matching(self, purchase, user_id, kind, target):
        if purchase.user_id != user_id or (purchase.course_id if kind == 'course' else purchase.subscription_tariff_id) != target:
            raise CommerceError('request_id_conflict')
        return purchase_data(purchase), False

    async def acquire(self, user_id: UUID, request_id: UUID, kind: str, target: UUID):
        try:
            await self.users.lock(user_id)
            previous = await self.commerce.purchase(request_id)
            if previous is not None:
                result = self.matching(previous, user_id, kind, target)
                await self.session.commit()
                return result
            now = datetime.now(UTC)
            purchases, subscriptions, discounts = await self.commerce.user_state(user_id)
            first = not any(p.course_id is not None for p in purchases)
            if kind == 'course':
                material = await self.catalog.get_course(target)
                if material is None:
                    raise CommerceError('not_found')
                links = {subscription_id for _, subscription_id in await self.commerce.subscription_links([target])}
                access, _, _ = card_access(material, [], links, purchases, subscriptions, discounts, self.config, now)
                if access in ('free', 'course_purchase', 'subscription'):
                    raise CommerceError('course_access_exists')
                price = self.config['access']['course_prices'].get(str(target))
                if not price or price['amount_minor'] <= 0:
                    raise CommerceError('offer_unavailable')
            else:
                row = await self.commerce.tariff(target)
                if row is None or row[0].IsDeleted:
                    raise CommerceError('not_found')
                subscription, tariff = row
                data = self.config['subscriptions']['tariffs'].get(str(target))
                if not data or data['subscription_id'] != str(subscription.Id) or data['price']['amount_minor'] <= 0 or data['duration_months'] <= 0:
                    raise CommerceError('offer_unavailable')
                if any(entry.subscription_id == subscription.Id and active(entry, now) for entry in subscriptions):
                    raise CommerceError('subscription_already_active')
                price = data['price']
            grant, amount = select_discount(price['amount_minor'], discounts, now, first_paid_course=first)
            purchase = await self.commerce.create_purchase(id=request_id, user_id=user_id,
                course_id=target if kind == 'course' else None, subscription_tariff_id=target if kind == 'subscription' else None,
                amount_minor=amount if amount is not None else price['amount_minor'], created_at=now)
            if kind == 'subscription':
                await self.commerce.create_access(user_id=user_id, subscription_id=subscription.Id, valid_from=now,
                    valid_until=add_months(now, data['duration_months']), source='mvp_purchase', source_reference=str(request_id))
            if grant is not None:
                await self.commerce.redeem(grant, now)
            result = purchase_data(purchase)
            await self.session.commit()
            return result, True
        except IntegrityError as exc:
            await self.session.rollback()
            if not purchase_pk_conflict(exc):
                raise
            previous = await self.commerce.purchase(request_id)
            if previous is None:
                raise
            return self.matching(previous, user_id, kind, target)
        except BaseException:
            await self.session.rollback()
            raise

    async def purchases(self, user_id):
        return [purchase_data(p) for p in await self.commerce.purchases(user_id)]

    async def discounts(self, user_id):
        now = datetime.now(UTC)
        return [{'id': d.id, 'reason': d.reason, 'granted_at': d.granted_at, 'expires_at': d.expires_at,
                 'redeemed_at': d.redeemed_at,
                 'status': 'redeemed' if d.redeemed_at else 'expired' if d.expires_at and d.expires_at <= now else 'available',
                 'value': {'kind': 'percent', 'percent': d.discount_percent} if d.discount_percent is not None else
                          {'kind': 'fixed', 'amount_minor': d.discount_amount_minor}}
                for d in await self.commerce.discounts(user_id)]

    async def subscriptions(self, user_id):
        rows = await self.commerce.active_subscriptions(user_id, datetime.now(UTC))
        return [{'id': access.id, 'subscription_id': access.subscription_id, 'title': title,
                 'valid_from': access.valid_from, 'valid_until': access.valid_until} for access, title in rows]

    async def offers(self, user_id):
        config = self.config['subscriptions']['tariffs']
        rows = await self.commerce.all_tariffs([UUID(key) for key in config])
        purchases, subscriptions, discounts = await self.commerce.user_state(user_id) if user_id is not None else ([], [], [])
        now = datetime.now(UTC)
        active_ids = {entry.subscription_id for entry in subscriptions if active(entry, now)}
        offers = []
        for subscription, tariff in rows:
            data = config[str(tariff.Id)]
            if (str(subscription.Id) != data['subscription_id'] or subscription.Id in active_ids
                    or data['price']['amount_minor'] <= 0 or data['duration_months'] <= 0):
                continue
            offers.append({'kind': 'subscription', 'subscription_id': subscription.Id, 'subscription_tariff_id': tariff.Id,
                           'title': tariff.Title, 'price': dict(data['price']), 'duration_months': data['duration_months'],
                           'discounted_amount_minor': discounted_amount(data['price']['amount_minor'], discounts, now,
                                first_paid_course=not any(p.course_id is not None for p in purchases))})
        return offers
