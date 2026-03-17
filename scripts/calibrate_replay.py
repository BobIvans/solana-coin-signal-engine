"""Constrained replay calibration harness (PR-12-lite)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import yaml

from src.calibration.evaluator import evaluate_candidate
from src.calibration.grid import build_candidate_grid, limit_candidates
from src.calibration.io import load_replay_artifacts, write_json
from src.calibration.leaderboard import compare_to_baseline, rank_candidates
from src.calibration.recommender import annotate_constraints, build_recommended_config, recommend_candidate
from src.calibration.report import write_leaderboard_csv, write_summary_json, write_summary_md
from src.calibration.splits import build_day_splits
from utils.io import ensure_dir


def _load_config(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _build_diff(baseline: dict, candidate: dict) -> dict:
    return {key: value for key, value in candidate.items() if baseline.get(key) != value}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config/calibration.default.yaml")
    parser.add_argument("--replay-run-id")
    parser.add_argument("--seed", type=int)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--max-candidates", type=int)
    parser.add_argument("--regime", choices=("scalp", "trend", "both"), default="both")
    parser.add_argument("--primary-metric")
    parser.add_argument("--emit-recommended-config", action="store_true")
    args = parser.parse_args()

    cfg = _load_config(Path(args.config))
    replay_run_id = args.replay_run_id or cfg.get("input", {}).get("replay_run_id")
    if not replay_run_id:
        raise ValueError("replay_run_id is required")
    if args.seed is not None:
        cfg["seed"] = args.seed
    if args.primary_metric:
        cfg.setdefault("selection", {})["primary_metric"] = args.primary_metric

    runs_dir = Path(cfg.get("input", {}).get("runs_dir", "runs"))
    run_dir = ensure_dir(runs_dir / args.run_id)
    primary_metric = cfg.get("selection", {}).get("primary_metric", "validation_expectancy")

    print(f"[calibration] run_id={args.run_id}")

    try:
        replay = load_replay_artifacts(runs_dir, replay_run_id)
        print(f"[calibration] replay_loaded run_id={replay_run_id}")

        split = build_day_splits(replay["manifest"], replay["signals"], replay["trades"], cfg)
        print(
            "[calibration] splits_built "
            f"train_days={len(split['train_days'])} validation_days={len(split['validation_days'])}"
        )

        candidates = limit_candidates(build_candidate_grid(cfg), args.max_candidates)
        print(f"[calibration] candidates_built count={len(candidates)}")

        baseline_candidate = next(candidate for candidate in candidates if candidate["is_baseline"])
        baseline_eval = evaluate_candidate(baseline_candidate["params"], replay, split)
        baseline_row = {
            "candidate_id": "baseline",
            "config_diff_from_baseline": {},
            "primary_metric": primary_metric,
            "replay_run_id": replay_run_id,
            **baseline_eval,
        }
        print("[calibration] baseline_evaluated")

        rows = [baseline_row]
        candidate_diffs: dict[str, dict] = {"baseline": {}}
        for candidate in candidates:
            if candidate["is_baseline"]:
                continue
            params = dict(candidate["params"])
            if args.regime == "scalp":
                for key in list(params):
                    if key.startswith("trend_"):
                        params[key] = cfg["baseline"][key]
            elif args.regime == "trend":
                for key in list(params):
                    if key.startswith("scalp_"):
                        params[key] = cfg["baseline"][key]

            row = {
                "candidate_id": candidate["candidate_id"],
                "config_diff_from_baseline": _build_diff(cfg["baseline"], params),
                "primary_metric": primary_metric,
                "replay_run_id": replay_run_id,
                **evaluate_candidate(params, replay, split),
            }
            candidate_diffs[candidate["candidate_id"]] = row["config_diff_from_baseline"]
            rows.append(row)
        print(f"[calibration] candidates_evaluated count={len(rows)}")

        baseline_for_compare = rows[0]
        for row in rows:
            row["beats_baseline"] = compare_to_baseline(row, baseline_for_compare, primary_metric)
            if row["candidate_id"] == "baseline":
                row["beats_baseline"] = False

        leaderboard = rank_candidates(rows, primary_metric)
        leaderboard = annotate_constraints(leaderboard, cfg.get("selection", {}))

        write_json(run_dir / "leaderboard.json", leaderboard)
        write_leaderboard_csv(run_dir / "leaderboard.csv", leaderboard)
        write_json(run_dir / "candidate_diffs.json", candidate_diffs)
        print(f"[calibration] leaderboard_written path={run_dir / 'leaderboard.csv'}")

        recommended = recommend_candidate(leaderboard, cfg.get("selection", {}))
        recommended_payload = build_recommended_config(recommended) if recommended else {"overrides": {}, "selection_basis": {}}
        Path(run_dir / "recommended_config.yaml").write_text(
            yaml.safe_dump(recommended_payload, sort_keys=True), encoding="utf-8"
        )
        print(f"[calibration] recommendation_written path={run_dir / 'recommended_config.yaml'}")

        rejected = [row for row in leaderboard if not row.get("passes_constraints")]
        summary = {
            "replay_run_id": replay_run_id,
            "calibration_run_id": args.run_id,
            "baseline_metrics": baseline_for_compare,
            "best_candidate_id": leaderboard[0]["candidate_id"] if leaderboard else None,
            "best_candidate_metrics": leaderboard[0] if leaderboard else None,
            "chosen_primary_metric": primary_metric,
            "candidate_count": len(leaderboard),
            "rejected_candidate_count": len(rejected),
            "reason_rejections_breakdown": {"constraints_failed": len(rejected)},
            "recommended_overrides": recommended_payload.get("overrides", {}),
            "notes": ["Calibration writes recommendations only; runtime configs are untouched."],
        }
        write_summary_json(run_dir / "calibration_summary.json", summary)
        write_summary_md(run_dir / "calibration_summary.md", summary)
        print("[calibration] done")
        return 0
    except Exception as exc:  # noqa: BLE001
        print(f"[calibration][error] stage=splits message={exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
