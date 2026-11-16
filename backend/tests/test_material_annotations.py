import asyncio
from contextlib import asynccontextmanager
from io import StringIO
from types import SimpleNamespace
from uuid import UUID

import pytest

from src.services.materials import MaterialAnnotationService

HEADER = 'source_table,source_id,learning_role,difficulty_level,annotation_source,annotation_version\n'
ROW = 'Articles,00000000-0000-0000-0000-000000000001,intro,beginner,model,v1\n'


class Session:
    @asynccontextmanager
    async def begin(self):
        yield


class Catalog:
    def __init__(self, rows):
        self.rows = rows

    async def lock_and_projections(self):
        return self.rows


def test_import_is_repeatable_and_preserves_other_fields():
    material = SimpleNamespace(id=UUID(int=99), title='Existing')
    service = MaterialAnnotationService(Session(), Catalog({('Articles', UUID(int=1)): material}))
    for _ in range(2):
        assert asyncio.run(service.import_csv(StringIO(HEADER + ROW))) == 1
    assert (material.id, material.title, material.learning_role, material.annotation_version) == (
        UUID(int=99), 'Existing', 'intro', 'v1')


def test_import_rejects_missing_and_duplicate_keys_before_changes():
    material = SimpleNamespace(learning_role='practice')
    service = MaterialAnnotationService(Session(), Catalog({('Articles', UUID(int=1)): material}))
    missing = 'Courses,00000000-0000-0000-0000-000000000002,practice,beginner,model,v1\n'
    with pytest.raises(ValueError, match='Matched 1/2; missing: Courses'):
        asyncio.run(service.import_csv(StringIO(HEADER + ROW + missing)))
    with pytest.raises(ValueError, match='Duplicate annotation'):
        asyncio.run(service.import_csv(StringIO(HEADER + ROW + ROW)))
    assert material.learning_role == 'practice'


def test_import_propagates_failure_through_transaction():
    class FailingMaterial:
        def __setattr__(self, name, value):
            raise RuntimeError('write failed')

    class TrackingSession:
        rolled_back = False

        @asynccontextmanager
        async def begin(self):
            try:
                yield
            except Exception:
                self.rolled_back = True
                raise

    session = TrackingSession()
    service = MaterialAnnotationService(session, Catalog({('Articles', UUID(int=1)): FailingMaterial()}))
    with pytest.raises(RuntimeError, match='write failed'):
        asyncio.run(service.import_csv(StringIO(HEADER + ROW)))
    assert session.rolled_back
