from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models.users import OnboardingResponses, UserProfiles


class OnboardingCRUD:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def latest(self, user_id):
        return await self.session.scalar(select(OnboardingResponses).where(
            OnboardingResponses.user_id == user_id,
        ).order_by(OnboardingResponses.submitted_at.desc(), OnboardingResponses.id.desc()).limit(1))

    async def profile(self, user_id):
        return await self.session.get(UserProfiles, user_id)

    async def create_response(self, **values):
        response = OnboardingResponses(**values)
        self.session.add(response)
        await self.session.flush()
        return response

    async def create_profile(self, **values):
        profile = UserProfiles(**values)
        self.session.add(profile)
        return profile

    async def fresh_profile(self, user_id):
        return await self.session.scalar(select(UserProfiles).where(UserProfiles.user_id == user_id)
                                         .execution_options(populate_existing=True))
