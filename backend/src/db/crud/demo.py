from sqlalchemy import exists, insert, select, text

from src.db.models import Base


class DemoCRUD:
    def __init__(self, session):
        self.session = session

    async def state(self, rows):
        await self.session.execute(text("SELECT pg_advisory_xact_lock(hashtext('mvp.demo.load'))"))
        populated = any([await self.session.scalar(select(exists().select_from(table)))
                         for table in Base.metadata.sorted_tables])
        if not populated:
            return 'empty'
        for name in ('mvp.users', 'mvp.materials'):
            table = Base.metadata.tables[name]
            expected = {row['id'] for row in rows[name]}
            actual = set((await self.session.scalars(select(table.c.id).where(table.c.id.in_(expected)))).all())
            if actual != expected:
                return 'incompatible'
        return 'loaded'

    async def insert(self, rows):
        for table in Base.metadata.sorted_tables:
            for row in rows.get(table.fullname, []):
                await self.session.execute(insert(table), row)
