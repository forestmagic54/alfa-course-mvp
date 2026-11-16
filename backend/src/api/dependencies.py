from collections.abc import AsyncIterator
from contextlib import aclosing
from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from src.context import AppContext
from src.db.crud.users import UsersCRUD
from src.db.models.users import Users
from src.db.session import get_session
from src.services.auth import token_account_id


def get_app_context(request: Request) -> AppContext:
    return request.app.state.context


ContextDep = Annotated[AppContext, Depends(get_app_context)]


async def get_request_session(context: ContextDep) -> AsyncIterator[AsyncSession]:
    async with aclosing(get_session(context.session_factory)) as sessions:
        async for session in sessions:
            yield session


SessionDep = Annotated[AsyncSession, Depends(get_request_session)]


async def find_account(account_id: UUID, session: AsyncSession) -> Users | None:
    return await UsersCRUD(session).get_by_id(account_id)


def unauthorized() -> HTTPException:
    return HTTPException(status_code=401, headers={'WWW-Authenticate': 'Bearer'})


async def optional_account(request: Request, context: ContextDep, session: SessionDep) -> object | None:
    authorization = request.headers.get('Authorization')
    if authorization is None:
        return None
    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != 'bearer':
        raise unauthorized()
    try:
        account_id = token_account_id(parts[1], context.settings.jwt)
    except ValueError:
        raise unauthorized() from None
    account = await find_account(account_id, session)
    if account is None:
        raise unauthorized()
    return account


async def required_account(account: Annotated[object | None, Depends(optional_account)]) -> object:
    if account is None:
        raise unauthorized()
    return account


OptionalAccountDep = Annotated[object | None, Depends(optional_account)]
AccountDep = Annotated[object, Depends(required_account)]
