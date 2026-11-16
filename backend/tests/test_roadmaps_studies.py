import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import UUID

import pytest
from sqlalchemy.dialects import postgresql

from src.db.crud.material_studies import MaterialStudiesCRUD
from src.db.crud.recommendations import RecommendationsCRUD
from src.services.material_studies import MaterialStudyService
from src.services.roadmaps import MissingGoal, RoadmapService


def run(coro):
    return asyncio.run(coro)


def profile(goal='sales'):
    return SimpleNamespace(goal_code=goal, industry_code=None, stage_code=None, learning_mode=None,
        profile_config_version='1', source_onboarding_response_id=None, updated_at=datetime(2026, 1, 1, tzinfo=UTC))


def test_generation_temporary_goal_and_profile_retry():
    user, material = UUID(int=1), UUID(int=2)
    events = []
    class Session:
        async def rollback(self): events.append('rollback')
        async def commit(self): events.append('commit')
    class Onboarding:
        current = profile()
        async def fresh_profile(self, user_id): return self.current
    onboarding = Onboarding()
    class Users:
        async def lock(self, user_id):
            if events.count('lock') == 0:
                onboarding.current = profile('marketing')
            events.append('lock')
    class CRUD:
        async def create_roadmap(self, user_id, snapshot, result):
            events.append(('create', snapshot['goal_code']))
            return SimpleNamespace(id=UUID(int=3))
    class Ranker:
        async def recommend(self, mode, **kwargs):
            events.append(('rank', kwargs['preferences'].goal_code))
            return SimpleNamespace(title='Title', summary='Summary', items=[{'material': {'id': material}}],
                                   material_versions={}, ranking_config={})
    class Studies:
        async def studied_ids(self, user_id, ids): return {material}
    service = RoadmapService(Session(), CRUD(), onboarding, Users(), None, Ranker(), None, Studies())
    async def render(user_id, rows): return [{'id': rows[0].id}]
    service.render = render
    temporary = {'form_type': 'simple', 'questionnaire_version': '1', 'status': 'partial', 'answers': {'current_task': 'sales'}}
    assert run(service.generate(None, temporary))['steps'][0]['is_studied'] is False
    assert run(service.generate(user, temporary))['steps'][0]['is_studied'] is True
    assert not any(isinstance(event, tuple) and event[0] == 'create' for event in events)
    run(service.generate(user))
    assert ('create', 'marketing') in events and events.count('commit') == 1
    onboarding.current = profile(None)
    with pytest.raises(MissingGoal):
        run(service.generate(user))


def test_render_batches_studies_and_hides_stale_course():
    user, material_id, first, second = (UUID(int=i) for i in range(1, 5))
    rows = [SimpleNamespace(id=i, title='T', summary='S', saved_at=None,
                            context_snapshot={'material_versions': {str(material_id): 'old'}}) for i in (first, second)]
    material = SimpleNamespace(id=material_id, kind='course', title='Course', source_version='new', verified_course_id=UUID(int=9))
    items = [SimpleNamespace(list_id=row.id, position=1, explanation='private', offer_text='private',
                             step_role='intro', transition_text=None) for row in rows]
    class CRUD:
        async def items(self, ids): return list(zip(items, [material, material], strict=True))
    class Catalog:
        async def visible_subset(self, ids): return set()
    class Studies:
        calls = 0
        async def studied_ids(self, account, ids):
            self.calls += 1
            assert account == user and ids == [material_id]
            return {material_id}
    studies = Studies()
    async def cards(*args): return []
    service = RoadmapService(None, CRUD(), None, None, Catalog(), None, cards, studies)
    result = run(service.render(user, rows))
    assert studies.calls == 1
    for row in result:
        step = row['steps'][0]
        assert step['is_studied'] and step['offer_text'] is None and step['explanation'] != 'private'
        assert step['material']['access'] == 'unknown' and step['material']['course_id'] == material.verified_course_id


@pytest.mark.parametrize(('changed_index', 'hidden_index'), [(None, None), (0, None), (None, 0), (1, None), (None, 1)])
def test_transition_checks_both_materials_and_keeps_roadmaps_separate(changed_index, hidden_index):
    materials = [SimpleNamespace(id=UUID(int=i), kind='article', title='Article', source_version='1')
                 for i in range(10, 14)]
    pairs = [materials[:2], materials[2:]]
    lists = [SimpleNamespace(id=UUID(int=i), title='Plan', summary='Summary', saved_at=None,
                             context_snapshot={'material_versions': {str(m.id): '1' for m in pair}})
             for i, pair in enumerate(pairs, 1)]
    if changed_index is not None:
        materials[changed_index].source_version = '2'
    visible = {m.id for m in materials}
    if hidden_index is not None:
        visible.remove(materials[hidden_index].id)
    original_transition = 'Объяснение связи двух материалов.'
    rows = []
    for position in (1, 2):
        for listing, pair in zip(lists, pairs, strict=True):
            item = SimpleNamespace(list_id=listing.id, position=position, explanation='Актуальное объяснение.',
                                   offer_text=None, step_role='intro' if position == 1 else 'practice',
                                   transition_text=None if position == 1 else original_transition)
            rows.append((item, pair[position - 1]))

    class CRUD:
        async def items(self, ids): return rows
    class Catalog:
        async def visible_subset(self, ids): return visible
    class Studies:
        async def studied_ids(self, user_id, ids): return set()
    async def cards(values, *args): return [{'id': m.id} for m in values]
    service = RoadmapService(None, CRUD(), None, None, Catalog(), None, cards, Studies())

    result = run(service.render(UUID(int=99), lists))

    assert all(roadmap['steps'][0]['transition_text'] is None for roadmap in result)
    transition = result[0]['steps'][1]['transition_text']
    if changed_index is None and hidden_index is None:
        assert transition == original_transition
    else:
        assert transition and transition != original_transition
    assert result[1]['steps'][1]['transition_text'] == original_transition
    if changed_index != 1 and hidden_index != 1:
        assert result[0]['steps'][1]['explanation'] == 'Актуальное объяснение.'


def test_study_visibility_and_rollback():
    events = []
    class Session:
        async def commit(self): events.append('commit')
        async def rollback(self): events.append('rollback')
    class Catalog:
        async def get(self, material): return None
        async def get_any(self, material): return object()
    class Studies:
        async def set_state(self, user, material, studied): events.append((user, material, studied))
    service = MaterialStudyService(Session(), Catalog(), Studies())
    user, material = UUID(int=1), UUID(int=2)
    assert not run(service.set(user, material, True))
    assert run(service.set(user, material, False))
    assert events == ['rollback', (user, material, False), 'commit']


def test_crud_sql_is_scoped_and_conflict_safe():
    statements = []
    class Session:
        async def execute(self, query): statements.append(query)
        async def scalar(self, query):
            statements.append(query)
            return None
    session = Session()
    run(MaterialStudiesCRUD(session).set_state(UUID(int=1), UUID(int=2), True))
    run(MaterialStudiesCRUD(session).set_state(UUID(int=1), UUID(int=2), False))
    run(RecommendationsCRUD(session).save_roadmap(UUID(int=1), UUID(int=2)))
    sql = [str(q.compile(dialect=postgresql.dialect())) for q in statements]
    assert 'ON CONFLICT DO NOTHING' in sql[0]
    assert 'user_id' in sql[1] and 'material_id' in sql[1]
    assert 'saved_at IS NULL' in sql[2]
    assert all('user_id' in q and 'list_type' in q and 'recommendation_format' in q for q in sql[2:])
