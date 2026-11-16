from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models.material_studies import UserMaterialStudies


class MaterialStudiesCRUD:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def set_state(self, user_id: UUID, material_id: UUID, studied: bool) -> None:
        if studied:
            query = insert(UserMaterialStudies).values(user_id=user_id, material_id=material_id).on_conflict_do_nothing()
        else:
            query = delete(UserMaterialStudies).where(UserMaterialStudies.user_id == user_id,
                                                       UserMaterialStudies.material_id == material_id)
        await self.session.execute(query)

    async def studied_ids(self, user_id: UUID, material_ids: list[UUID]) -> set[UUID]:
        if not material_ids:
            return set()
        query = select(UserMaterialStudies.material_id).where(UserMaterialStudies.user_id == user_id,
                                                               UserMaterialStudies.material_id.in_(material_ids))
        return set((await self.session.scalars(query)).all())
