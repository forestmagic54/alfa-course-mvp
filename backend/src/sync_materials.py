import asyncio

from sqlalchemy.ext.asyncio import async_sessionmaker

from src.config import load_demo_config
from src.config.settings import Settings
from src.db.crud.materials import MaterialsCRUD
from src.db.session import create_engine
from src.services.materials import MaterialSyncService


async def main():
    engine = create_engine(Settings().database.url)
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as session:
            config = load_demo_config()
            await MaterialSyncService(session, MaterialsCRUD(session, config), config).synchronize()
    finally:
        await engine.dispose()


if __name__ == '__main__':
    asyncio.run(main())
