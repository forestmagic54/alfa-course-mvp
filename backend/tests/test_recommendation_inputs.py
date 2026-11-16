import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID

import pytest
from fastapi.dependencies.utils import request_body_to_args
from fastapi.exceptions import RequestValidationError

from src.api.errors.handlers import validation_error_handler
from src.api.recommendations.routes import get_recommendations
from src.api.recommendations.routes import router as feeds_router
from src.api.roadmaps.routes import router as roadmaps_router


def generation_route(operation_id):
    return next(route for route in [*feeds_router.routes, *roadmaps_router.routes]
                if route.operation_id == operation_id)


def test_get_recommendations_requests_six_items():
    service = SimpleNamespace(feed=AsyncMock(return_value={}))
    asyncio.run(get_recommendations(service=service, account=None, mode=None, format=None))
    service.feed.assert_awaited_once_with(None, mode=None, format=None, limit=6)


@pytest.mark.parametrize(('operation_id', 'field'), [
    ('generateRecommendations', 'format'), ('generateRecommendations', 'onboarding'),
    ('generateRoadmap', 'onboarding'),
])
def test_explicit_null_returns_contract_validation_error(operation_id, field):
    route = generation_route(operation_id)

    async def validate():
        _, errors = await request_body_to_args(route.dependant.body_params, {field: None}, route._embed_body_fields)
        assert errors
        return await validation_error_handler(None, RequestValidationError(errors))

    response = asyncio.run(validate())

    assert response.status_code == 422
    body = json.loads(response.body)
    assert body['code'] == 'validation_error'
    assert [error['field'] for error in body['fields']] == [field]


@pytest.mark.parametrize('operation_id', ['generateRecommendations', 'generateRoadmap'])
@pytest.mark.parametrize('answers', [None, {'current_task': 'sales'}, {'current_task': None}])
def test_omitted_or_partial_onboarding_reaches_service_without_losing_resets(operation_id, answers):
    route = generation_route(operation_id)
    onboarding = (None if answers is None else
                  {'form_type': 'simple', 'questionnaire_version': '1', 'status': 'partial', 'answers': answers})
    payload = {} if onboarding is None else {'onboarding': onboarding}
    service = SimpleNamespace(feed=AsyncMock(return_value={}), generate=AsyncMock(return_value={}))
    user_id = UUID(int=1)

    async def call():
        values, errors = await request_body_to_args(route.dependant.body_params, payload, route._embed_body_fields)
        assert not errors
        return await route.endpoint(values['body'], service=service, account=SimpleNamespace(id=user_id))

    asyncio.run(call())

    if operation_id == 'generateRecommendations':
        service.feed.assert_awaited_once_with(user_id, format=None, onboarding=onboarding, regenerate=True)
    else:
        service.generate.assert_awaited_once_with(user_id, onboarding)
