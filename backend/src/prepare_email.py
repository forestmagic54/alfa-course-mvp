import argparse
import asyncio
from pathlib import Path
from uuid import UUID

from sqlalchemy.ext.asyncio import async_sessionmaker

from src.config import load_demo_config
from src.config.settings import Settings
from src.db.crud.email import EmailCRUD
from src.db.crud.users import UsersCRUD
from src.db.session import create_engine
from src.services.email import EmailError, EmailService


async def main(user_id: UUID, message_id: UUID) -> None:
    engine = create_engine(Settings().database.url)
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as session:
            version = load_demo_config()['email']['consent_version']
            service = EmailService(session, UsersCRUD(session), EmailCRUD(session), version)
            path = await service.prepare(user_id, message_id, Path('local_emails'))
            print(f'Подготовлено: {path}')
    finally:
        await engine.dispose()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Локальная подготовка тестового письма')
    parser.add_argument('--user-id', required=True, type=UUID)
    parser.add_argument('--message-id', required=True, type=UUID)
    args = parser.parse_args()
    try:
        asyncio.run(main(args.user_id, args.message_id))
    except EmailError as exc:
        parser.exit(1, f'Ошибка: {exc}\n')
