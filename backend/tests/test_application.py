import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from fastapi import APIRouter
from pydantic import ValidationError
from sqlalchemy.engine import make_url

from src.__main__ import create_app
from src.api.dependencies import get_request_session
from src.config.settings import ApplicationConfig, DatabaseConfig, JWTConfig, Settings
from src.context import AppContext


def settings(**changes):
    return Settings(
        app=ApplicationConfig(_env_file=None, port=changes.get('port', 8000)),
        database=DatabaseConfig(_env_file=None, username=changes.get('username', 'user'),
                                password=changes.get('password', 'private-db-secret'),
                                name=changes.get('name', 'db'), host=changes.get('host', 'localhost'),
                                port=changes.get('database_port', 5432)),
        jwt=JWTConfig(_env_file=None, jwt_secret=changes.get('jwt_secret', 'test-secret'),
                      jwt_expire_minutes=changes.get('jwt_expire_minutes', 10)),
    )


def test_settings_validation():
    for changes in ({'password': ''}, {'jwt_secret': ' '}, {'jwt_expire_minutes': 0}):
        with pytest.raises(ValidationError):
            settings(**changes)
    with pytest.raises(ValidationError):
        JWTConfig(_env_file=None, jwt_secret='secret', jwt_expire_minutes=None)
    assert 'private-db-secret' not in repr(settings())
    assert 'test-secret' not in repr(settings())


def test_database_settings_from_postgres_environment(monkeypatch):
    for key, value in {'POSTGRES_USER': 'env-user', 'POSTGRES_PASSWORD': 'env-password',
                       'POSTGRES_DB': 'env-db', 'DATABASE_HOST': 'db',
                       'DATABASE_PORT': '5433'}.items():
        monkeypatch.setenv(key, value)
    config = DatabaseConfig(_env_file=None)
    assert (config.url.username, config.url.password, config.url.database,
            config.url.host, config.url.port) == ('env-user', 'env-password', 'env-db', 'db', 5433)


def test_database_url_preserves_special_characters():
    config = DatabaseConfig(_env_file=None, username='user@name', password='p@ss:/word',
                            host='localhost', port=5433, name='example/db')
    url = make_url(config.url.render_as_string(hide_password=False))
    assert (url.username, url.password) == ('user@name', 'p@ss:/word')
    assert 'p@ss:/word' not in str(config.url)


def test_custom_api_prefix_applies_to_routes(monkeypatch):
    monkeypatch.setenv('API_PREFIX', '/custom/v2')
    router = APIRouter()
    router.add_api_route('/example', lambda: None, methods=['GET'])
    monkeypatch.setattr('src.__main__.api_router', router)
    config = settings()
    config.app = ApplicationConfig(_env_file=None)
    app = create_app(config)
    assert '/custom/v2/example' in app.openapi()['paths']


def test_configured_demo_document_is_served():
    from urllib.parse import urlsplit

    from src.config import load_demo_config

    urls = load_demo_config()['catalog']['demo_document_urls']
    app = create_app(settings())

    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
            for url in urls.values():
                response = await client.get(urlsplit(url).path)
                assert response.status_code == 200 and 'ДЕМОМАТЕРИАЛ' in response.text
            assert (await client.get('/demo-files/does-not-exist.txt')).status_code == 404

    asyncio.run(run())


def test_lifespan_disposes_and_apps_are_independent(monkeypatch):
    engines = []
    def create_engine(_):
        engine = MagicMock()
        engine.dispose = AsyncMock()
        engines.append(engine)
        return engine
    monkeypatch.setattr('src.__main__.create_engine', create_engine)
    monkeypatch.setattr('src.__main__.async_sessionmaker', lambda *args, **kwargs: object())
    first, second = create_app(settings()), create_app(settings(port=8001))

    async def run():
        async with first.router.lifespan_context(first):
            async with second.router.lifespan_context(second):
                assert first.state.context is not second.state.context
                assert first.state.context.session_factory is not second.state.context.session_factory
        with pytest.raises(RuntimeError):
            async with first.router.lifespan_context(first):
                raise RuntimeError('failure')
    asyncio.run(run())
    assert all(engine.dispose.await_count == 1 for engine in engines)


def test_lifespan_llm_configuration_and_cleanup(monkeypatch):
    from src.services.llm_generator import LLMGenerator
    from src.services.recommendation_stubs import StubGenerator

    engine = MagicMock(dispose=AsyncMock())
    monkeypatch.setattr('src.__main__.create_engine', lambda _: engine)
    monkeypatch.setattr('src.__main__.async_sessionmaker', lambda *args, **kwargs: object())
    client = MagicMock(aclose=AsyncMock())
    monkeypatch.setattr('src.__main__.LLMSettings', lambda: SimpleNamespace(llm_timeout_seconds=30))
    monkeypatch.setattr('src.__main__.LLMClient', lambda settings: client)
    config = settings()
    config.app.llm_enabled = True
    app = create_app(config)

    async def run():
        with pytest.raises(RuntimeError):
            async with app.router.lifespan_context(app):
                assert isinstance(app.state.context.generator, LLMGenerator)
                raise RuntimeError('startup failure')
        client.aclose.assert_awaited_once()
        monkeypatch.setattr('src.__main__.LLMClient', MagicMock(side_effect=ValueError('secret')))
        async with app.router.lifespan_context(app):
            assert isinstance(app.state.context.generator, StubGenerator)
    asyncio.run(run())


def test_lifespan_disposes_on_partial_startup(monkeypatch):
    engine = MagicMock(dispose=AsyncMock())
    monkeypatch.setattr('src.__main__.create_engine', lambda _: engine)
    def fail(*args, **kwargs):
        raise RuntimeError('failure')
    monkeypatch.setattr('src.__main__.async_sessionmaker', fail)
    app = create_app(settings())
    async def run():
        with pytest.raises(RuntimeError):
            async with app.router.lifespan_context(app):
                pass
    asyncio.run(run())
    engine.dispose.assert_awaited_once()


def test_request_sessions_are_distinct_and_closed_without_commit():
    sessions = []
    def factory():
        session = MagicMock()
        session.__aenter__ = AsyncMock(return_value=session)
        session.__aexit__ = AsyncMock(return_value=False)
        session.commit = AsyncMock()
        sessions.append(session)
        return session
    context = AppContext(settings=settings(), session_factory=factory)
    async def run():
        first = get_request_session(context)
        second = get_request_session(context)
        assert await anext(first) is not await anext(second)
        await first.aclose()
        with pytest.raises(RuntimeError):
            await second.athrow(RuntimeError('failure'))
    asyncio.run(run())
    for session in sessions:
        session.__aexit__.assert_awaited_once()
        session.commit.assert_not_awaited()
