import asyncio
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import jwt
import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import IntegrityError

from src.api.auth.routes import auth_session
from src.api.auth.routes import login as login_route
from src.api.auth.routes import register as register_route
from src.api.auth.schemas import Credentials, Registration
from src.config.settings import JWTConfig
from src.db.crud.users import UsersCRUD
from src.services import auth


def run(value):
    return asyncio.run(value)


def test_registration_atomicity_and_conflicts(monkeypatch):
    events = []
    user = SimpleNamespace(id=uuid4())
    class Users:
        def __init__(self, session): pass
        async def create(self, email, password_hash):
            events.append(('user', email, password_hash))
            return user
    class Favorites:
        def __init__(self, session): pass
        async def create_default(self, user_id, name):
            events.append(('folder', user_id, name))
            if failure[0]:
                raise failure[0]
    @asynccontextmanager
    async def begin():
        events.append('begin')
        try:
            yield
        except Exception:
            events.append('rollback')
            raise
        else:
            events.append('commit')
    session = SimpleNamespace(begin=begin)
    failure = [None]
    service = auth.AuthService(session, Users(session), Favorites(session), 'Избранное')
    assert run(service.register( 'TEST@example.com', 'password')) is user
    assert events[0] == 'begin' and events[-1] == 'commit'
    assert events[1][1] == 'test@example.com' and events[1][2] != 'password'
    assert events[2][1] == user.id
    failure[0] = RuntimeError('folder failure')
    with pytest.raises(RuntimeError):
        run(service.register('TEST@example.com', 'password'))
    assert events[-1] == 'rollback'
    class UniqueViolation(Exception):
        sqlstate = '23505'
        constraint_name = 'uq_users_email_lower'
    failure[0] = IntegrityError('', {}, UniqueViolation())
    with pytest.raises(auth.EmailTaken):
        run(service.register('TEST@example.com', 'password'))
    assert events[-1] == 'rollback'
    failure[0] = IntegrityError('', {}, SimpleException())
    with pytest.raises(IntegrityError):
        run(service.register('TEST@example.com', 'password'))


class SimpleException(Exception):
    sqlstate = '23505'
    constraint_name = 'uq_favorite_folders_default'


def test_login_normalizes_and_never_writes(monkeypatch):
    from pwdlib import PasswordHash
    user = SimpleNamespace(password_hash=PasswordHash.recommended().hash('Password  '))
    lookup = AsyncMock(return_value=user)
    session = SimpleNamespace()
    service = auth.AuthService(session, SimpleNamespace(get_by_email=lookup), None, 'Избранное')
    assert run(service.login('TEST@example.com', 'Password  ')) is user
    lookup.assert_awaited_with('test@example.com')
    with pytest.raises(auth.InvalidCredentials):
        run(service.login('test@example.com', 'wrong'))
    lookup.return_value = None
    with pytest.raises(auth.InvalidCredentials):
        run(service.login('missing@example.com', 'wrong'))
    lookup.side_effect = RuntimeError('database')
    with pytest.raises(RuntimeError):
        run(service.login('test@example.com', 'wrong'))


def test_jwt_and_account_response():
    config = JWTConfig(_env_file=None, jwt_secret='secret' * 8, jwt_expire_minutes=3)
    user = SimpleNamespace(id=uuid4(), email='test@example.com', created_at=datetime.now(UTC), password_hash='private')
    before = datetime.now(UTC).replace(microsecond=0)
    response = auth_session(user, True, config)
    after = datetime.now(UTC).replace(microsecond=0)
    claims = jwt.decode(response.access_token, config.jwt_secret.get_secret_value(), algorithms=[config.algorithm])
    assert auth.token_account_id(response.access_token, config) == user.id
    assert before + timedelta(seconds=180) <= datetime.fromtimestamp(claims['exp'], UTC) <= after + timedelta(seconds=180)
    assert response.expires_in == 180 and 'password_hash' not in response.model_dump()['user']
    with pytest.raises(ValueError):
        auth.token_account_id(response.access_token, JWTConfig(_env_file=None, jwt_secret='other' * 8, jwt_expire_minutes=3))


def test_onboarding_query_uses_user_and_completed_history():
    queries = []
    async def scalar(query):
        queries.append(query.compile(dialect=postgresql.dialect()))
        return True
    user_id = uuid4()
    assert run(UsersCRUD(SimpleNamespace(scalar=scalar)).onboarding_completed(user_id))
    sql = str(queries[0])
    assert 'EXISTS' in sql and 'user_id' in sql and 'status' in sql
    assert user_id in queries[0].params.values() and 'completed' in queries[0].params.values()
    assert 'ORDER BY' not in sql


def test_routes_map_errors_identically(monkeypatch):
    from fastapi import HTTPException
    context = SimpleNamespace(settings=SimpleNamespace(jwt=None))
    service = SimpleNamespace(register=AsyncMock(side_effect=auth.EmailTaken),
                              login=AsyncMock(side_effect=auth.InvalidCredentials))
    with pytest.raises(HTTPException) as error:
        run(register_route(Registration(email='test@example.com', password='password'), service, context))
    assert error.value.status_code == 409 and error.value.detail['code'] == 'email_taken'
    with pytest.raises(HTTPException) as error:
        run(login_route(Credentials(email='test@example.com', password='wrong'), service, context))
    assert error.value.status_code == 401 and error.value.detail == {'code': 'invalid_credentials', 'message': 'Проверьте email и пароль'}
