import asyncio

from alembic import context
from sqlalchemy import pool, text
from sqlalchemy.dialects.postgresql import CITEXT
from sqlalchemy.ext.asyncio import create_async_engine

from src.config.settings import DatabaseConfig
from src.db.models import Base

target_metadata = Base.metadata


def include_name(name, type_, parent_names):
    if type_ == 'schema':
        return name in (None, 'public', 'mvp')
    if type_ == 'table':
        schema = parent_names.get('schema_name') or 'public'
        return f'{schema}.{name}' in target_metadata.tables
    return True


def configure(**kwargs):
    context.configure(
        target_metadata=target_metadata,
        include_schemas=True,
        include_name=include_name,
        version_table_schema='mvp',
        **kwargs,
    )


def run_migrations_offline():
    configure(url=DatabaseConfig().url.render_as_string(hide_password=False), literal_binds=True)
    context.execute('CREATE SCHEMA IF NOT EXISTS mvp')
    with context.begin_transaction():
        context.run_migrations()


def run_sync_migrations(connection):
    configure(connection=connection)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations():
    engine = create_async_engine(DatabaseConfig().url, poolclass=pool.NullPool)
    try:
        async with engine.connect() as connection:
            await connection.execute(text('CREATE SCHEMA IF NOT EXISTS mvp'))
            # Keep public-qualified foreign keys stable during reflection.
            await connection.execute(text('SET search_path TO pg_catalog'))
            await connection.commit()
            connection.dialect.default_schema_name = 'pg_catalog'
            connection.dialect.ischema_names = {**connection.dialect.ischema_names, 'public.citext': CITEXT}
            await connection.run_sync(run_sync_migrations)
    finally:
        await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_async_migrations())
