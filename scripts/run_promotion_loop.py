#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import random
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.promotion.cooldowns import is_x_cooldown_active, register_x_error
from src.promotion.counters import roll_daily_state_if_needed, update_trade_counters
from src.promotion.guards import effective_position_scale, evaluate_entry_guards, should_block_entry
from src.promotion.io import append_jsonl, write_json
from src.promotion.kill_switch import is_kill_switch_active
from src.promotion.policy import config_hash, validate_runtime_config
from src.promotion.report import write_daily_summary_json, write_daily_summary_md
from src.promotion.session import restore_runtime_state, write_session_state
from src.promotion.state_machine import apply_transition
from src.promotion.types import utc_now_iso


def _load_config(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def _simulate_signals(loop_index: int) -> list[dict]:
    # deterministic synthetic signals for smoke/runtime testing
    return [
        {
            "signal_id": f"sig_{loop_index}_{i}",
            "token_address": f"token_{i}",
            "regime": "SCALP" if i % 2 == 0 else "TREND",
            "x_status": "degraded" if i == 0 and loop_index % 2 == 0 else "healthy",
        }
        for i in range(2)
    ]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--mode", required=True, choices=["shadow", "constrained_paper", "expanded_paper", "paused"])
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--max-loops", type=int, default=1)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force-watchlist-only", action="store_true")
    parser.add_argument("--kill-switch", action="store_true")
    parser.add_argument("--allow-regime", choices=["scalp", "trend", "both"])
    args = parser.parse_args()

    cfg = _load_config(args.config)
    cfg["runtime"]["mode"] = args.mode
    validate_runtime_config(cfg)
    cfg_hash = config_hash(cfg)

    runs_dir = Path(cfg.get("state", {}).get("runs_dir", "runs"))
    run_dir = runs_dir / args.run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    if args.allow_regime:
        allowed = {
            "scalp": ["SCALP"],
            "trend": ["TREND"],
            "both": ["SCALP", "TREND"],
        }[args.allow_regime]
        cfg["modes"][args.mode]["allow_regimes"] = allowed

    if args.kill_switch:
        kill_path = Path(cfg["safety"]["kill_switch_file"])
        kill_path.parent.mkdir(parents=True, exist_ok=True)
        kill_path.write_text("1\n", encoding="utf-8")

    session_path = run_dir / "session_state.json"
    state = restore_runtime_state(session_path, args.mode, cfg_hash, resume=args.resume)
    state["force_watchlist_only"] = bool(args.force_watchlist_only)

    current_mode = state.get("active_mode", args.mode)
    state, mode_event = apply_transition(current_mode, args.mode, state, cfg)

    event_log = run_dir / "event_log.jsonl"
    decisions_log = run_dir / "decisions.jsonl"

    manifest = {
        "run_id": args.run_id,
        "mode": args.mode,
        "config_hash": cfg_hash,
        "started_at": utc_now_iso(),
        "resumed": args.resume,
        "runtime_seed": cfg.get("runtime", {}).get("seed", 42),
        "allowed_regimes": cfg["modes"].get(args.mode, {}).get("allow_regimes", ["SCALP", "TREND"]),
        "degraded_x_policy": cfg["modes"].get(args.mode, {}).get("degraded_x_policy", "watchlist_only"),
    }
    write_json(run_dir / "runtime_manifest.json", manifest)

    print(f"[promotion] run_id={args.run_id}")
    append_jsonl(event_log, {"ts": utc_now_iso(), **mode_event})
    print(f"[promotion] mode_entered mode={args.mode}")
    append_jsonl(event_log, {"ts": utc_now_iso(), "event": "state_restored", "resumed": args.resume})
    print(f"[promotion] state_restored resumed={str(args.resume).lower()} open_positions={len(state.get('open_positions', []))}")
    print(f"[promotion] loop_started interval_sec={cfg.get('runtime', {}).get('loop_interval_sec', 30)}")

    rng = random.Random(cfg.get("runtime", {}).get("seed", 42))
    total_opened = 0
    total_rejected = 0

    for loop_idx in range(args.max_loops):
        roll_daily_state_if_needed(state)
        signals = _simulate_signals(loop_idx)
        opened = 0
        rejected = 0

        if rng.random() < 0.05:
            maybe_event = register_x_error("captcha", state, cfg)
            if maybe_event:
                append_jsonl(event_log, {"ts": utc_now_iso(), **maybe_event})
                print("[promotion] cooldown_started type=captcha duration_min=30")

        for signal in signals:
            append_jsonl(event_log, {"ts": utc_now_iso(), "event": "signal_seen", "signal_id": signal["signal_id"]})
            guard_results = evaluate_entry_guards(signal, state, cfg)
            scale = effective_position_scale(signal, state, cfg)

            if should_block_entry(guard_results) or args.dry_run:
                rejected += 1
                total_rejected += 1
                decision = {
                    "ts": utc_now_iso(),
                    "token_address": signal["token_address"],
                    "signal_id": signal["signal_id"],
                    "mode": args.mode,
                    "decision": "reject_signal",
                    "decision_reason_codes": guard_results["hard_block_reasons"] or ["dry_run"],
                    "x_status": signal.get("x_status", "healthy"),
                    "guard_results": guard_results,
                    "effective_position_scale": scale,
                }
                append_jsonl(decisions_log, decision)
                append_jsonl(event_log, {"ts": utc_now_iso(), "event": "signal_rejected", "signal_id": signal["signal_id"]})
                continue

            position = {
                "position_id": f"pos_{signal['signal_id']}",
                "token_address": signal["token_address"],
                "opened_at": utc_now_iso(),
                "size_scale": scale,
            }
            state.setdefault("open_positions", []).append(position)
            update_trade_counters(state, pnl_pct=0.0)
            opened += 1
            total_opened += 1
            append_jsonl(event_log, {"ts": utc_now_iso(), "event": "paper_position_opened", "position_id": position["position_id"]})
            append_jsonl(decisions_log, {
                "ts": utc_now_iso(),
                "token_address": signal["token_address"],
                "signal_id": signal["signal_id"],
                "mode": args.mode,
                "decision": "open_paper_position",
                "decision_reason_codes": guard_results.get("soft_reasons", []),
                "x_status": signal.get("x_status", "healthy"),
                "guard_results": guard_results,
                "effective_position_scale": scale,
            })

        if is_kill_switch_active(cfg):
            append_jsonl(event_log, {"ts": utc_now_iso(), "event": "kill_switch_triggered", "reason": "kill_switch_file_present"})

        print(f"[promotion] signals_processed count={len(signals)} opened={opened} rejected={rejected}")
        if not args.dry_run:
            time.sleep(cfg.get("runtime", {}).get("loop_interval_sec", 30))

    write_json(run_dir / "positions_snapshot.json", {"open_positions": state.get("open_positions", [])})
    summary = {
        "run_id": args.run_id,
        "mode": args.mode,
        "trades_today": state.get("counters", {}).get("trades_today", 0),
        "open_positions": len(state.get("open_positions", [])),
        "pnl_pct_today": state.get("counters", {}).get("pnl_pct_today", 0.0),
        "consecutive_losses": state.get("consecutive_losses", 0),
        "x_cooldown_active": is_x_cooldown_active(state),
        "total_opened": total_opened,
        "total_rejected": total_rejected,
    }
    summary_json_path = write_daily_summary_json(run_dir / "daily_summary.json", summary)
    write_daily_summary_md(run_dir / "daily_summary.md", summary)
    write_session_state(session_path, state)
    append_jsonl(event_log, {"ts": utc_now_iso(), "event": "state_persisted"})

    print(f"[promotion] daily_summary_written path={summary_json_path}")
    print("[promotion] done")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001
        print(f"[promotion][error] stage=runtime message={exc}")
        raise
