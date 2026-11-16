from fastapi import APIRouter, Security
from fastapi.security import HTTPBearer

from src.api.dependencies import AccountDep, SessionDep
from src.api.errors.schemas import Error
from src.api.preferences.schemas import Preferences
from src.db.crud.onboarding import OnboardingCRUD

router = APIRouter(tags=['Анкета'])


@router.get('/me/preferences', operation_id='getPreferences', response_model=Preferences | None,
            responses={401: {'model': Error}}, dependencies=[Security(HTTPBearer(auto_error=False))])
async def get_preferences(account: AccountDep, session: SessionDep):
    return await OnboardingCRUD(session).profile(account.id)
