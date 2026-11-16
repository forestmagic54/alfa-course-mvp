import io
import runpy
from contextlib import nullcontext
from pathlib import Path

import pytest
from alembic import command, context
from alembic.config import Config
from sqlalchemy.engine import make_url

from src.config import load_demo_config
from src.db.models import Base

ROOT = Path(__file__).resolve().parents[1]


def migration_sql(monkeypatch, action, revision):
    for key, value in {'POSTGRES_USER': 'test', 'POSTGRES_PASSWORD': 'a%@:/b', 'POSTGRES_DB': 'test', 'DATABASE_HOST': 'localhost'}.items():
        monkeypatch.setenv(key, value)
    output = io.StringIO()
    config = Config(str(ROOT / 'alembic.ini'), output_buffer=output)
    getattr(command, action)(config, revision, sql=True)
    return output.getvalue()


def test_migrations_cover_metadata_and_order(monkeypatch):
    upgrade = migration_sql(monkeypatch, 'upgrade', 'head')
    downgrade = migration_sql(monkeypatch, 'downgrade', 'head:base')
    assert upgrade.index('CREATE EXTENSION IF NOT EXISTS citext') < upgrade.index('CREATE TABLE public.') < upgrade.index('CREATE TABLE mvp.generation_runs')
    assert downgrade.index('DROP TABLE mvp.') < downgrade.index('DROP TABLE public.')
    assert 'DROP SCHEMA' not in downgrade and 'DROP EXTENSION' not in downgrade
    for table in Base.metadata.sorted_tables:
        quoted = f'"{table.name}"' if table.schema == 'public' else table.name
        name = f'{table.schema}.{quoted}'
        assert f'CREATE TABLE {name} (' in upgrade
        assert f'DROP TABLE {name}' in downgrade
        for fk in table.foreign_keys:
            assert fk.column.table in Base.metadata.sorted_tables
            target = fk.column.table
            target_name = f'{target.schema}."{target.name}"' if target.schema == 'public' else f'{target.schema}.{target.name}'
            assert upgrade.index(f'CREATE TABLE {target_name} (') <= upgrade.index(f'CREATE TABLE {name} (')
    assert 'uq_users_email_lower' in upgrade and 'uq_favorite_folders_default' in upgrade and 'uq_discount_grants_onboarding' in upgrade
    assert 'CREATE TABLE mvp.events' not in upgrade
    studies = Base.metadata.tables['mvp.user_material_studies']
    assert list(studies.primary_key.columns.keys()) == ['user_id', 'material_id']
    assert {fk.target_fullname for fk in studies.foreign_keys} == {'mvp.users.id', 'mvp.materials.id'}
    assert len([table for table in Base.metadata.tables.values() if table.schema == 'mvp']) == 16
    assert 'CREATE INDEX ix_user_material_studies_material_id ON mvp.user_material_studies (material_id)' in upgrade
    last_downgrade = migration_sql(monkeypatch, 'downgrade', '0003_material_studies:0002_mvp')
    assert 'DROP TABLE mvp.user_material_studies' in last_downgrade
    assert last_downgrade.count('DROP TABLE') == 1
    assert 'DROP INDEX mvp.ix_user_material_studies_material_id' in last_downgrade


def test_alembic_filter_and_secret_url(monkeypatch):
    for key, value in {'POSTGRES_USER': 'test', 'POSTGRES_PASSWORD': 'a%@:/b', 'POSTGRES_DB': 'test', 'DATABASE_HOST': 'localhost'}.items():
        monkeypatch.setenv(key, value)
    received = {}
    monkeypatch.setattr(context, 'is_offline_mode', lambda: True)
    monkeypatch.setattr(context, 'configure', lambda **kwargs: received.update(kwargs))
    monkeypatch.setattr(context, 'execute', lambda *args: None)
    monkeypatch.setattr(context, 'begin_transaction', nullcontext)
    monkeypatch.setattr(context, 'run_migrations', lambda: None)
    namespace = runpy.run_path(str(ROOT / 'src/db/alembic/env.py'))
    assert make_url(received['url']).password == 'a%@:/b'
    include = namespace['include_name']
    assert include('Courses', 'table', {'schema_name': None})
    assert include('users', 'table', {'schema_name': 'mvp'})
    assert include('user_material_studies', 'table', {'schema_name': 'mvp'})
    assert not include('unrelated', 'table', {'schema_name': 'mvp'})
    assert not include('other', 'schema', {})


def test_versioned_config_from_any_directory(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    config = load_demo_config('1')
    assert config['questionnaire']['form_type'] == 'simple'
    with pytest.raises(TypeError):
        config['welcome_discount']['percent'] = 99
    for version in ('3', '../1', 'v1', '', '01'):
        with pytest.raises(ValueError):
            load_demo_config(version)


def test_config_rejects_inconsistent_goal(monkeypatch):
    import importlib

    module = importlib.import_module('src.config.demo')
    parse = module.json.loads

    def invalid_config(content):
        data = parse(content)
        data['goals']['not_a_question_option'] = data['goals']['sales']
        return data

    monkeypatch.setattr(module.json, 'loads', invalid_config)
    with pytest.raises(ValueError, match='Unknown goal code'):
        module.load_demo_config('1')
