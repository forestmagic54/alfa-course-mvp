import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID

import pytest

from src.services import feeds
from src.services.onboarding import (
    InvalidAnswers,
    QuestionnaireVersionMismatch,
    effective_preferences,
)
from src.services.recommendation_stubs import StubGenerator, StubRanker
from src.services.recommendations import RecommendationService


def run(coro):
    return asyncio.run(coro)


def profile(goal='sales', mode='practical'):
    return SimpleNamespace(goal_code=goal, industry_code=None, stage_code=None, learning_mode=mode,
        profile_config_version='1', source_onboarding_response_id=None, updated_at=datetime(2026, 1, 1, tzinfo=UTC))


def test_effective_preferences_and_temporary_validation():
    assert (effective_preferences(profile(), None).personalized, effective_preferences(profile(), None).learning_mode) == (True, 'practical')
    assert (effective_preferences(profile(None), None).personalized, effective_preferences(profile(None), None).learning_mode) == (False, 'practical')
    temporary = {'form_type': 'simple', 'questionnaire_version': '1', 'status': 'partial',
                 'answers': {'current_task': 'sales'}}
    assert (effective_preferences(None, temporary).personalized, effective_preferences(None, temporary).learning_mode) == (True, None)
    with pytest.raises(QuestionnaireVersionMismatch):
        effective_preferences(None, {**temporary, 'questionnaire_version': 'old'})
    with pytest.raises(InvalidAnswers):
        effective_preferences(None, {**temporary, 'answers': {'current_task': 'invalid'}})
    skipped = {**temporary, 'status': 'skipped', 'answers': {}}
    assert not effective_preferences(None, skipped).personalized
    saved = profile('marketing')
    assert effective_preferences(saved, skipped).personalized
    assert not effective_preferences(saved, {**temporary, 'answers': {'current_task': None}}).personalized
    assert saved.goal_code == 'marketing'


@pytest.mark.parametrize('goal', ['sales', 'marketing'])
def test_feed_reuses_and_rechecks_profile(monkeypatch, goal):
    first, changed = profile(goal), profile(goal, mode='theory')
    state = {'profile': first, 'ranked': [], 'created': [], 'checks': 0}
    user = UUID(int=1)
    row = SimpleNamespace(id=UUID(int=2))
    class Session:
        async def rollback(self): pass
        async def commit(self): pass
    class Onboarding:
        def __init__(self, session): pass
        async def fresh_profile(self, user_id): return state['profile']
    class Users:
        def __init__(self, session): pass
        async def lock(self, user_id):
            if state['checks'] == 0:
                state['profile'] = changed
            state['checks'] += 1
    class CRUD:
        def __init__(self, session): pass
        async def current(self, user_id, format, profile): return None
        async def create(self, user_id, profile, format, result):
            state['created'].append((profile, format))
            return row
    class Ranker:
        async def recommend(self, mode, **kwargs):
            state['ranked'].append(mode)
            assert kwargs['preferences'].goal == effective_preferences(state['profile'], None).goal
            return SimpleNamespace(items=[], material_versions={}, ranking_config={})
    instance = feeds.FeedService(Session(), CRUD(None), Onboarding(None), Users(None), None, Ranker(), None)
    async def render(user, lists): return [{'id': lists[0].id}]
    instance.render = render
    assert run(instance.feed(user)) == {'id': row.id}
    assert state['ranked'] == ['medium', 'quick']
    assert len(state['created']) == 1 and state['created'][0][1] == 'quick'
    async def current(user_id, format, profile): return row
    instance.recommendations.current = current
    assert run(instance.feed(user)) == {'id': row.id}
    assert len(state['ranked']) == 2
    run(instance.feed(user, regenerate=True))
    assert len(state['ranked']) == 3 and len(state['created']) == 2


def test_temporary_and_popular_never_persist(monkeypatch):
    calls = []
    class Ranker:
        async def recommend(self, mode, **kwargs):
            calls.append(mode)
            return SimpleNamespace(items=[])
    instance = feeds.FeedService(None, None, None, None, None, Ranker(), None)
    temporary = {'form_type': 'simple', 'questionnaire_version': '1', 'status': 'partial',
                 'answers': {'current_task': 'sales'}}
    assert run(instance.feed(None))['mode'] == 'popular'
    result = run(instance.feed(None, onboarding=temporary))
    assert result['mode'] == 'personalized' and result['id'] is None
    assert calls == ['popular', 'quick']


@pytest.mark.parametrize('goal', ['marketing', 'management', 'other'])
def test_unmapped_goal_uses_personalized_fallback(goal):
    material_id = UUID(int=1)
    material = SimpleNamespace(id=material_id, kind='article', title='Article', source_table='Articles',
        is_recommendable=True, learning_role='intro', difficulty_level='beginner', annotation_source='manual',
        annotation_version='1', duration_minutes=None, source_version='1')
    catalog = SimpleNamespace(recommendation_candidates=AsyncMock(return_value=[material]),
        classification=AsyncMock(return_value={material_id: {'topics': {}, 'tags': {}, 'industries': {}}}))
    cards = AsyncMock(return_value=[{'id': material_id, 'primary_action': {'type': 'read_article'}, 'access': 'free'}])
    recommender = RecommendationService(None, StubRanker(), StubGenerator(), StubGenerator(), 1,
                                       lambda config: catalog, cards)
    instance = feeds.FeedService(None, None, None, None, None, recommender, cards)
    temporary = {'form_type': 'simple', 'questionnaire_version': '1', 'status': 'partial',
                 'answers': {'current_task': goal, 'learning_mode': 'practical'}}

    result = run(instance.feed(None, onboarding=temporary))

    assert result['mode'] == 'personalized' and result['format'] == 'medium' and result['id'] is None
    assert result['items'][0]['explanation'] == 'Материал можно изучить для знакомства с темой.'
    assert result['items'][0]['offer_text'] is None
    assert run(instance.feed(None, mode='popular', onboarding=temporary))['mode'] == 'popular'


