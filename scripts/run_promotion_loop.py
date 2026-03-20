#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import random
import sys
import time
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.promotion.cooldowns import is_x_cooldown_active, register_x_error
from src.promotion.counters import roll_daily_state_if_needed, update_trade_counters
from src.promotion.guards import compute_position_sizing, evaluate_entry_guards, should_block_entry
from src.promotion.io import append_jsonl, write_json
from src.promotion.kill_switch import is_kill_switch_active
from src.promotion.policy import config_hash, validate_runtime_config
from src.promotion.report import write_daily_summary_json, write_daily_summary_md
from src.promotion.runtime_signal_adapter import adapt_runtime_signal_batch
from src.promotion.runtime_signal_loader import load_runtime_signals
from src.promotion.session import restore_runtime_state, write_session_state
from src.promotion.state_machine import apply_transition
from src.promotion.types import utc_now_iso


def _parse_scalar(raw: str):
    value = raw.strip()
    if value == "":
        return {}
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        if not inner:
            return []
        return [item.strip().strip('"') for item in inner.split(',')]
    lowered = value.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    try:
        if "." in value:
            return float(value)
        return int(value)
    except ValueError:
        return value.strip('"')


def _load_simple_yaml(path: str) -> dict:
    root: dict = {}
    stack: list[tuple[int, dict]] = [(-1, root)]
    with open(path, "r", encoding="utf-8") as handle:
        for line in handle:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            indent = len(line) - len(line.lstrip(" "))
            key, sep, rest = stripped.partition(":")
            if not sep:
                continue
            while stack and indent <= stack[-1][0]:
                stack.pop()
            parent = stack[-1][1]
            parsed = _parse_scalar(rest)
            parent[key.strip()] = parsed
            if isinstance(parsed, dict):
                stack.append((indent, parsed))
    return root


