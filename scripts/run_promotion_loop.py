

#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any


REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.promotion.cooldowns import (
    is_x_cooldown_active,
    observe_x_signal,
    register_degraded_x_entry_attempt,
    register_degraded_x_entry_opened,
    resolve_degraded_x_guard,
)
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
from trading.exit_logic import decide_exits
from trading.paper_trader import process_entry_signals, process_exit_signals, run_mark_to_market
from trading.position_book import ensure_state


_DEFAULT_TRADING_SETTINGS = {
    "EXIT_ENGINE_FAILCLOSED": True,
    "EXIT_DEV_SELL_HARD": True,
    "EXIT_RUG_FLAG_HARD": True,
    "EXIT_SCALP_STOP_LOSS_PCT": -10,
    "EXIT_SCALP_LIQUIDITY_DROP_PCT": 20,
    "EXIT_SCALP_MAX_HOLD_SEC": 120,
    "EXIT_SCALP_RECHECK_SEC": 18,
    "EXIT_SCALP_VOLUME_VELOCITY_DECAY": 0.70,
    "EXIT_SCALP_X_SCORE_DECAY": 0.70,
    "EXIT_SCALP_BUY_PRESSURE_FLOOR": 0.60,
    "EXIT_TREND_HARD_STOP_PCT": -18,
    "EXIT_TREND_BUY_PRESSURE_FLOOR": 0.50,
    "EXIT_TREND_LIQUIDITY_DROP_PCT": 25,
    "EXIT_TREND_PARTIAL1_PCT": 35,
    "EXIT_TREND_PARTIAL2_PCT": 100,
    "EXIT_CLUSTER_DUMP_HARD": 0.82,
    "EXIT_CLUSTER_CONCENTRATION_SELL_THRESHOLD": 0.65,
    "EXIT_CLUSTER_SELL_CONCENTRATION_WARN": 0.72,
    "EXIT_CLUSTER_SELL_CONCENTRATION_HARD": 0.78,
    "EXIT_LIQUIDITY_REFILL_FAIL_MIN": 0.85,
    "EXIT_SELLER_REENTRY_WEAK_MAX": 0.20,
    "EXIT_SHOCK_RECOVERY_TOO_SLOW_SEC": 180,
    "EXIT_BUNDLE_FAILURE_SPIKE_THRESHOLD": 2.0,
    "EXIT_RETRY_MANIPULATION_HARD": 5.0,
    "EXIT_CREATOR_CLUSTER_RISK_HARD": 0.75,
    "EXIT_LINKAGE_RISK_HARD": 0.78,
    "PAPER_STARTING_CAPITAL_SOL": 0.1,
    "PAPER_DEFAULT_SLIPPAGE_BPS": 100,
    "PAPER_MAX_SLIPPAGE_BPS": 500,
    "PAPER_SLIPPAGE_LIQUIDITY_SENSITIVITY": 0.5,
    "PAPER_PRIORITY_FEE_BASE_SOL": 0.00002,
    "PAPER_PRIORITY_FEE_SPIKE_MULTIPLIER": 2.0,
    "PAPER_FAILED_TX_BASE_PROB": 0.0,
    "PAPER_FAILED_TX_LOW_LIQUIDITY_ADDON": 0.02,
    "PAPER_FAILED_TX_HIGH_VOLATILITY_ADDON": 0.02,
    "PAPER_PARTIAL_FILL_ALLOWED": True,
    "PAPER_PARTIAL_FILL_MIN_RATIO": 0.35,
    "PAPER_CONTRACT_VERSION": "paper_trader_v1",
    "EXIT_CONTRACT_VERSION": "exit_engine_v1",
}


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
            "entry_snapshot": {"price_usd": 1.0, "liquidity_usd": 25000.0},
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
        "origin_tier": batch.get("origin_tier"),
        "runtime_pipeline_origin": batch.get("runtime_pipeline_origin"),
        "runtime_pipeline_status": batch.get("runtime_pipeline_status"),
        "runtime_pipeline_manifest": batch.get("runtime_pipeline_manifest"),
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
            "origin_tier": "fallback",
            "runtime_pipeline_origin": "synthetic_dev",
            "runtime_pipeline_status": None,
            "runtime_pipeline_manifest": None,
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
        runtime_origin_tier=batch.get("origin_tier"),
        runtime_pipeline_origin=batch.get("runtime_pipeline_origin"),
        runtime_pipeline_status=batch.get("runtime_pipeline_status"),
        runtime_pipeline_manifest=batch.get("runtime_pipeline_manifest"),
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
            "origin_tier": summary.get("origin_tier"),
            "runtime_pipeline_origin": summary.get("runtime_pipeline_origin"),
            "runtime_pipeline_status": summary.get("runtime_pipeline_status"),
            "runtime_pipeline_manifest": summary.get("runtime_pipeline_manifest"),
        },
    )


