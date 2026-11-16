import asyncio
import json
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID

import pytest

from src.config import load_demo_config
from src.db.models.materials import Materials
from src.services.commerce import add_months
from src.services.demo import DemoService, prepare_fixture
from src.services.materials import source_visible, update_projection

ROOT = Path(__file__).resolve().parents[1]


def fixture():
    return json.loads((ROOT / 'tests/fixtures/demo.json').read_text())


@pytest.mark.parametrize('version', ['1', '2'])
def test_packaged_fixture_and_shifted_states(version):
    data = json.loads((ROOT / f'src/config/demo/fixture-v{version}.json').read_text())
    if version == '1':
        assert data == fixture()
    now = datetime(2026, 2, 15, 12, tzinfo=UTC)
    rows = prepare_fixture(data, load_demo_config(version), now, 'hashed')
    access = rows['mvp.subscription_access']
    assert access[0]['valid_from'] <= now < access[0]['valid_until']
    assert access[0]['valid_until'] == add_months(access[0]['valid_from'], 1)
    assert access[1]['valid_until'] < now and access[2]['revoked_at'] < now
    discounts = rows['mvp.discount_grants']
    assert discounts[0]['granted_at'] <= now < discounts[0]['expires_at']
    assert all(row['expires_at'] - row['granted_at'] == timedelta(days=7) for row in discounts)
    assert all(user['password_hash'] == 'hashed' for user in rows['mvp.users'])


def test_expanded_catalog_preserves_accounts_and_survives_sync():
    data = json.loads((ROOT / 'src/config/demo/fixture-v2.json').read_text())
    old = fixture()
    for table, values in old['mvp'].items():
        if table == 'materials':
            assert {row['id'] for row in values} <= {row['id'] for row in data['mvp'][table]}
        elif table == 'user_profiles':
            assert data['mvp'][table] == [{**row, 'profile_config_version': '2'} for row in values]
        else:
            assert data['mvp'][table] == values

    config = load_demo_config()
    now = datetime(2026, 2, 15, 12, tzinfo=UTC)
    rows = prepare_fixture(data, config, now, 'hashed')
    statuses = [UUID(value) for value in config['catalog']['published_status_ids']]
    for row in rows['mvp.materials']:
        source = next(item for item in rows[f'public.{row["source_table"]}'] if item['Id'] == row['source_id'])
        material = Materials(**{('metadata_' if key == 'metadata' else key): value for key, value in row.items()})
        visible = source_visible(material.kind, SimpleNamespace(SubjectId=None, **source), None, statuses)
        update_projection(material, material.kind, SimpleNamespace(**source), visible, config, now)
        assert (material.access_type, material.is_recommendable) == (row['access_type'], row['is_recommendable'])
        assert (material.duration_minutes, material.default_offer_text) == (row['duration_minutes'], row['default_offer_text'])


def test_invalid_reference_and_duplicate_rejected():
    data = fixture()
    broken = deepcopy(data)
    broken['mvp']['favorites'][0]['material_id'] = '00000000-0000-0000-0000-000000000001'
    with pytest.raises(ValueError, match='reference'):
        prepare_fixture(broken, load_demo_config('1'), datetime.now(UTC), 'hashed')
    broken = deepcopy(data)
    broken['mvp']['users'].append(broken['mvp']['users'][0])
    with pytest.raises(ValueError, match='Duplicate'):
        prepare_fixture(broken, load_demo_config('1'), datetime.now(UTC), 'hashed')


def test_load_repeat_and_failure_rolls_back():
    session = AsyncMock()
    crud = AsyncMock()
    service = DemoService(session, crud)
    config = load_demo_config('1')
    crud.state.return_value = 'loaded'
    assert asyncio.run(service.load(fixture(), config, 'hashed')) == 'loaded'
    crud.insert.assert_not_awaited()
    crud.state.return_value = 'empty'
    crud.insert.side_effect = RuntimeError('insert failed')
    with pytest.raises(RuntimeError, match='insert failed'):
        asyncio.run(service.load(fixture(), config, 'hashed'))
    session.rollback.assert_awaited_once()
    crud.state.return_value = 'incompatible'
    with pytest.raises(ValueError, match='not empty'):
        asyncio.run(service.load(fixture(), config, 'hashed'))
    assert session.rollback.await_count == 2
