from uuid import UUID

from fastapi import APIRouter, HTTPException, Security
from fastapi.exceptions import RequestValidationError
from fastapi.security import HTTPBearer

from src.api.dependencies import AccountDep, OptionalAccountDep
from src.api.errors.schemas import Error
from src.api.onboarding.routes import unavailable
from src.api.roadmaps.schemas import Roadmap, RoadmapInput
from src.api.service_dependencies import RoadmapServiceDep
from src.services.onboarding import (
    InvalidAnswers,
    QuestionnaireUnavailable,
    QuestionnaireVersionMismatch,
)
from src.services.recommendations import RankingUnavailable, RoadmapUnavailable
from src.services.roadmaps import MissingGoal

router = APIRouter(tags=['Карты цели'])
security = [Security(HTTPBearer(auto_error=False))]


@router.post('/roadmaps', operation_id='generateRoadmap', response_model=Roadmap,
             response_model_exclude_unset=True,
             responses={code: {'model': Error} for code in (401, 409, 422, 503)},
             dependencies=security, openapi_extra={'security': [{}]})
async def generate_roadmap(body: RoadmapInput, service: RoadmapServiceDep, account: OptionalAccountDep):
    try:
        return await service.generate(account.id if account else None, body.onboarding.model_dump() if body.onboarding else None)
    except MissingGoal:
        raise RequestValidationError([{'loc': ('body', 'onboarding', 'answers', 'current_task'), 'msg': 'Goal required', 'type': 'value_error'}]) from None
    except InvalidAnswers as exc:
        raise RequestValidationError([{'loc': ('body', 'onboarding', *field.split('.')), 'msg': 'Invalid answer', 'type': 'value_error'} for field in exc.fields]) from None
    except QuestionnaireUnavailable:
        raise unavailable() from None
    except QuestionnaireVersionMismatch:
        raise HTTPException(409, detail={'code': 'questionnaire_version_mismatch', 'message': 'Версия анкеты изменилась'}) from None
    except RoadmapUnavailable:
        raise HTTPException(422, detail={'code': 'roadmap_unavailable', 'message': 'Карта для этой цели недоступна'}) from None
    except RankingUnavailable:
        raise HTTPException(503, detail={'code': 'ranking_unavailable', 'message': 'Рекомендации временно недоступны'}) from None


@router.get('/me/roadmaps', operation_id='listSavedRoadmaps', response_model=list[Roadmap],
            response_model_exclude_unset=True,
            responses={401: {'model': Error}}, dependencies=security)
async def list_roadmaps(service: RoadmapServiceDep, account: AccountDep):
    return await service.saved(account.id)


@router.get('/me/roadmaps/{list_id}', operation_id='getRoadmap', response_model=Roadmap,
            response_model_exclude_unset=True,
            responses={code: {'model': Error} for code in (401, 404, 422)}, dependencies=security)
async def get_roadmap(list_id: UUID, service: RoadmapServiceDep, account: AccountDep):
    result = await service.get(account.id, list_id)
    if result is None:
        raise HTTPException(404)
    return result


@router.put('/me/roadmaps/{list_id}/saved', operation_id='saveRoadmap', response_model=Roadmap,
            response_model_exclude_unset=True,
            responses={code: {'model': Error} for code in (401, 404, 422)}, dependencies=security)
async def save_roadmap(list_id: UUID, service: RoadmapServiceDep, account: AccountDep):
    result = await service.save(account.id, list_id)
    if result is None:
        raise HTTPException(404)
    return result
