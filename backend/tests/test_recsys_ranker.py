import asyncio
import csv
import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import pytest

from src.services.onboarding import effective_preferences
from src.services.recommendation_stubs import Candidate, RankingInput, StubGenerator
from src.services.recommendations import RecommendationService, validate_ranking
from src.services.recsys_ranker import RecSysRanker


def test_completed_sales_uses_ml_and_returns_backend_ids():
    preferences = effective_preferences(None, {
        'form_type': 'simple', 'questionnaire_version': '1', 'status': 'completed',
        'answers': {'business_stage': 'operating', 'current_task': 'sales', 'learning_mode': 'quick'},
    })
    task_topics = frozenset(preferences.goal['topic_ids'])
    source = UUID('a8184af0-7007-4bc3-98c1-1ff55c949a97')
    sales = Candidate(
        UUID(int=1), 'course', 'Sales', task_topics, frozenset(), frozenset(),
        'practice', 'intermediate', 120, None, '1', '1', 'free', source,
    )
    unknown = replace(sales, material_id=UUID(int=2), source_id=UUID(int=20), topics=frozenset())
    omitted_source = UUID('8be9c4dc-d301-4af3-9548-0a091b8cf441')
    data = RankingInput('quick', task_topics, frozenset(), preferences.industry,
                        preferences.profile_version, preferences.config['version'], (unknown, sales),
                        goal_code=preferences.goal_code, stage_code=preferences.stage_code)

    result = asyncio.run(RecSysRanker().rank(data))

    validate_ranking(result, data.candidates, data.mode)
    assert result.ranking_version == 'offline-materials-0.9-v5.5'
    assert result.ranking_config['ml_items'] + result.ranking_config['fallback_items'] == 2
    assert {item.material_id for item in result.items} == {sales.material_id, unknown.material_id}
    assert 'goal_match' in next(item for item in result.items if item.material_id == sales.material_id).reasons
    assert all(item.material_id not in (source, omitted_source) for item in result.items)


def test_draft_roadmap_uses_existing_backend_selection():
    sales = Candidate(
        UUID(int=1), 'article', 'Sales', frozenset({'sales'}), frozenset(), frozenset(),
        'intro', 'beginner', None, None, '1', '1', 'free',
        UUID('d3b549ed-3433-4975-b964-d1785f79fbaf'),
    )
    data = RankingInput('deep', sales.topics, frozenset(), None, None, '1', (sales,),
                        goal_code='sales', stage_code='operating')

    result = asyncio.run(RecSysRanker().rank(data))

    validate_ranking(result, data.candidates, data.mode)
    assert result.ranking_config.get('trajectory_id') is None
    assert result.ranking_config['scenario'] == 'short_roadmap'
    assert [(item.material_id, item.step_role) for item in result.items] == [(sales.material_id, 'intro')]


def test_live_catalog_ranking_when_sources_are_absent_from_ml_catalog():
    sales = Candidate(
        UUID(int=1), 'article', 'Продажи', frozenset({'sales'}), frozenset(), frozenset(),
        'intro', 'beginner', None, None, '1', '1', 'free', UUID(int=10),
    )
    unrelated = replace(sales, material_id=UUID(int=2), title='Материал', topics=frozenset(), source_id=UUID(int=11))
    data = RankingInput('quick', sales.topics, frozenset(), None, None, '1', (unrelated, sales),
                        goal_code='sales', stage_code='operating')

    result = asyncio.run(RecSysRanker().rank(data))

    validate_ranking(result, data.candidates, data.mode)
    assert result.ranking_version == 'offline-materials-0.9-v5.5'
    assert result.ranking_config['scenario'] in ('feed', 'catalog_exploration')
    assert [item.material_id for item in result.items] == [sales.material_id, unrelated.material_id]


def test_short_roadmap_uses_confirmed_topics_and_ordered_difficulty():
    base = Candidate(UUID(int=1), 'article', 'A', frozenset({'sales'}), frozenset(), frozenset(),
                     'intro', 'intermediate', None, None, '1', '1', 'free', UUID(int=1))
    lower = replace(base, material_id=UUID(int=2), role='practice', difficulty='beginner')
    higher = replace(base, material_id=UUID(int=3), role='advanced', difficulty='advanced')
    unrelated = replace(base, material_id=UUID(int=4), topics=frozenset())
    data = RankingInput('deep', base.topics, frozenset(), None, None, '1',
                        (unrelated, higher, lower, base), goal_code='sales', stage_code='operating')
    ranker = RecSysRanker()
    model = SimpleNamespace(recommend=lambda request, limit: {'scenario': 'feed_fallback', 'model_version': 'test'},
                            score_titles=lambda titles, task, stage: [1.0] * len(titles))
    ranker._get_model = lambda data: (model, 'test-catalog')

    result = asyncio.run(ranker.rank(data))

    validate_ranking(result, data.candidates, 'deep')
    assert result.ranking_config['scenario'] == 'short_roadmap'
    assert [item.material_id for item in result.items] == [base.material_id, higher.material_id]


