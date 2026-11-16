from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models.email import EmailMessages, EmailPreferences


class EmailCRUD:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def preferences(self, user_id: UUID) -> EmailPreferences | None:
        return await self.session.get(EmailPreferences, user_id)

    async def message(self, message_id: UUID) -> EmailMessages | None:
        return await self.session.get(EmailMessages, message_id)

    async def add(self, row: EmailPreferences | EmailMessages) -> None:
        self.session.add(row)
        await self.session.flush()
