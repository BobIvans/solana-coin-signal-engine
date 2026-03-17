"""Report writers for calibration artifacts."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from utils.io import ensure_dir


def write_summary_json(path: Path, payload: dict) -> Path:
    ensure_dir(path.parent)
    path.write_text(json.dumps(payload, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return path


def write_summary_md(path: Path, summary: dict) -> Path:
    ensure_dir(path.parent)
    lines = [
        f"# Calibration Summary ({summary.get('calibration_run_id')})",
        "",
        f"- Replay run: `{summary.get('replay_run_id')}`",
        f"- Primary metric: `{summary.get('chosen_primary_metric')}`",
        f"- Candidate count: `{summary.get('candidate_count')}`",
        f"- Best candidate: `{summary.get('best_candidate_id')}`",
        "",
        "## Recommended overrides",
        "",
    ]
    overrides = summary.get("recommended_overrides", {})
    if overrides:
        for key, value in sorted(overrides.items()):
            lines.append(f"- `{key}`: `{value}`")
    else:
        lines.append("- none")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def write_leaderboard_csv(path: Path, leaderboard: list[dict]) -> Path:
    ensure_dir(path.parent)
    headers = [
        "candidate_id",
        "rank",
        "train_trades",
        "validation_trades",
        "train_winrate",
        "validation_winrate",
        "train_expectancy",
        "validation_expectancy",
        "validation_median_pnl",
        "validation_max_drawdown_est",
        "scalp_trade_count",
        "trend_trade_count",
        "passes_constraints",
        "beats_baseline",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers)
        writer.writeheader()
        for row in leaderboard:
            writer.writerow(
                {
                    "candidate_id": row.get("candidate_id"),
                    "rank": row.get("rank"),
                    "train_trades": row.get("train", {}).get("trades"),
                    "validation_trades": row.get("validation", {}).get("trades"),
                    "train_winrate": row.get("train", {}).get("winrate"),
                    "validation_winrate": row.get("validation", {}).get("winrate"),
                    "train_expectancy": row.get("train", {}).get("expectancy"),
                    "validation_expectancy": row.get("validation", {}).get("expectancy"),
                    "validation_median_pnl": row.get("validation", {}).get("median_pnl_pct"),
                    "validation_max_drawdown_est": row.get("validation", {}).get("max_drawdown_est"),
                    "scalp_trade_count": row.get("regimes", {}).get("scalp_trades"),
                    "trend_trade_count": row.get("regimes", {}).get("trend_trades"),
                    "passes_constraints": row.get("passes_constraints"),
                    "beats_baseline": row.get("beats_baseline"),
                }
            )
    return path
