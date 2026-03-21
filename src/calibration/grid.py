"""Candidate grid generation for constrained replay calibration."""

from __future__ import annotations

from itertools import product
from typing import Any


def _candidate_key(params: dict[str, Any]) -> tuple[tuple[str, Any], ...]:
    return tuple((key, params.get(key)) for key in sorted(params))


def build_candidate_grid(config: dict) -> list[dict]:
    grid_cfg = config.get("grid", {})
    baseline = dict(config.get("baseline", {}))

    candidates: list[dict] = [{"candidate_id": "baseline", "params": baseline, "is_baseline": True}]
    seen: set[tuple[tuple[str, Any], ...]] = {_candidate_key(baseline)}

    if not grid_cfg:
        return candidates

    ordered_keys = sorted(grid_cfg)
    ordered_values = [list(grid_cfg.get(key) or [baseline.get(key)]) for key in ordered_keys]

    index = 1
    for combo in product(*ordered_values):
        candidate = dict(baseline)
        for key, value in zip(ordered_keys, combo):
            candidate[key] = value
        candidate_key = _candidate_key(candidate)
        if candidate_key in seen:
            continue
        seen.add(candidate_key)
        candidates.append({"candidate_id": f"cand_{index:04d}", "params": candidate, "is_baseline": False})
        index += 1
    return candidates


def limit_candidates(candidates: list[dict], max_candidates: int | None) -> list[dict]:
    if max_candidates is None or max_candidates <= 0:
        return candidates
    baseline = [candidate for candidate in candidates if candidate.get("is_baseline")]
    non_baseline = [candidate for candidate in candidates if not candidate.get("is_baseline")]
    return baseline + non_baseline[:max_candidates]
