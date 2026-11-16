from fastapi import APIRouter, HTTPException, Security
from fastapi.exceptions import RequestValidationError
from fastapi.security import HTTPBearer

from src.api.dependencies import AccountDep, SessionDep
from src.api.errors.schemas import Error
from src.api.onboarding.schemas import (
    FormType,
    OnboardingInput,
    OnboardingResponse,
    Questionnaire,
)
from src.api.service_dependencies import OnboardingServiceDep
from src.db.crud.onboarding import OnboardingCRUD
from src.services.onboarding import (
    InvalidAnswers,
    QuestionnaireUnavailable,
    QuestionnaireVersionMismatch,
    current_config,
)

router = APIRouter(tags=['Анкета'])
security = [Security(HTTPBearer(auto_error=False))]


def unavailable():
    return HTTPException(404, detail={'code': 'questionnaire_not_available', 'message': 'Анкета недоступна'})


@router.get('/onboarding/questionnaire', operation_id='getQuestionnaire', response_model=Questionnaire,
            response_model_exclude_none=True, responses={404: {'model': Error}, 422: {'model': Error}},
            openapi_extra={'security': []})
async def get_questionnaire(form_type: FormType = 'simple'):
    try:
        return current_config(form_type)['questionnaire']
    except QuestionnaireUnavailable:
        raise unavailable() from None


@router.get('/me/onboarding', operation_id='getOnboarding', response_model=OnboardingResponse | None,
            responses={401: {'model': Error}}, dependencies=security)
async def get_onboarding(account: AccountDep, session: SessionDep):
    return await OnboardingCRUD(session).latest(account.id)


@router.put('/me/onboarding', operation_id='saveOnboarding', response_model=OnboardingResponse,
            responses={401: {'model': Error}, 404: {'model': Error}, 409: {'model': Error}, 422: {'model': Error}},
            dependencies=security)
async def put_onboarding(body: OnboardingInput, account: AccountDep, service: OnboardingServiceDep):
    try:
        return await service.save(account.id, body.form_type, body.questionnaire_version,
                                     body.status, body.answers)
    except QuestionnaireUnavailable:
        raise unavailable() from None
    except QuestionnaireVersionMismatch:
        raise HTTPException(409, detail={'code': 'questionnaire_version_mismatch', 'message': 'Версия анкеты изменилась'}) from None
    except InvalidAnswers as exc:
        raise RequestValidationError([{'loc': ('body', *field.split('.')), 'msg': 'Invalid answer', 'type': 'value_error'}
                                      for field in exc.fields]) from None
