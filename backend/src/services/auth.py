from math import isfinite
from uuid import UUID

import jwt
from sqlalchemy.ext.asyncio import AsyncSession

from src.config.settings import JWTConfig
from src.db.crud.favorites import FavoritesCRUD
from src.db.crud.users import UsersCRUD


def token_account_id(token: str, config: JWTConfig) -> UUID:
    try:
        claims = jwt.decode(token, config.jwt_secret.get_secret_value(), algorithms=[config.algorithm],
                            options={'require': ['sub', 'exp']})
        expiry = claims['exp']
        if isinstance(expiry, bool) or not isinstance(expiry, (int, float)) or not isfinite(expiry):
            raise ValueError('Invalid expiry')
        return UUID(claims['sub'])
    except (jwt.InvalidTokenError, ValueError, TypeError, AttributeError, OverflowError) as exc:
        raise ValueError('Invalid token') from exc


class EmailTaken(Exception):
    pass


class InvalidCredentials(Exception):
    pass


def issue_token(account_id: UUID, config: JWTConfig) -> tuple[str, int]:
    from datetime import UTC, datetime, timedelta

    expires_in = config.jwt_expire_minutes * 60
    expiry = datetime.now(UTC).replace(microsecond=0) + timedelta(seconds=expires_in)
    return jwt.encode({'sub': str(account_id), 'exp': expiry}, config.jwt_secret.get_secret_value(),
                      algorithm=config.algorithm), expires_in


class AuthService:
    def __init__(self, session: AsyncSession, users: UsersCRUD, favorites: FavoritesCRUD, default_folder_name: str):
        self.session = session
        self.users = users
        self.favorites = favorites
        self.default_folder_name = default_folder_name

    async def register(self, email: str, password: str):
        import asyncio

        from pwdlib import PasswordHash
        from sqlalchemy.exc import IntegrityError

        password_hash = await asyncio.to_thread(PasswordHash.recommended().hash, password)
        try:
            async with self.session.begin():
                user = await self.users.create(email.lower(), password_hash)
                await self.favorites.create_default(user.id, self.default_folder_name)
        except IntegrityError as exc:
            cause = exc.orig
            while cause is not None:
                constraint = getattr(cause, 'constraint_name', None) or getattr(getattr(cause, 'diag', None), 'constraint_name', None)
                if constraint in ('uq_users_email_lower', 'users_email_key') and getattr(cause, 'sqlstate', getattr(exc.orig, 'sqlstate', None)) == '23505':
                    raise EmailTaken from exc
                cause = cause.__cause__
            raise
        return user

    async def login(self, email: str, password: str):
        import asyncio

        from pwdlib import PasswordHash

        user = await self.users.get_by_email(email.lower())
        if user is None or not await asyncio.to_thread(PasswordHash.recommended().verify, password, user.password_hash):
            raise InvalidCredentials
        return user

    async def onboarding_completed(self, user_id: UUID) -> bool:
        return await self.users.onboarding_completed(user_id)
