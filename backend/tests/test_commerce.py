import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError

from src.api.purchases.schemas import PurchaseInput
from src.services.access import select_discount
from src.services.commerce import CommerceError, CommerceService, add_months


def test_input_targets_and_client_price():
    request_id, target = uuid4(), uuid4()
    assert PurchaseInput(request_id=request_id, kind='course', course_id=target).course_id == target
    for extra in ({'subscription_tariff_id': None}, {'course_id': None}, {'amount_minor': 1}):
        values = {'request_id': request_id, 'kind': 'course', 'course_id': target} | extra
        with pytest.raises(ValidationError):
            PurchaseInput(**values)


def test_discount_choice_and_boundaries():
    now = datetime(2024, 1, 31, tzinfo=UTC)
    def grant(**kw):
        return SimpleNamespace(id=uuid4(), reason='promotion', granted_at=now, expires_at=None,
                               redeemed_at=None, discount_percent=None, discount_amount_minor=20, **kw)
    first, second = grant(), grant()
    chosen, amount = select_discount(101, [second, first], now, first_paid_course=True)
    assert (chosen.id, amount) == (min(first.id, second.id), 81)
    first.granted_at -= timedelta(days=1)
    assert select_discount(101, [second, first], now, first_paid_course=True)[0] is first
    first.expires_at = now
    second.granted_at += timedelta(seconds=1)
    assert select_discount(101, [first, second], now, first_paid_course=True) == (None, None)
    first.expires_at = None
    first.discount_percent, first.discount_amount_minor = 25, None
    assert select_discount(101, [first], now, first_paid_course=True)[1] == 76
    first.reason = 'onboarding'
    assert select_discount(101, [first], now, first_paid_course=True) == (first, 76)


def test_calendar_months():
    assert add_months(datetime(2024, 1, 31, 12, tzinfo=UTC), 1) == datetime(2024, 2, 29, 12, tzinfo=UTC)
    assert add_months(datetime(2023, 12, 31, tzinfo=UTC), 2) == datetime(2024, 2, 29, tzinfo=UTC)


async def check_repeat_and_conflict_precede_state_checks():
    user, target, request = uuid4(), uuid4(), uuid4()
    purchase = SimpleNamespace(id=request, user_id=user, course_id=target, subscription_tariff_id=None,
                               amount_minor=None, created_at=datetime.now(UTC))
    session, users, crud = AsyncMock(), AsyncMock(), AsyncMock()
    crud.purchase.return_value = purchase
    service = CommerceService(session, users, crud, AsyncMock(), {})
    result, created = await service.acquire(user, request, 'course', target)
    assert not created and result['amount_minor'] is None and 'subscription_tariff_id' not in result
    crud.user_state.assert_not_awaited()
    with pytest.raises(CommerceError, match='request_id_conflict'):
        await service.acquire(uuid4(), request, 'course', target)
    session.rollback.assert_awaited_once()


async def check_integrity_error_is_not_masked():
    session, users, crud = AsyncMock(), AsyncMock(), AsyncMock()
    crud.purchase.side_effect = IntegrityError('x', {}, Exception('unrelated'))
    service = CommerceService(session, users, crud, AsyncMock(), {})
    with pytest.raises(IntegrityError):
        await service.acquire(uuid4(), uuid4(), 'course', uuid4())
    session.rollback.assert_awaited_once()


def test_repeat_and_conflict():
    asyncio.run(check_repeat_and_conflict_precede_state_checks())


def test_unrelated_integrity_error():
    asyncio.run(check_integrity_error_is_not_masked())


def test_new_purchase_and_rollback():
    async def scenario(fail):
        user, target, request = uuid4(), uuid4(), uuid4()
        now = datetime.now(UTC)
        grant = SimpleNamespace(id=uuid4(), reason='onboarding', granted_at=now - timedelta(days=1),
                                expires_at=None, redeemed_at=None, discount_percent=10, discount_amount_minor=None)
        session, users, crud, catalog = AsyncMock(), AsyncMock(), AsyncMock(), AsyncMock()
        crud.purchase.return_value = None
        crud.user_state.return_value = ([], [], [grant])
        crud.subscription_links.return_value = []
        catalog.get_course.return_value = SimpleNamespace(verified_course_id=target, access_type='paid', kind='course')
        crud.create_purchase.side_effect = lambda **values: SimpleNamespace(**values)
        if fail:
            crud.redeem.side_effect = RuntimeError('failure')
        config = {'access': {'course_prices': {str(target): {'amount_minor': 101, 'currency': 'RUB', 'source': 'demo_config'}},
                             'offer_order': ['course']}}
        service = CommerceService(session, users, crud, catalog, config)
        if fail:
            with pytest.raises(RuntimeError):
                await service.acquire(user, request, 'course', target)
            session.rollback.assert_awaited_once()
            session.commit.assert_not_awaited()
        else:
            result, created = await service.acquire(user, request, 'course', target)
            assert created and result['amount_minor'] == 91
            crud.redeem.assert_awaited_once()
            session.commit.assert_awaited_once()
        users.lock.assert_awaited_once_with(user)
    asyncio.run(scenario(False))
    asyncio.run(scenario(True))


