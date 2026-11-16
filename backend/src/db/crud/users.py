from uuid import UUID

from sqlalchemy import exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models.users import OnboardingResponses, Users


class UsersCRUD:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, account_id: UUID) -> Users | None:
        return await self.session.get(Users, account_id)

    async def get_by_email(self, email: str) -> Users | None:
        return await self.session.scalar(select(Users).where(func.lower(Users.email) == email.lower()))

    async def create(self, email: str, password_hash: str) -> Users:
        user = Users(email=email.lower(), password_hash=password_hash)
        self.session.add(user)
        await self.session.flush()
        return user

    async def onboarding_completed(self, user_id: UUID) -> bool:
        return bool(await self.session.scalar(select(exists().where(
            OnboardingResponses.user_id == user_id, OnboardingResponses.status == 'completed',
        ))))

    async def lock(self, user_id: UUID) -> Users | None:
        return await self.session.scalar(select(Users).where(Users.id == user_id).with_for_update())