def test_render_hides_material_and_stale_text(monkeypatch):
    ids = [UUID(int=1), UUID(int=2)]
    listing = SimpleNamespace(id=UUID(int=3), recommendation_format='quick', saved_at=None,
                              context_snapshot={'material_versions': {str(ids[0]): 'old', str(ids[1]): '1'}})
    materials = [SimpleNamespace(id=i, kind='course', title='Title', source_version='1', verified_course_id=UUID(int=10 + n))
                 for n, i in enumerate(ids)]
    items = [SimpleNamespace(list_id=listing.id, position=n, explanation='old text', offer_text='old offer')
             for n in (1, 2)]
    class CRUD:
        def __init__(self, session): pass
        async def items(self, list_ids): return list(zip(items, materials, strict=True))
    class Catalog:
        def __init__(self, *args): pass
        async def visible_subset(self, material_ids): return {ids[0]}
    async def cards(values, user, config): return [{'id': ids[0], 'access': 'free'}]
    instance = feeds.FeedService(None, CRUD(None), None, None, Catalog(), None, cards)
    rows = run(instance.render(None, [listing]))[0]['items']
    assert all(x['offer_text'] is None and x['explanation'] != 'old text' for x in rows)
    assert rows[1]['material']['access'] == 'unknown' and rows[1]['material']['topics'] == []
    assert rows[1]['material']['course_id'] == materials[1].verified_course_id


def test_save_filters_owner_type_and_preserves_timestamp():
    from sqlalchemy.dialects import postgresql

    from src.db.crud.recommendations import RecommendationsCRUD

    statements = []
    class Session:
        async def execute(self, query): statements.append(query)
        async def scalar(self, query):
            statements.append(query)
            return None
    assert run(RecommendationsCRUD(Session()).save(UUID(int=1), UUID(int=2))) is None
    update = str(statements[0].compile(dialect=postgresql.dialect()))
    query = str(statements[1].compile(dialect=postgresql.dialect()))
    assert 'saved_at IS NULL' in update
    for sql in (update, query):
        assert 'user_id' in sql and 'list_type' in sql and 'mode' in sql and 'id' in sql


def test_feed_rolls_back_failed_write(monkeypatch):
    user = UUID(int=1)
    events = []
    class Session:
        async def rollback(self): events.append('rollback')
        async def commit(self): events.append('commit')
    class Onboarding:
        def __init__(self, session): pass
        async def fresh_profile(self, user_id): return profile()
    class Users:
        def __init__(self, session): pass
        async def lock(self, user_id): pass
    class CRUD:
        def __init__(self, session): pass
        async def current(self, *args): return None
        async def create(self, *args): raise RuntimeError('item insert failed')
    class Ranker:
        async def recommend(self, *args, **kwargs):
            return SimpleNamespace(items=[], material_versions={}, ranking_config={})
    instance = feeds.FeedService(Session(), CRUD(None), Onboarding(None), Users(None), None, Ranker(), None)
    with pytest.raises(RuntimeError):
        run(instance.feed(user))
    assert events == ['rollback', 'rollback']


def test_service_factories_use_request_session():
    from src.api.service_dependencies import (
        get_auth_service,
        get_feed_service,
        get_material_service,
        get_onboarding_service,
    )

    first, second = object(), object()
    context = SimpleNamespace(ranker=object(), generator=object(), fallback_generator=object(),
                              settings=SimpleNamespace(app=SimpleNamespace(generation_timeout_seconds=1)))
    materials = get_material_service(first)
    feed = get_feed_service(first, context, materials)
    auth = get_auth_service(first)
    onboarding = get_onboarding_service(second)
    assert auth.users.session is first and auth.favorites.session is first
    assert materials.commerce.session is first and materials.favorites.session is first
    assert feed.ranker.fallback_generator is context.fallback_generator
    assert feed.build_cards.__self__ is materials and feed.ranker.build_cards.__self__ is materials
    assert feed.session is first
    assert all(dependency.session is first for dependency in
               (feed.recommendations, feed.onboarding, feed.users, feed.catalog, feed.ranker))
    assert feed.ranker.materials_factory(effective_preferences(None, None).config).session is first
    assert onboarding.session is second
    assert all(dependency.session is second for dependency in
               (onboarding.users, onboarding.onboarding, onboarding.commerce))


def test_routes_pass_authenticated_id_and_guest(monkeypatch):
    from unittest.mock import AsyncMock

    from src.api.recommendations.routes import (
        get_recommendations,
        list_saved_recommendations,
    )

    user_id = UUID(int=55)
    service = SimpleNamespace(feed=AsyncMock(return_value={}), saved=AsyncMock(return_value=[]))
    run(get_recommendations(service, SimpleNamespace(id=user_id)))
    run(get_recommendations(service, None))
    assert service.feed.await_args_list[0].args == (user_id,)
    assert service.feed.await_args_list[1].args == (None,)
    run(list_saved_recommendations(service, SimpleNamespace(id=user_id)))
    service.saved.assert_awaited_once_with(user_id)
