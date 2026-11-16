from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models.material_explanations import MaterialExplanations


class MaterialExplanationsCRUD:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get(self, user_id: UUID, material_id: UUID) -> MaterialExplanations | None:
        return await self.session.get(MaterialExplanations, (user_id, material_id))

    async def lock(self, user_id: UUID, material_id: UUID) -> MaterialExplanations:
        await self.session.execute(insert(MaterialExplanations).values(
            user_id=user_id, material_id=material_id).on_conflict_do_nothing())
        query = (select(MaterialExplanations).where(MaterialExplanations.user_id == user_id,
                  MaterialExplanations.material_id == material_id).with_for_update()
                 .execution_options(populate_existing=True))
        return (await self.session.execute(query)).scalar_one()
