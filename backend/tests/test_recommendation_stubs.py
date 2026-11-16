import asyncio
from dataclasses import replace
from types import SimpleNamespace
from uuid import UUID

import pytest

from src.services import recommendations as service
from src.services.recommendation_stubs import (
    Candidate,
    GeneratedText,
    GenerationInput,
    GenerationResult,
    RankedItem,
    RankingInput,
    RankingResult,
    StubGenerator,
    StubRanker,
)


def candidate(number, *, role='intro', duration=None, topics=frozenset({'sales'}), kind='article'):
    return Candidate(UUID(int=number), kind, f'Title {number}', topics, frozenset(), frozenset(), role,
                     'beginner', duration, None, 'source-v1', 'annotation-v1', 'free')


def ranking_input(mode, candidates, topics=frozenset({'sales'})):
    return RankingInput(mode, topics, frozenset(), None, '1', '1', tuple(candidates))


def run(coro):
    return asyncio.run(coro)


def test_ranking_is_deterministic_and_respects_mode_and_unknown_duration():
    candidates = [candidate(1), candidate(2, duration=10), candidate(3, role='practice', duration=5),
                  candidate(4, topics=frozenset({'finance'}))]
    ranker = StubRanker()
    quick = run(ranker.rank(ranking_input('quick', candidates)))
    assert quick == run(ranker.rank(ranking_input('quick', list(reversed(candidates)))))
    assert [x.material_id.int for x in quick.items] == [2, 1, 3, 4]
    assert run(ranker.rank(ranking_input('medium', candidates))).items[0].material_id.int == 3
    assert run(ranker.rank(ranking_input('quick', candidates, frozenset({'finance'})))).items[0].material_id.int == 4
    assert run(ranker.rank(ranking_input('popular', candidates))).items == run(
        ranker.rank(ranking_input('popular', candidates, frozenset({'finance'})))).items


def test_deep_uses_only_matching_topics_and_weakens_industry():
    candidates = [candidate(1), candidate(2, role='practice'), candidate(3, role='advanced'),
                  candidate(4, topics=frozenset({'other'}))]
    data = replace(ranking_input('deep', candidates), industry='other')
    result = run(StubRanker().rank(data))
    assert [x.step_role for x in result.items] == ['intro', 'practice', 'advanced']
    assert len({x.material_id for x in result.items}) == 3
    text = run(StubGenerator().generate(GenerationInput('deep', '1', tuple(candidates[:3]), result.items)))
    assert text.items[result.items[0].material_id].transition_text is None
    assert text.items[result.items[1].material_id].transition_text


@pytest.mark.parametrize('items', [
    (RankedItem(UUID(int=99), 'article', (), 'fallback'),),
    (RankedItem(UUID(int=1), 'course', (), 'fallback'),),
    (RankedItem(UUID(int=1), 'article', (), 'fallback', score=float('nan')),),
    (RankedItem(UUID(int=1), 'article', (), 'fallback'), RankedItem(UUID(int=1), 'article', (), 'fallback')),
])
def test_invalid_ranking(items):
    with pytest.raises(ValueError):
        service.validate_ranking(RankingResult(items, 'v', {}), (candidate(1),), 'quick')


def test_orchestration_fallback_and_popular_no_generator(monkeypatch):
    c = candidate(1)
    material = SimpleNamespace(id=c.material_id, kind=c.kind, title=c.title, source_table='Articles',
        is_recommendable=True, learning_role=c.role, difficulty_level=c.difficulty, annotation_source='manual',
        annotation_version='1', duration_minutes=None, source_version='1')
    class CRUD:
        def __init__(self, *args): pass
        async def recommendation_candidates(self): return [material]
        async def classification(self, ids):
            return {c.material_id: {'topics': {}, 'tags': {}, 'industries': {}}}
    async def cards(*args):
        return [{'id': c.material_id, 'primary_action': {'type': 'read_article'}, 'access': 'free'}]
    class BrokenGenerator:
        async def generate(self, data):
            raise RuntimeError('unavailable')
    ctx = SimpleNamespace(ranker=StubRanker(), generator=BrokenGenerator(),
                          settings=SimpleNamespace(app=SimpleNamespace(generation_timeout_seconds=0.01)))
    recommender = service.RecommendationService(None, ctx.ranker, ctx.generator, StubGenerator(), ctx.settings.app.generation_timeout_seconds,
                                                lambda config: CRUD(), cards)
    result = run(recommender.recommend('quick'))
    assert result.items[0]['explanation'] and result.items[0]['offer_text'] is None
    assert run(recommender.recommend('popular')).items[0]['explanation'] is None
    with pytest.raises(service.RoadmapUnavailable):
        run(recommender.recommend('deep'))
    class InvalidRanker:
        async def rank(self, data): return RankingResult((RankedItem(UUID(int=99), 'article', (), 'fallback'),), 'v', {})
    recommender.ranker = InvalidRanker()
    with pytest.raises(service.RankingUnavailable):
        run(recommender.recommend('quick'))


