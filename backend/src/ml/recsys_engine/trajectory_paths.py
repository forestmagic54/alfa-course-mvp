"""Curated three-step paths with explicit draft/approved provenance.

This file only validates and selects from catalog keys. It cannot prove a
material is free, substantiate an educational prerequisite, or award a discount.
Only external human editorial approval can upgrade a draft to 'approved'.
"""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from .material_taxonomy import INDUSTRIES, STAGES, TASKS

EXPECTED_ROLES = ("intro", "practice", "advanced")


@dataclass(frozen=True)
class CuratedPath:
    path_id: str
    task: str
    keys: tuple[str, str, str]
    status: str
    rationale: str
    reviewer: str | None = None
    reviewed_at: str | None = None
    allowed_stages: tuple[str, ...] = ()
    allowed_industries: tuple[str, ...] = ()


def read_curated_paths(path: str | Path) -> list[CuratedPath]:
    """Validate external, non-sensitive editorial data. Fail fast on bad input."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if (
        not isinstance(data, dict)
        or data.get("schema_version") != 1
        or not isinstance(data.get("paths"), list)
    ):
        raise ValueError(
            "Expected trajectory paths JSON object with schema_version=1 and paths=[]"
        )
    result = []
    seen = set()
    for entry in data["paths"]:
        if not isinstance(entry, Mapping):
            raise ValueError("Each path must be an object")
        path_id = entry.get("path_id")
        task = entry.get("task")
        status = entry.get("status")
        if not isinstance(path_id, str) or not path_id.strip() or path_id in seen:
            raise ValueError("Duplicate or empty path_id")
        seen.add(path_id)
        if task not in TASKS:
            raise ValueError(f"Unknown path task {task!r}")
        if status not in ("draft", "approved"):
            raise ValueError(f"Unknown path status {status!r}")
        steps = entry.get("steps")
        if not isinstance(steps, list) or len(steps) != 3:
            raise ValueError(f"{path_id} needs exactly three steps")
        keys = []
        for role, item in zip(EXPECTED_ROLES, steps, strict=False):
            if not isinstance(item, Mapping) or item.get("role") != role:
                raise ValueError(f"{path_id}: expected role {role}")
            key = item.get("material_key")
            if not isinstance(key, str) or not any(
                key.startswith(k + ":") for k in ("course", "article", "document")
            ):
                raise ValueError(f"{path_id}: invalid material_key")
            if not key.split(":", 1)[1].strip():
                raise ValueError(f"{path_id}: empty material ID")
            if (
                not isinstance(item.get("why_this_step"), str)
                or not item["why_this_step"].strip()
            ):
                raise ValueError(
                    f"{path_id}: explain why this material serves its step"
                )
            keys.append(key)
        if len(set(keys)) != 3:
            raise ValueError(f"{path_id}: duplicate steps")
        # Product fallback may use a verified-free document for step 3.
        # The ranking engine still checks access and content coherence.
        if not keys[2].startswith(("course:", "document:")):
            raise ValueError(f"{path_id}: last step must be a course or document")
        reviewer = entry.get("reviewer") or None
        reviewed_at = entry.get("reviewed_at") or None
        if status == "approved" and (
            not isinstance(reviewer, str)
            or not reviewer.strip()
            or not isinstance(reviewed_at, str)
            or not reviewed_at.strip()
        ):
            raise ValueError(
                f"{path_id}: approved paths require reviewer and reviewed_at"
            )
        stages = entry.get("allowed_stages", [])
        industries = entry.get("allowed_industries", [])
        if not isinstance(stages, list) or any(code not in STAGES for code in stages):
            raise ValueError(f"{path_id}: invalid allowed_stages")
        if not isinstance(industries, list) or any(
            code not in INDUSTRIES for code in industries
        ):
            raise ValueError(f"{path_id}: invalid allowed_industries")
        rationale = entry.get("rationale", "")
        if not isinstance(rationale, str) or not rationale.strip():
            raise ValueError(f"{path_id}: rationale required")
        result.append(
            CuratedPath(
                path_id,
                task,
                tuple(keys),
                status,
                rationale,
                reviewer=reviewer,
                reviewed_at=reviewed_at,
                allowed_stages=tuple(stages),
                allowed_industries=tuple(industries),
            )
        )
    return result


def pick_curated_path(
    paths,
    *,
    task,
    stage=None,
    industry=None,
    candidate_indices,
    positions,
    rows,
    scores,
    pair_similarity=None,
    text_matrix=None,
    include_drafts=False,
    completed_keys=None,
):
    """Choose one feasible, thematically coherent editorial path.

    Drafts are ignored by default and must never be mistaken for a reviewed
    production trajectory. Document access type 'unknown' is not 'free'.
    """
    candidates = set(candidate_indices)
    completed_keys = set(completed_keys or ())
    feasible = []
    for path in paths:
        if path.task != task or (path.status != "approved" and not include_drafts):
            continue
        if path.allowed_stages and stage not in path.allowed_stages:
            continue
        if (
            industry is not None
            and path.allowed_industries
            and industry not in path.allowed_industries
        ):
            continue
        if any(key not in positions for key in path.keys):
            continue
        idx = [positions[key] for key in path.keys]
        if any(i not in candidates for i in idx):
            continue
        # If a path has already been completed in full, recommend a new one.
        if all(key in completed_keys for key in path.keys):
            continue
        if any(rows[i]["access_type"] != "free" for i in idx[:2]):
            continue
        if rows[idx[2]]["access_type"] != "paid" or rows[idx[2]]["kind"] != "course":
            continue
        relation = []
        for i, j in zip(idx, idx[1:], strict=False):
            if pair_similarity is not None:
                relation.append(float(pair_similarity[i, j]))
            elif text_matrix is not None and text_matrix.shape[1]:
                relation.append(
                    float((text_matrix[i] @ text_matrix[j].T).toarray()[0, 0])
                )
        # Both edges must have lexical support; averaging hid broken transitions.
        # Conservative sanity check, never a substitute for editorial approval.
        if len(relation) != 2 or any(
            not math.isfinite(x) or x < 0.015 for x in relation
        ):
            continue
        similarity = sum(relation) / len(relation)
        # Coherence is an explicit part of ranking across approved candidates.
        score = float(sum(scores[i] for i in idx) / 3) + 0.15 * similarity
        if not math.isfinite(score):
            continue
        feasible.append((score, path.path_id, path, idx, relation))
    if not feasible:
        return None
    _, _, path, idx, relations = min(feasible, key=lambda x: (-x[0], x[1]))
    return path, idx, relations
