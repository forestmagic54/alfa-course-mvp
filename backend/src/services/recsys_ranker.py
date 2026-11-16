import asyncio
import hashlib
import json
from dataclasses import replace
from itertools import pairwise
from pathlib import Path
from threading import Lock

from src.ml.recsys_engine.product_policy import (
    PRODUCT_EXCLUDED_IDS,
    ProductAlignedRecommender,
    ProductPolicy,
)
from src.ml.recsys_engine.trajectory_paths import read_curated_paths
from src.services.recommendation_stubs import (
    RankedItem,
    RankingInput,
    RankingResult,
    StubRanker,
)

DATA_DIR = Path(__file__).resolve().parents[1] / 'ml' / 'data'
TASK_BY_GOAL = {
    'sales': 'task_sales',
    'marketing': 'task_marketing',
    'finance': 'task_finance',
    'management': 'task_team',
}
STAGE_BY_CODE = {'starting': 'stage_idea', 'operating': 'stage_active'}
INDUSTRY_BY_CODE = {'retail': 'ind_retail', 'services': 'ind_services'}
DEPTH_BY_MODE = {'quick': 'brief', 'medium': 'detailed', 'deep': 'trajectory'}
DIFFICULTIES = ('beginner', 'intermediate', 'advanced')


class RecSysRanker:
    def __init__(self) -> None:
        self._model: ProductAlignedRecommender | None = None
        self._catalog_version: str | None = None
        self._load_lock = Lock()
        self._baseline = StubRanker()

    def _get_model(self, data: RankingInput) -> tuple[ProductAlignedRecommender, str]:
        rows = []
        for c in data.index_candidates if data.index_candidates is not None else data.candidates:
            if c.source_id is None or str(c.source_id) in PRODUCT_EXCLUDED_IDS:
                continue
            rows.append({'kind': c.kind, 'source_table': {'course': 'Courses', 'article': 'Articles', 'document': 'Documents'}[c.kind],
                'source_id': str(c.source_id), 'material_id': str(c.material_id), 'title': c.title,
                'description': c.description, 'public_description': c.description,
                'topics': sorted(c.topic_labels), 'tags': sorted(c.tag_labels), 'industries': sorted(c.industry_labels),
                'is_recommendable': True, 'access_type': c.catalog_access,
                'popularity': c.popularity, 'duration_minutes': c.duration_minutes, 'learning_role': c.role,
                'difficulty_level': c.difficulty, 'annotation_version': c.annotation_version, 'source_version': c.source_version,
                'feature_codes': sorted(TASK_BY_GOAL[code] for code, topics, tags in data.goal_mappings
                                        if code in TASK_BY_GOAL and (c.topics & topics or c.tags & tags))})
        rows.sort(key=lambda row: (row['kind'], row['source_id']))
        version = hashlib.sha256(json.dumps(rows, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()).hexdigest()
        with self._load_lock:
            if self._model is None or version != self._catalog_version:
                model = ProductAlignedRecommender(rows, trajectory_paths=read_curated_paths(DATA_DIR / 'trajectory_paths.json'),
                                                  product_policy=ProductPolicy(max_feed_items=6))
                self._model, self._catalog_version = model, version
            return self._model, version

    async def _short_roadmap(self, data: RankingInput, task: str, stage: str, version: str,
                             model: ProductAlignedRecommender, catalog_version: str) -> RankingResult:
        candidates = tuple(c for c in data.candidates if c.topics & data.goal_topics or c.tags & data.goal_tags)
        scores = await asyncio.to_thread(
            model.score_titles, [c.title for c in candidates], task, stage,
        ) if candidates else ()
        ranked = sorted(zip(candidates, scores, strict=True), key=lambda pair: (-pair[1], pair[0].title.casefold(), str(pair[0].material_id)))
        paths = {-1: ((), 0.0)}
        for role in ('intro', 'practice', 'advanced'):
            updated = dict(paths)
            for candidate, score in ranked:
                level = DIFFICULTIES.index(candidate.difficulty)
                if candidate.role != role:
                    continue
                for last_level, (items, total) in paths.items():
                    if level < last_level:
                        continue
                    item = RankedItem(candidate.material_id, candidate.kind, ('goal_match',),
                                      'relevance' if score > 0 else 'fallback', role, float(score))
                    option = (items + (item,), total + float(score))
                    current = updated.get(level)
                    if current is None or (len(option[0]), option[1]) > (len(current[0]), current[1]):
                        updated[level] = option
            paths = updated
        items, _ = max(paths.values(), key=lambda path: (len(path[0]), path[1]))
        return RankingResult(tuple(items), version, {'mode': 'deep', 'limit': 3, 'rules_version': data.rules_version,
            'scenario': 'short_roadmap', 'trajectory_id': None,
            'ml_items': sum(item.selection_kind == 'relevance' for item in items),
            'fallback_items': sum(item.selection_kind == 'fallback' for item in items),
            'catalog_version': catalog_version})

    async def rank(self, data: RankingInput) -> RankingResult:
        candidates = tuple(c for c in data.candidates if str(c.source_id) not in PRODUCT_EXCLUDED_IDS)
        data = replace(data, candidates=candidates)
        task = TASK_BY_GOAL.get(data.goal_code)
        stage = STAGE_BY_CODE.get(data.stage_code)
        if data.mode == 'popular' or task is None or stage is None or not candidates:
            baseline = await self._baseline.rank(data)
            return replace(baseline, ranking_config={**baseline.ranking_config,
                'scenario': ('popular' if data.mode == 'popular' else
                             'no_candidates' if not candidates else 'incomplete_profile'),
                'ml_items': 0, 'fallback_items': len(baseline.items)})

        deep = data.mode == 'deep'
        limit = 3 if deep else data.limit
        by_key = {
            f'{c.kind}:{c.source_id}': c for c in candidates if c.source_id is not None
            and (not deep or bool(c.topics & data.goal_topics or c.tags & data.goal_tags))
        }
        if not any(c.source_id is not None and str(c.source_id) not in PRODUCT_EXCLUDED_IDS
                   for c in (data.index_candidates if data.index_candidates is not None else candidates)):
            return RankingResult((), 'catalog-empty', {'mode': data.mode, 'rules_version': data.rules_version,
                                                       'scenario': 'no_indexed_candidates', 'ml_items': 0, 'fallback_items': 0})
        model, catalog_version = await asyncio.to_thread(self._get_model, data)
        response = await asyncio.to_thread(model.recommend, {
            'onboarding_completed': True, 'mode': 'smart',
            'stage': stage, 'task': task, 'industry': INDUSTRY_BY_CODE.get(data.industry_code),
            'depth': DEPTH_BY_MODE[data.mode], 'eligible_material_keys': tuple(by_key),
        }, limit=limit)

        if deep and response['scenario'] != 'trajectory':
            return await self._short_roadmap(data, task, stage, response['model_version'], model, catalog_version)

        selected = [
            (by_key[f"{item['kind']}:{item['source_id']}"], item) for item in response['items']
        ]
        if deep and (
            any(candidate.role != item['step_role'] for candidate, item in selected)
            or any(candidate.access != 'free' for candidate, _ in selected[:2])
            or any(DIFFICULTIES.index(a.difficulty) > DIFFICULTIES.index(b.difficulty)
                   for (a, _), (b, _) in pairwise(selected))
        ):
            return await self._short_roadmap(data, task, stage, response['model_version'], model, catalog_version)

        items = []
        exploration = response['scenario'] == 'catalog_exploration'
        for candidate, item in selected:
            goal_match = bool(candidate.topics & data.goal_topics or candidate.tags & data.goal_tags
                              or task in item['matched_features'])
            items.append(RankedItem(
                candidate.material_id, candidate.kind, ('goal_match',) if goal_match else (),
                'fallback' if exploration else 'relevance' if goal_match else 'exploration', item['step_role'], item['score'],
            ))

        if not items and deep:
            return await self._short_roadmap(data, task, stage, response['model_version'], model, catalog_version)

        return RankingResult(tuple(items), response['model_version'], {
            'mode': data.mode, 'limit': limit, 'rules_version': data.rules_version,
            'scenario': response['scenario'], 'trajectory_id': response['trajectory_id'],
            'ml_items': 0 if exploration else len(selected), 'fallback_items': len(selected) if exploration else 0,
            'catalog_version': catalog_version,
        })
