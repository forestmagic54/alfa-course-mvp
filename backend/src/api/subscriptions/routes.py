from fastapi import APIRouter, Security
from fastapi.security import HTTPBearer

from src.api.dependencies import AccountDep, OptionalAccountDep
from src.api.errors.schemas import Error
from src.api.materials.schemas import SubscriptionOffer
from src.api.service_dependencies import CommerceServiceDep
from src.api.subscriptions.schemas import SubscriptionAccess

router = APIRouter(tags=['Приобретения'])
security = [Security(HTTPBearer(auto_error=False))]


@router.get('/me/subscriptions', operation_id='listActiveSubscriptions', response_model=list[SubscriptionAccess],
            responses={401: {'model': Error}}, dependencies=security)
async def list_subscriptions(service: CommerceServiceDep, account: AccountDep):
    return await service.subscriptions(account.id)


@router.get('/subscriptions/offers', operation_id='listSubscriptionOffers', response_model=list[SubscriptionOffer],
            responses={401: {'model': Error}}, dependencies=security, openapi_extra={'security': [{}]})
async def list_offers(service: CommerceServiceDep, account: OptionalAccountDep):
    return await service.offers(account.id if account else None)
