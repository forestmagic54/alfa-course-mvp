from uuid import UUID

from fastapi import APIRouter, HTTPException, Response, Security
from fastapi.security import HTTPBearer

from src.api.dependencies import AccountDep
from src.api.errors.schemas import Error
from src.api.material_studies.schemas import MaterialStudyStateInput
from src.api.service_dependencies import MaterialStudyServiceDep

router = APIRouter(tags=['Карты цели'])


@router.put('/me/materials/{material_id}/study-state', operation_id='setMaterialStudyState', status_code=204,
            responses={code: {'model': Error} for code in (401, 404, 422)},
            dependencies=[Security(HTTPBearer(auto_error=False))])
async def set_material_study_state(material_id: UUID, body: MaterialStudyStateInput,
                                   service: MaterialStudyServiceDep, account: AccountDep):
    if not await service.set(account.id, material_id, body.is_studied):
        raise HTTPException(404)
    return Response(status_code=204)
