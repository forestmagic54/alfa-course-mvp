import asyncio
import json
from importlib.resources import files

from pwdlib import PasswordHash
from sqlalchemy.ext.asyncio import async_sessionmaker

from src.config import load_demo_config
from src.config.settings import Settings
from src.db.crud.demo import DemoCRUD
from src.db.session import create_engine
from src.services.demo import DemoService


async def main():
    password_hash = await asyncio.to_thread(PasswordHash.recommended().hash, '0123456789')
    config = load_demo_config()
    fixture = json.loads(files('src.config').joinpath('demo', f'fixture-v{config["version"]}.json').read_text(encoding='utf-8'))
    engine = create_engine(Settings().database.url)
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as session:
            state = await DemoService(session, DemoCRUD(session)).load(fixture, config, password_hash)
            print('Demo dataset loaded.' if state == 'empty' else 'Demo dataset already present; nothing changed.')
    finally:
        await engine.dispose()


if __name__ == '__main__':
    asyncio.run(main())
