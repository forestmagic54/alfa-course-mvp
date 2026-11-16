from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.db.crud.favorites import FavoritesCRUD
from src.db.crud.materials import MaterialsCRUD
from src.services.materials import MaterialService
from src.services.types import FavoriteMaterialData


class FavoriteNotFound(Exception):
    pass


class DefaultFolderProtected(Exception):
    pass


class FavoriteService:
    def __init__(self, session: AsyncSession, favorites: FavoritesCRUD, catalog: MaterialsCRUD,
                 materials: MaterialService, config: Any):
        self.session, self.favorites, self.catalog = session, favorites, catalog
        self.materials, self.config = materials, config

    async def folder(self, user_id: UUID, folder_id: UUID, *, lock: bool = False):
        folder = await self.favorites.folder(user_id, folder_id, lock=lock)
        if folder is None:
            raise FavoriteNotFound
        return folder

    async def list_folders(self, user_id: UUID):
        return await self.favorites.folders(user_id)

    async def create_folder(self, user_id: UUID, name: str):
        try:
            folder = await self.favorites.create_folder(user_id, name)
            await self.session.commit()
            return folder
        except BaseException:
            await self.session.rollback()
            raise

    async def change_folder(self, user_id: UUID, folder_id: UUID, name: str | None):
        try:
            folder = await self.folder(user_id, folder_id, lock=True)
            if folder.is_default:
                raise DefaultFolderProtected
            if name is None:
                await self.favorites.delete_folder(folder)
            else:
                folder.name = name
            await self.session.commit()
            return folder
        except BaseException:
            await self.session.rollback()
            raise

    async def list_materials(self, user_id: UUID, folder_id: UUID) -> list[FavoriteMaterialData]:
        await self.folder(user_id, folder_id)
        rows = await self.favorites.saved_materials(folder_id)
        if not rows:
            return []
        visible = await self.catalog.visible_subset([saved.material_id for saved, _ in rows])
        cards = await self.materials.build_cards([material for _, material in rows if material.id in visible],
                                                 user_id, self.config)
        by_id = {card['id']: card for card in cards}
        return [{'material_id': saved.material_id, 'created_at': saved.created_at,
                 'material': by_id.get(saved.material_id)} for saved, _ in rows]

    async def change_material(self, user_id: UUID, folder_id: UUID, material_id: UUID, *, add: bool) -> None:
        try:
            await self.folder(user_id, folder_id, lock=True)
            material = await (self.catalog.get(material_id) if add else self.catalog.get_any(material_id))
            if material is None:
                raise FavoriteNotFound
            if add:
                await self.favorites.add_material(folder_id, material_id)
            else:
                await self.favorites.delete_material(folder_id, material_id)
            await self.session.commit()
        except BaseException:
            await self.session.rollback()
            raise