def test_pk_race_and_other_target():
    async def scenario():
        user, target, request = uuid4(), uuid4(), uuid4()
        session, users, crud, catalog = AsyncMock(), AsyncMock(), AsyncMock(), AsyncMock()
        previous = SimpleNamespace(id=request, user_id=user, course_id=target, subscription_tariff_id=None,
                                   amount_minor=0, created_at=datetime.now(UTC))
        error = Exception('duplicate')
        error.constraint_name, error.sqlstate = 'purchases_pkey', '23505'
        crud.purchase.side_effect = [None, previous]
        crud.user_state.return_value = ([], [], [])
        crud.subscription_links.return_value = []
        catalog.get_course.return_value = SimpleNamespace(verified_course_id=target, access_type='paid', kind='course')
        crud.create_purchase.side_effect = IntegrityError('insert', {}, error)
        config = {'access': {'course_prices': {str(target): {'amount_minor': 10}}, 'offer_order': ['course']}}
        service = CommerceService(session, users, crud, catalog, config)
        result, created = await service.acquire(user, request, 'course', target)
        assert not created and result['amount_minor'] == 0
        session.rollback.assert_awaited_once()
    asyncio.run(scenario())


def test_subscription_purchase_and_active_offer_filter():
    async def scenario():
        user, tariff_id, subscription_id, request = uuid4(), uuid4(), uuid4(), uuid4()
        session, users, crud = AsyncMock(), AsyncMock(), AsyncMock()
        subscription = SimpleNamespace(Id=subscription_id, IsDeleted=False)
        tariff = SimpleNamespace(Id=tariff_id, Title='Demo')
        crud.purchase.return_value = None
        crud.tariff.return_value = (subscription, tariff)
        crud.all_tariffs.return_value = [(subscription, tariff)]
        now = datetime.now(UTC)
        grant = SimpleNamespace(id=uuid4(), reason='onboarding', granted_at=now - timedelta(days=1),
                                expires_at=None, redeemed_at=None, discount_percent=10, discount_amount_minor=None)
        crud.user_state.return_value = ([], [], [grant])
        crud.create_purchase.side_effect = lambda **values: SimpleNamespace(**values)
        config = {'subscriptions': {'tariffs': {str(tariff_id): {'subscription_id': str(subscription_id),
            'duration_months': 1, 'price': {'amount_minor': 100, 'currency': 'RUB', 'source': 'demo_config'}}}}}
        service = CommerceService(session, users, crud, AsyncMock(), config)
        assert len(await service.offers(None)) == 1
        assert (await service.offers(user))[0]['discounted_amount_minor'] == 90
        result, created = await service.acquire(user, request, 'subscription', tariff_id)
        assert created and result['amount_minor'] == 90
        crud.redeem.assert_awaited_once_with(grant, crud.create_access.await_args.kwargs['valid_from'])
        kwargs = crud.create_access.await_args.kwargs
        assert kwargs['valid_until'] == add_months(kwargs['valid_from'], 1)
        assert kwargs['source_reference'] == str(request)
        entry = SimpleNamespace(subscription_id=subscription_id, valid_from=kwargs['valid_from'],
                                valid_until=kwargs['valid_until'], revoked_at=None)
        crud.user_state.return_value = ([], [entry], [])
        assert await service.offers(user) == []
        with pytest.raises(CommerceError, match='subscription_already_active'):
            await service.acquire(user, uuid4(), 'subscription', tariff_id)
        crud.create_access.assert_awaited_once()
    asyncio.run(scenario())


def test_access_creation_failure_rolls_back():
    async def scenario():
        user, tariff_id, subscription_id = uuid4(), uuid4(), uuid4()
        session, users, crud = AsyncMock(), AsyncMock(), AsyncMock()
        crud.purchase.return_value = None
        crud.user_state.return_value = ([], [], [])
        crud.tariff.return_value = (SimpleNamespace(Id=subscription_id, IsDeleted=False), SimpleNamespace())
        crud.create_purchase.side_effect = lambda **values: SimpleNamespace(**values)
        crud.create_access.side_effect = RuntimeError('access failed')
        config = {'subscriptions': {'tariffs': {str(tariff_id): {'subscription_id': str(subscription_id),
                  'duration_months': 1, 'price': {'amount_minor': 100}}}}}
        with pytest.raises(RuntimeError):
            await CommerceService(session, users, crud, AsyncMock(), config).acquire(user, uuid4(), 'subscription', tariff_id)
        session.rollback.assert_awaited_once()
        session.commit.assert_not_awaited()
    asyncio.run(scenario())