def _state_open_positions(state: dict[str, Any]) -> list[dict[str, Any]]:
    return [position for position in state.get("positions", []) if position.get("is_open")]


def _sync_open_positions_compat(state: dict[str, Any]) -> None:
    state["open_positions"] = [dict(position) for position in _state_open_positions(state)]


def _signal_price(signal: dict[str, Any], fallback: float = 0.0) -> float:
    entry_snapshot = signal.get("entry_snapshot") or {}
    for key in ("price_usd_now", "price_usd", "current_price_usd"):
        if signal.get(key) is not None:
            return float(signal.get(key) or 0.0)
    return float(entry_snapshot.get("price_usd") or fallback or 0.0)


def _market_state_from_signal(signal: dict[str, Any]) -> dict[str, Any]:
    entry_snapshot = signal.get("entry_snapshot") or {}
    return {
        "token_address": signal.get("token_address"),
        "price_usd": _signal_price(signal),
        "price_usd_now": _signal_price(signal),
        "liquidity_usd": signal.get("liquidity_usd") or entry_snapshot.get("liquidity_usd"),
        "liquidity_usd_now": signal.get("liquidity_usd_now") or signal.get("liquidity_usd") or entry_snapshot.get("liquidity_usd"),
        "buy_pressure": signal.get("buy_pressure") or entry_snapshot.get("buy_pressure"),
        "buy_pressure_now": signal.get("buy_pressure_now") or signal.get("buy_pressure") or entry_snapshot.get("buy_pressure"),
        "volume_velocity": signal.get("volume_velocity") or entry_snapshot.get("volume_velocity"),
        "volume_velocity_now": signal.get("volume_velocity_now") or signal.get("volume_velocity") or entry_snapshot.get("volume_velocity"),
        "x_validation_score": signal.get("x_validation_score") or entry_snapshot.get("x_validation_score"),
        "x_validation_score_now": signal.get("x_validation_score_now") or signal.get("x_validation_score") or entry_snapshot.get("x_validation_score"),
        "x_status": signal.get("x_status") or entry_snapshot.get("x_status"),
        "x_status_now": signal.get("x_status_now") or signal.get("x_status") or entry_snapshot.get("x_status"),
        "bundle_cluster_score": signal.get("bundle_cluster_score") or entry_snapshot.get("bundle_cluster_score"),
        "bundle_cluster_score_now": signal.get("bundle_cluster_score_now") or signal.get("bundle_cluster_score") or entry_snapshot.get("bundle_cluster_score"),
        "cluster_sell_concentration_now": signal.get("cluster_sell_concentration_now"),
        "cluster_sell_concentration_120s": signal.get("cluster_sell_concentration_120s") or entry_snapshot.get("cluster_sell_concentration_120s"),
        "liquidity_refill_ratio_now": signal.get("liquidity_refill_ratio_now"),
        "liquidity_refill_ratio_120s": signal.get("liquidity_refill_ratio_120s") or entry_snapshot.get("liquidity_refill_ratio_120s"),
        "seller_reentry_ratio": signal.get("seller_reentry_ratio") or entry_snapshot.get("seller_reentry_ratio"),
        "liquidity_shock_recovery_sec": signal.get("liquidity_shock_recovery_sec") or entry_snapshot.get("liquidity_shock_recovery_sec"),
        "cluster_concentration_ratio_now": signal.get("cluster_concentration_ratio_now") or signal.get("cluster_concentration_ratio") or entry_snapshot.get("cluster_concentration_ratio"),
        "bundle_composition_dominant_now": signal.get("bundle_composition_dominant_now") or signal.get("bundle_composition_dominant") or entry_snapshot.get("bundle_composition_dominant"),
        "bundle_failure_retry_pattern_now": signal.get("bundle_failure_retry_pattern_now") or signal.get("bundle_failure_retry_pattern") or entry_snapshot.get("bundle_failure_retry_pattern"),
        "bundle_failure_retry_delta": signal.get("bundle_failure_retry_delta"),
        "cross_block_bundle_correlation_now": signal.get("cross_block_bundle_correlation_now") or signal.get("cross_block_bundle_correlation") or entry_snapshot.get("cross_block_bundle_correlation"),
        "creator_in_cluster_flag_now": signal.get("creator_in_cluster_flag_now") if signal.get("creator_in_cluster_flag_now") is not None else signal.get("creator_in_cluster_flag"),
        "creator_cluster_activity_now": signal.get("creator_cluster_activity_now"),
        "linkage_risk_score_now": signal.get("linkage_risk_score_now") or signal.get("linkage_risk_score"),
        "linkage_confidence": signal.get("linkage_confidence"),
        "creator_buyer_link_score_now": signal.get("creator_buyer_link_score_now") or signal.get("creator_buyer_link_score"),
        "dev_buyer_link_score_now": signal.get("dev_buyer_link_score_now") or signal.get("dev_buyer_link_score"),
        "shared_funder_link_score_now": signal.get("shared_funder_link_score_now") or signal.get("shared_funder_link_score"),
        "cluster_dev_link_score_now": signal.get("cluster_dev_link_score_now") or signal.get("cluster_dev_link_score"),
        "wallet_features": signal.get("wallet_features") or entry_snapshot.get("wallet_features") or {},
        "now_ts": utc_now_iso(),
    }


