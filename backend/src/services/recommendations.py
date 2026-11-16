import asyncio
import json
import math
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from src.clients.llm_schemas import MaterialInput, ProfileInput
from src.services.onboarding import EffectivePreferences, effective_preferences
from src.services.recommendation_stubs import (
    Candidate,
    GeneratedText,
    GenerationInput,
    GenerationResult,
    Generator,
    Mode,
    RankedItem,
    Ranker,
    RankingInput,
    RankingResult,
)
from src.services.types import RecommendationItemData


class RankingUnavailable(Exception):
    pass


class RoadmapUnavailable(Exception):
    pass


@dataclass(frozen=True)
class Recommendations:
    items: list[RecommendationItemData]
    ranking_version: str
    ranking_config: dict[str, Any]
    title: str | None = None
    summary: str | None = None
    ranked_items: tuple[RankedItem, ...] = ()
    material_versions: dict[str, str] | None = None


def validate_ranking(result: RankingResult, candidates: tuple[Candidate, ...], mode: Mode, limit: int = 5) -> None:
    by_id = {c.material_id: c for c in candidates}
    if not isinstance(result, RankingResult) or not isinstance(result.ranking_version, str) or not result.ranking_version or not isinstance(result.ranking_config, dict):
        raise ValueError('Invalid ranking result')
    if len(result.items) > (3 if mode == 'deep' else limit):
        raise ValueError('Too many ranking items')
    seen = set()
    roles = ('intro', 'practice', 'advanced')
    last_role = last_difficulty = -1
    for item in result.items:
        candidate = by_id.get(item.material_id)
        if (candidate is None or item.material_id in seen or item.kind != candidate.kind
                or not isinstance(item.reasons, tuple) or not all(isinstance(r, str) for r in item.reasons)
                or item.selection_kind not in ('relevance', 'exploration', 'fallback')
                or (item.score is not None and (isinstance(item.score, bool) or not isinstance(item.score, (int, float)) or not math.isfinite(item.score)))):
            raise ValueError('Invalid ranking item')
        seen.add(item.material_id)
        if mode == 'deep':
            if item.step_role != candidate.role or item.step_role not in roles:
                raise ValueError('Invalid step role')
            role = roles.index(item.step_role)
            difficulty = ('beginner', 'intermediate', 'advanced').index(candidate.difficulty)
            if role <= last_role or difficulty < last_difficulty:
                raise ValueError('Invalid roadmap order')
            last_role, last_difficulty = role, difficulty
        elif item.step_role is not None:
            raise ValueError('Unexpected step role')


def nonempty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def classification_labels(groups, key, allowed=None):
    entries = groups.get(key, {})
    if not isinstance(entries, dict):
        return []
    return [name[:200] for key_id, name in entries.items()
            if isinstance(name, str) and name.strip() and
            (allowed is None or str(key_id) in allowed)][:30]


