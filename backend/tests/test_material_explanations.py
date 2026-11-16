import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx

from src.__main__ import create_app
from src.api.dependencies import get_app_context, get_request_session, required_account
from src.api.service_dependencies import get_explanation_service
from src.config import load_demo_config
from src.config.settings import ApplicationConfig, DatabaseConfig, JWTConfig, Settings
from src.services.material_explanations import (
    ExplanationLeaseService,
    ExplanationReader,
    MaterialExplanationService,
    may_generate,
    preferences_hash,
    usable,
)
from src.services.onboarding import effective_preferences


def test_explanation_reuse_and_refresh_policy():
    now = datetime(2026, 1, 8, tzinfo=UTC)
    row = SimpleNamespace(explanation='Текст.', profile_hash='profile', context_hash='context', source_version='v1',
                          generated_at=now - timedelta(days=7), attempted_at=None, lease_until=None)
    assert usable(row, 'profile', 'context', 'v1')
    assert not usable(row, 'profile', 'other', 'v1')
    assert not usable(row, 'profile', 'context', 'v2')
    assert may_generate(row, 'profile', now)
    assert not may_generate(row, 'profile', now - timedelta(microseconds=1))
    assert may_generate(row, 'new-profile', now - timedelta(days=1))
    row.attempted_at = now - timedelta(minutes=4)
    assert not may_generate(row, 'new-profile', now)
    row.attempted_at = now - timedelta(minutes=5)
    row.lease_until = now + timedelta(seconds=1)
    assert not may_generate(row, 'new-profile', now)
    row.lease_until = now
    assert may_generate(row, 'new-profile', now)


def test_empty_profile_matches_missing_profile():
    profile = SimpleNamespace(goal_code=None, industry_code=None, stage_code=None, learning_mode=None,
                              profile_config_version=load_demo_config()['profile_config_version'])
    assert preferences_hash(effective_preferences(profile, None)) == preferences_hash(effective_preferences(None, None))


def test_lease_preserves_old_result_on_failure_and_rejects_expired_worker():
    async def check():
        now = datetime(2026, 1, 8, tzinfo=UTC)
        row = SimpleNamespace(explanation='Предыдущий текст', offer_text=None, profile_hash='old',
                              context_hash='old', source_version='v1', generated_at=now - timedelta(days=8),
                              attempted_at=None, lease_id=None, lease_until=None)
        session = SimpleNamespace(commit=AsyncMock(), rollback=AsyncMock())
        service = ExplanationLeaseService(session, SimpleNamespace(lock=AsyncMock(return_value=row)))
        user_id, material_id = uuid4(), uuid4()
        lease = await service.acquire(user_id, material_id, 'old', now, timedelta(seconds=30))
        assert lease is not None
        assert await service.acquire(user_id, material_id, 'old', now, timedelta(seconds=30)) is None
        assert not await service.finish(user_id, material_id, uuid4(), now, explanation='Чужой текст',
                                        profile_hash='old', context_hash='old', source_version='v1')
        assert await service.finish(user_id, material_id, lease, now, explanation=None,
                                    profile_hash='old', context_hash='old', source_version='v1')
        assert row.explanation == 'Предыдущий текст'
        assert row.generated_at == now - timedelta(days=8)
        assert not may_generate(row, 'old', now + timedelta(minutes=4))
        second = await service.acquire(user_id, material_id, 'old', now + timedelta(minutes=5), timedelta(seconds=30))
        assert second is not None
        assert not await service.finish(user_id, material_id, second, now + timedelta(minutes=5, seconds=30),
                                        explanation='Опоздавший текст', profile_hash='old', context_hash='old',
                                        source_version='v1')
        assert row.explanation == 'Предыдущий текст'

    asyncio.run(check())


def test_reader_keeps_guest_and_stale_results_separate():
    async def check():
        user_id, material_id = uuid4(), uuid4()
        material = SimpleNamespace(id=material_id, default_offer_text='Базовый', source_version='v1')
        profile_hash = preferences_hash(effective_preferences(None, None))
        row = SimpleNamespace(explanation='Личный', profile_hash=profile_hash, context_hash=profile_hash,
                              source_version='v1')
        storage = SimpleNamespace(get=AsyncMock(return_value=row))
        profiles = SimpleNamespace(fresh_profile=AsyncMock(return_value=None))
        reader = ExplanationReader(storage, profiles)
        assert await reader.read(material, None) == 'Базовый'
        storage.get.assert_not_awaited()
        profiles.fresh_profile.assert_not_awaited()
        assert await reader.read(material, user_id) == 'Личный'
        storage.get.assert_awaited_once_with(user_id, material_id)
        material.source_version = 'v2'
        assert await reader.read(material, user_id) == 'Базовый'
        material.default_offer_text = None
        assert await reader.read(material, user_id) is None

    asyncio.run(check())


