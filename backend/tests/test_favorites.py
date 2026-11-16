import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID

import pytest
from fastapi.routing import serialize_response
from pydantic import ValidationError
from sqlalchemy.dialects import postgresql

from src.api.favorites.routes import router
from src.api.favorites.schemas import FavoriteFolderInput
from src.db.crud.favorites import FavoritesCRUD
from src.services.favorites import (
    DefaultFolderProtected,
    FavoriteNotFound,
    FavoriteService,
)


def run(value):
    return asyncio.run(value)


@pytest.fixture
def setup():
    session = SimpleNamespace(commit=AsyncMock(), rollback=AsyncMock())
    folders = SimpleNamespace(folder=AsyncMock(), folders=AsyncMock(return_value=[]),
                              create_folder=AsyncMock(), delete_folder=AsyncMock(),
                              saved_materials=AsyncMock(return_value=[]), add_material=AsyncMock(),
                              delete_material=AsyncMock())
    catalog = SimpleNamespace(get=AsyncMock(), get_any=AsyncMock(), visible_subset=AsyncMock())
    materials = SimpleNamespace(build_cards=AsyncMock(return_value=[]))
    return FavoriteService(session, folders, catalog, materials, {}), session, folders, catalog, materials


def test_input_and_folder_creation(setup):
    service, session, folders, _, _ = setup
    assert FavoriteFolderInput(name='  name  ').name == 'name'
    for value in ({'name': '  '}, {'name': None}, {'name': 'a', 'is_default': True}):
        with pytest.raises(ValidationError):
            FavoriteFolderInput(**value)
    user = UUID(int=1)
    run(service.list_folders(user))
    run(service.create_folder(user, 'name'))
    folders.folders.assert_awaited_once_with(user)
    folders.create_folder.assert_awaited_once_with(user, 'name')
    session.commit.assert_awaited_once()


@pytest.mark.parametrize('name', ['new', None])
def test_protected_default_and_missing_folder(setup, name):
    service, session, folders, _, _ = setup
    user, folder = UUID(int=1), UUID(int=2)
    folders.folder.return_value = SimpleNamespace(is_default=True)
    with pytest.raises(DefaultFolderProtected):
        run(service.change_folder(user, folder, name))
    folders.folder.assert_awaited_with(user, folder, lock=True)
    folders.folder.return_value = None
    with pytest.raises(FavoriteNotFound):
        run(service.change_folder(user, folder, name))
    assert session.rollback.await_count == 2
    session.commit.assert_not_awaited()


def test_owner_checked_before_material_access_and_writes(setup):
    service, session, folders, catalog, _ = setup
    user, folder, material = UUID(int=1), UUID(int=2), UUID(int=3)
    folders.folder.return_value = None
    for action in (service.list_materials(user, folder),
                   service.change_material(user, folder, material, add=True),
                   service.change_material(user, folder, material, add=False)):
        with pytest.raises(FavoriteNotFound):
            run(action)
    catalog.get.assert_not_awaited()
    catalog.get_any.assert_not_awaited()
    folders.saved_materials.assert_not_awaited()
    folders.add_material.assert_not_awaited()
    folders.delete_material.assert_not_awaited()
    assert session.rollback.await_count == 2


def test_material_visibility_and_rollback(setup):
    service, session, folders, catalog, _ = setup
    user, folder, material = UUID(int=1), UUID(int=2), UUID(int=3)
    folders.folder.return_value = SimpleNamespace(is_default=True)
    catalog.get.return_value = None
    catalog.get_any.return_value = object()
    with pytest.raises(FavoriteNotFound):
        run(service.change_material(user, folder, material, add=True))
    run(service.change_material(user, folder, material, add=False))
    run(service.change_material(user, folder, material, add=False))
    assert folders.delete_material.await_count == 2
    assert session.commit.await_count == 2
    catalog.get_any.return_value = None
    with pytest.raises(FavoriteNotFound):
        run(service.change_material(user, folder, material, add=False))
    catalog.get.return_value = object()
    folders.add_material.side_effect = RuntimeError('database error')
    with pytest.raises(RuntimeError):
        run(service.change_material(user, folder, material, add=True))
    assert session.rollback.await_count == 3


def test_folder_deletion_rolls_back_on_error(setup):
    service, session, folders, _, _ = setup
    folder = SimpleNamespace(is_default=False)
    folders.folder.return_value = folder
    folders.delete_folder.side_effect = RuntimeError('failure')
    with pytest.raises(RuntimeError):
        run(service.change_folder(UUID(int=1), UUID(int=2), None))
    folders.delete_folder.assert_awaited_once_with(folder)
    session.rollback.assert_awaited_once()
    session.commit.assert_not_awaited()


