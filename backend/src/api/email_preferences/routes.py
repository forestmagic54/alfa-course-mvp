from fastapi import APIRouter, Security
from fastapi.exceptions import RequestValidationError
from fastapi.security import HTTPBearer

from src.api.dependencies import AccountDep
from src.api.email_preferences.schemas import EmailPreferences, EmailPreferencesInput
from src.api.errors.schemas import Error
from src.api.service_dependencies import EmailServiceDep
from src.services.email import EmailError

router = APIRouter(tags=['Рассылка'])
security = [Security(HTTPBearer(auto_error=False))]


@router.get('/me/email-preferences', operation_id='getEmailPreferences', response_model=EmailPreferences,
            responses={401: {'model': Error}}, dependencies=security)
async def get_email_preferences(account: AccountDep, service: EmailServiceDep):
    return await service.get(account.id)


@router.put('/me/email-preferences', operation_id='updateEmailPreferences', response_model=EmailPreferences,
            responses={401: {'model': Error}, 422: {'model': Error}}, dependencies=security)
async def update_email_preferences(body: EmailPreferencesInput, account: AccountDep, service: EmailServiceDep):
    try:
        return await service.update(account.id, body.marketing_consent, body.consent_version)
    except EmailError:
        raise RequestValidationError([{'loc': ('body', 'consent_version'), 'msg': 'Invalid version',
                                       'type': 'value_error'}]) from None