def test_routes_serialization_and_statuses():
    import json

    from src.__main__ import create_app
    from src.api.dependencies import optional_account, required_account
    from src.api.service_dependencies import get_commerce_service
    from src.config.settings import (
        ApplicationConfig,
        DatabaseConfig,
        JWTConfig,
        Settings,
    )

    settings = Settings(app=ApplicationConfig(_env_file=None),
        database=DatabaseConfig(_env_file=None, username='test', password='test', name='test', host='localhost'),
        jwt=JWTConfig(_env_file=None, jwt_secret='test-secret-with-at-least-32-bytes-long', jwt_expire_minutes=10))
    app = create_app(settings)
    user, target, request_id = uuid4(), uuid4(), uuid4()
    service = AsyncMock()
    service.acquire.return_value = ({'id': request_id, 'kind': 'course', 'course_id': target,
        'amount_minor': None, 'currency': 'RUB', 'created_at': datetime.now(UTC), 'mode': 'demo'}, True)
    app.dependency_overrides[required_account] = lambda: SimpleNamespace(id=user)
    app.dependency_overrides[optional_account] = lambda: None
    app.dependency_overrides[get_commerce_service] = lambda: service

    async def call(body):
        messages = []
        async def receive():
            return {'type': 'http.request', 'body': json.dumps(body).encode(), 'more_body': False}
        async def send(message):
            messages.append(message)
        path = '/api/v1/me/purchases'
        scope = {'type': 'http', 'asgi': {'version': '3.0'}, 'http_version': '1.1', 'method': 'POST',
                 'scheme': 'http', 'path': path, 'raw_path': path.encode(), 'query_string': b'',
                 'headers': [(b'content-type', b'application/json')], 'server': ('test', 80), 'client': ('test', 1)}
        await app(scope, receive, send)
        return messages

    body = {'request_id': str(request_id), 'kind': 'course', 'course_id': str(target)}
    messages = asyncio.run(call(body))
    data = json.loads(messages[1]['body'])
    assert messages[0]['status'] == 201 and data['amount_minor'] is None and 'subscription_tariff_id' not in data
    service.acquire.return_value = (service.acquire.return_value[0], False)
    assert asyncio.run(call(body))[0]['status'] == 200
    assert asyncio.run(call(body | {'amount_minor': 1}))[0]['status'] == 422
    paths = app.openapi()['paths']
    for path in ('/api/v1/me/discounts', '/api/v1/me/purchases', '/api/v1/me/subscriptions', '/api/v1/subscriptions/offers'):
        assert path in paths


def test_course_conflicts_and_missing_offers():
    async def scenario():
        user, target = uuid4(), uuid4()
        session, users, crud, catalog = AsyncMock(), AsyncMock(), AsyncMock(), AsyncMock()
        crud.purchase.return_value = None
        crud.user_state.return_value = ([], [], [])
        crud.subscription_links.return_value = []
        config = {'access': {'course_prices': {}, 'offer_order': ['course']}}
        service = CommerceService(session, users, crud, catalog, config)
        catalog.get_course.return_value = None
        with pytest.raises(CommerceError, match='not_found'):
            await service.acquire(user, uuid4(), 'course', target)
        material = SimpleNamespace(verified_course_id=target, access_type='free', kind='course', url=None)
        catalog.get_course.return_value = material
        with pytest.raises(CommerceError, match='course_access_exists'):
            await service.acquire(user, uuid4(), 'course', target)
        material.access_type = 'unknown'
        with pytest.raises(CommerceError, match='offer_unavailable'):
            await service.acquire(user, uuid4(), 'course', target)
        assert session.rollback.await_count == 3
        crud.create_purchase.assert_not_awaited()
    asyncio.run(scenario())


def test_discount_status_and_period_boundaries():
    from src.services.commerce import active

    now = datetime.now(UTC)
    access = SimpleNamespace(valid_from=now, valid_until=now + timedelta(seconds=1), revoked_at=None)
    assert active(access, now)
    access.valid_until = now
    assert not active(access, now)
    access.valid_until = None
    assert active(access, now)
    access.valid_from = now + timedelta(seconds=1)
    assert not active(access, now)
    access.valid_from, access.revoked_at = now, now
    assert not active(access, now)

    async def scenario():
        crud = AsyncMock()
        common = {'id': uuid4(), 'reason': 'promotion', 'granted_at': now, 'discount_percent': 10,
                  'discount_amount_minor': None}
        crud.discounts.return_value = [SimpleNamespace(**common, expires_at=now, redeemed_at=now),
                                       SimpleNamespace(**common, expires_at=now, redeemed_at=None),
                                       SimpleNamespace(**common, expires_at=None, redeemed_at=None)]
        result = await CommerceService(AsyncMock(), AsyncMock(), crud, AsyncMock(), {}).discounts(uuid4())
        assert [d['status'] for d in result] == ['redeemed', 'expired', 'available']
    asyncio.run(scenario())
