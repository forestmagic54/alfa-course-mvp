from typing import Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Security
from fastapi.exceptions import RequestValidationError
from fastapi.security import HTTPBearer

from src.api.dependencies import AccountDep, OptionalAccountDep
from src.api.errors.schemas import Error
from src.api.onboarding.routes import unavailable
from src.api.recommendations.schemas import FeedFormat, FeedInput, RecommendationList
from src.api.service_dependencies import FeedServiceDep
from src.services.feeds import FeedService
from src.services.onboarding import (
    InvalidAnswers,
    QuestionnaireUnavailable,
    QuestionnaireVersionMismatch,
)
from src.services.recommendations import RankingUnavailable

router = APIRouter(tags=['Рекомендации'])
bearer = HTTPBearer(auto_error=False)
security = [Security(bearer)]
errors = {code: {'model': Error} for code in (401, 422, 503)}


async def get_feed(service: FeedService, account, **kwargs):
    try:
        return await service.feed(account.id if account is not None else None, **kwargs)
    except RankingUnavailable:
        raise HTTPException(503, detail={'code': 'ranking_unavailable', 'message': 'Рекомендации временно недоступны'}) from None
    except QuestionnaireUnavailable:
        raise unavailable() from None
    except QuestionnaireVersionMismatch:
        raise HTTPException(409, detail={'code': 'questionnaire_version_mismatch', 'message': 'Версия анкеты изменилась'}) from None
    except InvalidAnswers as exc:
        raise RequestValidationError([{'loc': ('body', 'onboarding', *field.split('.')), 'msg': 'Invalid answer', 'type': 'value_error'}
                                      for field in exc.fields]) from None


@router.get('/recommendations', operation_id='getRecommendations', response_model=RecommendationList,
            response_model_exclude_unset=True,
            responses=errors, dependencies=security, openapi_extra={'security': [{}]})
async def get_recommendations(service: FeedServiceDep, account: OptionalAccountDep,
                              mode: Literal['popular', 'personalized'] | None = None, format: FeedFormat | None = None):
    return await get_feed(service, account, mode=mode, format=format, limit=6)


@router.post('/recommendations', operation_id='generateRecommendations', response_model=RecommendationList,
             response_model_exclude_unset=True,
             responses={**errors, 409: {'model': Error}}, dependencies=security, openapi_extra={'security': [{}]})
async def generate_recommendations(body: FeedInput, service: FeedServiceDep, account: OptionalAccountDep):
    return await get_feed(service, account, format=body.format,
                          onboarding=body.onboarding.model_dump() if body.onboarding else None, regenerate=True)


@router.get('/me/recommendations', operation_id='listSavedRecommendations', response_model=list[RecommendationList],
            response_model_exclude_unset=True,
            responses={401: {'model': Error}}, dependencies=security)
async def list_saved_recommendations(service: FeedServiceDep, account: AccountDep):
    return await service.saved(account.id)


@router.put('/me/recommendations/{list_id}/saved', operation_id='saveRecommendations', response_model=RecommendationList,
            response_model_exclude_unset=True,
            responses={code: {'model': Error} for code in (401, 404, 422)}, dependencies=security)
async def save_recommendations(list_id: UUID, service: FeedServiceDep, account: AccountDep):
    result = await service.save_feed(account.id, list_id)
    if result is None:
        raise HTTPException(404)
    return result
