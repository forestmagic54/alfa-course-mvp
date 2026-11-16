from fastapi import APIRouter, HTTPException, Response, Security
from fastapi.security import HTTPBearer

from src.api.dependencies import AccountDep
from src.api.errors.schemas import Error
from src.api.purchases.schemas import Purchase, PurchaseInput
from src.api.service_dependencies import CommerceServiceDep
from src.services.commerce import CommerceError

router = APIRouter(tags=['Приобретения'])
security = [Security(HTTPBearer(auto_error=False))]


@router.post('/me/purchases', operation_id='acquire', response_model=Purchase, response_model_exclude_unset=True,
             status_code=201, responses={code: {'model': Error} for code in (401, 404, 409, 422)} | {200: {'model': Purchase}}, dependencies=security)
async def acquire(body: PurchaseInput, response: Response, service: CommerceServiceDep, account: AccountDep):
    try:
        purchase, created = await service.acquire(account.id, body.request_id, body.kind,
                                                   body.course_id if body.kind == 'course' else body.subscription_tariff_id)
    except CommerceError as exc:
        if exc.code == 'not_found':
            raise HTTPException(404) from None
        raise HTTPException(409, detail={'code': exc.code, 'message': 'Приобретение недоступно'}) from None
    response.status_code = 201 if created else 200
    return purchase


@router.get('/me/purchases', operation_id='listPurchases', response_model=list[Purchase], response_model_exclude_unset=True,
            responses={401: {'model': Error}}, dependencies=security)
async def list_purchases(service: CommerceServiceDep, account: AccountDep):
    return await service.purchases(account.id)
