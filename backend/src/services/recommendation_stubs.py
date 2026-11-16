from dataclasses import dataclass
from typing import Literal, Protocol
from uuid import UUID

from src.clients.llm_schemas import MaterialInput, ProfileInput

Mode = Literal['popular', 'quick', 'medium', 'deep']


@dataclass(frozen=True)
class Candidate:
    material_id: UUID
    kind: str
    title: str
    topics: frozenset[str]
    tags: frozenset[str]
    industries: frozenset[str]
    role: str
    difficulty: str
    duration_minutes: int | None
    popularity: float | None
    source_version: str
    annotation_version: str
    access: str
    source_id: UUID | None = None
    description: str = ''
    topic_labels: tuple[str, ...] = ()
    tag_labels: tuple[str, ...] = ()
    industry_labels: tuple[str, ...] = ()
    catalog_access: str = 'unknown'


@dataclass(frozen=True)
class RankingInput:
    mode: Mode
    goal_topics: frozenset[str]
    goal_tags: frozenset[str]
    industry: str | None
    profile_version: str | None
    rules_version: str
    candidates: tuple[Candidate, ...]
    goal_code: str | None = None
    stage_code: str | None = None
    industry_code: str | None = None
    index_candidates: tuple[Candidate, ...] | None = None
    goal_mappings: tuple[tuple[str, frozenset[str], frozenset[str]], ...] = ()
    limit: int = 5


@dataclass(frozen=True)
class RankedItem:
    material_id: UUID
    kind: str
    reasons: tuple[str, ...]
    selection_kind: str
    step_role: str | None = None
    score: float | None = None


@dataclass(frozen=True)
class RankingResult:
    items: tuple[RankedItem, ...]
    ranking_version: str
    ranking_config: dict


@dataclass(frozen=True)
class GenerationInput:
    mode: Mode
    profile_version: str | None
    materials: tuple[Candidate, ...]
    ranking: tuple[RankedItem, ...]
    profile: ProfileInput | None = None
    facts: dict[UUID, MaterialInput] | None = None


@dataclass(frozen=True)
class GeneratedText:
    kind: str
    explanation: str
    offer_text: str | None = None
    transition_text: str | None = None


@dataclass(frozen=True)
class GenerationResult:
    items: dict[UUID, GeneratedText]
    title: str | None = None
    summary: str | None = None


class StubRanker:
    async def rank(self, data: RankingInput) -> RankingResult:
        # shortcut: simple deterministic matching until the real ranker is available.
        def matches(c):
            return bool(c.topics & data.goal_topics or c.tags & data.goal_tags)

        def key(c):
            if data.mode == 'popular':
                return (-(c.popularity if c.popularity is not None else float('-inf')), c.title.casefold(), str(c.material_id))
            role = 'intro' if data.mode == 'quick' else 'practice'
            return (not matches(c), bool(data.industry and data.industry not in c.industries),
                    c.role != role, c.duration_minutes is None,
                    c.duration_minutes if c.duration_minutes is not None else 0,
                    c.title.casefold(), str(c.material_id))

        ordered = sorted(data.candidates, key=key)
        if data.mode == 'deep':
            # Deep requires a confirmed thematic link and non-decreasing difficulty.
            ordered = [c for c in ordered if matches(c)]
            chosen = []
            difficulty = -1
            for role in ('intro', 'practice', 'advanced'):
                options = [c for c in ordered if c.role == role and
                           ('beginner', 'intermediate', 'advanced').index(c.difficulty) >= difficulty]
                if options:
                    c = options[0]
                    chosen.append(c)
                    difficulty = ('beginner', 'intermediate', 'advanced').index(c.difficulty)
            ordered = chosen
        else:
            ordered = ordered[:data.limit]
        items = tuple(RankedItem(c.material_id, c.kind, ('goal_match',) if matches(c) and data.mode != 'popular' else (),
                                 'relevance' if matches(c) and data.mode != 'popular' else 'fallback',
                                 c.role if data.mode == 'deep' else None) for c in ordered)
        return RankingResult(items, 'stub-v1', {'mode': data.mode, 'limit': 3 if data.mode == 'deep' else data.limit,
            'comparison': 'popularity,title,id' if data.mode == 'popular' else 'goal,industry,role,duration,title,id',
            'rules_version': data.rules_version})


class StubGenerator:
    async def generate(self, data: GenerationInput) -> GenerationResult:
        items = {}
        for index, item in enumerate(data.ranking):
            explanation = ('Материал относится к выбранной теме.' if 'goal_match' in item.reasons
                           else 'Материал можно изучить для знакомства с темой.')
            items[item.material_id] = GeneratedText(item.kind, explanation, None,
                'Следующий материал продолжает последовательность обучения.' if data.mode == 'deep' and index else None)
        return GenerationResult(items, 'План обучения' if data.mode == 'deep' else None,
                                'Последовательное изучение выбранной темы.' if data.mode == 'deep' else None)


class Ranker(Protocol):
    async def rank(self, data: RankingInput) -> RankingResult: ...


class Generator(Protocol):
    async def generate(self, data: GenerationInput) -> GenerationResult: ...
