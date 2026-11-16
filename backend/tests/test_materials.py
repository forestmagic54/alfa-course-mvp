import asyncio
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from sqlalchemy.dialects import postgresql

from src.api.materials.schemas import MaterialFilters
from src.config import load_demo_config
from src.db.crud.materials import MaterialsCRUD
from src.db.models.materials import Materials
from src.services.access import card_access, discounted_amount
from src.services.materials import (
    MaterialService,
    MaterialSyncService,
    source_visible,
    update_projection,
)

NOW = datetime(2025, 6, 15, tzinfo=UTC)
CONFIG = load_demo_config('1')
STATUS = UUID(CONFIG['catalog']['published_status_ids'][0])


def source(**changes):
    values = dict(Id=uuid4(), Title='Example', Description='Description', Url='https://example.test',
                  StatusId=STATUS, IsDeleted=False, IsClosed=False, IsPublic=True, IsLesson=False, SubjectId=None)
    values.update(changes)
    return SimpleNamespace(**values)


def discount(**changes):
    values = dict(id=uuid4(), reason='promotion', granted_at=NOW - timedelta(days=1), expires_at=None,
                  redeemed_at=None, discount_percent=10, discount_amount_minor=None)
    values.update(changes)
    return SimpleNamespace(**values)


def test_visibility_and_source_types():
    article = source()
    assert source_visible('article', article, None, [STATUS])
    assert not source_visible('article', source(IsLesson=True), None, [STATUS])
    assert not source_visible('article', source(IsPublic=False), None, [STATUS])
    assert not source_visible('article', source(SubjectId=uuid4()), SimpleNamespace(IsPublic=False, IsDeleted=False), [STATUS])
    assert not source_visible('course', source(IsClosed=True), None, [STATUS])
    assert source_visible('document', SimpleNamespace(StatusId=STATUS, IsDeleted=False), None, [STATUS])
    assert not source_visible('document', SimpleNamespace(StatusId=STATUS, IsDeleted=True), None, [STATUS])


def test_discount_rules_and_subscription_access():
    discounts = [discount(expires_at=NOW, discount_percent=90), discount(redeemed_at=NOW, discount_percent=90),
                 discount(granted_at=NOW + timedelta(seconds=1), discount_percent=90),
                 discount(reason='onboarding', discount_percent=25),
                 discount(discount_percent=None, discount_amount_minor=11)]
    assert discounted_amount(101, discounts, NOW, first_paid_course=True) == 76
    assert discounted_amount(101, discounts, NOW, first_paid_course=False) == 90
    assert discounted_amount(5, discounts[-1:], NOW, first_paid_course=True) == 0
    subscription_id = uuid4()
    course_id = uuid4()
    material = SimpleNamespace(kind='course', verified_course_id=course_id, access_type='unknown', url='https://example.test')
    active = SimpleNamespace(subscription_id=subscription_id, valid_from=NOW, valid_until=NOW + timedelta(days=1), revoked_at=None)
    expired = SimpleNamespace(subscription_id=subscription_id, valid_from=NOW - timedelta(days=1), valid_until=NOW, revoked_at=None)
    revoked = SimpleNamespace(subscription_id=subscription_id, valid_from=NOW, valid_until=None, revoked_at=NOW)
    future = SimpleNamespace(subscription_id=subscription_id, valid_from=NOW + timedelta(days=1), valid_until=None, revoked_at=None)
    assert card_access(material, [], {subscription_id}, [], [active], [], CONFIG, NOW)[0] == 'subscription'
    for entry in (expired, revoked, future):
        assert card_access(material, [], {subscription_id}, [], [entry], [], CONFIG, NOW)[0] == 'unknown'
    purchase = SimpleNamespace(course_id=course_id, amount_minor=100)
    assert card_access(material, [], {subscription_id}, [purchase], [active], [], CONFIG, NOW)[0] == 'course_purchase'
    material.access_type = 'free'
    assert card_access(material, [], {subscription_id}, [purchase], [active], [], CONFIG, NOW)[0] == 'free'


@pytest.mark.parametrize(('previous_course_id', 'expected_discount'), [(UUID(int=777), None), (None, 179100)])
def test_onboarding_discount_counts_zero_total_course_purchase(previous_course_id, expected_discount):
    course_id = UUID(next(iter(CONFIG['access']['course_prices'])))
    material = SimpleNamespace(kind='course', verified_course_id=course_id,
                               access_type='paid', url='https://example.test/course')
    purchase = SimpleNamespace(course_id=previous_course_id, amount_minor=0)
    grant = discount(reason='onboarding')

    _, offers, _ = card_access(material, [], set(), [purchase], [], [grant], CONFIG, NOW)

    assert offers[0]['discounted_amount_minor'] == expected_discount


