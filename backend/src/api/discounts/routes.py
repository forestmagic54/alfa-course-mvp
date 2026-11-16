from fastapi import APIRouter, Security
from fastapi.security import HTTPBearer

from src.api.dependencies import AccountDep
from src.api.discounts.schemas import DiscountGrant
from src.api.errors.schemas import Error
from src.api.service_dependencies import CommerceServiceDep

router = APIRouter(tags=['Приобретения'])


@router.get('/me/discounts', operation_id='listDiscounts', response_model=list[DiscountGrant],
            responses={401: {'model': Error}}, dependencies=[Security(HTTPBearer(auto_error=False))])
async def list_discounts(service: CommerceServiceDep, account: AccountDep):
    return await service.discounts(account.id)
