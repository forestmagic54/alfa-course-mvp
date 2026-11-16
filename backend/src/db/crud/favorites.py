from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models.favorites import FavoriteFolders, Favorites


class FavoritesCRUD:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def material_ids(self, user_id, material_ids):
        query = (select(Favorites.material_id).join(FavoriteFolders, FavoriteFolders.id == Favorites.folder_id)
                 .where(FavoriteFolders.user_id == user_id, Favorites.material_id.in_(material_ids)).distinct())
        return set((await self.session.scalars(query)).all())

    async def create_default(self, user_id, name: str) -> None:
        self.session.add(FavoriteFolders(user_id=user_id, name=name, is_default=True))
        await self.session.flush()

    async def folders(self, user_id):
        query = select(FavoriteFolders).where(FavoriteFolders.user_id == user_id).order_by(
            FavoriteFolders.created_at, FavoriteFolders.id)
        return list((await self.session.scalars(query)).all())

    async def folder(self, user_id, folder_id, *, lock=False):
        query = select(FavoriteFolders).where(FavoriteFolders.id == folder_id, FavoriteFolders.user_id == user_id)
        if lock:
            query = query.with_for_update()
        return await self.session.scalar(query)

    async def create_folder(self, user_id, name):
        folder = FavoriteFolders(user_id=user_id, name=name, is_default=False)
        self.session.add(folder)
        await self.session.flush()
        return folder

    async def saved_materials(self, folder_id):
        from src.db.models.materials import Materials

        query = (select(Favorites, Materials).join(Materials, Materials.id == Favorites.material_id)
                 .where(Favorites.folder_id == folder_id)
                 .order_by(Favorites.created_at.desc(), Favorites.material_id))
        return (await self.session.execute(query)).all()

    async def add_material(self, folder_id, material_id):
        from sqlalchemy.dialects.postgresql import insert

        query = insert(Favorites).values(folder_id=folder_id, material_id=material_id).on_conflict_do_nothing(
            index_elements=[Favorites.folder_id, Favorites.material_id])
        await self.session.execute(query)

    async def delete_material(self, folder_id, material_id):
        from sqlalchemy import delete

        await self.session.execute(delete(Favorites).where(
            Favorites.folder_id == folder_id, Favorites.material_id == material_id))

    async def delete_folder(self, folder):
        from sqlalchemy import delete

        await self.session.execute(delete(Favorites).where(Favorites.folder_id == folder.id))
        await self.session.delete(folder)
