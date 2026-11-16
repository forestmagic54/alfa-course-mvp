from fastapi import APIRouter, Security
from fastapi.security import HTTPBearer

from src.api.account.schemas import Account
from src.api.dependencies import AccountDep, SessionDep
from src.api.errors.schemas import Error
from src.db.crud.users import UsersCRUD

router = APIRouter(tags=['Аккаунт'])


@router.get('/me', operation_id='getMe', response_model=Account, responses={401: {'model': Error}},
            dependencies=[Security(HTTPBearer(auto_error=False))])
async def get_me(account: AccountDep, session: SessionDep):
    completed = await UsersCRUD(session).onboarding_completed(account.id)
    return Account(id=account.id, email=account.email, created_at=account.created_at, onboarding_completed=completed)
