import asyncio
import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import jwt
import pytest
from fastapi import HTTPException
from fastapi.exceptions import RequestValidationError
from starlette.requests import Request

from src.__main__ import create_app
from src.api.dependencies import optional_account, required_account
from src.api.errors.handlers import http_error_handler, validation_error_handler
from src.config.settings import ApplicationConfig, DatabaseConfig, JWTConfig, Settings
from src.services.auth import token_account_id


def run(coro):
    return asyncio.run(coro)


def request(authorization=None):
    headers = [] if authorization is None else [(b'authorization', authorization.encode())]
    return Request({'type': 'http', 'method': 'GET', 'path': '/', 'headers': headers})


def config():
    return JWTConfig(_env_file=None, jwt_secret='test-secret-with-at-least-32-bytes-long', jwt_expire_minutes=10)


def token(**claims):
    return jwt.encode(claims, 'test-secret-with-at-least-32-bytes-long', algorithm='HS256')


def test_validation_errors_do_not_expose_values():
    errors = [
        {'loc': ('body', 'answers', 'current_task'), 'msg': 'secret', 'input': 'secret'},
        {'loc': ('body', 4), 'msg': 'JSON secret', 'input': 'secret'},
    ]
    response = run(validation_error_handler(request(), RequestValidationError(errors)))
    body = json.loads(response.body)
    assert body['code'] == 'validation_error'
    assert [field['field'] for field in body['fields']] == ['answers.current_task', '4']
    assert 'secret' not in response.body.decode()


def test_http_errors_preserve_authentication_header():
    response = run(http_error_handler(request(), HTTPException(401, detail='secret', headers={'WWW-Authenticate': 'Bearer'})))
    assert json.loads(response.body)['code'] == 'unauthorized'
    assert response.headers['www-authenticate'] == 'Bearer'
    assert b'secret' not in response.body


def test_jwt_rejects_invalid_claims_signature_and_expiry():
    future = datetime.now(UTC) + timedelta(minutes=1)
    account_id = uuid4()
    assert token_account_id(token(sub=str(account_id), exp=future), config()) == account_id
    invalid = [token(sub=str(account_id), exp=future) + 'x',
               token(sub=str(account_id), exp=datetime.now(UTC) - timedelta(seconds=1)),
               token(sub=str(account_id)), token(exp=future), token(sub='bad', exp=future),
               token(sub=str(account_id), exp='invalid'), token(sub=str(account_id), exp='9999999999'),
               token(sub=str(account_id), exp=True)]
    for value in invalid:
        with pytest.raises(ValueError):
            token_account_id(value, config())


def test_optional_and_required_authorization(monkeypatch):
    context = SimpleNamespace(settings=SimpleNamespace(jwt=config()))
    lookup = AsyncMock(return_value=object())
    monkeypatch.setattr('src.api.dependencies.find_account', lookup)
    assert run(optional_account(request(), context, None)) is None
    with pytest.raises(HTTPException) as error:
        run(required_account(None))
    assert error.value.status_code == 401
    for header in ('', 'Basic abc', 'Bearer broken', 'Bearer'):
        with pytest.raises(HTTPException) as error:
            run(optional_account(request(header), context, None))
        assert error.value.status_code == 401
        assert error.value.headers['WWW-Authenticate'] == 'Bearer'
    account_id = uuid4()
    header = 'Bearer ' + token(sub=str(account_id), exp=datetime.now(UTC) + timedelta(minutes=1))
    assert run(optional_account(request(header), context, None)) is lookup.return_value
    lookup.assert_awaited_once_with(account_id, None)
    lookup.return_value = None
    with pytest.raises(HTTPException):
        run(optional_account(request(header), context, None))
    lookup.side_effect = RuntimeError('database failure')
    with pytest.raises(RuntimeError):
        run(optional_account(request(header), context, None))


def test_no_store_preserves_response_and_respects_prefix():
    settings = Settings(app=ApplicationConfig(_env_file=None, api_prefix='/custom'),
                        database=DatabaseConfig(_env_file=None, username='user', password='password', name='db', host='localhost'),
                        jwt=config())
    app = create_app(settings)
    @app.get('/custom/private')
    @app.get('/other')
    async def endpoint():
        raise HTTPException(401, headers={'WWW-Authenticate': 'Bearer', 'X-Example': 'kept'})

    @app.get('/custom/failure')
    async def failure():
        raise RuntimeError('private database details')

    async def call(path):
        messages = []
        received = False
        async def receive():
            nonlocal received
            if not received:
                received = True
                return {'type': 'http.request', 'body': b'', 'more_body': False}
            await asyncio.Event().wait()
        async def send(message):
            messages.append(message)
        scope = {'type': 'http', 'asgi': {'version': '3.0'}, 'http_version': '1.1',
                   'method': 'GET', 'scheme': 'http', 'path': path, 'raw_path': path.encode(),
                   'query_string': b'', 'headers': [], 'server': ('test', 80), 'client': ('test', 1)}
        try:
            await app(scope, receive, send)
        except RuntimeError:
            pass
        return messages

    private = run(call('/custom/private'))
    other = run(call('/other'))
    failure_response = run(call('/custom/failure'))
    headers = dict(private[0]['headers'])
    assert private[0]['status'] == 401
    assert headers[b'cache-control'] == b'no-store'
    assert headers[b'www-authenticate'] == b'Bearer'
    assert headers[b'x-example'] == b'kept'
    assert json.loads(private[1]['body'])['code'] == 'unauthorized'
    assert b'cache-control' not in dict(other[0]['headers'])
    assert failure_response[0]['status'] == 500
    assert dict(failure_response[0]['headers'])[b'cache-control'] == b'no-store'
    assert b'private database details' not in failure_response[1]['body']


def test_find_account_uses_request_session():
    from src.api.dependencies import find_account
    from src.db.models.users import Users

    account_id = uuid4()
    account = object()
    session = SimpleNamespace(get=AsyncMock(return_value=account))
    assert run(find_account(account_id, session)) is account
    session.get.assert_awaited_once_with(Users, account_id)
    session.get.side_effect = RuntimeError('database failure')
    with pytest.raises(RuntimeError):
        run(find_account(account_id, session))
