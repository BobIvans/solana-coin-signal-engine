"""Candidate grid generation for constrained replay calibration."""

from __future__ import annotations


def build_candidate_grid(config: dict) -> list[dict]:
    grid_cfg = config.get("grid", {})
    baseline = dict(config.get("baseline", {}))

    candidates: list[dict] = [{"candidate_id": "baseline", "params": baseline, "is_baseline": True}]
    seen: set[tuple] = {tuple((k, baseline.get(k)) for k in sorted(baseline))}

    index = 1
    for key in sorted(grid_cfg):
        for value in grid_cfg[key]:
            candidate = dict(baseline)
            candidate[key] = value
            candidate_key = tuple((k, candidate[k]) for k in sorted(candidate))
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