def test_short_roadmap_prefers_longer_valid_sequence():
    base = Candidate(UUID(int=1), 'article', 'A', frozenset({'sales'}), frozenset(), frozenset(),
                     'intro', 'advanced', None, None, '1', '1', 'free', UUID(int=1))
    intro = replace(base, material_id=UUID(int=2), title='B', difficulty='beginner')
    practice = replace(base, material_id=UUID(int=3), title='C', role='practice', difficulty='beginner')
    advanced = replace(base, material_id=UUID(int=4), title='D', role='advanced', difficulty='intermediate')
    data = RankingInput('deep', base.topics, frozenset(), None, None, '1', (base, intro, practice, advanced),
                        goal_code='sales', stage_code='operating')
    ranker = RecSysRanker()
    model = SimpleNamespace(recommend=lambda request, limit: {'scenario': 'feed_fallback', 'model_version': 'test'},
                            score_titles=lambda titles, task, stage: [10.0, 1.0, 1.0, 1.0])
    ranker._get_model = lambda data: (model, 'test-catalog')

    result = asyncio.run(ranker.rank(data))

    validate_ranking(result, data.candidates, 'deep')
    assert [item.material_id for item in result.items] == [intro.material_id, practice.material_id, advanced.material_id]


def test_industry_code_is_translated_before_model_call():
    candidate = Candidate(UUID(int=1), 'article', 'A', frozenset({'sales'}), frozenset(), frozenset(),
                          'intro', 'beginner', None, None, '1', '1', 'free', UUID(int=2))
    data = RankingInput('quick', candidate.topics, frozenset(), 'backend-uuid', None, '1', (candidate,),
                        goal_code='sales', stage_code='operating', industry_code='retail')
    request = {}
    ranker = RecSysRanker()

    def recommend(value, limit):
        request.update(value)
        return {'scenario': 'feed', 'model_version': 'test', 'trajectory_id': None,
                'items': [{'kind': 'article', 'source_id': str(candidate.source_id),
                           'matched_features': [], 'step_role': None, 'score': 1.0}]}

    ranker._get_model = lambda data: (SimpleNamespace(recommend=recommend), 'test-catalog')
    asyncio.run(ranker.rank(data))
    assert request['industry'] == 'ind_retail'


def test_database_index_rebuilds_on_catalog_change_and_ignores_user_access(monkeypatch):
    built = []

    def build(rows, trajectory_paths, product_policy):
        built.append(rows)
        return object()

    monkeypatch.setattr('src.services.recsys_ranker.ProductAlignedRecommender', build)
    candidate = Candidate(UUID(int=1), 'course', 'Тест', frozenset({'topic'}), frozenset(), frozenset(),
                          'intro', 'beginner', 10, 1, 'v1', 'a1', 'none', UUID(int=2),
                          catalog_access='paid')
    data = RankingInput('quick', candidate.topics, frozenset(), None, '1', '1', (candidate,),
                        goal_code='sales', stage_code='operating', index_candidates=(candidate,),
                        goal_mappings=(('sales', frozenset({'topic'}), frozenset()),))
    ranker = RecSysRanker()
    first, version = ranker._get_model(data)
    purchased = replace(candidate, access='course_purchase')
    same, same_version = ranker._get_model(replace(data, candidates=(purchased,), index_candidates=(purchased,)))
    changed, changed_version = ranker._get_model(replace(data, index_candidates=(replace(candidate, title='Новое'),)))

    assert first is same and version == same_version and changed is not first and changed_version != version
    assert len(built) == 2 and built[0][0]['access_type'] == 'paid'
    assert built[0][0]['feature_codes'] == ['task_sales']


def test_database_index_does_not_return_ineligible_materials():
    allowed = Candidate(UUID(int=1), 'article', 'Продажи и клиенты', frozenset({'sales'}), frozenset(), frozenset(),
                        'intro', 'beginner', 10, 1, 'v1', 'a1', 'free', UUID(int=1), catalog_access='free')
    hidden = replace(allowed, material_id=UUID(int=2), source_id=UUID(int=2), title='Продажи для клиентов')
    data = RankingInput('quick', allowed.topics, frozenset(), None, '1', '1', (allowed,),
                        goal_code='sales', stage_code='operating', index_candidates=(allowed, hidden),
                        goal_mappings=(('sales', allowed.topics, frozenset()),))

    result = asyncio.run(RecSysRanker().rank(data))

    assert [item.material_id for item in result.items] == [allowed.material_id]


