from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Security
from fastapi.exceptions import RequestValidationError
from fastapi.security import HTTPBearer
from pydantic import BeforeValidator

from src.api.dependencies import AccountDep, OptionalAccountDep
from src.api.errors.schemas import Error
from src.api.materials.schemas import (
    FilterOptions,
    MaterialDetail,
    MaterialExplanation,
    MaterialExplanationInput,
    MaterialFilters,
    MaterialPage,
)
from src.api.onboarding.routes import unavailable
from src.api.service_dependencies import ExplanationServiceDep, MaterialServiceDep
from src.config import load_demo_config
from src.services.onboarding import (
    InvalidAnswers,
    QuestionnaireUnavailable,
    QuestionnaireVersionMismatch,
)

router = APIRouter(prefix='/materials', tags=['Каталог'])
bearer = HTTPBearer(auto_error=False)
optional_security = {'security': [{}]}
errors = {401: {'model': Error}, 422: {'model': Error}}


def invalid(field):
    raise RequestValidationError([{'loc': ('query', field), 'msg': 'Invalid value', 'type': 'value_error'}])


@router.get('', operation_id='listMaterials', response_model=MaterialPage, response_model_exclude_unset=True,
            description='Без поиска материалы отсортированы по популярности, при поиске — по совпадению с запросом.',
            responses=errors, dependencies=[Security(bearer)], openapi_extra=optional_security)
async def list_materials(
    service: MaterialServiceDep, account: OptionalAccountDep,
    q: Annotated[str | None, BeforeValidator(lambda value: value.strip() if isinstance(value, str) else value),
                 Query(min_length=1, max_length=200)] = None,
    kind: Literal['course', 'article', 'document'] | None = None,
    topic_id: UUID | None = None, industry_id: UUID | None = None, skill_id: UUID | None = None,
    access_type: Literal['free', 'paid', 'subscription'] | None = None,
    min_price_minor: Annotated[int | None, Query(ge=0)] = None,
    max_price_minor: Annotated[int | None, Query(ge=0)] = None,
    max_duration_minutes: Annotated[int | None, Query(ge=1)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    if min_price_minor is not None and max_price_minor is not None and min_price_minor > max_price_minor:
        invalid('min_price_minor')
    filters = MaterialFilters(q=q, kind=kind, topic_id=topic_id, industry_id=industry_id, skill_id=skill_id,
                              access_type=access_type, min_price_minor=min_price_minor, max_price_minor=max_price_minor,
                              max_duration_minutes=max_duration_minutes, limit=limit, offset=offset)
    config = load_demo_config()
    return await service.search(filters, account.id if account is not None else None, config)


@router.get('/filters', operation_id='getMaterialFilters', response_model=FilterOptions)
async def material_filters(service: MaterialServiceDep):
    return await service.get_filters(load_demo_config())


@router.get('/{material_id}', operation_id='getMaterial', response_model=MaterialDetail, response_model_exclude_unset=True,
            responses={**errors, 404: {'model': Error}}, dependencies=[Security(bearer)], openapi_extra=optional_security)
async def get_material(material_id: UUID, service: MaterialServiceDep, account: OptionalAccountDep):
    result = await service.detail(material_id, account.id if account is not None else None, load_demo_config())
    if result is None:
        raise HTTPException(status_code=404)
    return result


@router.post('/{material_id}/explanation', operation_id='generateMaterialExplanation', response_model=MaterialExplanation,
             responses={code: {'model': Error} for code in (401, 404, 409, 422)}, dependencies=[Security(bearer)])
async def generate_material_explanation(material_id: UUID, body: MaterialExplanationInput,
                                        service: ExplanationServiceDep, account: AccountDep):
    try:
        result = await service.generate(account.id, material_id,
                                        body.onboarding.model_dump() if body.onboarding is not None else None)
    except QuestionnaireUnavailable:
        raise unavailable() from None
    except QuestionnaireVersionMismatch:
        raise HTTPException(409, detail={'code': 'questionnaire_version_mismatch', 'message': 'Версия анкеты изменилась'}) from None
    except InvalidAnswers as exc:
        raise RequestValidationError([{'loc': ('body', 'onboarding', *field.split('.')), 'msg': 'Invalid answer', 'type': 'value_error'}
                                      for field in exc.fields]) from None
    if result is None:
        raise HTTPException(404)
    return result