def _load_config(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as handle:
        raw = handle.read()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return _load_simple_yaml(path)


def _simulate_signals(loop_index: int) -> list[dict]:
    return [
        {
            "signal_id": f"sig_{loop_index}_{i}",
            "token_address": f"token_{i}",
            "regime": "SCALP" if i % 2 == 0 else "TREND",
            "entry_decision": "SCALP" if i % 2 == 0 else "TREND",
            "x_status": "degraded" if i == 0 and loop_index % 2 == 0 else "healthy",
            "recommended_position_pct": 0.5,
            "regime_confidence": 0.6,
            "runtime_signal_origin": "synthetic_dev",
            "runtime_signal_status": "ok",
            "runtime_signal_confidence": 0.6,
            "runtime_signal_warning": "synthetic_dev_mode",
            "runtime_signal_partial_flag": False,
            "source_artifact": None,
        }
        for i in range(2)
    ]


def _summarize_runtime_signal_batch(batch: dict, normalized_signals: list[dict]) -> dict:
    status_counts: dict[str, int] = {}
    origin_counts: dict[str, int] = {}
    for signal in normalized_signals:
        status = str(signal.get("runtime_signal_status") or "unknown")
        origin = str(signal.get("runtime_signal_origin") or "unknown")
        status_counts[status] = status_counts.get(status, 0) + 1
        origin_counts[origin] = origin_counts.get(origin, 0) + 1
    return {
        "batch_status": batch.get("batch_status", "missing"),
        "signal_count": len(normalized_signals),
        "selected_origin": batch.get("selected_origin"),
        "selected_artifact": batch.get("selected_artifact"),
        "status_counts": status_counts,
        "origin_counts": origin_counts,
        "warnings": batch.get("warnings", []),
    }


def _load_normalized_signals(args: argparse.Namespace, loop_idx: int) -> tuple[list[dict], dict]:
    if args.signal_source == "synthetic-dev":
        signals = _simulate_signals(loop_idx)
        summary = {
            "batch_status": "synthetic_dev",
            "signal_count": len(signals),
            "selected_origin": "synthetic_dev",
            "selected_artifact": None,
            "status_counts": {"ok": len(signals)},
            "origin_counts": {"synthetic_dev": len(signals)},
            "warnings": ["synthetic_dev_mode_enabled"],
        }
        return signals, summary

    batch = load_runtime_signals(args.signals_dir, stale_after_sec=args.signal_stale_after_sec)
    normalized = adapt_runtime_signal_batch(
        batch["signals"],
        runtime_signal_origin=batch.get("selected_origin") or "unknown",
        source_artifact=batch.get("selected_artifact"),
    )
    return normalized, _summarize_runtime_signal_batch(batch, normalized)


def _emit_signal_batch_events(event_log: Path, run_id: str, summary: dict) -> None:
    append_jsonl(
        event_log,
        {
            "ts": utc_now_iso(),
            "event": "runtime_real_signals_loaded",
            "run_id": run_id,
            "signal_origin": summary.get("selected_origin"),
            "signal_status": summary.get("batch_status"),
            "signal_count": summary.get("signal_count", 0),
            "warnings": summary.get("warnings", []),
            "selected_artifact": summary.get("selected_artifact"),
        },
    )


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
    parser.add_argument("--signals-dir", default="data/processed")
    parser.add_argument("--signal-source", choices=["auto", "synthetic-dev"], default="auto")
    parser.add_argument("--signal-stale-after-sec", type=int, default=3600)
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
        "runtime_signal_source": args.signal_source,
        "signals_dir": args.signals_dir,
        "signal_stale_after_sec": args.signal_stale_after_sec,
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
    total_invalid = 0
    latest_signal_summary: dict[str, object] = {"batch_status": "missing", "origin_counts": {}, "status_counts": {}, "warnings": []}

    for loop_idx in range(args.max_loops):
        roll_daily_state_if_needed(state)
        signals, signal_summary = _load_normalized_signals(args, loop_idx)
        latest_signal_summary = signal_summary
        _emit_signal_batch_events(event_log, args.run_id, signal_summary)
        opened = 0
        rejected = 0

        if rng.random() < 0.05:
            maybe_event = register_x_error("captcha", state, cfg)
            if maybe_event:
                append_jsonl(event_log, {"ts": utc_now_iso(), **maybe_event})
                print("[promotion] cooldown_started type=captcha duration_min=30")

        for signal in signals:
            append_jsonl(
                event_log,
                {
                    "ts": utc_now_iso(),
                    "event": "runtime_signal_adapted",
                    "run_id": args.run_id,
                    "signal_id": signal.get("signal_id"),
                    "token_address": signal.get("token_address"),
                    "signal_origin": signal.get("runtime_signal_origin"),
                    "signal_status": signal.get("runtime_signal_status"),
                    "warning": signal.get("runtime_signal_warning"),
                },
            )

            if signal.get("runtime_signal_status") == "invalid" or not signal.get("token_address"):
                total_invalid += 1
                append_jsonl(
                    event_log,
                    {
                        "ts": utc_now_iso(),
                        "event": "runtime_signal_invalid",
                        "run_id": args.run_id,
                        "signal_id": signal.get("signal_id"),
                        "token_address": signal.get("token_address"),
                        "signal_origin": signal.get("runtime_signal_origin"),
                        "signal_status": signal.get("runtime_signal_status"),
                        "warning": signal.get("runtime_signal_warning"),
                        "blockers": signal.get("blockers", []),
                    },
                )
                continue

            if signal.get("runtime_signal_partial_flag"):
                append_jsonl(
                    event_log,
                    {
                        "ts": utc_now_iso(),
                        "event": "runtime_signal_partial",
                        "run_id": args.run_id,
                        "signal_id": signal.get("signal_id"),
                        "token_address": signal.get("token_address"),
                        "signal_origin": signal.get("runtime_signal_origin"),
                        "warning": signal.get("runtime_signal_warning"),
                    },
                )

            if signal.get("entry_decision") == "IGNORE":
                rejected += 1
                total_rejected += 1
                append_jsonl(
                    decisions_log,
                    {
                        "ts": utc_now_iso(),
                        "token_address": signal["token_address"],
                        "signal_id": signal["signal_id"],
                        "mode": args.mode,
                        "decision": "reject_signal",
                        "decision_reason_codes": ["entry_decision_ignore"],
                        "x_status": signal.get("x_status", "unknown"),
                        "signal_origin": signal.get("runtime_signal_origin"),
                        "signal_status": signal.get("runtime_signal_status"),
                        "effective_position_scale": 0.0,
                    },
                )
                append_jsonl(
                    event_log,
                    {
                        "ts": utc_now_iso(),
                        "event": "runtime_signal_skipped",
                        "run_id": args.run_id,
                        "signal_id": signal["signal_id"],
                        "token_address": signal["token_address"],
                        "signal_origin": signal.get("runtime_signal_origin"),
                        "reason": "entry_decision_ignore",
                    },
                )
                continue

            append_jsonl(event_log, {"ts": utc_now_iso(), "event": "signal_seen", "signal_id": signal["signal_id"]})
            guard_results = evaluate_entry_guards(signal, state, cfg)
            sizing = compute_position_sizing(signal, state, cfg)
            scale = sizing["effective_position_scale"]

            append_jsonl(
                event_log,
                {
                    "ts": utc_now_iso(),
                    "event": "evidence_weighted_sizing_started",
                    "run_id": args.run_id,
                    "signal_id": signal.get("signal_id"),
                    "token_address": signal.get("token_address"),
                    "base_position_pct": sizing.get("base_position_pct"),
                    "policy_origin": sizing.get("policy_origin"),
                },
            )
            append_jsonl(
                event_log,
                {
                    "ts": utc_now_iso(),
                    "event": "evidence_quality_computed",
                    "run_id": args.run_id,
                    "signal_id": signal.get("signal_id"),
                    "token_address": signal.get("token_address"),
                    "evidence_quality_score": sizing.get("evidence_quality_score"),
                    "sizing_confidence": sizing.get("sizing_confidence"),
                    "partial_evidence_flag": sizing.get("partial_evidence_flag"),
                    "evidence_conflict_flag": sizing.get("evidence_conflict_flag"),
                },
            )
            append_jsonl(
                event_log,
                {
                    "ts": utc_now_iso(),
                    "event": "sizing_multiplier_computed",
                    "run_id": args.run_id,
                    "signal_id": signal.get("signal_id"),
                    "token_address": signal.get("token_address"),
                    "base_position_pct": sizing.get("base_position_pct"),
                    "effective_position_pct": sizing.get("effective_position_pct"),
                    "sizing_multiplier": sizing.get("sizing_multiplier"),
                    "reason_codes": sizing.get("sizing_reason_codes", []),
                },
            )
            event_reason_map = {
                "partial_evidence_size_reduced": "sizing_reduced_partial_evidence",
                "x_status_degraded_size_reduced": "sizing_reduced_degraded_x",
                "creator_link_risk_size_reduced": "sizing_reduced_creator_link_risk",
                "creator_link_risk_moderate_size_reduced": "sizing_reduced_creator_link_risk",
            }
            for reason_code, event_name in event_reason_map.items():
                if reason_code in sizing.get("sizing_reason_codes", []):
                    append_jsonl(
                        event_log,
                        {
                            "ts": utc_now_iso(),
                            "event": event_name,
                            "run_id": args.run_id,
                            "signal_id": signal.get("signal_id"),
                            "token_address": signal.get("token_address"),
                            "base_position_pct": sizing.get("base_position_pct"),
                            "effective_position_pct": sizing.get("effective_position_pct"),
                            "sizing_multiplier": sizing.get("sizing_multiplier"),
                            "reason_codes": sizing.get("sizing_reason_codes", []),
                            "sizing_confidence": sizing.get("sizing_confidence"),
                        },
                    )

            if should_block_entry(guard_results) or args.dry_run or scale <= 0:
                rejected += 1
                total_rejected += 1
                reason_codes = list(guard_results["hard_block_reasons"])
                if args.dry_run:
                    reason_codes.append("dry_run")
                if scale <= 0:
                    reason_codes.append("zero_effective_position_scale")
                decision = {
                    "ts": utc_now_iso(),
                    "token_address": signal["token_address"],
                    "signal_id": signal["signal_id"],
                    "mode": args.mode,
                    "decision": "reject_signal",
                    "decision_reason_codes": reason_codes,
                    "x_status": signal.get("x_status", "healthy"),
                    "guard_results": guard_results,
                    "effective_position_scale": scale,
                    "signal_origin": signal.get("runtime_signal_origin"),
                    "signal_status": signal.get("runtime_signal_status"),
                    "recommended_position_pct": signal.get("recommended_position_pct"),
                    "base_position_pct": sizing.get("base_position_pct"),
                    "effective_position_pct": sizing.get("effective_position_pct"),
                    "sizing_multiplier": sizing.get("sizing_multiplier"),
                    "sizing_reason_codes": sizing.get("sizing_reason_codes", []),
                    "sizing_confidence": sizing.get("sizing_confidence"),
                    "sizing_origin": sizing.get("sizing_origin"),
                    "evidence_quality_score": sizing.get("evidence_quality_score"),
                    "evidence_conflict_flag": sizing.get("evidence_conflict_flag"),
                    "partial_evidence_flag": sizing.get("partial_evidence_flag"),
                    "sizing_warning": sizing.get("sizing_warning"),
                }
                append_jsonl(decisions_log, decision)
                append_jsonl(
                    event_log,
                    {
                        "ts": utc_now_iso(),
                        "event": "runtime_real_signal_rejected",
                        "run_id": args.run_id,
                        "signal_id": signal["signal_id"],
                        "token_address": signal["token_address"],
                        "signal_origin": signal.get("runtime_signal_origin"),
                        "signal_status": signal.get("runtime_signal_status"),
                        "reason": reason_codes,
                    },
                )
                append_jsonl(
                    event_log,
                    {
                        "ts": utc_now_iso(),
                        "event": "evidence_weighted_sizing_completed",
                        "run_id": args.run_id,
                        "signal_id": signal.get("signal_id"),
                        "token_address": signal.get("token_address"),
                        "base_position_pct": sizing.get("base_position_pct"),
                        "effective_position_pct": sizing.get("effective_position_pct"),
                        "sizing_multiplier": sizing.get("sizing_multiplier"),
                        "reason_codes": sizing.get("sizing_reason_codes", []),
                        "sizing_confidence": sizing.get("sizing_confidence"),
                    },
                )
                continue

            position = {
                "position_id": f"pos_{signal['signal_id']}",
                "token_address": signal["token_address"],
                "pair_address": signal.get("pair_address"),
                "entry_decision": signal.get("entry_decision"),
                "opened_at": utc_now_iso(),
                "size_scale": scale,
                "recommended_position_pct": signal.get("recommended_position_pct"),
                "base_position_pct": sizing.get("base_position_pct"),
                "effective_position_pct": sizing.get("effective_position_pct"),
                "sizing_multiplier": sizing.get("sizing_multiplier"),
                "sizing_reason_codes": sizing.get("sizing_reason_codes", []),
                "sizing_confidence": sizing.get("sizing_confidence"),
                "sizing_origin": sizing.get("sizing_origin"),
                "sizing_warning": sizing.get("sizing_warning"),
                "evidence_quality_score": sizing.get("evidence_quality_score"),
                "evidence_conflict_flag": sizing.get("evidence_conflict_flag"),
                "partial_evidence_flag": sizing.get("partial_evidence_flag"),
                "signal_origin": signal.get("runtime_signal_origin"),
                "signal_status": signal.get("runtime_signal_status"),
                "source_artifact": signal.get("source_artifact"),
                "entry_snapshot": signal.get("entry_snapshot") or {},
            }
            state.setdefault("open_positions", []).append(position)
            update_trade_counters(state, pnl_pct=0.0)
            opened += 1
            total_opened += 1
            append_jsonl(
                event_log,
                {
                    "ts": utc_now_iso(),
                    "event": "runtime_real_signal_opened",
                    "run_id": args.run_id,
                    "signal_id": signal["signal_id"],
                    "position_id": position["position_id"],
                    "token_address": signal["token_address"],
                    "signal_origin": signal.get("runtime_signal_origin"),
                    "signal_status": signal.get("runtime_signal_status"),
                    "base_position_pct": sizing.get("base_position_pct"),
                    "effective_position_pct": sizing.get("effective_position_pct"),
                    "sizing_multiplier": sizing.get("sizing_multiplier"),
                    "sizing_reason_codes": sizing.get("sizing_reason_codes", []),
                },
            )
            append_jsonl(
                decisions_log,
                {
                    "ts": utc_now_iso(),
                    "token_address": signal["token_address"],
                    "signal_id": signal["signal_id"],
                    "mode": args.mode,
                    "decision": "open_paper_position",
                    "decision_reason_codes": guard_results.get("soft_reasons", []),
                    "x_status": signal.get("x_status", "healthy"),
                    "guard_results": guard_results,
                    "effective_position_scale": scale,
                    "signal_origin": signal.get("runtime_signal_origin"),
                    "signal_status": signal.get("runtime_signal_status"),
                    "recommended_position_pct": signal.get("recommended_position_pct"),
                    "base_position_pct": sizing.get("base_position_pct"),
                    "effective_position_pct": sizing.get("effective_position_pct"),
                    "sizing_multiplier": sizing.get("sizing_multiplier"),
                    "sizing_reason_codes": sizing.get("sizing_reason_codes", []),
                    "sizing_confidence": sizing.get("sizing_confidence"),
                    "sizing_origin": sizing.get("sizing_origin"),
                    "evidence_quality_score": sizing.get("evidence_quality_score"),
                    "evidence_conflict_flag": sizing.get("evidence_conflict_flag"),
                    "partial_evidence_flag": sizing.get("partial_evidence_flag"),
                    "sizing_warning": sizing.get("sizing_warning"),
                },
            )

            append_jsonl(
                event_log,
                {
                    "ts": utc_now_iso(),
                    "event": "evidence_weighted_sizing_completed",
                    "run_id": args.run_id,
                    "signal_id": signal.get("signal_id"),
                    "token_address": signal.get("token_address"),
                    "base_position_pct": sizing.get("base_position_pct"),
                    "effective_position_pct": sizing.get("effective_position_pct"),
                    "sizing_multiplier": sizing.get("sizing_multiplier"),
                    "reason_codes": sizing.get("sizing_reason_codes", []),
                    "sizing_confidence": sizing.get("sizing_confidence"),
                },
            )

        if is_kill_switch_active(cfg):
            append_jsonl(event_log, {"ts": utc_now_iso(), "event": "kill_switch_triggered", "reason": "kill_switch_file_present"})

        print(
            f"[promotion] signals_processed count={len(signals)} opened={opened} rejected={rejected} "
            f"origin={signal_summary.get('selected_origin')} status={signal_summary.get('batch_status')}"
        )
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
        "total_invalid": total_invalid,
        "runtime_signal_source": args.signal_source,
        "runtime_signal_origin": latest_signal_summary.get("selected_origin"),
        "runtime_signal_status": latest_signal_summary.get("batch_status"),
        "runtime_signal_status_counts": latest_signal_summary.get("status_counts", {}),
        "runtime_signal_origin_counts": latest_signal_summary.get("origin_counts", {}),
        "runtime_signal_warnings": latest_signal_summary.get("warnings", []),
        "signals_dir": args.signals_dir,
    }
    summary_json_path = write_daily_summary_json(run_dir / "daily_summary.json", summary)
    write_daily_summary_md(run_dir / "daily_summary.md", summary)
    write_session_state(session_path, state)
    append_jsonl(
        event_log,
        {
            "ts": utc_now_iso(),
            "event": "runtime_real_signal_loop_completed",
            "run_id": args.run_id,
            "total_opened": total_opened,
            "total_rejected": total_rejected,
            "total_invalid": total_invalid,
            "signal_origin": latest_signal_summary.get("selected_origin"),
            "signal_status": latest_signal_summary.get("batch_status"),
        },
    )
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
