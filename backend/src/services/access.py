from datetime import datetime
from typing import Any, cast
from urllib.parse import urlsplit

from src.services.types import (
    CourseOfferData,
    MaterialActionData,
    PriceData,
    SubscriptionOfferData,
)


def public_url(url: str | None) -> str | None:
    if not url or any(char.isspace() or ord(char) < 32 for char in url):
        return None
    try:
        parsed = urlsplit(url)
        if parsed.scheme.lower() in ('http', 'https') and parsed.hostname:
            return url
    except ValueError:
        pass
    return None


def select_discount(amount: int, discounts: list, now: datetime, *, first_paid_course: bool) -> tuple[Any | None, int | None]:
    applicable = []
    for discount in discounts:
        if (discount.granted_at > now or discount.redeemed_at is not None
                or (discount.expires_at is not None and discount.expires_at <= now)):
            continue
        if discount.reason == 'onboarding' and not first_paid_course:
            continue
        saving = (amount * discount.discount_percent // 100 if discount.discount_percent is not None
                  else min(amount, discount.discount_amount_minor))
        applicable.append((-saving, discount.granted_at, discount.id, discount))
    if not applicable:
        return None, None
    saving, _, _, grant = min(applicable, key=lambda item: item[:3])
    return grant, amount + saving


def discounted_amount(amount: int, discounts: list, now: datetime, *, first_paid_course: bool) -> int | None:
    return select_discount(amount, discounts, now, first_paid_course=first_paid_course)[1]


def card_access(material: Any, tariffs: list, course_subscriptions: set, purchases: list, subscriptions: list,
                discounts: list, config: Any, now: datetime) -> tuple[str, list[CourseOfferData | SubscriptionOfferData], MaterialActionData | None]:
    course_id = material.verified_course_id
    price = config['access']['course_prices'].get(str(course_id)) if course_id else None
    price = dict(price) if price and price['amount_minor'] > 0 else None
    active = {entry.subscription_id for entry in subscriptions
              if entry.valid_from <= now and (entry.valid_until is None or entry.valid_until > now)
              and entry.revoked_at is None}
    purchased = {entry.course_id for entry in purchases if entry.course_id is not None}
    if material.access_type == 'free':
        access = 'free'
    elif course_id in purchased and course_id is not None:
        access = 'course_purchase'
    elif active.intersection(course_subscriptions):
        access = 'subscription'
    elif material.kind == 'course' and (price or tariffs):
        access = 'none'
    else:
        access = 'unknown'
    offers: list[CourseOfferData | SubscriptionOfferData] = []
    action: MaterialActionData | None = None
    if access in ('free', 'course_purchase', 'subscription'):
        url = public_url(material.url)
        if url and material.kind == 'document':
            demo_url = config['catalog'].get('demo_document_urls', {}).get(str(material.id))
            if url == demo_url:
                action = {'type': 'open_document', 'url': url}
        elif url:
            action = {'type': 'open_course' if material.kind == 'course' else 'read_article', 'url': url}
    elif access == 'none':
        for kind in config['access']['offer_order']:
            if kind == 'course' and price:
                offers.append({'kind': 'course', 'price': cast(PriceData, price),
                               'discounted_amount_minor': discounted_amount(price['amount_minor'], discounts, now,
                                                                            first_paid_course=not purchased)})
            if kind == 'subscription':
                for subscription, tariff in sorted(tariffs, key=lambda pair: str(pair[1].Id)):
                    if subscription.Id in active:
                        continue
                    data = config['subscriptions']['tariffs'][str(tariff.Id)]
                    tariff_price = cast(PriceData, dict(data['price']))
                    offers.append({'kind': 'subscription', 'subscription_id': subscription.Id,
                                   'subscription_tariff_id': tariff.Id, 'title': tariff.Title,
                                   'price': tariff_price, 'duration_months': data['duration_months'],
                                   'discounted_amount_minor': discounted_amount(tariff_price['amount_minor'], discounts, now,
                                                                                first_paid_course=not purchased)})
        if offers:
            action = ({'type': 'buy_course'} if offers[0]['kind'] == 'course' else
                      {'type': 'subscribe', 'subscription_tariff_id': offers[0]['subscription_tariff_id']})
    return access, offers, action
