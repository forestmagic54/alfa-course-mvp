"""Product v5.5 two-stage content ranking, limited by the current backend contract.

Pure offline ML. No HTTP routes, PostgreSQL, telemetry, discount calculation or
claims that unverified documents are free. Can be compared with the v5.4 engine.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from functools import lru_cache

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.preprocessing import normalize

from .material_taxonomy import FEATURE_CODES, INDUSTRIES, PROFILE_TEXT, STAGES, TASKS
from .materials import MaterialRecommender
from .text_utils import clean_text

# Product design: 0.45 task, 0.25 text, 0.20 stage, 0.10 industry.
# These are policy priors, NOT guaranteed task dominance or validated accuracy.
PRODUCT_WEIGHTS = {"task": 0.45, "text": 0.25, "stage": 0.20, "industry": 0.10}
PRODUCT_EXCLUDED_IDS = {"4a6deac5-46e2-4d47-9388-73df6874bc6e"}


@dataclass(frozen=True)
class ProductPolicy:
    candidate_k: int = 50
    mmr_lambda: float = 0.75
    duration_weight: float = 0.25
    max_feed_items: int = 5


class ProductAlignedRecommender(MaterialRecommender):
    """Preserve the old methods/API; apply product 2-stage ranking to feed.

    Trajectories are still selected by the v5.4 curated-plan workflow:
    only editorially approved paths can be published. The proposed *automatic*
    paths are audit suggestions, not factual educational prerequisites.
    """

    def __init__(
        self,
        materials,
        config=None,
        *,
        trajectory_paths=None,
        enable_draft_trajectories=False,
        product_policy=None,
    ):
        # Exclude promo/synthetic course from all recommendations and denominators
        clean = [
            r for r in materials if str(r.get("source_id")) not in PRODUCT_EXCLUDED_IDS
        ]
        super().__init__(
            clean,
            config,
            trajectory_paths=trajectory_paths,
            enable_draft_trajectories=enable_draft_trajectories,
        )
        self.product_policy = product_policy or ProductPolicy()
        self._feature_idx = {name: idx for idx, name in enumerate(FEATURE_CODES)}
        self._vector_groups = {}
        # Producer-approved heuristic: source label 'без опыта' denotes idea;
        # 'с опытом' is ambiguous between active and scale, so mark both.
        # These labels are weak metadata, never a certified difficulty level.
        self.product_matrix = self.matrix.copy()
        for i, row in enumerate(self.rows):
            tags = set(row["industries"])
            if "без опыта" in tags:
                self.product_matrix[i, self._feature_idx["stage_idea"]] = 1
            if "с опытом" in tags:
                self.product_matrix[i, self._feature_idx["stage_active"]] = 1
                self.product_matrix[i, self._feature_idx["stage_scale"]] = 1
        for group, codes in [
            ("task", TASKS),
            ("stage", STAGES),
            ("industry", INDUSTRIES),
        ]:
            self._vector_groups[group] = normalize(
                self.product_matrix[:, [self._feature_idx[c] for c in codes]], norm="l2"
            )
        # Product text corpus: only canonical title, topics and tags. Retain the
        # fuller legacy index for old explainability / curated path checks.
        corpus = [
            clean_text(
                " ".join([r["title"], " ".join(r["topics"]), " ".join(r["tags"])])
            )
            for r in self.rows
        ]
        self.product_tfidf = TfidfVectorizer(
            ngram_range=(1, 2), min_df=2, sublinear_tf=True, max_features=60000
        )
        try:
            self.product_text = self.product_tfidf.fit_transform(corpus)
        except ValueError:  # small fixture with no shared vocabulary
            self.product_tfidf.set_params(min_df=1)
            self.product_text = self.product_tfidf.fit_transform(corpus)
        self.product_text = normalize(self.product_text)
        self.product_similarity = (
            (self.product_text @ self.product_text.T).toarray().astype("float32")
        )
        # Only indexed items are eligible. No IDs other than actual source UUIDs.
        self.quality_report["product_policy_indexed"] = sum(
            r["availability"] for r in self.rows
        )
        self._profile_scores = lru_cache(maxsize=4096)(self._compute_profile_scores)

    @classmethod
    def from_path(
        cls,
        path,
        config=None,
        *,
        trajectory_paths_path=None,
        enable_draft_trajectories=False,
        product_policy=None,
    ):
        from .materials import load_materials
        from .trajectory_paths import read_curated_paths

        routes = (
            read_curated_paths(trajectory_paths_path) if trajectory_paths_path else []
        )
        return cls(
            load_materials(path),
            config,
            trajectory_paths=routes,
            enable_draft_trajectories=enable_draft_trajectories,
            product_policy=product_policy,
        )

    def _compute_profile_scores(self, stage, task, industry):
        """Scores for exact user state, reused across identical requests."""
        n = len(self.rows)
        parts = {}
        if task is not None:
            ui = np.zeros(len(TASKS))
            ui[TASKS.index(task)] = 1.0
            parts["task"] = (self._vector_groups["task"] @ ui).ravel()
        if stage is not None:
            ui = np.zeros(len(STAGES))
            ui[STAGES.index(stage)] = 1.0
            parts["stage"] = (self._vector_groups["stage"] @ ui).ravel()
        if industry is not None:
            ui = np.zeros(len(INDUSTRIES))
            ui[INDUSTRIES.index(industry)] = 1.0
            parts["industry"] = (self._vector_groups["industry"] @ ui).ravel()
        query = " ".join(PROFILE_TEXT[k] for k in (task, stage, industry) if k)
        parts["text"] = (
            (self.product_text @ self.product_tfidf.transform([clean_text(query)]).T)
            .toarray()
            .ravel()
            .clip(0.0, 1.0)
            if query
            else np.zeros(n)
        )
        denom = sum(PRODUCT_WEIGHTS[k] for k in parts)
        # Explicit renormalization when industry isn't provided.
        score = sum(parts[k] * PRODUCT_WEIGHTS[k] / denom for k in parts)
        return np.clip(np.asarray(score, dtype=float), 0.0, 1.0)

    def score_titles(
        self, titles: list[str], task: str, stage: str | None
    ) -> list[float]:
        query = clean_text(
            " ".join(PROFILE_TEXT[code] for code in (task, stage) if code)
        )
        vectors = self.product_tfidf.transform([clean_text(title) for title in titles])
        similarities = vectors @ self.product_tfidf.transform([query]).T
        return similarities.toarray().ravel().clip(0.0, 1.0).tolist()

    def _duration_factor(self, index, depth):
        # Unknown duration is NOT imputed as factual; neutral multiplier.
        duration = self.rows[index]["duration_minutes"]
        if duration is None or depth == "trajectory":
            return 1.0
        mu, sigma = (10.0, 20.0) if depth == "brief" else (180.0, 90.0)
        kernel = math.exp(-((duration - mu) ** 2) / (2 * sigma**2))
        return 1.0 - self.product_policy.duration_weight * (1.0 - kernel)

    def _relevance(self, stage, task, industry, depth):
        base = self._profile_scores(stage, task, industry).copy()
        # duration is a reranking factor, not a replacement for relevance
        return np.array(
            [base[i] * self._duration_factor(i, depth) for i in range(len(self.rows))]
        )

    def _retrieval(self, eligible_indices, scores):
        # Important: apply backend visibility filter BEFORE top-50 retrieval.
        # Otherwise unsynced/hidden materials can crowd out legitimate results.
        return sorted(eligible_indices, key=lambda i: (-scores[i], self.keys[i]))[
            : self.product_policy.candidate_k
        ]

    def _mmr(self, indices, scores, desired, already=()):
        chosen = list(already)
        remaining = set(indices) - set(chosen)
        while remaining and len(chosen) - len(already) < desired:

            def rating(i):
                if not chosen:
                    redundancy = 0.0
                else:
                    redundancy = float(self.product_similarity[i, chosen].max())
                return (
                    self.product_policy.mmr_lambda * float(scores[i])
                    - (1 - self.product_policy.mmr_lambda) * redundancy
                )

            selected = min(remaining, key=lambda i: (-rating(i), self.keys[i]))
            chosen.append(selected)
            remaining.remove(selected)
        return chosen[len(already) :]

    def _calibrated(self, pool, scores, limit, depth, task):
        """Soft material-type calibration for max FIVE backend feed cards.

        Only force formats where topically supported, never pad with unrelated
        courses to reach a product quota. Backfill from globally ranked pool.
        """
        if not pool or limit <= 0:
            return []
        relevant = [
            i
            for i in pool
            if self.product_matrix[i, self._feature_idx[task]] > 0
            or self._profile_scores(None, task, None)[i] > 0.06
        ]
        course_pool = [i for i in relevant if self.rows[i]["kind"] == "course"]
        other_pool = [i for i in relevant if self.rows[i]["kind"] != "course"]
        if depth == "brief":
            course_pool = [
                i
                for i in course_pool
                if self.rows[i]["duration_minutes"] is None
                or self.rows[i]["duration_minutes"] <= 120
            ]
            course_target = min(2, max(0, limit - 2))
        else:
            # Preserve the product's approximately 1:1
            # split without forcing unrelated courses into a small feed.
            course_target = min(2, max(0, limit - 2))
        course_pick = self._mmr(
            course_pool, scores, min(course_target, len(course_pool))
        )
        other_pick = self._mmr(
            other_pool,
            scores,
            min(limit - len(course_pick), len(other_pool)),
            already=course_pick,
        )
        chosen = course_pick + other_pick
        if len(chosen) < limit:
            chosen += self._mmr(
                [i for i in pool if i not in chosen],
                scores,
                limit - len(chosen),
                already=chosen,
            )
        # MMR decides membership; product tie policy controls display order.
        return sorted(
            chosen[:limit],
            key=lambda i: (-float(scores[i]), -float(self.popularity[i]), self.keys[i]),
        )

    def _popular(self, pool, limit):
        """Stable anonymous discovery. No fake views for non-course materials."""
        if not pool:
            return []
        # Prefer a useful mix of kinds when available rather than top-5 courses.
        return self._cold_start(pool, limit)[0]

    def _reviewed_path(self, eligible, scores, task, stage, industry):
        """Accept only editor-reviewed, coherent product-shaped paths.

        Backend roles remain intro / practice / advanced. A free third-course
        or verified-free document is an editorial fallback, not a monetization
        claim. Unapproved paths must never enter the public response.
        """
        eligible = set(eligible)
        found = []
        for path in self.trajectory_paths:
            if path.task != task or (
                path.status != "approved" and not self.enable_draft_trajectories
            ):
                continue
            if path.allowed_stages and stage not in path.allowed_stages:
                continue
            if (
                industry
                and path.allowed_industries
                and industry not in path.allowed_industries
            ):
                continue
            if any(key not in self.positions for key in path.keys):
                continue
            idx = [self.positions[key] for key in path.keys]
            if len(set(idx)) != 3 or any(i not in eligible for i in idx):
                continue
            a, b, c = [self.rows[i] for i in idx]
            if not (
                a["kind"] == "article"
                and a["access_type"] == "free"
                and b["kind"] == "course"
                and b["access_type"] == "free"
            ):
                continue
            if c["kind"] == "course" and c["access_type"] == "paid":
                pass
            elif (
                c["kind"] == "course"
                and c["access_type"] == "free"
                and c["duration_minutes"] is not None
                and b["duration_minutes"] is not None
                and c["duration_minutes"] > b["duration_minutes"]
            ):
                pass
            elif c["kind"] == "document" and c["access_type"] == "free":
                pass
            else:
                continue
            edges = [float(self.product_similarity[idx[k], idx[k + 1]]) for k in (0, 1)]
            if any(e < 0.015 for e in edges):
                continue
            found.append(
                (
                    float(np.mean(scores[idx])) + 0.15 * np.mean(edges),
                    path.path_id,
                    path,
                    idx,
                )
            )
        if not found:
            return None
        _, _, path, indices = min(found, key=lambda row: (-row[0], row[1]))
        return path, indices

    def _draft_product_path(self, eligible, scores, task):
        """Propose (NOT publish) a coherent three-stage chain for human review.

        Joint selection is crucial: picking the highest-scoring item at each
        stage independently produced unrelated pairs on the real catalog.
        """
        relevant = [
            i for i in eligible if self.product_matrix[i, self._feature_idx[task]] > 0
        ]
        article = sorted(
            (
                i
                for i in relevant
                if self.rows[i]["kind"] == "article"
                and self.rows[i]["access_type"] == "free"
            ),
            key=lambda i: (-scores[i], self.keys[i]),
        )[:50]
        basic = [
            i
            for i in relevant
            if self.rows[i]["kind"] == "course"
            and self.rows[i]["access_type"] == "free"
        ]
        advance = [
            i
            for i in relevant
            if self.rows[i]["kind"] == "course"
            and self.rows[i]["access_type"] == "paid"
        ]
        if not article or not basic:
            return None
        feasible = []
        for b in basic:
            final = advance or [
                i
                for i in basic
                if i != b
                and self.rows[i]["duration_minutes"] is not None
                and self.rows[b]["duration_minutes"] is not None
                and self.rows[i]["duration_minutes"] > self.rows[b]["duration_minutes"]
            ]
            for c in final:
                if c == b:
                    continue
                bc = float(self.product_similarity[b, c])
                if bc < 0.10:
                    continue
                for a in article:
                    ab = float(self.product_similarity[a, b])
                    if ab < 0.10:
                        continue
                    quality = float(scores[a] + scores[b] + scores[c]) + 0.5 * (ab + bc)
                    feasible.append(
                        (quality, (self.keys[a], self.keys[b], self.keys[c]), [a, b, c])
                    )
        if not feasible:
            return None
        return min(feasible, key=lambda candidate: (-candidate[0], candidate[1]))[2]

    def recommend(
        self, request: Mapping, limit: int = 5
    ):
        if not isinstance(request, Mapping):
            raise TypeError("request must be an object")
        if (
            not isinstance(limit, int)
            or isinstance(limit, bool)
            or not 0 <= limit <= self.product_policy.max_feed_items
        ):
            raise ValueError(f"Backend feed supports 0..{self.product_policy.max_feed_items} materials")
        completed, mode, stage, task, industry, depth = self._validate_request(request)
        # Only explicit user/backend exclusions affect selection. Global study
        # marks never enter ranking (as mandated by backend OpenAPI).
        excluded = set(map(str, request.get("exclude_material_keys") or ()))
        allowed_raw = request.get("eligible_material_keys")
        allowed = None if allowed_raw is None else set(map(str, allowed_raw))
        eligible = self._candidate_indices(excluded, allowed)
        if not completed or mode == "popular":
            indices = self._popular(eligible, limit)
            return self._response(
                "popular" if mode == "popular" else "catalog_exploration",
                indices,
                self.popularity,
                stage,
                task,
                industry,
                depth,
                eligible_indices=eligible,
            )
        if mode in ("baseline", "topic"):
            matching = [
                i
                for i in eligible
                if self.product_matrix[i, self._feature_idx[task]] > 0
            ]
            indices = sorted(matching, key=lambda i: self.keys[i])[:limit]
            return self._response(
                "topic_baseline",
                indices,
                np.zeros(len(self.rows)),
                stage,
                task,
                industry,
                depth,
                eligible_indices=eligible,
            )
        scores = self._relevance(stage, task, industry, depth)
        candidate = self._retrieval(eligible, scores)
        if not candidate or max((scores[i] for i in candidate), default=0.0) <= 0:
            return self._response(
                "catalog_exploration",
                self._popular(eligible, limit),
                self.popularity,
                None,
                None,
                None,
                None,
                eligible_indices=eligible,
            )
        if depth == "trajectory" and limit >= 3:
            curated = self._reviewed_path(eligible, scores, task, stage, industry)
            if curated is not None:
                path, indices = curated
                items = [
                    self._item(
                        i,
                        scores[i],
                        [
                            x
                            for x in (stage, task, industry)
                            if x and self.product_matrix[i, self._feature_idx[x]] > 0
                        ],
                        ("intro", "practice", "advanced")[k],
                        k + 1,
                    )
                    for k, i in enumerate(indices)
                ]
                return {
                    "scenario": "trajectory"
                    if path.status == "approved"
                    else "trajectory_draft",
                    "items": items,
                    "trajectory_id": path.path_id,
                    "discount_course_candidate": None,
                    "model_version": "offline-materials-0.9-v5.5",
                }
            if self.enable_draft_trajectories:
                auto = self._draft_product_path(eligible, scores, task)
                if auto:
                    items = [
                        self._item(
                            i,
                            scores[i],
                            [
                                x
                                for x in (stage, task, industry)
                                if x
                                and self.product_matrix[i, self._feature_idx[x]] > 0
                            ],
                            ("intro", "practice", "advanced")[k],
                            k + 1,
                        )
                        for k, i in enumerate(auto)
                    ]
                    return {
                        "scenario": "trajectory_draft",
                        "items": items,
                        "trajectory_id": f"auto-draft-{task}",
                        "publishable": False,
                        "discount_course_candidate": None,
                        "model_version": "offline-materials-0.9-v5.5",
                    }
            # If no approved path, use valid topic-ranked items; backend handles
            # roadmap_unavailable or shortened roadmap under its API policy.
            depth = "detailed"
            scenario = "feed_fallback"
        else:
            scenario = "feed"
        picked = self._calibrated(candidate, scores, limit, depth, task)
        return self._response(
            scenario,
            picked,
            scores,
            stage,
            task,
            industry,
            depth,
            eligible_indices=eligible,
        )

    def _response(
        self,
        scenario,
        indices,
        scores,
        stage,
        task,
        industry,
        depth,
        eligible_indices=(),
    ):
        completed = task is not None
        items = []
        for i in indices:
            matched = [
                key
                for key in (stage, task, industry)
                if key and self.product_matrix[i, self._feature_idx[key]] > 0
            ]
            item = self._item(i, float(scores[i]), matched)
            item["duration_minutes"] = self.rows[i]["duration_minutes"]
            item["access_type"] = self.rows[i]["access_type"]
            items.append(item)
        discount = (
            self._discount_candidate(list(eligible_indices), scores, completed, task)
            if scenario not in ("popular", "catalog_exploration", "topic_baseline")
            else None
        )
        return dict(
            scenario=scenario,
            items=items,
            trajectory_id=None,
            discount_course_candidate=discount,
            model_version="offline-materials-0.9-v5.5",
        )