def test_subscription_card_applies_onboarding_discount():
    tariff_id, data = next(iter(CONFIG['subscriptions']['tariffs'].items()))
    subscription = SimpleNamespace(Id=UUID(data['subscription_id']))
    tariff = SimpleNamespace(Id=UUID(tariff_id), Title='Demo')
    material = SimpleNamespace(kind='course', verified_course_id=uuid4(), access_type='paid', url=None)

    _, offers, _ = card_access(material, [(subscription, tariff)], set(), [], [],
                               [discount(reason='onboarding')], CONFIG, NOW)

    amount = data['price']['amount_minor']
    assert offers[0]['discounted_amount_minor'] == amount - amount * 10 // 100


def test_synchronization_keeps_ids_annotation_and_ignores_hidden_content(monkeypatch):
    course, article, document = source(), source(), source()
    existing = Materials(id=uuid4(), source_table='Courses', source_id=course.Id, kind='course',
                         verified_course_id=course.Id, learning_role='intro', difficulty_level='beginner',
                         annotation_source='manual', annotation_version='1', metadata_={'reviewed': True},
                         metadata_schema_version='1')
    orphan = Materials(id=uuid4(), source_table='Articles', source_id=uuid4(), kind='article',
                       is_recommendable=True)
    data = {('Courses', course.Id): existing, ('Articles', orphan.source_id): orphan}
    class CRUD:
        statuses = [STATUS]
        def __init__(self, session, config): pass
        async def lock_and_projections(self): return data
        async def sources(self): return [course], [(article, None)], [document]
        def add(self, material): data[(material.source_table, material.source_id)] = material
    @asynccontextmanager
    async def transaction(): yield
    session = SimpleNamespace(begin=transaction)
    config = {**CONFIG, 'catalog': {**CONFIG['catalog'], 'duration_minutes': {str(existing.id): 45}}}
    service = MaterialSyncService(session, CRUD(session, config), config)
    asyncio.run(service.synchronize())
    version = existing.source_version
    ids = {key: value.id for key, value in data.items()}
    asyncio.run(service.synchronize())
    assert ids == {key: value.id for key, value in data.items()}
    assert existing.source_version == version and existing.metadata_ == {'reviewed': True}
    assert existing.learning_role == 'intro' and existing.is_recommendable and not orphan.is_recommendable
    assert existing.duration_minutes == 45 and data[('Articles', article.Id)].duration_minutes is None
    assert data[('Documents', document.Id)].url is None
    course.Title = 'Changed'
    article.IsPublic = False
    asyncio.run(service.synchronize())
    assert existing.source_version != version
    assert data[('Articles', article.Id)].public_description is None


def test_only_configured_visible_demo_documents_get_an_action():
    material_id = uuid4()
    url = f'http://localhost:8000/demo-files/{material_id}.txt'
    config = {**CONFIG, 'catalog': {**CONFIG['catalog'], 'demo_document_urls': {str(material_id): url}},
              'access': {**CONFIG['access'], 'free_material_ids': [str(material_id)]}}
    material = Materials(id=material_id, kind='document', source_id=uuid4(), verified_course_id=None,
                         learning_role='practice', difficulty_level='beginner', annotation_source='manual',
                         annotation_version='1')
    update_projection(material, 'document', source(), True, config, NOW)
    access, _, action = card_access(material, [], set(), [], [], [], config, NOW)
    assert access == 'free' and action == {'type': 'open_document', 'url': url}
    material.url = 'https://unverified.example/document'
    assert card_access(material, [], set(), [], [], [], config, NOW)[2] is None
    update_projection(material, 'document', source(), False, config, NOW)
    assert material.url is None and card_access(material, [], set(), [], [], [], config, NOW)[2] is None


def test_search_escapes_wildcards_and_uses_same_filters_for_count():
    queries = []
    class Session:
        async def scalar(self, query):
            queries.append(query)
            return 0
        async def scalars(self, query):
            queries.append(query)
            return SimpleNamespace(all=lambda: [])
    filters = MaterialFilters(q=r'100%_\x', kind='course', topic_id=uuid4(), min_price_minor=0)
    assert asyncio.run(MaterialsCRUD(Session(), CONFIG).search(filters)) == ([], 0)
    compiled = [query.compile(dialect=postgresql.dialect()) for query in queries]
    assert any(value == r'%100\%\_\\x%' for value in compiled[0].params.values())
    assert str(compiled[0]).count('EXISTS') == str(compiled[1]).count('EXISTS')
    assert 'count(' in str(compiled[0]) and ' LIMIT ' in str(compiled[1])


