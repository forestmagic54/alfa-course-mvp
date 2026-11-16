"""Offline course/article/document recommendation engine, without SQL or events.

Run once per backend worker. All functions are deterministic, read-only and
never calculate discounts or access permissions. The catalog is a prevalidated
local JSONL/CSV export; source_table + source_id is its stable identity.
"""

from __future__ import annotations

import json
import math
from collections import OrderedDict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from threading import RLock

import numpy as np
import pandas as pd
from sklearn.preprocessing import normalize

from .features import TextFeatures
from .material_taxonomy import (
    FEATURE_CODES,
    INDUSTRIES,
    PROFILE_TEXT,
    STAGES,
    TASKS,
    features_for,
    normalize_label,
    unknown_labels,
)
from .text_utils import clean_text, display_text
from .trajectory_paths import pick_curated_path, read_curated_paths

KIND_TABLE = {"course": "Courses", "article": "Articles", "document": "Documents"}
DEPTHS = {"brief", "detailed", "trajectory"}
MODES = {"smart", "baseline", "topic", "popular"}
ROLES = {"intro", "practice", "advanced"}


def _labels(raw: object) -> list[str]:
    if raw is None or (isinstance(raw, float) and math.isnan(raw)):
        return []
    if isinstance(raw, (list, tuple, set)):
        return [normalize_label(x) for x in raw if clean_text(x)]
    if isinstance(raw, str):
        v = raw.strip()
        if not v:
            return []
        if v.startswith("["):
            a = json.loads(v)
            if not isinstance(a, list):
                raise ValueError("Label JSON must be a list")
            return _labels(a)
        return [normalize_label(x) for x in v.split("|") if clean_text(x)]
    raise ValueError(
        f"Label fields require JSON lists or pipe separated text, got {type(raw).__name__}"
    )


def _bool(v: object, name: str) -> bool:
    if isinstance(v, (bool, np.bool_)):
        return bool(v)
    if isinstance(v, str) and v.lower().strip() in ("true", "false", "1", "0"):
        return v.lower().strip() in ("true", "1")
    if isinstance(v, (int, np.integer)) and v in (0, 1):
        return bool(v)
    raise ValueError(f"{name} must be a boolean, not {v!r}")


def _optional_float(value: object) -> float | None:
    if value is None or value == "":
        return None
    try:
        f = float(value)
        return f if math.isfinite(f) else None
    except (ValueError, TypeError):
        return None


def _slug(kind: str, ident: str) -> str:
    return f"{kind}:{ident}"


def _parse_hist(values: object) -> tuple[set[str], set[str], set[str]]:
    """Only explicit backend-supplied history; no inferred clicks/paid access."""
    seen, completed, started = set(), set(), set()
    if values is None:
        return seen, completed, started
    if not isinstance(values, (list, tuple)):
        raise ValueError("history must be a list")
    for entry in values:
        if not isinstance(entry, Mapping):
            raise ValueError("history items must be objects")
        kind, ident = entry.get("kind"), entry.get("source_id")
        if kind not in KIND_TABLE or not isinstance(ident, str) or not ident.strip():
            raise ValueError("history item requires known kind and source_id")
        key = _slug(kind, ident)
        seen.add(key)
        if entry.get("completed") is True:
            completed.add(key)
        if entry.get("started") is True and entry.get("completed") is not True:
            started.add(key)
    return seen, completed, started


