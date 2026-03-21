#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from utils.clock import utc_now_iso
from utils.io import append_jsonl, ensure_dir, read_json, write_json


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )


def _fixture_payload() -> dict:
    now = utc_now_iso()
    return {
        "contract_version": "runtime_signal_smoke_v1",
        "generated_at": now,
        "tokens": [
            {
                "signal_id": "smoke_valid_entry",
                "token_address": "So11111111111111111111111111111111111111112",
                "pair_address": "pair_smoke_valid",
                "symbol": "SMOKE",
                "signal_ts": now,
                "regime": "SCALP",
                "x_status": "healthy",
                "entry_decision": "SCALP",
                "entry_confidence": 0.82,
                "regime_confidence": 0.81,
                "recommended_position_pct": 0.42,
                "entry_reason": "smoke_fixture_valid_entry",
                "entry_flags": ["smoke_fixture"],
                "regime_blockers": [],
                "entry_snapshot": {"price_usd": 1.23},
            },
            {
                "signal_id": "smoke_degraded_x",
                "token_address": "So22222222222222222222222222222222222222222",
                "pair_address": "pair_smoke_degraded",
                "symbol": "SMKX",
                "signal_ts": now,
                "regime": "TREND",
                "x_status": "degraded",
                "entry_decision": "TREND",
                "entry_confidence": 0.76,
                "regime_confidence": 0.74,
                "recommended_position_pct": 0.36,
                "entry_reason": "smoke_fixture_degraded_x",
                "entry_flags": ["smoke_fixture", "x_degraded_size_reduced"],
                "regime_blockers": [],
                "entry_snapshot": {"price_usd": 0.77},
                "partial_evidence_flag": True,
            },
            {
                "signal_id": "smoke_invalid_row",
                "token_address": "",
                "signal_ts": now,
                "regime": "UNKNOWN",
                "x_status": "healthy",
                "entry_decision": "SCALP",
                "entry_confidence": 0.7,
                "regime_confidence": 0.4,
                "recommended_position_pct": 0.25,
                "entry_reason": "missing_token",
            },
        ],
    }


def _config_payload(base_dir: Path) -> dict:
    return {
        "runtime": {"mode": "expanded_paper", "chain": "solana", "loop_interval_sec": 0, "seed": 42},
        "modes": {
            "shadow": {"open_positions": False, "simulate_entries": True, "simulate_exits": True, "allow_regimes": ["SCALP", "TREND"]},
            "constrained_paper": {"open_positions": True, "max_open_positions": 1, "max_trades_per_day": 10, "position_size_scale": 0.5, "allow_regimes": ["SCALP"], "degraded_x_policy": "watchlist_only"},
            "expanded_paper": {"open_positions": True, "max_open_positions": 2, "max_trades_per_day": 20, "position_size_scale": 1.0, "allow_regimes": ["SCALP", "TREND"], "degraded_x_policy": "reduced_size"},
            "paused": {"open_positions": False, "simulate_entries": False, "simulate_exits": False, "allow_regimes": ["SCALP", "TREND"]},
        },
        "safety": {"kill_switch_file": str(base_dir / "kill.flag"), "max_daily_loss_pct": 8.0, "max_consecutive_losses": 4},
        "x_protection": {"captcha_cooldown_trigger_count": 2, "captcha_cooldown_minutes": 30, "soft_ban_cooldown_minutes": 30, "timeout_cooldown_trigger_count": 5, "timeout_cooldown_minutes": 15},
        "degraded_x": {"baseline_score": 45, "allow_shadow": True, "allow_constrained_paper": True, "allow_expanded_paper": True, "constrained_policy": "watchlist_only", "expanded_policy": "reduced_size"},
        "state": {"runs_dir": str(base_dir / "runs"), "state_dir": str(base_dir / "runtime_state"), "write_session_state": True, "write_event_log": True, "write_daily_summary": True},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Deterministic runtime real-signal smoke.")
    parser.add_argument("--base-dir", default=str(REPO_ROOT / "data/smoke/runtime_signal"))
    args = parser.parse_args()

    smoke_dir = Path(args.base_dir).expanduser().resolve()
    if smoke_dir.exists():
        shutil.rmtree(smoke_dir)
    ensure_dir(smoke_dir)
    processed_dir = ensure_dir(smoke_dir / "processed")
    run_id = "runtime_signal_smoke"
    run_dir = smoke_dir / "runs" / run_id

    payload = _fixture_payload()
    matrix_rows = [{**row, "schema_version": row.get("schema_version") or "trade_feature_matrix.v1"} for row in payload["tokens"]]
    _write_jsonl(processed_dir / "trade_feature_matrix.jsonl", matrix_rows)
    append_jsonl(smoke_dir / "runtime_signal_events.jsonl", {"ts": utc_now_iso(), "event": "fixture_written", "count": len(payload["tokens"])})

    config_path = smoke_dir / "promotion.json"
    write_json(config_path, _config_payload(smoke_dir))

    cmd = [
        sys.executable,
        "scripts/run_promotion_loop.py",
        "--config",
        str(config_path),
        "--mode",
        "expanded_paper",
        "--run-id",
        run_id,
        "--max-loops",
        "1",
        "--signals-dir",
        str(processed_dir),
        "--signal-source",
        "auto",
        "--dry-run",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False, cwd=REPO_ROOT)
    if result.returncode != 0:
        raise SystemExit(result.returncode)

    summary = read_json(run_dir / "daily_summary.json", default={}) or {}
    runtime_health = read_json(run_dir / "runtime_health.json", default={}) or {}
    decisions = (run_dir / "decisions.jsonl").read_text(encoding="utf-8").splitlines() if (run_dir / "decisions.jsonl").exists() else []
    compact = {
        "run_id": run_id,
        "signals_written": len(payload["tokens"]),
        "runtime_signal_origin": summary.get("runtime_signal_origin"),
        "runtime_signal_status": summary.get("runtime_signal_status"),
        "total_opened": summary.get("total_opened"),
        "total_rejected": summary.get("total_rejected"),
        "total_invalid": summary.get("total_invalid"),
        "decision_count": len(decisions),
        "runtime_health_present": bool(runtime_health),
        "stdout": result.stdout.strip().splitlines(),
    }
    write_json(smoke_dir / "runtime_signal_summary.json", compact)
    print(json.dumps(compact, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