def test_list_batch_visibility_and_empty(setup):
    service, _, folders, catalog, materials = setup
    user, folder = UUID(int=10), UUID(int=11)
    folders.folder.return_value = object()
    assert run(service.list_materials(user, folder)) == []
    catalog.visible_subset.assert_not_awaited()
    timestamp = datetime.now(UTC)
    items = [SimpleNamespace(id=UUID(int=i), kind=kind) for i, kind in enumerate(
        ('course', 'article', 'document', 'article'), 1)]
    folders.saved_materials.return_value = [(SimpleNamespace(material_id=m.id, created_at=timestamp), m) for m in items]
    catalog.visible_subset.return_value = {m.id for m in items[:3]}
    materials.build_cards.return_value = [{'id': m.id} for m in items[:3]]
    output = run(service.list_materials(user, folder))
    materials.build_cards.assert_awaited_once_with(items[:3], user, {})
    assert [row['material_id'] for row in output] == [m.id for m in items]
    assert output[-1] == {'material_id': items[-1].id, 'created_at': timestamp, 'material': None}


def test_nested_card_serialization():
    timestamp = datetime.now(UTC)
    cards = [{'id': UUID(int=i), 'kind': kind, 'title': kind, 'duration_minutes': None,
              'topics': [], 'industries': [], 'skills': [], 'access_type': 'free', 'access': 'free',
              'offers': [], 'primary_action': None, 'is_favorite': True,
              **({'course_id': UUID(int=9)} if kind == 'course' else {})}
             for i, kind in enumerate(('course', 'article', 'document'), 1)]
    payload = [{'material_id': c['id'], 'created_at': timestamp, 'material': c} for c in cards]
    payload.append({'material_id': UUID(int=4), 'created_at': timestamp, 'material': None})
    route = next(r for r in router.routes if r.operation_id == 'listFavoriteMaterials')
    output = run(serialize_response(field=route.response_field, response_content=payload, exclude_unset=True))
    assert output[0]['material']['course_id'] == str(UUID(int=9))
    assert all('course_id' not in row['material'] for row in output[1:3])
    assert all(row['material']['duration_minutes'] is None for row in output[:3])
    assert output[-1]['material'] is None


def test_sql_scopes_and_idempotent_insert():
    session = SimpleNamespace(execute=AsyncMock(), scalar=AsyncMock(return_value=None), delete=AsyncMock())
    crud = FavoritesCRUD(session)
    user, folder, material = UUID(int=1), UUID(int=2), UUID(int=3)
    run(crud.folder(user, folder, lock=True))
    run(crud.add_material(folder, material))
    run(crud.delete_material(folder, material))
    locked = str(session.scalar.await_args.args[0].compile(dialect=postgresql.dialect()))
    insert, delete = [str(call.args[0].compile(dialect=postgresql.dialect())) for call in session.execute.await_args_list]
    assert 'user_id' in locked and 'FOR UPDATE' in locked
    assert 'ON CONFLICT (folder_id, material_id) DO NOTHING' in insert
    assert 'folder_id' in delete and 'material_id' in delete


def test_write_order_and_shared_favorite_state():
    events = []
    user, other = UUID(int=1), UUID(int=2)
    first, second, material = UUID(int=3), UUID(int=4), UUID(int=5)
    owned = {first: user, second: user}
    saved = set()

    class Session:
        async def commit(self): events.append('commit')
        async def rollback(self): events.append('rollback')

    class Folders:
        async def folder(self, owner, folder_id, *, lock=False):
            events.append(('folder', folder_id, lock))
            return SimpleNamespace(id=folder_id, is_default=False) if owned.get(folder_id) == owner else None

        async def add_material(self, folder_id, material_id):
            events.append('add')
            saved.add((folder_id, material_id))

        async def delete_material(self, folder_id, material_id):
            events.append('remove')
            saved.discard((folder_id, material_id))

        async def delete_folder(self, folder):
            events.append('delete_folder')
            saved.difference_update({pair for pair in saved if pair[0] == folder.id})

        async def material_ids(self, owner, ids):
            return {m for f, m in saved if owned[f] == owner and m in ids}

    class Catalog:
        async def get(self, material_id):
            events.append('visible')
            return object()

        async def get_any(self, material_id):
            events.append('exists')
            return object()

    folders = Folders()
    service = FavoriteService(Session(), folders, Catalog(), None, {})
    run(service.change_material(user, first, material, add=True))
    assert events == [('folder', first, True), 'visible', 'add', 'commit']
    run(service.change_material(user, first, material, add=True))
    run(service.change_material(user, second, material, add=True))
    assert len(saved) == 2
    run(service.change_material(user, first, material, add=False))
    assert run(folders.material_ids(user, [material])) == {material}
    assert run(folders.material_ids(other, [material])) == set()
    run(service.change_folder(user, second, None))
    assert run(folders.material_ids(user, [material])) == set()
    assert events[-3:] == [('folder', second, True), 'delete_folder', 'commit']