def test_generator_fallback_preserves_order_and_valid_items(monkeypatch):
    candidates = [candidate(1), candidate(2, kind='course')]
    materials = [SimpleNamespace(id=c.material_id, kind=c.kind, title=c.title,
        source_table='Articles' if c.kind == 'article' else 'Courses', is_recommendable=True,
        learning_role=c.role, difficulty_level=c.difficulty, annotation_source='manual',
        annotation_version='1', duration_minutes=None, source_version='1',
        source_id=c.material_id, verified_course_id=c.material_id if c.kind == 'course' else None)
        for c in candidates]
    class CRUD:
        def __init__(self, *args): pass
        async def recommendation_candidates(self): return materials
        async def classification(self, ids):
            return {i: {'topics': {}, 'tags': {}, 'industries': {}} for i in ids}
    async def cards(*args):
        return [{'id': c.material_id, 'primary_action': {'type': 'open'}, 'access': 'free'} for c in candidates]
    class Generator:
        async def generate(self, data):
            return GenerationResult({candidates[0].material_id: GeneratedText('article', 'Готовый текст', 'лишнее'),
                                     candidates[1].material_id: GeneratedText('course', '')})
    ctx = SimpleNamespace(ranker=StubRanker(), generator=Generator(),
                          settings=SimpleNamespace(app=SimpleNamespace(generation_timeout_seconds=0.001)))
    recommender = service.RecommendationService(None, ctx.ranker, ctx.generator, StubGenerator(), ctx.settings.app.generation_timeout_seconds,
                                                lambda config: CRUD(), cards)
    result = run(recommender.recommend('quick'))
    assert [x['material']['id'] for x in result.items] == [c.material_id for c in candidates]
    assert result.items[0]['explanation'] == 'Готовый текст'
    assert result.items[0]['offer_text'] is None
    assert result.items[1]['explanation']
    class SlowGenerator:
        async def generate(self, data):
            await asyncio.sleep(1)
    recommender.generator = SlowGenerator()
    assert all(x['explanation'] for x in run(recommender.recommend('quick')).items)


def test_injected_fallback_and_authenticated_cards():
    from unittest.mock import AsyncMock

    c = candidate(1)
    material = SimpleNamespace(id=c.material_id, kind=c.kind, title=c.title, source_table='Articles',
        is_recommendable=True, learning_role=c.role, difficulty_level=c.difficulty, annotation_source='manual',
        annotation_version='1', duration_minutes=None, source_version='1')
    class CRUD:
        async def recommendation_candidates(self): return [material]
        async def classification(self, ids):
            return {c.material_id: {'topics': {}, 'tags': {}, 'industries': {}}}
    calls = []
    async def cards(materials, user_id, config):
        calls.append(user_id)
        return [{'id': c.material_id, 'primary_action': {'type': 'read_article'}, 'access': 'free'}]
    fallback = SimpleNamespace(generate=AsyncMock(return_value=GenerationResult({
        c.material_id: GeneratedText('article', 'Резервный текст')})))
    broken = SimpleNamespace(generate=AsyncMock(side_effect=RuntimeError('unavailable')))
    recommender = service.RecommendationService(None, StubRanker(), broken, fallback, 1, lambda config: CRUD(), cards)
    user_id = UUID(int=42)
    result = run(recommender.recommend('quick', user_id=user_id))
    assert result.items[0]['explanation'] == 'Резервный текст' and calls == [user_id]
    fallback.generate.assert_awaited_once()
    calls.clear()
    run(recommender.recommend('popular', user_id=user_id))
    assert calls == [None, user_id]
    fallback.generate.assert_awaited_once()