def load_materials(path: str | Path) -> list[dict]:
    """Read local canonical materials.jsonl or .csv; no network or PostgreSQL."""
    p = Path(path)
    if p.is_dir():
        choices = [p / "materials.jsonl", p / "materials.csv"]
        p = next((q for q in choices if q.exists()), choices[0])
    if p.suffix.lower() == ".jsonl":
        data = [
            json.loads(line)
            for line in p.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    elif p.suffix.lower() == ".csv":
        data = pd.read_csv(p, keep_default_na=False).to_dict("records")
    else:
        raise ValueError("Use materials.jsonl or materials.csv")
    return data


@dataclass(frozen=True)
class RankingConfig:
    task: float = 0.38
    stage: float = 0.11
    industry: float = 0.08
    text: float = 0.27
    format: float = 0.10
    history: float = 0.03
    popularity: float = 0.03
    mmr_lambda: float = 0.68

    def __post_init__(self):
        values = (
            self.task,
            self.stage,
            self.industry,
            self.text,
            self.format,
            self.history,
            self.popularity,
        )
        if any((not math.isfinite(v) or v < 0) for v in values) or sum(values) == 0:
            raise ValueError("Invalid ranking weights")
        if not 0 <= self.mmr_lambda <= 1:
            raise ValueError("mmr_lambda must be in [0,1]")


class MaterialRecommender:
    def __init__(
        self,
        materials: Sequence[Mapping],
        config: RankingConfig | None = None,
        *,
        trajectory_paths=None,
        enable_draft_trajectories: bool = False,
    ):
        self.config = config or RankingConfig()
        self._score_cache = OrderedDict()
        self._cache_lock = RLock()
        self._cold_scores = None
        self._score_cache_limit = 128
        if not isinstance(enable_draft_trajectories, bool):
            raise ValueError("enable_draft_trajectories must be a bool")
        self.trajectory_paths = list(trajectory_paths or [])
        self.enable_draft_trajectories = enable_draft_trajectories
        rows = []
        unique = set()
        for raw in materials:
            if not isinstance(raw, Mapping):
                raise ValueError("materials must contain mappings")
            kind = raw.get("kind")
            if kind not in KIND_TABLE:
                raise ValueError(f"Unknown material type {kind!r}")
            ident = str(raw.get("source_id", "")).strip()
            if not ident or ident.lower() in ("none", "nan", "<na>"):
                raise ValueError("source_id required")
            if raw.get("source_table", KIND_TABLE[kind]) != KIND_TABLE[kind]:
                raise ValueError("source_table and kind disagree")
            key = _slug(kind, ident)
            if key in unique:
                raise ValueError(f"Duplicate material {key}")
            unique.add(key)
            allowed = _bool(raw.get("is_recommendable", False), "is_recommendable")
            topics, tags, industries = (
                _labels(raw.get(k)) for k in ("topics", "tags", "industries")
            )
            explicit = _labels(raw.get("feature_codes"))
            vector = features_for(
                topics=topics,
                tags=tags,
                industries=industries,
                kind=kind,
                explicit=explicit,
            )
            raw_title = raw.get("title")
            title = display_text(raw_title)
            if title.lower() in ("", "nan", "none", "<na>"):
                raise ValueError(f"Title missing for {key}")
            role = raw.get("learning_role") or None
            if role is not None and role not in ROLES:
                raise ValueError(f"Invalid learning role {role}")
            access = str(raw.get("access_type", "unknown"))
            if access not in ("free", "paid", "unknown"):
                raise ValueError("Invalid access_type")
            popularity = _optional_float(raw.get("popularity")) or 0.0
            if popularity < 0:
                raise ValueError("Negative popularity")
            description = clean_text(raw.get("description", ""))[:4500]
            public_desc = display_text(raw.get("public_description", ""))[:1500]
            duration = _optional_float(raw.get("duration_minutes"))
            if duration is not None and duration <= 0:
                duration = None
            rows.append(
                dict(
                    key=key,
                    kind=kind,
                    source_table=KIND_TABLE[kind],
                    source_id=ident,
                    material_id=str(raw.get("material_id", "")).strip() or None,
                    title=title,
                    description=description,
                    public_description=public_desc,
                    topics=topics,
                    tags=tags,
                    industries=industries,
                    vector=vector,
                    learning_role=role,
                    annotation_reviewed_by=str(
                        raw.get("annotation_reviewed_by") or ""
                    ).strip(),
                    access_type=access,
                    availability=allowed,
                    popularity=popularity,
                    duration_minutes=duration,
                    published_at=raw.get("published_at") or None,
                    source_version=raw.get("source_version"),
                    feature_codes=[
                        code for code, flag in zip(FEATURE_CODES, vector, strict=False) if flag
                    ],
                )
            )
        if not rows:
            raise ValueError("Material catalog is empty")
        first_date = materials[0].get("catalog_as_of") if materials else None
        self.catalog_as_of = (
            pd.to_datetime(first_date, utc=True, errors="coerce")
            if first_date
            else pd.Timestamp.now(tz="UTC")
        )
        if pd.isna(self.catalog_as_of):
            raise ValueError("Invalid catalog_as_of")
        self.rows = sorted(rows, key=lambda r: r["key"])
        self.keys = [r["key"] for r in self.rows]
        self.positions = {k: i for i, k in enumerate(self.keys)}
        self.matrix = np.asarray([r["vector"] for r in self.rows], dtype=float)
        self.texts = [
            clean_text(
                " ".join(
                    [
                        r["title"],
                        r["title"],
                        r["description"],
                        " ".join(r["topics"]),
                        " ".join(r["tags"]),
                        " ".join(r["industries"]),
                    ]
                )
            )[:7500]
            for r in self.rows
        ]
        self.text = TextFeatures().fit(self.texts)
        self._task_query_scores = {
            task: self.text.query_scores(PROFILE_TEXT[task]) for task in TASKS
        }
        # Pairwise similarities are reused by MMR on every recommendation.
        # Materializing a small/medium catalogue avoids thousands of sparse
        # matrix multiplications per request. Fall back to sparse for large N.
        self.pair_similarity = (
            (self.text.matrix @ self.text.matrix.T).toarray().astype("float32")
            if len(self.rows) <= 5000
            else None
        )
        counts = np.log1p([r["popularity"] for r in self.rows])
        self.popularity = np.asarray(counts, dtype=float)
        mx = float(self.popularity.max())
        if mx > 0:
            self.popularity /= mx
        self.quality_report = {
            "total": len(self.rows),
            "recommendable": sum(r["availability"] for r in self.rows),
            "by_type": {k: sum(r["kind"] == k for r in self.rows) for k in KIND_TABLE},
            "unmapped_taxonomy_labels": unknown_labels(self.rows),
        }

    @classmethod
    def from_path(
        cls,
        path: str | Path,
        config: RankingConfig | None = None,
        *,
        trajectory_paths_path: str | Path | None = None,
        enable_draft_trajectories: bool = False,
    ) -> MaterialRecommender:
        paths = (
            read_curated_paths(trajectory_paths_path)
            if trajectory_paths_path is not None
            else []
        )
        return cls(
            load_materials(path),
            config,
            trajectory_paths=paths,
            enable_draft_trajectories=enable_draft_trajectories,
        )

    def _validate_request(
        self, request: Mapping
    ) -> tuple[bool, str, str | None, str | None, str | None, str | None]:
        completed = request.get("onboarding_completed")
        if not isinstance(completed, bool):
            raise ValueError("onboarding_completed must be true or false")
        mode = request.get("mode", "smart")
        if mode not in MODES:
            raise ValueError("Invalid mode")
        stage = request.get("stage")
        task = request.get("task")
        industry = request.get("industry")
        depth = request.get("depth")
        if completed:
            if stage not in STAGES or task not in TASKS or depth not in DEPTHS:
                raise ValueError(
                    "Completed onboarding requires valid stage, task and depth"
                )
            if industry is not None and industry not in INDUSTRIES:
                raise ValueError("Invalid industry")
        elif any(x is not None for x in (stage, task, industry, depth)):
            raise ValueError(
                "Skipped onboarding must not contain partial profile answers"
            )
        return completed, mode, stage, task, industry, depth

    def _candidate_indices(
        self, exclude: set[str], eligible: set[str] | None
    ) -> list[int]:
        return [
            i
            for i, r in enumerate(self.rows)
            if r["availability"]
            and r["key"] not in exclude
            and (eligible is None or r["key"] in eligible)
        ]

    def _scores(self, **kwargs) -> np.ndarray:
        # Cache only anonymous profile scores. Eligibility/history are always applied anew.
        if kwargs["history"]:
            return self._compute_scores(**kwargs)
        key = (self.config,) + tuple(
            kwargs[k] for k in ("completed", "stage", "task", "industry", "depth")
        )
        with self._cache_lock:
            cached = self._score_cache.get(key)
            if cached is not None:
                self._score_cache.move_to_end(key)
                return cached.copy()
        scores = self._compute_scores(**kwargs)
        with self._cache_lock:
            self._score_cache[key] = scores.copy()
            if len(self._score_cache) > self._score_cache_limit:
                self._score_cache.popitem(last=False)
        return scores

    def _compute_scores(
        self,
        *,
        completed: bool,
        stage: str | None,
        task: str | None,
        industry: str | None,
        depth: str | None,
        history: set[str],
    ) -> np.ndarray:
        n = len(self.rows)
        if not completed:
            return self.popularity.copy()
        index = {k: i for i, k in enumerate(FEATURE_CODES)}
        task_scores = self.matrix[:, index[task]]
        stage_scores = self.matrix[:, index[stage]]
        industry_scores = self.matrix[:, index[industry]] if industry else np.zeros(n)
        query = " ".join(PROFILE_TEXT.get(x, "") for x in (task, stage, industry) if x)
        text_scores = self.text.query_scores(query) if query else np.zeros(n)
        format_scores = np.array([self._format_score(r, depth) for r in self.rows])
        history_idx = [self.positions[k] for k in history if k in self.positions]
        history_scores = np.zeros(n)
        if history_idx and self.text.matrix.shape[1]:
            from scipy import sparse

            v = normalize(sparse.csr_matrix(self.text.matrix[history_idx].mean(axis=0)))
            history_scores = (self.text.matrix @ v.T).toarray().ravel().clip(0, 1)
        c = self.config
        weights = {
            "task": c.task,
            "stage": c.stage,
            "industry": c.industry if industry else 0,
            "text": c.text,
            "format": c.format,
            "history": c.history if history_idx else 0,
            "popularity": c.popularity,
        }
        values = {
            "task": task_scores,
            "stage": stage_scores,
            "industry": industry_scores,
            "text": text_scores,
            "format": format_scores,
            "history": history_scores,
            "popularity": self.popularity,
        }
        denominator = sum(weights.values())
        return sum(values[k] * (weights[k] / denominator) for k in weights)

    @staticmethod
    def _format_score(row: dict, depth: str | None) -> float:
        length = row["duration_minutes"]
        if depth == "brief":
            if row["kind"] == "document" and length is None:
                return 0.50
            return (
                1.0
                if length is not None and length <= 15
                else 0.15
                if length is not None
                else 0.50
            )
        if depth == "detailed":
            if row["kind"] == "document" and length is None:
                return 0.50
            if row["kind"] == "course":
                return (
                    1.0
                    if length is not None and length >= 15
                    else 0.50
                    if length is None
                    else 0.30
                )
            return 0.70 if length is not None and length >= 15 else 0.35
        return 0.5

    def _diverse_top(
        self, candidates: list[int], scores: np.ndarray, limit: int
    ) -> list[int]:
        if not candidates or not limit:
            return []
        # Vectorized exact greedy MMR: stable catalog order resolves score ties.
        pool = np.array(sorted(candidates), dtype=int)
        chosen = []
        redundancy = np.zeros(len(pool))
        for _ in range(min(limit, len(pool))):
            adjusted = (
                scores[pool].copy()
                if not chosen
                else self.config.mmr_lambda * scores[pool]
                - (1 - self.config.mmr_lambda) * redundancy
            )
            adjusted[np.isin(pool, chosen)] = -np.inf
            pick = int(pool[int(np.argmax(adjusted))])
            chosen.append(pick)
            lexical = (
                self.pair_similarity[pool, pick]
                if self.pair_similarity is not None
                else (self.text.matrix[pool] @ self.text.matrix[pick].T)
                .toarray()
                .ravel()
            )
            # Preserve max lexical and max same-kind independently, as in v5.2.
            if len(chosen) == 1:
                max_lexical = lexical.copy()
                same_kind = np.zeros(len(pool))
            else:
                max_lexical = np.maximum(max_lexical, lexical)
            same_kind = np.maximum(
                same_kind,
                [self.rows[i]["kind"] == self.rows[pick]["kind"] for i in pool],
            )
            redundancy = 0.82 * max_lexical + 0.18 * same_kind
        return chosen

    def _item(
        self,
        i: int,
        score: float,
        matched: list[str],
        role: str | None = None,
        step: int | None = None,
    ) -> dict:
        r = self.rows[i]
        return {
            "kind": r["kind"],
            "source_table": r["source_table"],
            "source_id": r["source_id"],
            "material_id": r["material_id"],
            "title": r["title"],
            "score": round(float(max(0, score)), 6),
            "matched_features": matched,
            "step": step,
            "step_role": role,
            "reason_code": "matched_profile" if matched else "general_selection",
            "public_description": r["public_description"],
            "source_version": r["source_version"],
        }

    def _cold_start(
        self, candidates: list[int], limit: int
    ) -> tuple[list[int], np.ndarray]:
        """Broad, deterministic discovery when no profile is available.

        Articles/documents have no measured user popularity in the source dump.
        Treating missing interactions as zero would show ONLY popular courses.
        Instead, deliberately include catalog types and prefer published, well
        described materials. This is editorial exploration, NOT personalization.
        """
        if not candidates or limit <= 0:
            return [], np.zeros(len(self.rows))
        now = self.catalog_as_of.to_pydatetime()

        def base(i):
            r = self.rows[i]
            metadata = min(1.0, (len(r["topics"]) + len(r["tags"])) / 3)
            if r["kind"] == "course":
                return 0.35 + 0.55 * float(self.popularity[i]) + 0.10 * metadata
            if r["kind"] == "article":
                freshness = 0.0
                try:
                    pub = pd.to_datetime(r["published_at"], utc=True, errors="coerce")
                    if pd.notna(pub):
                        age_days = max(
                            0.0, (now - pub.to_pydatetime()).total_seconds() / 86400
                        )
                        freshness = max(0.0, 1.0 - age_days / 730.0)
                except (TypeError, ValueError):
                    pass
                return (
                    0.30
                    + 0.42 * freshness
                    + 0.18 * metadata
                    + 0.10 * bool(r["public_description"])
                )
            # Document publish time is unknown: do not infer freshness.
            return 0.33 + 0.19 * metadata + 0.13 * bool(r["public_description"])

        if self._cold_scores is None:
            self._cold_scores = np.array([base(i) for i in range(len(self.rows))])
        scores = self._cold_scores
        chosen = []
        # Ensure an exploratory mix when all three types exist, before ranking
        # the remaining places. No fabricated popularity for articles/documents.
        for kind in ("course", "article", "document"):
            if len(chosen) >= limit:
                break
            options = [
                i
                for i in candidates
                if self.rows[i]["kind"] == kind and i not in chosen
            ]
            if options:
                selected = self._diverse_top(options, scores, 1)[0]
                chosen.append(selected)
        rest = [i for i in candidates if i not in chosen]
        # MMR within the remaining positions, aware of already selected items.
        while rest and len(chosen) < limit:

            def adjusted(i):
                text_similarity = (
                    (
                        float(self.pair_similarity[i, chosen].max())
                        if self.pair_similarity is not None
                        else float(
                            (self.text.matrix[i] @ self.text.matrix[chosen].T).max()
                        )
                    )
                    if chosen and self.text.matrix.shape[1]
                    else 0.0
                )
                same_kind = sum(
                    self.rows[i]["kind"] == self.rows[j]["kind"] for j in chosen
                )
                return scores[i] - 0.18 * text_similarity - 0.10 * same_kind

            selected = min(rest, key=lambda i: (-adjusted(i), self.keys[i]))
            chosen.append(selected)
            rest.remove(selected)
        return chosen, scores

    def recommend(self, request: Mapping, limit: int = 5) -> dict:
        if not isinstance(request, Mapping):
            raise TypeError("request must be an object")
        if (
            isinstance(limit, bool)
            or not isinstance(limit, int)
            or not 0 <= limit <= 50
        ):
            raise ValueError("Invalid limit")
        completed, mode, stage, task, industry, depth = self._validate_request(request)
        seen, completed_items, started = _parse_hist(request.get("history"))
        excluded = set(seen)
        explicit_exclusions = set(map(str, request.get("exclude_material_keys", [])))
        excluded.update(explicit_exclusions)
        eligible_raw = request.get("eligible_material_keys")
        eligible = None if eligible_raw is None else set(map(str, eligible_raw))
        candidates = self._candidate_indices(excluded, eligible)
        # Historical completions remain visible as progress within a saved
        # learning path. Explicit user/backend exclusions still block it.
        route_candidates = self._candidate_indices(explicit_exclusions, eligible)
        scores = (
            self._scores(
                completed=completed,
                stage=stage,
                task=task,
                industry=industry,
                depth=depth,
                history=seen,
            )
            if mode == "smart"
            else self.popularity.copy()
        )
        if mode in ("baseline", "topic"):
            scores = (
                self._topic_scores(task, stage, industry)
                if completed
                else self.popularity.copy()
            )
        elif mode == "popular":
            scores = self.popularity.copy()
        if not completed and mode == "smart":
            picks, cold_scores = self._cold_start(candidates, limit)
            return {
                "scenario": "catalog_exploration",
                "items": [self._item(i, cold_scores[i], []) for i in picks],
                "discount_course_candidate": None,
                "model_version": "offline-materials-0.8-v5.4",
            }
        if completed and depth == "trajectory" and mode == "smart" and limit >= 3:
            curated = pick_curated_path(
                self.trajectory_paths,
                task=task,
                stage=stage,
                industry=industry,
                candidate_indices=route_candidates,
                positions=self.positions,
                rows=self.rows,
                scores=scores,
                pair_similarity=self.pair_similarity,
                text_matrix=self.text.matrix,
                include_drafts=self.enable_draft_trajectories,
                completed_keys=completed_items,
            )
            if curated:
                path, idx, relations = curated
                route = [
                    self._item(
                        i,
                        scores[i],
                        [
                            key
                            for key in (stage, task, industry)
                            if key and key in self.rows[i]["feature_codes"]
                        ],
                        role=role,
                        step=step,
                    )
                    for step, (role, i) in enumerate(
                        zip(("intro", "practice", "advanced"), idx, strict=False), 1
                    )
                ]
                for item in route:
                    key = f"{item['kind']}:{item['source_id']}"
                    item["progress_state"] = (
                        "completed"
                        if key in completed_items
                        else "in_progress"
                        if key in started
                        else "not_started"
                    )
                next_step = next(
                    (
                        item["step"]
                        for item in route
                        if item["progress_state"] != "completed"
                    ),
                    None,
                )
                return {
                    "scenario": "trajectory"
                    if path.status == "approved"
                    else "trajectory_draft",
                    "items": route,
                    "next_step": next_step,
                    "completed_steps": sum(
                        item["progress_state"] == "completed" for item in route
                    ),
                    "trajectory_id": path.path_id,
                    "trajectory_review_status": path.status,
                    "publishable": path.status == "approved",
                    "pairwise_content_similarity": [round(x, 4) for x in relations],
                    "warning": None
                    if path.status == "approved"
                    else "Редактор должен подтвердить учебную последовательность перед публикацией",
                    "discount_course_candidate": self._discount_candidate(
                        candidates, scores, completed, task
                    ),
                    "model_version": "offline-materials-0.8-v5.4",
                }
            # The existing fully annotated slot method remains compatible, but
            # is never used to fabricate a path from unannotated real materials.
            route = self._trajectory(candidates, scores, task, stage, industry)
            if route:
                return {
                    "scenario": "trajectory",
                    "items": route,
                    "trajectory_review_status": "catalog_annotations",
                    "discount_course_candidate": self._discount_candidate(
                        candidates, scores, completed, task
                    ),
                    "model_version": "offline-materials-0.8-v5.4",
                }
        picks = (
            sorted(candidates, key=lambda i: (-scores[i], self.keys[i]))[:limit]
            if mode in ("baseline", "topic", "popular")
            else self._diverse_top(candidates, scores, limit)
        )
        result = []
        for i in picks:
            r = self.rows[i]
            matched = (
                [
                    key
                    for key in (stage, task, industry)
                    if key and key in r["feature_codes"]
                ]
                if completed
                else []
            )
            result.append(self._item(i, scores[i], matched))
        scenario = (
            ("popular" if not completed else "feed")
            if mode == "smart"
            else (
                "topic_baseline"
                if mode in ("baseline", "topic")
                else "popular_baseline"
            )
        )
        if completed and depth == "trajectory" and mode == "smart":
            scenario = "feed_fallback"
        return {
            "scenario": scenario,
            "items": result,
            "discount_course_candidate": self._discount_candidate(
                candidates, scores, completed, task
            )
            if mode == "smart"
            else None,
            "model_version": "offline-materials-0.8-v5.4",
        }

    def _topic_scores(self, task, stage, industry):
        if not task:
            return self.popularity.copy()
        idx = {k: i for i, k in enumerate(FEATURE_CODES)}
        return self.matrix[:, idx[task]] + (
            0.1 * self.matrix[:, idx[industry]] if industry else 0
        )

    def _trajectory(
        self,
        candidates: list[int],
        scores: np.ndarray,
        task: str,
        stage: str,
        industry: str | None,
    ) -> list[dict]:
        slots = [
            ("intro", "free", None),
            ("practice", "free", None),
            ("advanced", "paid", "course"),
        ]
        picked = []
        goal_text = PROFILE_TEXT.get(task, "")
        goal_similarity = (
            self.text.query_scores(goal_text) if goal_text else np.zeros(len(self.rows))
        )
        task_col = FEATURE_CODES.index(task)
        for role, access, kind in slots:
            eligible = [
                i
                for i in candidates
                if i not in picked
                and self.rows[i]["learning_role"] == role
                and bool(self.rows[i]["annotation_reviewed_by"])
                and self.rows[i]["access_type"] == access
                and (kind is None or self.rows[i]["kind"] == kind)
                and
                # Do not stitch together unrelated steps merely to fill slots.
                (self.matrix[i, task_col] > 0 or goal_similarity[i] >= 0.06)
            ]
            if not eligible:
                return []

            def route_score(i):
                relation = 0.0
                if picked and self.text.matrix.shape[1]:
                    relation = (
                        float(self.pair_similarity[i, picked[-1]])
                        if self.pair_similarity is not None
                        else float(
                            (
                                self.text.matrix[i] @ self.text.matrix[picked[-1]].T
                            ).toarray()[0, 0]
                        )
                    )
                # Industry is a soft boost; fall back to broad topical relevance.
                return float(scores[i]) + 0.12 * relation

            if picked:
                eligible = [
                    i
                    for i in eligible
                    if (
                        float(self.pair_similarity[i, picked[-1]])
                        if self.pair_similarity is not None
                        else float(
                            (
                                self.text.matrix[i] @ self.text.matrix[picked[-1]].T
                            ).toarray()[0, 0]
                        )
                    )
                    >= 0.015
                ]
                if not eligible:
                    return []
            best = min(eligible, key=lambda i: (-route_score(i), self.keys[i]))
            picked.append(best)
        return [
            self._item(
                i,
                scores[i],
                [
                    key
                    for key in (stage, task, industry)
                    if key and key in self.rows[i]["feature_codes"]
                ],
                role=slot[0],
                step=pos + 1,
            )
            for pos, (i, slot) in enumerate(zip(picked, slots, strict=False))
        ]

    def _discount_candidate(
        self,
        candidates: list[int],
        scores: np.ndarray,
        completed: bool,
        task: str | None = None,
    ) -> dict | None:
        if not completed:
            return None
        paid = [
            i
            for i in candidates
            if self.rows[i]["kind"] == "course"
            and self.rows[i]["access_type"] == "paid"
            and scores[i] > 0.1
        ]
        if task:
            semantic = self._task_query_scores[task]
            paid = [
                i
                for i in paid
                if self.matrix[i, FEATURE_CODES.index(task)] or semantic[i] >= 0.06
            ]
        if not paid:
            return None
        best = min(paid, key=lambda i: (-scores[i], self.keys[i]))
        r = self.rows[best]
        # Eligibility, amounts, redemption and prices are checked by backend.
        return {
            "kind": "course",
            "source_id": r["source_id"],
            "material_id": r["material_id"],
            "score": round(float(scores[best]), 6),
            "eligibility": "backend_must_verify",
        }


_default_material_model: MaterialRecommender | None = None


def initialize_materials(
    path: str | Path,
    config: RankingConfig | None = None,
    *,
    trajectory_paths_path: str | Path | None = None,
    enable_draft_trajectories: bool = False,
) -> MaterialRecommender:
    global _default_material_model
    model = MaterialRecommender.from_path(
        path,
        config,
        trajectory_paths_path=trajectory_paths_path,
        enable_draft_trajectories=enable_draft_trajectories,
    )

    _default_material_model = model
    return model


def recommend_materials(request: Mapping, limit: int = 5) -> dict:
    if _default_material_model is None:
        raise RuntimeError("Call initialize_materials(path) first")
    return _default_material_model.recommend(request, limit)
