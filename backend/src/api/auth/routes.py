from fastapi import APIRouter, HTTPException

from src.api.account.schemas import Account
from src.api.auth.schemas import AuthSession, Credentials, Registration
from src.api.dependencies import ContextDep
from src.api.errors.schemas import Error
from src.api.service_dependencies import AuthServiceDep
from src.services.auth import EmailTaken, InvalidCredentials, issue_token

router = APIRouter(prefix='/auth', tags=['Аккаунт'])


def auth_session(user, completed: bool, config) -> AuthSession:
    token, expires_in = issue_token(user.id, config)
    return AuthSession(access_token=token, expires_in=expires_in, user=Account(
        id=user.id, email=user.email, created_at=user.created_at, onboarding_completed=completed,
    ))


@router.post('/register', operation_id='register', status_code=201, response_model=AuthSession,
             responses={409: {'model': Error}, 422: {'model': Error}}, openapi_extra={'security': []})
async def register(body: Registration, service: AuthServiceDep, context: ContextDep):
    try:
        user = await service.register(body.email, body.password)
    except EmailTaken:
        raise HTTPException(409, detail={'code': 'email_taken', 'message': 'Этот email уже зарегистрирован'}) from None
    return auth_session(user, False, context.settings.jwt)


@router.post('/login', operation_id='login', response_model=AuthSession,
             responses={401: {'model': Error}, 422: {'model': Error}}, openapi_extra={'security': []})
async def login(body: Credentials, service: AuthServiceDep, context: ContextDep):
    try:
        user = await service.login(body.email, body.password)
    except InvalidCredentials:
        raise HTTPException(401, detail={'code': 'invalid_credentials', 'message': 'Проверьте email и пароль'}) from None
    completed = await service.onboarding_completed(user.id)
    return auth_session(user, completed, context.settings.jwt)