def test_generation_reuses_success_and_discards_changed_material():
    async def check():
        user_id, material_id = uuid4(), uuid4()
        material = SimpleNamespace(id=material_id, kind='document', title='Бюджет', public_description=None,
                                   default_offer_text='Базовый текст.', access_type='unknown', source_version='v1')
        row = SimpleNamespace(explanation=None, offer_text=None, profile_hash=None, context_hash=None,
                              source_version=None, generated_at=None, attempted_at=None, lease_id=None, lease_until=None)
        session = SimpleNamespace(commit=AsyncMock(), rollback=AsyncMock())
        catalog = SimpleNamespace(get=AsyncMock(return_value=material), lock_visible=AsyncMock(return_value=material),
                                  recent_studied=AsyncMock(return_value=[('Старый курс', 'course')]))
        onboarding = SimpleNamespace(fresh_profile=AsyncMock(return_value=None))
        users = SimpleNamespace(lock=AsyncMock())
        storage = SimpleNamespace(get=AsyncMock(return_value=row), lock=AsyncMock(return_value=row))
        response = SimpleNamespace(status='succeeded', material_id=material_id, source_version='v1', text='О бюджете.')
        client = SimpleNamespace(generate_document_description=AsyncMock(return_value=response))
        service = MaterialExplanationService(session, catalog, onboarding, users, storage, client, 1)
        assert (await service.generate(user_id, material_id, None))['explanation'] == 'О бюджете.'
        assert (await service.generate(user_id, material_id, None))['explanation'] == 'О бюджете.'
        assert client.generate_document_description.await_count == 1
        assert client.generate_document_description.await_args.kwargs['studied_materials'] == [
            {'title': 'Старый курс', 'kind': 'course'}]
        temporary = {'form_type': 'simple', 'questionnaire_version': '1', 'status': 'partial',
                     'answers': {'current_task': 'sales'}}
        assert (await service.generate(user_id, material_id, temporary))['explanation'] == 'Базовый текст.'
        assert client.generate_document_description.await_count == 1
        row.generated_at -= timedelta(days=7)

        async def changed(*args, **kwargs):
            material.source_version = 'v2'
            return response

        client.generate_document_description.side_effect = changed
        assert (await service.generate(user_id, material_id, None))['explanation'] == 'Базовый текст.'
        assert row.explanation == 'О бюджете.'
        material.source_version = 'v1'
        onboarding.fresh_profile.side_effect = None
        onboarding.fresh_profile.return_value = None
        row.attempted_at = None
        client.generate_document_description.side_effect = TimeoutError
        assert (await service.generate(user_id, material_id, None))['explanation'] == 'О бюджете.'
        assert row.explanation == 'О бюджете.'
        calls = client.generate_document_description.await_count
        assert (await service.generate(user_id, material_id, None))['explanation'] == 'О бюджете.'
        assert client.generate_document_description.await_count == calls
        assert row.source_version == 'v1'
        material.source_version = 'v1'
        row.attempted_at = None
        changed_profile = SimpleNamespace(goal_code='sales', stage_code=None, industry_code=None,
                                          learning_mode=None, profile_config_version='1')
        onboarding.fresh_profile.side_effect = [None, changed_profile]
        client.generate_document_description.side_effect = None
        assert (await service.generate(user_id, material_id, None))['explanation'] == 'Базовый текст.'
        assert row.explanation == 'О бюджете.'

    asyncio.run(check())


def test_post_requires_account_and_valid_body():
    async def check():
        jwt = JWTConfig(_env_file=None, jwt_secret='a' * 32, jwt_expire_minutes=10)
        settings = Settings(app=ApplicationConfig(_env_file=None),
                            database=DatabaseConfig(_env_file=None, username='test', password='test',
                                                    name='test', host='localhost'), jwt=jwt)
        app = create_app(settings)
        user_id, material_id = uuid4(), uuid4()
        service = SimpleNamespace(generate=AsyncMock(return_value={
            'material_id': material_id, 'kind': 'document', 'explanation': 'Текст.', 'offer_text': None}))
        app.dependency_overrides[get_app_context] = lambda: SimpleNamespace(settings=settings)
        app.dependency_overrides[get_request_session] = lambda: object()
        app.dependency_overrides[get_explanation_service] = lambda: service
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
            path = f'/api/v1/materials/{material_id}/explanation'
            assert (await client.post(path, json={})).status_code == 401
            assert (await client.post(path, json={}, headers={'Authorization': 'Bearer invalid'})).status_code == 401
            app.dependency_overrides[required_account] = lambda: SimpleNamespace(id=user_id)
            response = await client.post(path, json={})
            assert response.status_code == 200 and response.headers['cache-control'] == 'no-store'
            service.generate.assert_awaited_once_with(user_id, material_id, None)
            assert (await client.post(path, json={'onboarding': None})).status_code == 422
            assert (await client.post(path, json={'user_id': str(user_id)})).status_code == 422
            assert (await client.post(path)).status_code == 422

    asyncio.run(check())
