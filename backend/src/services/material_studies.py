from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.db.crud.material_studies import MaterialStudiesCRUD
from src.db.crud.materials import MaterialsCRUD


class MaterialStudyService:
    def __init__(self, session: AsyncSession, catalog: MaterialsCRUD, studies: MaterialStudiesCRUD):
        self.session, self.catalog, self.studies = session, catalog, studies

    async def set(self, user_id: UUID, material_id: UUID, studied: bool) -> bool:
        try:
            material = await (self.catalog.get(material_id) if studied else self.catalog.get_any(material_id))
            if material is None:
                await self.session.rollback()
                return False
            await self.studies.set_state(user_id, material_id, studied)
            await self.session.commit()
            return True
        except BaseException:
            await self.session.rollback()
            raise