def _build_market_states(signals: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: dict[str, dict[str, Any]] = {}
    for signal in signals:
        token = str(signal.get("token_address") or "")
        if token:
            seen[token] = _market_state_from_signal(signal)
    return list(seen.values())


def _runtime_market_state_cache(state: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return state.setdefault("runtime_market_state_cache", {})


def _update_runtime_market_state_cache(state: dict[str, Any], market_states: list[dict[str, Any]]) -> None:
    cache = _runtime_market_state_cache(state)
    for market in market_states:
        token = str(market.get("token_address") or "")
        if not token:
            continue
        cache[token] = {**dict(market), "cached_at": str(market.get("now_ts") or utc_now_iso())}


def _classify_fallback_status(current: dict[str, Any]) -> tuple[str, float, str]:
    present = [
        current.get("price_usd_now") is not None,
        current.get("liquidity_usd_now") is not None,
        current.get("buy_pressure_now") is not None,
        current.get("volume_velocity_now") is not None,
        current.get("x_status_now") is not None or current.get("x_validation_score_now") is not None,
    ]
    coverage = round(sum(1 for item in present if item) / len(present), 4)
    if current.get("price_usd_now") is not None and coverage <= 0.4:
        return "fallback_price_only", coverage, "position_missing_from_fresh_signals_price_only_fallback"
    return "fallback_partial", coverage, "position_missing_from_fresh_signals_partial_fallback"


def _summarize_current_states(current_states: list[dict[str, Any]]) -> dict[str, int]:
    summary = {
        "runtime_current_state_live_count": 0,
        "runtime_current_state_fallback_count": 0,
        "runtime_current_state_stale_count": 0,
        "runtime_current_state_refresh_failed_count": 0,
    }
    for current in current_states:
        status = str(current.get("runtime_current_state_status") or "unknown")
        if status == "live_refresh":
            summary["runtime_current_state_live_count"] += 1
        elif status in {"fallback_price_only", "fallback_partial"}:
            summary["runtime_current_state_fallback_count"] += 1
        elif status == "stale_entry_snapshot":
            summary["runtime_current_state_stale_count"] += 1
        elif status == "refresh_failed":
            summary["runtime_current_state_refresh_failed_count"] += 1
    return summary


def _accumulate_runtime_metrics(state: dict[str, Any], current_state_summary: dict[str, int]) -> None:
    metrics = state.setdefault("runtime_metrics", {})
    for key, value in current_state_summary.items():
        metrics[key] = int(metrics.get(key, 0)) + int(value or 0)


def _build_current_states(state: dict[str, Any], signals: list[dict[str, Any]]) -> list[dict[str, Any]]:
    market_states = _build_market_states(signals)
    market_by_token = {str(item.get("token_address") or ""): item for item in market_states}
    cache = _runtime_market_state_cache(state)
    current_states: list[dict[str, Any]] = []
    for position in _state_open_positions(state):
        token = str(position.get("token_address") or "")
        entry_snapshot = position.get("entry_snapshot") or {}
        current = dict(market_by_token.get(token) or {})
        current.setdefault("token_address", token)
        current.setdefault("price_usd_now", float(position.get("last_mark_price_usd") or position.get("entry_price_usd") or entry_snapshot.get("price_usd") or 0.0))
        current.setdefault("price_usd", current.get("price_usd_now"))
        current.setdefault("liquidity_usd_now", entry_snapshot.get("liquidity_usd"))
        current.setdefault("buy_pressure_now", entry_snapshot.get("buy_pressure"))
        current.setdefault("volume_velocity_now", entry_snapshot.get("volume_velocity"))
        current.setdefault("x_validation_score_now", entry_snapshot.get("x_validation_score"))
        current.setdefault("x_status_now", entry_snapshot.get("x_status"))
        current.setdefault("bundle_cluster_score_now", entry_snapshot.get("bundle_cluster_score"))
        current.setdefault("wallet_features", entry_snapshot.get("wallet_features") or {})
        current.setdefault("now_ts", utc_now_iso())

        if token in market_by_token:
            current["runtime_current_state_origin"] = "fresh_signal_batch"
            current["runtime_current_state_status"] = "live_refresh"
            current["runtime_current_state_warning"] = None
            current["runtime_current_state_confidence"] = 1.0
            cache[token] = {**dict(current), "cached_at": str(current.get("now_ts") or utc_now_iso())}
        else:
            cached = dict(cache.get(token) or {})
            if cached:
                cached.setdefault("token_address", token)
                cached.setdefault("price_usd_now", current.get("price_usd_now"))
                cached.setdefault("price_usd", cached.get("price_usd_now", current.get("price_usd")))
                cached.setdefault("liquidity_usd_now", current.get("liquidity_usd_now"))
                cached.setdefault("buy_pressure_now", current.get("buy_pressure_now"))
                cached.setdefault("volume_velocity_now", current.get("volume_velocity_now"))
                cached.setdefault("x_validation_score_now", current.get("x_validation_score_now"))
                cached.setdefault("x_status_now", current.get("x_status_now"))
                cached.setdefault("bundle_cluster_score_now", current.get("bundle_cluster_score_now"))
                cached.setdefault("wallet_features", current.get("wallet_features") or {})
                cached["now_ts"] = utc_now_iso()
                status, confidence, warning = _classify_fallback_status(cached)
                current = {**current, **cached}
                current["runtime_current_state_origin"] = "position_state_cache"
                current["runtime_current_state_status"] = status
                current["runtime_current_state_warning"] = warning
                current["runtime_current_state_confidence"] = confidence
            else:
                current["runtime_current_state_origin"] = "entry_snapshot"
                current["runtime_current_state_status"] = "stale_entry_snapshot"
                current["runtime_current_state_warning"] = "position_missing_from_fresh_signals_and_no_cached_refresh"
                current["runtime_current_state_confidence"] = 0.0

        current_states.append(current)
    return current_states


def _build_runtime_trading_settings(cfg: dict[str, Any], args: argparse.Namespace, run_dir: Path) -> Any:
    settings = dict(_DEFAULT_TRADING_SETTINGS)
    paper_cfg = cfg.get("paper", {}) if isinstance(cfg.get("paper"), dict) else {}
    exit_cfg = cfg.get("exit", {}) if isinstance(cfg.get("exit"), dict) else {}
    settings.update(paper_cfg)
    settings.update(exit_cfg)
    settings["PAPER_MAX_CONCURRENT_POSITIONS"] = int(cfg.get("modes", {}).get(args.mode, {}).get("max_open_positions", settings.get("PAPER_MAX_CONCURRENT_POSITIONS", 3)))
    settings["KILL_SWITCH_FILE"] = str(cfg.get("safety", {}).get("kill_switch_file", "runs/runtime/kill_switch.flag"))
    settings["PROCESSED_DATA_DIR"] = run_dir
    settings["SIGNALS_DIR"] = run_dir
    settings["TRADES_DIR"] = run_dir
    settings["POSITIONS_DIR"] = run_dir
    return SimpleNamespace(**settings)


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
        allowed = {"scalp": ["SCALP"], "trend": ["TREND"], "both": ["SCALP", "TREND"]}[args.allow_regime]
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
    trading_settings = _build_runtime_trading_settings(cfg, args, run_dir)
    state["paths"] = {"signals": run_dir / "signals.jsonl", "trades": run_dir / "trades.jsonl"}
    ensure_state(state, trading_settings)
    _sync_open_positions_compat(state)

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
    print(f"[promotion] state_restored resumed={str(args.resume).lower()} open_positions={len(_state_open_positions(state))}")
    print(f"[promotion] loop_started interval_sec={cfg.get('runtime', {}).get('loop_interval_sec', 30)}")

    total_opened = 0
    total_rejected = 0
    total_invalid = 0
    latest_signal_summary: dict[str, object] = {"batch_status": "missing", "origin_counts": {}, "status_counts": {}, "warnings": [], "origin_tier": None, "runtime_pipeline_origin": None, "runtime_pipeline_status": None, "runtime_pipeline_manifest": None}
    state.setdefault("runtime_metrics", {})

    for loop_idx in range(args.max_loops):
        roll_daily_state_if_needed(state)
        signals, signal_summary = _load_normalized_signals(args, loop_idx)
        latest_signal_summary = signal_summary
        _emit_signal_batch_events(event_log, args.run_id, signal_summary)
        opened = 0
        rejected = 0

        current_states = _build_current_states(state, signals)
        current_state_summary = _summarize_current_states(current_states)
        _accumulate_runtime_metrics(state, current_state_summary)
        append_jsonl(
            event_log,
            {
                "ts": utc_now_iso(),
                "event": "runtime_current_state_refresh_completed",
                "run_id": args.run_id,
                **current_state_summary,
            },
        )
        if _state_open_positions(state):
            run_mark_to_market(state, current_states, trading_settings)
            exit_signals = decide_exits(_state_open_positions(state), current_states, trading_settings)
            state = process_exit_signals(exit_signals, current_states, state, trading_settings)
            _sync_open_positions_compat(state)
            append_jsonl(
                event_log,
                {
                    "ts": utc_now_iso(),
                    "event": "runtime_exit_processing_completed",
                    "run_id": args.run_id,
                    "evaluated_positions": len(exit_signals),
                    "full_exit_count": len([row for row in exit_signals if row.get("exit_decision") == "FULL_EXIT"]),
                    "partial_exit_count": len([row for row in exit_signals if row.get("exit_decision") == "PARTIAL_EXIT"]),
                },
            )

        market_states = _build_market_states(signals)
        _update_runtime_market_state_cache(state, market_states)
        for signal in signals:
            token_address = str(signal.get("token_address") or "").strip()
            if not token_address:
                total_invalid += 1
                append_jsonl(
                    event_log,
                    {
                        "ts": utc_now_iso(),
                        "event": "runtime_signal_invalid",
                        "run_id": args.run_id,
                        "signal_id": signal.get("signal_id"),
                        "reason": "missing_token_address",
                    },
                )
                continue

            observe_x_signal(signal, state, cfg)
            guard_results = evaluate_entry_guards(signal, state, cfg)
            sizing = compute_position_sizing(signal, state, cfg)
            scale = float(sizing.get("effective_position_scale", 0.0))
            runtime_position_pct = float(
                signal.get("recommended_position_pct")
                or sizing.get("effective_position_pct")
                or sizing.get("base_position_pct")
                or 0.0
            )
            signal.update(
                {
                    "base_position_pct": runtime_position_pct,
                    "effective_position_pct": runtime_position_pct,
                    "sizing_multiplier": sizing.get("sizing_multiplier"),
                    "sizing_reason_codes": sizing.get("sizing_reason_codes", []),
                    "sizing_confidence": sizing.get("sizing_confidence"),
                    "sizing_origin": sizing.get("sizing_origin"),
                    "sizing_warning": sizing.get("sizing_warning"),
                    "evidence_quality_score": sizing.get("evidence_quality_score"),
                    "evidence_conflict_flag": sizing.get("evidence_conflict_flag"),
                    "partial_evidence_flag": sizing.get("partial_evidence_flag"),
                }
            )
            signal.setdefault("symbol", signal.get("token_address"))
            signal.setdefault("entry_snapshot", signal.get("entry_snapshot") or {"price_usd": _signal_price(signal)})
            signal["entry_snapshot"].setdefault("price_usd", _signal_price(signal))
            signal["entry_snapshot"].setdefault("liquidity_usd", signal.get("liquidity_usd"))
            signal["entry_snapshot"].setdefault("buy_pressure", signal.get("buy_pressure"))
            signal["entry_snapshot"].setdefault("volume_velocity", signal.get("volume_velocity"))
            signal["entry_snapshot"].setdefault("x_validation_score", signal.get("x_validation_score"))
            signal["entry_snapshot"].setdefault("x_status", signal.get("x_status"))
            signal["contract_version"] = trading_settings.PAPER_CONTRACT_VERSION

            if signal.get("x_status") == "degraded":
                register_degraded_x_entry_attempt(state, blocked=bool(should_block_entry(guard_results) or scale <= 0))

            if should_block_entry(guard_results) or scale <= 0:
                rejected += 1
                total_rejected += 1
                append_jsonl(
                    decisions_log,
                    {
                        "ts": utc_now_iso(),
                        "token_address": signal.get("token_address"),
                        "signal_id": signal.get("signal_id"),
                        "mode": args.mode,
                        "decision": "reject_entry",
                        "decision_reason_codes": guard_results.get("hard_block_reasons", []) or sizing.get("sizing_reason_codes", []),
                        "x_status": signal.get("x_status", "healthy"),
                        "guard_results": guard_results,
                        "degraded_x_guard": guard_results.get("degraded_x_guard", {}),
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
                        "event": "runtime_real_signal_rejected",
                        "run_id": args.run_id,
                        "signal_id": signal.get("signal_id"),
                        "token_address": signal.get("token_address"),
                        "signal_origin": signal.get("runtime_signal_origin"),
                        "signal_status": signal.get("runtime_signal_status"),
                        "reason": guard_results.get("hard_block_reasons", []) or sizing.get("sizing_reason_codes", []),
                        "degraded_x_guard": guard_results.get("degraded_x_guard", {}),
                    },
                )
                continue

            before_open = len(_state_open_positions(state))
            entry_signal = dict(signal)
            entry_signal["base_position_pct"] = runtime_position_pct
            entry_signal["effective_position_pct"] = runtime_position_pct
            state = process_entry_signals([entry_signal], market_states, state, trading_settings)
            opened_position = next(
                (
                    position
                    for position in _state_open_positions(state)
                    if position.get("token_address") == signal.get("token_address")
                ),
                None,
            )
            if opened_position is not None:
                opened_position["base_position_pct"] = runtime_position_pct
                opened_position["effective_position_pct"] = runtime_position_pct
            after_open = len(_state_open_positions(state))
            opened_delta = max(after_open - before_open, 0)
            if opened_delta > 0:
                opened += opened_delta
                total_opened += opened_delta
                if signal.get("x_status") == "degraded":
                    for _ in range(opened_delta):
                        register_degraded_x_entry_opened(state)
                for _ in range(opened_delta):
                    update_trade_counters(state, pnl_pct=0.0)
                append_jsonl(
                    decisions_log,
                    {
                        "ts": utc_now_iso(),
                        "token_address": signal.get("token_address"),
                        "signal_id": signal.get("signal_id"),
                        "mode": args.mode,
                        "decision": "open_paper_position",
                        "decision_reason_codes": guard_results.get("soft_reasons", []),
                        "x_status": signal.get("x_status", "healthy"),
                        "guard_results": guard_results,
                        "degraded_x_guard": guard_results.get("degraded_x_guard", {}),
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
            else:
                rejected += 1
                total_rejected += 1

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

        _sync_open_positions_compat(state)
        print(
            f"[promotion] signals_processed count={len(signals)} opened={opened} rejected={rejected} "
            f"origin={signal_summary.get('selected_origin')} status={signal_summary.get('batch_status')}"
        )
        if not args.dry_run:
            time.sleep(cfg.get("runtime", {}).get("loop_interval_sec", 30))

    positions_payload = {"positions": state.get("positions", []), "open_positions": _state_open_positions(state)}
    write_json(run_dir / "positions.json", positions_payload)
    degraded_x_guard = resolve_degraded_x_guard(args.mode, state, cfg)
    runtime_metrics = state.get("runtime_metrics", {})
    degraded_x_runtime = state.get("degraded_x_runtime", {})
    summary = {
        "run_id": args.run_id,
        "mode": args.mode,
        "trades_today": state.get("counters", {}).get("trades_today", 0),
        "open_positions": len(_state_open_positions(state)),
        "pnl_pct_today": state.get("counters", {}).get("pnl_pct_today", 0.0),
        "consecutive_losses": state.get("consecutive_losses", 0),
        "x_cooldown_active": is_x_cooldown_active(state),
        "degraded_x_budget_active": degraded_x_guard.get("budget_exhausted", False),
        "total_opened": total_opened,
        "total_rejected": total_rejected,
        "total_invalid": total_invalid,
        "runtime_current_state_live_count": runtime_metrics.get("runtime_current_state_live_count", 0),
        "runtime_current_state_fallback_count": runtime_metrics.get("runtime_current_state_fallback_count", 0),
        "runtime_current_state_stale_count": runtime_metrics.get("runtime_current_state_stale_count", 0),
        "runtime_current_state_refresh_failed_count": runtime_metrics.get("runtime_current_state_refresh_failed_count", 0),
        "degraded_x_entries_attempted": degraded_x_runtime.get("degraded_entries_attempted", 0),
        "degraded_x_entries_opened": degraded_x_runtime.get("degraded_entries_opened", 0),
        "degraded_x_entries_blocked": degraded_x_runtime.get("degraded_entries_blocked", 0),
        "runtime_signal_source": args.signal_source,
        "runtime_signal_origin": latest_signal_summary.get("selected_origin"),
        "runtime_signal_status": latest_signal_summary.get("batch_status"),
        "runtime_signal_status_counts": latest_signal_summary.get("status_counts", {}),
        "runtime_signal_origin_counts": latest_signal_summary.get("origin_counts", {}),
        "runtime_signal_warnings": latest_signal_summary.get("warnings", []),
        "runtime_origin_tier": latest_signal_summary.get("origin_tier"),
        "runtime_pipeline_origin": latest_signal_summary.get("runtime_pipeline_origin"),
        "runtime_pipeline_status": latest_signal_summary.get("runtime_pipeline_status"),
        "runtime_pipeline_manifest": latest_signal_summary.get("runtime_pipeline_manifest"),
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