def test_database_ranker_respects_get_and_post_limits():
    base = Candidate(UUID(int=1), 'article', 'Продажи и клиенты', frozenset({'sales'}), frozenset(), frozenset(),
                     'intro', 'beginner', 10, 1, 'v1', 'a1', 'free', UUID(int=1), catalog_access='free')
    candidates = tuple(replace(base, material_id=UUID(int=i), source_id=UUID(int=i), title=f'Продажи и клиенты {i}')
                       for i in range(1, 9))
    data = RankingInput('quick', base.topics, frozenset(), None, '1', '1', candidates,
                        goal_code='sales', stage_code='operating', index_candidates=candidates,
                        goal_mappings=(('sales', base.topics, frozenset()),))
    ranker = RecSysRanker()

    assert len(asyncio.run(ranker.rank(data)).items) == 5
    assert len(asyncio.run(ranker.rank(replace(data, limit=6))).items) == 6
    assert len(asyncio.run(ranker.rank(replace(data, mode='popular', limit=6))).items) == 6


@pytest.mark.parametrize(('goal', 'path_id', 'unavailable'), [
    ('sales', 'sales_online_v1', False), ('marketing', 'marketing_v1', False),
    ('finance', 'finance_margin_v1', False), ('management', 'team_v1', False),
    ('sales', 'sales_online_v1', True),
])
def test_approved_path_reaches_service_with_backend_ids(goal, path_id, unavailable):
    data_dir = Path(__file__).resolve().parents[1] / 'src' / 'ml' / 'data'
    paths = json.loads((data_dir / 'trajectory_paths.json').read_text())['paths']
    path = next(path for path in paths if path['path_id'] == path_id)
    annotations = {}
    with (data_dir / 'material_annotations.csv').open(newline='') as source:
        for row in csv.DictReader(source):
            annotations[(row['source_table'], row['source_id'])] = row
    with (data_dir / 'real_materials.jsonl').open() as source:
        catalog = {(row['kind'], row['source_id']): row for line in source if (row := json.loads(line))}
    fixture = json.loads((data_dir.parents[1] / 'config' / 'demo' / 'fixture-v2.json').read_text())
    fixture_materials = {row['source_id']: row for row in fixture['mvp']['materials']}
    settings = {str(row['EntityId']): row['Id'] for row in fixture['source']['ContentSettings']}
    bindings = fixture['source']['ContentSettingsTopics']
    preferences = effective_preferences(None, {'form_type': 'simple', 'questionnaire_version': '1',
        'status': 'completed', 'answers': {'business_stage': 'operating', 'current_task': goal}})
    materials = []
    for step in path['steps']:
        kind, source_id = step['material_key'].split(':')
        row = catalog[kind, source_id]
        annotation = annotations[row['source_table'], source_id]
        materials.append(SimpleNamespace(id=UUID(fixture_materials[source_id]['id']), kind=kind, source_id=UUID(source_id),
            source_table=row['source_table'], title=row['title'], is_recommendable=True,
            learning_role=annotation['learning_role'], difficulty_level=annotation['difficulty_level'],
            annotation_source=annotation['annotation_source'], annotation_version=annotation['annotation_version'],
            duration_minutes=row['duration_minutes'], source_version='backend-test',
            access_type=fixture_materials[source_id]['access_type'], public_description=row['public_description'],
            verified_course_id=UUID(source_id) if kind == 'course' else None))

    class Catalog:
        async def recommendation_candidates(self):
            return materials

        async def classification(self, ids):
            return {material.id: {'topics': {UUID(binding['TopicId']): 'Тестовая тема' for binding in bindings
                                            if binding['ContentSettingsId'] == settings[str(material.source_id)]},
                                  'tags': {}, 'industries': {}} for material in materials if material.id in ids}

    async def cards(rows, user_id, config):
        return [{'id': row.id, 'primary_action': None if unavailable and i == 0 else {'type': 'open'},
                 'access': 'free' if str(row.id) in config['access']['free_material_ids'] else 'unknown'}
                for i, row in enumerate(rows)]

    service = RecommendationService(None, RecSysRanker(), StubGenerator(), StubGenerator(), 1,
                                    lambda config: Catalog(), cards)
    result = asyncio.run(service.recommend('deep', preferences=preferences))

    assert result.ranking_config['scenario'] == ('short_roadmap' if unavailable else 'trajectory')
    assert result.ranking_config['trajectory_id'] == (None if unavailable else path_id)
    assert result.ranking_config['ml_items'] + result.ranking_config['fallback_items'] == (2 if unavailable else 3)
    if not unavailable:
        assert result.ranking_config['ml_items'] == 3
    assert [item['material']['id'] for item in result.items] == [row.id for row in materials[int(unavailable):]]
    assert [item['step_role'] for item in result.items] == ['intro', 'practice', 'advanced'][int(unavailable):]
