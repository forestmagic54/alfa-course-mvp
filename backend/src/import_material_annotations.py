import asyncio
from importlib.resources import files

from sqlalchemy.ext.asyncio import async_sessionmaker

from src.config import load_demo_config
from src.config.settings import Settings
from src.db.crud.materials import MaterialsCRUD
from src.db.session import create_engine
from src.services.materials import MaterialAnnotationService


async def main():
    engine = create_engine(Settings().database.url)
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as session:
            service = MaterialAnnotationService(session, MaterialsCRUD(session, load_demo_config()))
            with files('src.ml').joinpath('data', 'material_annotations.csv').open(encoding='utf-8', newline='') as source:
                count = await service.import_csv(source)
            print(f'Imported annotations: {count}. Run sync_materials to update projections.')
    finally:
        await engine.dispose()


if __name__ == '__main__':
    asyncio.run(main())