class RecommendationService:
    def __init__(self, session: AsyncSession, ranker: Ranker, generator: Generator, fallback_generator: Generator,
                 generation_timeout: float, materials_factory, card_builder):
        self.session = session
        self.ranker = ranker
        self.generator = generator
        self.fallback_generator = fallback_generator
        self.generation_timeout = generation_timeout
        self.materials_factory = materials_factory
        self.build_cards = card_builder

    async def recommend(self, mode: Mode, *, user_id: UUID | None = None,
                        preferences: EffectivePreferences | None = None, limit: int = 5) -> Recommendations:
        if mode not in ('popular', 'quick', 'medium', 'deep'):
            raise ValueError('Unknown recommendation mode')
        preferences = preferences or effective_preferences(None, None)
        config = preferences.config
        crud = self.materials_factory(config)
        materials = await crud.recommendation_candidates()
        materials = [m for m in materials if m.is_recommendable and m.kind in ('course', 'article', 'document')
                     and m.source_table == {'course': 'Courses', 'article': 'Articles', 'document': 'Documents'}[m.kind]
                     and m.learning_role in ('intro', 'practice', 'advanced')
                     and m.difficulty_level in ('beginner', 'intermediate', 'advanced')
                     and m.annotation_source in ('import', 'manual', 'model') and m.annotation_version
                     and (m.kind != 'course' or m.verified_course_id == m.source_id)]
        classification = await crud.classification([m.id for m in materials])
        cards = await self.build_cards(materials, None if mode == 'popular' else user_id, config)
        all_cards = {c['id']: c for c in cards}
        cards_by_id = {c['id']: c for c in cards if c['primary_action'] is not None}
        popularity = config['catalog']['popularity']
        index_candidates = tuple(Candidate(m.id, m.kind, m.title, frozenset(map(str, classification[m.id]['topics'])),
            frozenset(map(str, classification[m.id]['tags'])), frozenset(map(str, classification[m.id]['industries'])),
            m.learning_role, m.difficulty_level, m.duration_minutes, popularity.get(str(m.id)), m.source_version,
            m.annotation_version, all_cards[m.id]['access'], getattr(m, 'source_id', None),
            getattr(m, 'public_description', None) or '', tuple(classification[m.id]['topics'].values()),
            tuple(classification[m.id]['tags'].values()), tuple(classification[m.id]['industries'].values()),
            getattr(m, 'access_type', 'unknown'))
            for m in materials if m.id in all_cards)
        candidates = tuple(c for c in index_candidates if c.material_id in cards_by_id)
        ranking_input = RankingInput(mode, frozenset(preferences.goal.get('topic_ids', ())), frozenset(preferences.goal.get('tag_ids', ())),
                                     preferences.industry, preferences.profile_version, config['version'], candidates,
                                     goal_code=preferences.goal_code, stage_code=preferences.stage_code,
                                     industry_code=preferences.industry_code, index_candidates=index_candidates,
                                     goal_mappings=tuple((code, frozenset(goal['topic_ids']), frozenset(goal['tag_ids']))
                                                         for code, goal in config['goals'].items()), limit=limit)
        try:
            ranking = await self.ranker.rank(ranking_input)
            validate_ranking(ranking, candidates, mode, limit)
            json.dumps(ranking.ranking_config, allow_nan=False)
            if mode == 'deep' and any(not (selected.topics & ranking_input.goal_topics or
                                            selected.tags & ranking_input.goal_tags)
                                      for item in ranking.items for selected in candidates
                                      if selected.material_id == item.material_id):
                raise ValueError('Roadmap material does not match the goal')
        except Exception as exc:
            raise RankingUnavailable from exc
        if mode == 'deep' and not ranking.items:
            raise RoadmapUnavailable
        if mode == 'popular':
            if user_id is not None:
                cards_by_id = {c['id']: c for c in await self.build_cards(materials, user_id, config)}
            return Recommendations([{'position': i, 'material': cards_by_id[x.material_id], 'explanation': None,
                                     'offer_text': None} for i, x in enumerate(ranking.items, 1)],
                                   ranking.ranking_version, ranking.ranking_config)
        selected = {c.material_id: c for c in candidates}
        material_by_id = {m.id: m for m in materials}
        facts = {}
        for item in ranking.items:
            material = material_by_id[item.material_id]
            groups = classification[item.material_id]
            if item.kind not in ('article', 'course'):
                continue
            try:
                facts[item.material_id] = MaterialInput(
                    id=item.material_id, kind=item.kind, title=material.title,
                    public_description=getattr(material, 'public_description', None),
                    access_type=getattr(material, 'access_type', 'unknown'),
                    duration_minutes=material.duration_minutes, difficulty_level=material.difficulty_level,
                    learning_role=material.learning_role, source_version=material.source_version,
                    topics=classification_labels(groups, 'topics'), tags=classification_labels(groups, 'tags'),
                    industries=classification_labels(groups, 'industries'),
                    selection_kind=item.selection_kind, mode=mode,
                    matched_topics=classification_labels(groups, 'topics', ranking_input.goal_topics) if 'goal_match' in item.reasons else [],
                    matched_tags=classification_labels(groups, 'tags', ranking_input.goal_tags) if 'goal_match' in item.reasons else [],
                )
            except ValidationError:
                continue
        try:
            profile = ProfileInput(stage_code=preferences.stage_code, industry_code=preferences.industry_code,
                goal_code=preferences.goal_code, learning_mode=preferences.learning_mode,
                profile_config_version=preferences.profile_version) if preferences.profile_version else None
        except ValidationError:
            profile = None
        generation_input = GenerationInput(mode, ranking_input.profile_version,
                                           tuple(selected[x.material_id] for x in ranking.items), ranking.items,
                                           profile, facts)
        fallback = await self.fallback_generator.generate(generation_input)
        default_offers = {m.id: getattr(m, 'default_offer_text', None) for m in materials}
        try:
            generated = await asyncio.wait_for(self.generator.generate(generation_input),
                                               timeout=self.generation_timeout)
            if not isinstance(generated, GenerationResult) or not isinstance(generated.items, dict):
                generated = fallback
        except Exception:
            generated = fallback
        items: list[RecommendationItemData] = []
        for index, item in enumerate(ranking.items):
            default = fallback.items[item.material_id]
            text = generated.items.get(item.material_id)
            if not isinstance(text, GeneratedText) or text.kind != item.kind:
                text = default
            explanation = text.explanation if nonempty(text.explanation) else default.explanation
            offer = None
            if item.kind == 'course':
                offer = text.offer_text if nonempty(text.offer_text) else default_offers.get(item.material_id)
                offer = offer if nonempty(offer) else None
            row: RecommendationItemData = {'position': index + 1, 'material': cards_by_id[item.material_id],
                   'explanation': explanation, 'offer_text': offer}
            if mode == 'deep':
                row['step_role'] = item.step_role
                row['transition_text'] = (None if index == 0 else
                                          text.transition_text if nonempty(text.transition_text) else default.transition_text)
                row['is_studied'] = False
            items.append(row)
        return Recommendations(items, ranking.ranking_version, ranking.ranking_config,
            (generated.title if nonempty(generated.title) else fallback.title) if mode == 'deep' else None,
            (generated.summary if nonempty(generated.summary) else fallback.summary) if mode == 'deep' else None,
            ranking.items, {str(x.material_id): selected[x.material_id].source_version for x in ranking.items})