def test_catalog_orders_by_popularity_before_pagination_and_handles_missing_ratings():
    queries = []

    class Session:
        async def scalar(self, query):
            return 0

        async def scalars(self, query):
            queries.append(query)
            return SimpleNamespace(all=lambda: [])

    high, low = uuid4(), uuid4()
    config = {**CONFIG, 'catalog': {**CONFIG['catalog'], 'popularity': {str(high): 10, str(low): 0}}}
    asyncio.run(MaterialsCRUD(Session(), config).search(MaterialFilters(limit=2, offset=1)))
    compiled = queries[-1].compile(dialect=postgresql.dialect())
    ordering = str(compiled).split('ORDER BY ', 1)[1]
    assert ordering.startswith('CASE mvp.materials.id')
    assert 'DESC NULLS LAST, lower(mvp.materials.title), mvp.materials.id' in ordering
    assert high in compiled.params.values() and low in compiled.params.values()

    empty = {**config, 'catalog': {**config['catalog'], 'popularity': {}}}
    asyncio.run(MaterialsCRUD(Session(), empty).search(MaterialFilters()))
    assert str(queries[-1].compile(dialect=postgresql.dialect())).split('ORDER BY ', 1)[1].startswith('lower(mvp.materials.title)')


def test_account_lookup_propagates_database_errors():
    from src.api.dependencies import find_account
    session = SimpleNamespace(get=AsyncMock(side_effect=RuntimeError('database')))
    with pytest.raises(RuntimeError):
        asyncio.run(find_account(uuid4(), session))


def test_cards_load_personal_data_once_and_select_actions(monkeypatch):
    user_id = uuid4()
    free = Materials(id=uuid4(), source_id=uuid4(), kind='article', title='Free', duration_minutes=None,
                     access_type='free', url='https://example.test/article')
    course_id = UUID(next(iter(CONFIG['access']['course_prices'])))
    paid = Materials(id=uuid4(), source_id=course_id, verified_course_id=course_id, kind='course', title='Course',
                     duration_minutes=None, access_type='paid', url='https://example.test/course')
    ids = [free.id, paid.id]
    counts = {'classification': 0, 'tariffs': 0, 'links': 0, 'state': 0, 'favorites': 0}
    class Catalog:
        def __init__(self, session, config): pass
        async def classification(self, material_ids):
            counts['classification'] += 1
            return {item_id: {'topics': {}, 'industries': {}, 'tags': set()} for item_id in material_ids}
    class Commerce:
        def __init__(self, session): pass
        async def tariffs(self, course_ids, tariff_ids):
            counts['tariffs'] += 1
            return []
        async def subscription_links(self, course_ids):
            counts['links'] += 1
            return []
        async def user_state(self, account_id):
            counts['state'] += 1
            return [], [], [discount(reason='onboarding', discount_percent=10)]
    class Favorites:
        def __init__(self, session): pass
        async def material_ids(self, account_id, material_ids):
            counts['favorites'] += 1
            assert account_id == user_id and material_ids == ids
            return {free.id}
    service = MaterialService(lambda config: Catalog(None, config), Commerce(None), Favorites(None))
    cards = asyncio.run(service.build_cards([free, paid], user_id, CONFIG, now=NOW))
    assert all(value == 1 for value in counts.values())
    assert cards[0]['is_favorite'] and cards[0]['primary_action']['type'] == 'read_article'
    assert 'course_id' not in cards[0] and cards[0]['offers'] == []
    assert cards[1]['access'] == 'none' and cards[1]['primary_action']['type'] == 'buy_course'
    assert cards[1]['offers'][0]['discounted_amount_minor'] == 179100


def test_public_url_requires_absolute_http_address():
    from src.services.access import public_url

    assert public_url('https://example.test/article') == 'https://example.test/article'
    for value in ('javascript:alert(1)', '/relative', 'https://', 'https://[invalid'):
        assert public_url(value) is None


def test_material_service_uses_requested_config_and_handles_missing_material():
    config = object()
    user = uuid4()
    material = SimpleNamespace(id=uuid4(), public_description='description')
    seen = []
    class Catalog:
        async def search(self, filters): return [material], 1
        async def get(self, material_id): return material if material_id == material.id else None
        async def classification(self, ids): return {material.id: {'topics': {}}}
        async def related(self, material_id, topics): return []
    def factory(value):
        seen.append(value)
        return Catalog()
    service = MaterialService(factory, None, None)
    async def cards(materials, account, requested_config):
        assert materials == [material] and account is user and requested_config is config
        return [{'id': material.id}]
    service.build_cards = cards
    assert asyncio.run(service.search(object(), user, config)) == {'items': [{'id': material.id}], 'total': 1}
    assert asyncio.run(service.detail(material.id, user, config))['description'] == 'description'
    assert asyncio.run(service.detail(uuid4(), user, config)) is None
    assert seen == [config, config, config]
