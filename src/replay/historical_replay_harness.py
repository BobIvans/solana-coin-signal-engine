from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import yaml

from src.replay.calibration_metrics import derive_outcome_metrics, extract_price_observations
from src.replay.deterministic import hash_config, make_run_paths
from src.replay.replay_input_loader import load_replay_inputs
from src.replay.wallet_mode_rescore import rescore_replay_inputs
from src.replay.replay_state_machine import ReplayStateMachine
from trading.exit_rules import evaluate_hard_exit, evaluate_scalp_exit, evaluate_trend_exit
from trading.regime_rules import decide_regime
from utils.bundle_contract_fields import copy_bundle_contract_fields, copy_linkage_contract_fields
from utils.io import ensure_dir, write_json
from utils.logger import log_info, log_warning
from utils.short_horizon_contract_fields import (
    CONTINUATION_METADATA_FIELDS,
    SHORT_HORIZON_SIGNAL_FIELDS,
    copy_continuation_metadata_fields,
    copy_short_horizon_contract_fields,
)
from utils.wallet_family_contract_fields import (
    SMART_WALLET_FAMILY_CONTRACT_FIELDS,
    copy_wallet_family_contract_fields,
)

_CONTRACT_VERSION = "replay_harness.v1"
_TRADE_FEATURE_MATRIX_SCHEMA_VERSION = "trade_feature_matrix.v1"
_REPLAY_SCORE_SOURCE_VALUES = {"mode_specific_scored_artifact", "generic_scored_artifact_rescored", "no_scored_artifact_passthrough"}
_WALLET_MODE_PARITY_STATUS_VALUES = {"comparable", "partial", "unavailable"}
_DEFAULT_TS = "2026-03-16T00:00:00Z"
_DEFAULT_OUTPUT_BASE = "runs"
_DEFAULT_REPLAY_SETTINGS = {
    "ENTRY_SELECTOR_FAILCLOSED": True,
    "ENTRY_SCALP_SCORE_MIN": 82,
    "ENTRY_TREND_SCORE_MIN": 86,
    "ENTRY_SCALP_MAX_AGE_SEC": 480,
    "ENTRY_RUG_MAX_SCALP": 0.30,
    "ENTRY_RUG_MAX_TREND": 0.20,
    "ENTRY_BUY_PRESSURE_MIN_SCALP": 0.75,
    "ENTRY_BUY_PRESSURE_MIN_TREND": 0.65,
    "ENTRY_FIRST30S_BUY_RATIO_MIN": 0.65,
    "ENTRY_BUNDLE_CLUSTER_MIN": 0.55,
    "ENTRY_SCALP_MIN_X_SCORE": 50,
    "ENTRY_TREND_MIN_X_SCORE": 65,
    "ENTRY_HOLDER_GROWTH_MIN_TREND": 20,
    "ENTRY_SMART_WALLET_HITS_MIN_TREND": 2,
    "ENTRY_TREND_MULTI_CLUSTER_MIN": 3,
    "ENTRY_TREND_CLUSTER_CONCENTRATION_MAX": 0.55,
    "ENTRY_TREND_DEV_SELL_MAX": 0.02,
    "ENTRY_SCALP_BUNDLE_COUNT_MIN": 2,
    "ENTRY_REGIME_CONFIDENCE_FLOOR_TREND": 0.55,
    "ENTRY_REGIME_CONFIDENCE_FLOOR_SCALP": 0.40,
    "RUG_DEV_SELL_PRESSURE_HARD": 0.25,
    "LINKAGE_HIGH_RISK_THRESHOLD": 0.70,
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
}
_DEFAULT_WALLET_FEATURES = {
    "smart_wallet_hits": 0,
    "smart_wallet_score_sum": 0.0,
    "smart_wallet_tier1_hits": 0,
    "smart_wallet_tier2_hits": 0,
    "smart_wallet_unique_count": 0,
    "smart_wallet_early_entry_hits": 0,
    "smart_wallet_netflow_bias": 0.0,
}
_TRADE_FEATURE_MATRIX_FIELDS = [
    "run_id", "ts", "token_address", "pair_address", "symbol", "config_hash", "decision", "entry_decision",
    "regime_decision", "regime_confidence", "regime_reason_flags", "regime_blockers", "expected_hold_class",
    "entry_confidence", "recommended_position_pct", "base_position_pct", "effective_position_pct", "sizing_multiplier",
    "sizing_reason_codes", "sizing_confidence", "sizing_origin", "sizing_warning", "evidence_quality_score",
    "evidence_conflict_flag", "partial_evidence_flag", "final_score_pre_wallet", "final_score", "onchain_core", "early_signal_bonus",
    "x_validation_bonus", "rug_penalty", "spam_penalty", "confidence_adjustment", "wallet_adjustment",
    "bundle_aggression_bonus", "organic_multi_cluster_bonus", "single_cluster_penalty", "creator_cluster_penalty",
    "cluster_dev_link_penalty", "shared_funder_penalty", "bundle_sell_heavy_penalty", "retry_manipulation_penalty",
    "age_sec", "age_minutes", "liquidity_usd", "buy_pressure_entry", "volume_velocity_entry", "holder_growth_5m_entry",
    "smart_wallet_hits_entry", *SHORT_HORIZON_SIGNAL_FIELDS, *CONTINUATION_METADATA_FIELDS, "x_status",
    "x_validation_score_entry", "x_validation_delta_entry", "bundle_count_first_60s", "bundle_size_value",
    "unique_wallets_per_bundle_avg", "bundle_timing_from_liquidity_add_min", "bundle_success_rate",
    "bundle_composition_dominant", "bundle_tip_efficiency", "bundle_failure_retry_pattern",
    "cross_block_bundle_correlation", "bundle_wallet_clustering_score", "cluster_concentration_ratio",
    "num_unique_clusters_first_60s", "creator_in_cluster_flag", "creator_dev_link_score", "creator_buyer_link_score",
    "dev_buyer_link_score", "shared_funder_link_score", "creator_cluster_link_score", "cluster_dev_link_score",
    "linkage_risk_score", "creator_funder_overlap_count", "buyer_funder_overlap_count", "funder_overlap_count",
    "linkage_reason_codes", "linkage_confidence", "linkage_metric_origin", "linkage_status", "linkage_warning",
    "smart_wallet_score_sum", "smart_wallet_tier1_hits", "smart_wallet_tier2_hits", "smart_wallet_unique_count",
    "smart_wallet_early_entry_hits", "smart_wallet_netflow_bias", *SMART_WALLET_FAMILY_CONTRACT_FIELDS, "exit_decision", "exit_reason_final", "exit_flags",
    "exit_warnings", "hold_sec", "gross_pnl_pct", "net_pnl_pct", "mfe_pct", "mae_pct", "time_to_first_profit_sec",
    "mfe_pct_240s", "mae_pct_240s", "trend_survival_15m", "trend_survival_60m", "wallet_weighting",
    "wallet_weighting_requested_mode", "wallet_weighting_effective_mode", "wallet_score_component_raw",
    "wallet_score_component_applied", "wallet_score_component_applied_shadow", "replay_score_source",
    "wallet_mode_parity_status", "score_contract_version", "historical_input_hash", "dry_run",
    "synthetic_trade_flag", "replay_input_origin", "replay_data_status", "replay_resolution_status", "synthetic_assist_flag",
    "schema_version",
]


@dataclass(frozen=True)
class ReplayArtifacts:
    signals: list[dict[str, Any]]
    trades: list[dict[str, Any]]
    positions: list[dict[str, Any]]
    trade_feature_matrix: list[dict[str, Any]]
    universe: list[dict[str, Any]]
    backfill: list[dict[str, Any]]
    events: list[dict[str, Any]]
    summary: dict[str, Any]
    manifest: dict[str, Any]


def _safe_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_wallet_features(*sources: dict[str, Any]) -> dict[str, Any]:
    features = dict(_DEFAULT_WALLET_FEATURES)
    for source in sources:
        candidate = source.get("wallet_features") if isinstance(source, dict) else None
        if isinstance(candidate, dict):
            features.update(candidate)
    return features


def _first_present(sources: list[dict[str, Any]], *fields: str) -> Any:
    for field in fields:
        for source in sources:
            if isinstance(source, dict) and field in source:
                return source.get(field)
    return None


def _merge_context(*sources: dict[str, Any]) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for source in sources:
        if isinstance(source, dict):
            merged.update(source)
            features = source.get("features")
            if isinstance(features, dict):
                merged.update(features)
            snapshot = source.get("entry_snapshot")
            if isinstance(snapshot, dict):
                merged.update(snapshot)
    return merged


def _load_config(path: str | Path | None) -> dict[str, Any]:
    if not path:
        return {}
    target = Path(path)
    if not target.exists():
        return {}
    return yaml.safe_load(target.read_text(encoding="utf-8")) or {}


def _build_settings(config: dict[str, Any], wallet_weighting: str) -> Any:
    settings = dict(_DEFAULT_REPLAY_SETTINGS)
    baseline_overrides = config.get("baseline") if isinstance(config.get("baseline"), dict) else {}
    candidate_overrides = (
        config.get("candidate")
        if isinstance(config.get("candidate"), dict)
        else config.get("candidate_overrides") if isinstance(config.get("candidate_overrides"), dict) else {}
    )
    root_overrides = {
        key: value
        for key, value in config.items()
        if key not in {"baseline", "grid", "candidate", "candidate_overrides", "input", "selection", "splits", "seed"}
    }
    settings.update(baseline_overrides)
    settings.update(root_overrides)
    settings.update(candidate_overrides)
    settings["WALLET_WEIGHTING_MODE"] = wallet_weighting
    return SimpleNamespace(**settings)


def _compute_config_hash(config: dict[str, Any], wallet_weighting: str, run_id: str) -> str:
    payload = {"config": config, "wallet_weighting": wallet_weighting, "run_id": run_id}
    return hash_config(payload)


def _scrub_for_hash(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _scrub_for_hash(item)
            for key, item in sorted(value.items())
            if key not in {"_source_file", "_source_line", "_source_index", "rescored_row"}
        }
    if isinstance(value, list):
        return [_scrub_for_hash(item) for item in value]
    return value


def _compute_historical_input_hash(loaded_inputs: dict[str, Any]) -> str:
    token_inputs: dict[str, Any] = {}
    for token, payload in sorted((loaded_inputs.get("token_inputs") or {}).items()):
        token_inputs[token] = {
            "token_address": payload.get("token_address"),
            "pair_address": payload.get("pair_address"),
            "warnings": sorted(set(payload.get("warnings") or [])),
            "malformed_rows": int(payload.get("malformed_rows") or 0),
            "entry_candidates": _scrub_for_hash(payload.get("entry_candidates") or []),
            "signals": _scrub_for_hash(payload.get("signals") or []),
            "trades": _scrub_for_hash(payload.get("trades") or []),
            "positions": _scrub_for_hash(payload.get("positions") or []),
            "price_paths": _scrub_for_hash(payload.get("price_paths") or []),
        }
    payload = {
        "artifact_dir": loaded_inputs.get("artifact_dir"),
        "loaded_files": {
            key: value
            for key, value in sorted((loaded_inputs.get("loaded_files") or {}).items())
            if key != "scored_rows"
        },
        "token_inputs": token_inputs,
        "universe": _scrub_for_hash(loaded_inputs.get("universe") or []),
    }
    return hash_config(payload)


def _coalesce_list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def _replay_score_metadata(base_context: dict[str, Any], token_payload: dict[str, Any], historical_input_hash: str) -> dict[str, Any]:
    rescored = token_payload.get("rescored_row") or {}
    return {
        "final_score_pre_wallet": rescored.get("final_score_pre_wallet", base_context.get("final_score_pre_wallet")),
        "wallet_weighting_requested_mode": token_payload.get("wallet_weighting_requested_mode") or rescored.get("wallet_weighting_requested_mode"),
        "wallet_weighting_effective_mode": token_payload.get("wallet_weighting_effective_mode") or rescored.get("wallet_weighting_effective_mode"),
        "wallet_score_component_raw": rescored.get("wallet_score_component_raw", 0.0),
        "wallet_score_component_applied": rescored.get("wallet_score_component_applied", 0.0),
        "wallet_score_component_applied_shadow": rescored.get("wallet_score_component_applied_shadow", 0.0),
        "replay_score_source": token_payload.get("replay_score_source", "no_scored_artifact_passthrough"),
        "wallet_mode_parity_status": token_payload.get("wallet_mode_parity_status", "unavailable"),
        "score_contract_version": token_payload.get("score_contract_version") or rescored.get("score_contract_version") or base_context.get("contract_version"),
        "historical_input_hash": historical_input_hash,
    }


def _jsonl_write(path: Path, rows: list[dict[str, Any]]) -> None:
    ensure_dir(path.parent)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n")


def _status_from_missing(missing_evidence: list[str]) -> str:
    return "historical" if not missing_evidence else "historical_partial"


def _entry_decision(context: dict[str, Any], regime: dict[str, Any], token_payload: dict[str, Any]) -> tuple[str, list[str]]:
    explicit = str(context.get("entry_decision") or context.get("decision") or "").strip().upper()
    reasons: list[str] = []
    if explicit in {"ENTER", "PAPER_ENTER", "BUY", "OPEN"}:
        return "ENTER", ["historical_entry_artifact"]
    if explicit in {"IGNORE", "SKIP", "BLOCKED", "REJECT"}:
        return "IGNORE", [f"historical_decision_{explicit.lower()}"]
    if token_payload.get("trades") or token_payload.get("positions"):
        return "ENTER", ["entry_reconstructed_from_trade_history"]
    if str(regime.get("regime_decision") or "").upper() == "IGNORE":
        return "IGNORE", ["regime_ignore"]
    return "IGNORE", ["no_entry_evidence"]


def _extract_entry_context(context: dict[str, Any], token_payload: dict[str, Any]) -> dict[str, Any]:
    first_trade = (token_payload.get("trades") or [{}])[0]
    first_position = (token_payload.get("positions") or [{}])[0]
    sources = [context, first_trade, first_position]
    entry_ts = _first_present(sources, "entry_time", "entry_ts", "opened_at", "ts", "timestamp") or _DEFAULT_TS
    entry_price = _first_present(sources, "entry_price", "entry_price_usd", "price", "avg_entry_price", "fill_price")
    pair_address = _first_present(sources, "pair_address", "pool_address")
    return {
        "entry_time": entry_ts,
        "entry_price": _safe_float(entry_price),
        "pair_address": pair_address,
    }


def _collect_observations(token_payload: dict[str, Any]) -> list[dict[str, Any]]:
    price_paths = token_payload.get("price_paths") or []
    rows: list[dict[str, Any]] = []
    for price_path in price_paths:
        observations = price_path.get("price_path") or []
        if isinstance(observations, list):
            rows.extend(obs for obs in observations if isinstance(obs, dict))
    rows.sort(key=lambda row: float(row.get("offset_sec", row.get("elapsed_sec", row.get("t", 0))) or 0.0))
    return rows


def _augment_current_context(base: dict[str, Any], observation: dict[str, Any], entry_price: float | None) -> dict[str, Any]:
    current = dict(base)
    current.update(observation)
    price = _safe_float(observation.get("price") if "price" in observation else observation.get("price_usd"))
    hold_sec = _safe_float(observation.get("offset_sec") if "offset_sec" in observation else observation.get("elapsed_sec") if "elapsed_sec" in observation else observation.get("t")) or 0.0
    current["hold_sec"] = int(hold_sec)
    current["price"] = price
    if entry_price and price is not None and entry_price > 0:
        current["pnl_pct"] = ((price - entry_price) / entry_price) * 100.0
        current.setdefault("gross_pnl_pct", current["pnl_pct"])
        current.setdefault("net_pnl_pct", current["pnl_pct"])
    return current


def _resolve_exit(base_context: dict[str, Any], entry: dict[str, Any], token_payload: dict[str, Any], regime_decision: str, state: ReplayStateMachine) -> dict[str, Any]:
    observations = _collect_observations(token_payload)
    price_path_missing = not observations
    price_path_truncated = any(bool(path.get("truncated")) for path in (token_payload.get("price_paths") or []))

    if price_path_missing:
        return {
            "resolution_status": "unresolved",
            "replay_data_status": "historical_partial",
            "warning": "missing_price_path",
            "exit_decision": None,
            "exit_reason_final": None,
            "exit_flags": [],
            "exit_warnings": ["missing_price_path"],
        }

    position_ctx = {
        "entry_snapshot": dict(base_context),
        "entry_price": entry.get("entry_price"),
        "opened_at": entry.get("entry_time"),
        "partials_taken": [],
    }
    last_current: dict[str, Any] | None = None
    partial_exit_events: list[str] = []

    for observation in observations:
        current = _augment_current_context(base_context, observation, entry.get("entry_price"))
        last_current = current
        hard = evaluate_hard_exit(position_ctx, current, _build_settings({}, "off"))
        if hard["exit_decision"] == "FULL_EXIT":
            state.full_exit(exit_reason=hard["exit_reason"], hold_sec=current.get("hold_sec"), pnl_pct=current.get("pnl_pct"))
            return {
                "resolution_status": "resolved",
                "replay_data_status": "historical",
                "exit_decision": hard["exit_decision"],
                "exit_reason_final": hard["exit_reason"],
                "exit_flags": hard["exit_flags"],
                "exit_warnings": hard["exit_warnings"],
                "exit_price": current.get("price"),
                "exit_time": observation.get("timestamp") or observation.get("ts") or entry.get("entry_time"),
                "hold_sec": current.get("hold_sec"),
                "gross_pnl_pct": current.get("pnl_pct"),
                "net_pnl_pct": current.get("pnl_pct"),
            }

        evaluator = evaluate_trend_exit if regime_decision == "TREND" else evaluate_scalp_exit
        decision = evaluator(position_ctx, current, _build_settings({}, "off"))
        if decision["exit_decision"] == "PARTIAL_EXIT":
            position_ctx.setdefault("partials_taken", []).append(f"partial_{len(position_ctx['partials_taken']) + 1}")
            partial_exit_events.append(decision["exit_reason"])
            state.partial_exit(exit_reason=decision["exit_reason"], hold_sec=current.get("hold_sec"), pnl_pct=current.get("pnl_pct"))
            continue
        if decision["exit_decision"] == "FULL_EXIT":
            state.full_exit(exit_reason=decision["exit_reason"], hold_sec=current.get("hold_sec"), pnl_pct=current.get("pnl_pct"))
            return {
                "resolution_status": "resolved",
                "replay_data_status": "historical" if not price_path_truncated else "historical_partial",
                "exit_decision": decision["exit_decision"],
                "exit_reason_final": decision["exit_reason"],
                "exit_flags": decision["exit_flags"],
                "exit_warnings": decision["exit_warnings"],
                "exit_price": current.get("price"),
                "exit_time": observation.get("timestamp") or observation.get("ts") or entry.get("entry_time"),
                "hold_sec": current.get("hold_sec"),
                "gross_pnl_pct": current.get("pnl_pct"),
                "net_pnl_pct": current.get("pnl_pct"),
            }

    if price_path_truncated:
        state.unresolved(warning="truncated_price_path")
        return {
            "resolution_status": "partial",
            "replay_data_status": "historical_partial",
            "warning": "truncated_price_path",
            "exit_decision": None,
            "exit_reason_final": None,
            "exit_flags": partial_exit_events,
            "exit_warnings": ["truncated_price_path"],
            "hold_sec": (last_current or {}).get("hold_sec"),
            "gross_pnl_pct": (last_current or {}).get("pnl_pct"),
            "net_pnl_pct": (last_current or {}).get("pnl_pct"),
        }

    if partial_exit_events:
        state.unresolved(warning="partial_exit_without_full_exit")
        return {
            "resolution_status": "partial",
            "replay_data_status": "historical_partial",
            "warning": "partial_exit_without_full_exit",
            "exit_decision": "PARTIAL_EXIT",
            "exit_reason_final": partial_exit_events[-1],
            "exit_flags": partial_exit_events,
            "exit_warnings": ["partial_exit_without_full_exit"],
            "hold_sec": (last_current or {}).get("hold_sec"),
            "gross_pnl_pct": (last_current or {}).get("pnl_pct"),
            "net_pnl_pct": (last_current or {}).get("pnl_pct"),
        }

    state.unresolved(warning="historical_exit_not_resolved")
    return {
        "resolution_status": "unresolved",
        "replay_data_status": "historical_partial",
        "warning": "historical_exit_not_resolved",
        "exit_decision": None,
        "exit_reason_final": None,
        "exit_flags": [],
        "exit_warnings": ["historical_exit_not_resolved"],
        "hold_sec": (last_current or {}).get("hold_sec"),
        "gross_pnl_pct": (last_current or {}).get("pnl_pct"),
        "net_pnl_pct": (last_current or {}).get("pnl_pct"),
    }


def _build_replay_contract_fields(
    *,
    base_context: dict[str, Any],
    signal_artifact: dict[str, Any] | None = None,
    trade_artifact: dict[str, Any] | None = None,
    position_artifact: dict[str, Any] | None = None,
) -> dict[str, Any]:
    features = _safe_dict(base_context.get("features"))
    entry_snapshot = _safe_dict(base_context.get("entry_snapshot"))
    fallback = {
        **_safe_dict(signal_artifact),
        **_safe_dict(trade_artifact),
        **_safe_dict(position_artifact),
        **features,
        **entry_snapshot,
    }
    return {
        **copy_bundle_contract_fields(base_context, fallback=fallback),
        **copy_linkage_contract_fields(base_context, fallback=fallback),
        **copy_short_horizon_contract_fields(base_context, fallback=fallback),
        **copy_continuation_metadata_fields(base_context, fallback=fallback),
        **copy_wallet_family_contract_fields(base_context, fallback=fallback),
    }


def _build_trade_feature_row(
    *,
    run_id: str,
    wallet_weighting: str,
    dry_run: bool,
    config_hash: str,
    base_context: dict[str, Any],
    signal: dict[str, Any],
    trade: dict[str, Any],
    replay_data_status: str,
    replay_resolution_status: str,
    replay_input_origin: str,
    synthetic_assist_flag: bool,
) -> dict[str, Any]:
    features = _safe_dict(base_context.get("features"))
    entry_snapshot = _safe_dict(base_context.get("entry_snapshot"))
    wallet_features = _safe_wallet_features(base_context, signal, trade)
    contract_fields = _build_replay_contract_fields(
        base_context=base_context,
        signal_artifact=signal,
        trade_artifact=trade,
    )
    sources = [trade, signal, base_context, features, entry_snapshot, wallet_features, contract_fields]
    calibration_metrics = derive_outcome_metrics(base_context, signal, trade, entry_snapshot, features)
    row = {field: None for field in _TRADE_FEATURE_MATRIX_FIELDS}
    row.update({
        "run_id": run_id,
        "ts": _first_present(sources, "ts", "entry_time", "entry_ts") or _DEFAULT_TS,
        "token_address": _first_present(sources, "token_address"),
        "pair_address": _first_present(sources, "pair_address"),
        "symbol": (_first_present(sources, "symbol") or None),
        "config_hash": config_hash,
        "decision": _first_present(sources, "decision", "entry_decision"),
        "entry_decision": _first_present(sources, "entry_decision", "decision"),
        "regime_decision": _first_present(sources, "regime_decision"),
        "regime_confidence": _first_present(sources, "regime_confidence"),
        "regime_reason_flags": _first_present(sources, "regime_reason_flags", "reason_flags"),
        "regime_blockers": _first_present(sources, "regime_blockers", "blockers"),
        "expected_hold_class": _first_present(sources, "expected_hold_class"),
        "entry_confidence": _first_present(sources, "entry_confidence"),
        "recommended_position_pct": _first_present(sources, "recommended_position_pct"),
        "base_position_pct": _first_present(sources, "base_position_pct"),
        "effective_position_pct": _first_present(sources, "effective_position_pct"),
        "sizing_multiplier": _first_present(sources, "sizing_multiplier"),
        "sizing_reason_codes": _first_present(sources, "sizing_reason_codes"),
        "sizing_confidence": _first_present(sources, "sizing_confidence"),
        "sizing_origin": _first_present(sources, "sizing_origin"),
        "sizing_warning": _first_present(sources, "sizing_warning"),
        "evidence_quality_score": _first_present(sources, "evidence_quality_score"),
        "evidence_conflict_flag": _first_present(sources, "evidence_conflict_flag"),
        "partial_evidence_flag": _first_present(sources, "partial_evidence_flag"),
        "final_score_pre_wallet": _first_present(sources, "final_score_pre_wallet"),
        "final_score": _first_present(sources, "final_score"),
        "onchain_core": _first_present(sources, "onchain_core"),
        "early_signal_bonus": _first_present(sources, "early_signal_bonus"),
        "x_validation_bonus": _first_present(sources, "x_validation_bonus"),
        "rug_penalty": _first_present(sources, "rug_penalty"),
        "spam_penalty": _first_present(sources, "spam_penalty"),
        "confidence_adjustment": _first_present(sources, "confidence_adjustment"),
        "wallet_adjustment": (
            wallet_adjustment.get("applied_delta")
            if isinstance((wallet_adjustment := _first_present(sources, "wallet_adjustment")), dict)
            else wallet_adjustment
        ),
        "bundle_aggression_bonus": _first_present(sources, "bundle_aggression_bonus"),
        "organic_multi_cluster_bonus": _first_present(sources, "organic_multi_cluster_bonus"),
        "single_cluster_penalty": _first_present(sources, "single_cluster_penalty"),
        "creator_cluster_penalty": _first_present(sources, "creator_cluster_penalty"),
        "cluster_dev_link_penalty": _first_present(sources, "cluster_dev_link_penalty"),
        "shared_funder_penalty": _first_present(sources, "shared_funder_penalty"),
        "bundle_sell_heavy_penalty": _first_present(sources, "bundle_sell_heavy_penalty"),
        "retry_manipulation_penalty": _first_present(sources, "retry_manipulation_penalty"),
        "age_sec": _first_present(sources, "age_sec"),
        "age_minutes": _first_present(sources, "age_minutes"),
        "liquidity_usd": _first_present(sources, "liquidity_usd"),
        "buy_pressure_entry": _first_present(sources, "buy_pressure_entry", "buy_pressure"),
        "volume_velocity_entry": _first_present(sources, "volume_velocity_entry", "volume_velocity"),
        "holder_growth_5m_entry": _first_present(sources, "holder_growth_5m_entry", "holder_growth_5m"),
        "smart_wallet_hits_entry": _first_present(sources, "smart_wallet_hits_entry", "smart_wallet_hits"),
        "x_status": _first_present(sources, "x_status"),
        "x_validation_score_entry": _first_present(sources, "x_validation_score_entry", "x_validation_score"),
        "x_validation_delta_entry": _first_present(sources, "x_validation_delta_entry", "x_validation_delta"),
        "creator_in_cluster_flag": _first_present(sources, "creator_in_cluster_flag"),
        "creator_dev_link_score": _first_present(sources, "creator_dev_link_score"),
        "creator_buyer_link_score": _first_present(sources, "creator_buyer_link_score"),
        "dev_buyer_link_score": _first_present(sources, "dev_buyer_link_score"),
        "shared_funder_link_score": _first_present(sources, "shared_funder_link_score"),
        "creator_cluster_link_score": _first_present(sources, "creator_cluster_link_score"),
        "cluster_dev_link_score": _first_present(sources, "cluster_dev_link_score"),
        "linkage_risk_score": _first_present(sources, "linkage_risk_score"),
        "creator_funder_overlap_count": _first_present(sources, "creator_funder_overlap_count"),
        "buyer_funder_overlap_count": _first_present(sources, "buyer_funder_overlap_count"),
        "funder_overlap_count": _first_present(sources, "funder_overlap_count"),
        "linkage_reason_codes": _first_present(sources, "linkage_reason_codes"),
        "linkage_confidence": _first_present(sources, "linkage_confidence"),
        "linkage_metric_origin": _first_present(sources, "linkage_metric_origin"),
        "linkage_status": _first_present(sources, "linkage_status"),
        "linkage_warning": _first_present(sources, "linkage_warning"),
        "smart_wallet_score_sum": wallet_features.get("smart_wallet_score_sum"),
        "smart_wallet_tier1_hits": wallet_features.get("smart_wallet_tier1_hits"),
        "smart_wallet_tier2_hits": wallet_features.get("smart_wallet_tier2_hits"),
        "smart_wallet_unique_count": wallet_features.get("smart_wallet_unique_count"),
        "smart_wallet_early_entry_hits": wallet_features.get("smart_wallet_early_entry_hits"),
        "smart_wallet_netflow_bias": wallet_features.get("smart_wallet_netflow_bias"),
        "exit_decision": _first_present(sources, "exit_decision"),
        "exit_reason_final": _first_present(sources, "exit_reason_final"),
        "exit_flags": _first_present(sources, "exit_flags"),
        "exit_warnings": _first_present(sources, "exit_warnings"),
        "hold_sec": _first_present(sources, "hold_sec"),
        "gross_pnl_pct": _first_present(sources, "gross_pnl_pct"),
        "net_pnl_pct": _first_present(sources, "net_pnl_pct"),
        "mfe_pct": _first_present(sources, "mfe_pct"),
        "mae_pct": _first_present(sources, "mae_pct"),
        **contract_fields,
        **calibration_metrics,
        "wallet_weighting": wallet_weighting,
        "wallet_weighting_requested_mode": _first_present(sources, "wallet_weighting_requested_mode") or wallet_weighting,
        "wallet_weighting_effective_mode": _first_present(sources, "wallet_weighting_effective_mode") or wallet_weighting,
        "wallet_score_component_raw": _first_present(sources, "wallet_score_component_raw") or 0.0,
        "wallet_score_component_applied": _first_present(sources, "wallet_score_component_applied") or 0.0,
        "wallet_score_component_applied_shadow": _first_present(sources, "wallet_score_component_applied_shadow") or 0.0,
        "replay_score_source": _first_present(sources, "replay_score_source") or "no_scored_artifact_passthrough",
        "wallet_mode_parity_status": _first_present(sources, "wallet_mode_parity_status") or "unavailable",
        "score_contract_version": _first_present(sources, "score_contract_version"),
        "historical_input_hash": _first_present(sources, "historical_input_hash"),
        "dry_run": dry_run,
        "synthetic_trade_flag": synthetic_assist_flag,
        "replay_input_origin": replay_input_origin,
        "replay_data_status": replay_data_status,
        "replay_resolution_status": replay_resolution_status,
        "synthetic_assist_flag": synthetic_assist_flag,
        "schema_version": _TRADE_FEATURE_MATRIX_SCHEMA_VERSION,
    })
    return row


def replay_token_lifecycle(
    *,
    token_payload: dict[str, Any],
    run_id: str,
    wallet_weighting: str,
    dry_run: bool,
    config_hash: str,
    historical_input_hash: str,
    settings: Any,
    replay_input_origin: str = "historical",
    synthetic_assist_flag: bool = False,
) -> dict[str, Any]:
    raw_scored = (token_payload.get("scored_rows") or [None])[0] or {}
    rescored = token_payload.get("rescored_row") or {}
    scored = {**raw_scored, **rescored}
    candidate = (token_payload.get("entry_candidates") or [None])[0] or {}
    signal_artifact = (token_payload.get("signals") or [None])[0] or {}
    trade_artifact = (token_payload.get("trades") or [None])[0] or {}
    position_artifact = (token_payload.get("positions") or [None])[0] or {}
    replay_score_metadata = _replay_score_metadata(scored, token_payload, historical_input_hash)
    base_context = _merge_context(scored, candidate, signal_artifact, trade_artifact, position_artifact, replay_score_metadata)
    token_address = token_payload.get("token_address") or base_context.get("token_address") or "unknown_token"
    pair_address = token_payload.get("pair_address") or base_context.get("pair_address")
    historical_decision = _first_present([base_context, candidate, signal_artifact, trade_artifact, position_artifact], "decision", "entry_decision")
    historical_regime_decision = _first_present([base_context, candidate, signal_artifact, trade_artifact, position_artifact], "regime_decision")
    historical_regime_confidence = _first_present([base_context, candidate, signal_artifact, trade_artifact, position_artifact], "regime_confidence")
    historical_regime_reason_flags = _first_present([base_context, candidate, signal_artifact, trade_artifact, position_artifact], "regime_reason_flags", "reason_flags")
    historical_regime_blockers = _first_present([base_context, candidate, signal_artifact, trade_artifact, position_artifact], "regime_blockers", "blockers")
    historical_expected_hold_class = _first_present([base_context, candidate, signal_artifact, trade_artifact, position_artifact], "expected_hold_class")

    if historical_regime_decision is not None:
        scored["regime_decision"] = historical_regime_decision
        base_context["regime_decision"] = historical_regime_decision
    if historical_regime_confidence is not None:
        scored["regime_confidence"] = historical_regime_confidence
        base_context["regime_confidence"] = historical_regime_confidence
    if historical_regime_reason_flags is not None:
        scored["regime_reason_flags"] = historical_regime_reason_flags
        base_context["regime_reason_flags"] = historical_regime_reason_flags
    if historical_regime_blockers is not None:
        scored["regime_blockers"] = historical_regime_blockers
        base_context["regime_blockers"] = historical_regime_blockers
    if historical_expected_hold_class is not None:
        scored["expected_hold_class"] = historical_expected_hold_class
        base_context["expected_hold_class"] = historical_expected_hold_class

    scored.update(replay_score_metadata)
    base_context.update(replay_score_metadata)

    missing_evidence = []
    if not token_payload.get("price_paths"):
        missing_evidence.append("price_path")

    state = ReplayStateMachine(token_address=token_address)
    state.candidate_seen(pair_address=pair_address, run_id=run_id)
    log_info("replay_candidate_seen", run_id=run_id, token_address=token_address, pair_address=pair_address)

    regime = decide_regime({**base_context, "token_address": token_address, "pair_address": pair_address}, settings)
    entry_decision, entry_reason_codes = _entry_decision(base_context, regime, token_payload)

    signal_contract_fields = _build_replay_contract_fields(
        base_context=base_context,
        signal_artifact=signal_artifact,
        trade_artifact=trade_artifact,
        position_artifact=position_artifact,
    )
    signal = {
        "run_id": run_id,
        "ts": _first_present([base_context, signal_artifact, trade_artifact, position_artifact], "ts", "timestamp", "entry_time", "entry_ts") or _DEFAULT_TS,
        "token_address": token_address,
        "pair_address": pair_address,
        "symbol": base_context.get("symbol"),
        "decision": historical_decision or entry_decision,
        "entry_decision": historical_decision or entry_decision,
        "decision_reason_codes": entry_reason_codes,
        "regime_decision": historical_regime_decision if historical_regime_decision is not None else regime.get("regime_decision"),
        "regime_confidence": historical_regime_confidence if historical_regime_confidence is not None else regime.get("regime_confidence"),
        "regime_reason_flags": historical_regime_reason_flags if historical_regime_reason_flags is not None else regime.get("regime_reason_flags"),
        "regime_blockers": historical_regime_blockers if historical_regime_blockers is not None else regime.get("regime_blockers"),
        "expected_hold_class": historical_expected_hold_class if historical_expected_hold_class is not None else regime.get("expected_hold_class"),
        "entry_confidence": base_context.get("entry_confidence"),
        "recommended_position_pct": base_context.get("recommended_position_pct"),
        "final_score_pre_wallet": base_context.get("final_score_pre_wallet"),
        "final_score": base_context.get("final_score"),
        "x_status": base_context.get("x_status"),
        "x_validation_score": base_context.get("x_validation_score"),
        "x_validation_delta": base_context.get("x_validation_delta"),
        **replay_score_metadata,
        **signal_contract_fields,
        "features": _safe_dict(base_context.get("features")) or {k: v for k, v in base_context.items() if k not in {"wallet_features", "entry_snapshot", "price_path"}},
        "wallet_features": _safe_wallet_features(base_context, signal_artifact, trade_artifact),
        "replay_input_origin": replay_input_origin,
        "replay_data_status": "synthetic_smoke" if synthetic_assist_flag else _status_from_missing(missing_evidence),
        "synthetic_assist_flag": synthetic_assist_flag,
    }

    trade: dict[str, Any] | None = None
    position: dict[str, Any] = {
        "run_id": run_id,
        "token_address": token_address,
        "pair_address": pair_address,
        "status": "ignored",
        "resolution_status": "ignored",
        "opened_at": None,
        "closed_at": None,
        "warnings": [],
        "replay_data_status": signal["replay_data_status"],
        **replay_score_metadata,
    }

    if entry_decision != "ENTER":
        state.ignore(reason=entry_reason_codes[0])
        position.update({
            "status": "ignored",
            "resolution_status": state.resolution_status,
            "warnings": entry_reason_codes,
        })
        return {
            "signal": signal,
            "trade": None,
            "position": position,
            "trade_feature_row": None,
            "universe_row": {"run_id": run_id, "token_address": token_address, "pair_address": pair_address, "historical_input_hash": historical_input_hash},
            "backfill_row": {"run_id": run_id, "token_address": token_address, "status": signal["replay_data_status"], "historical_input_hash": historical_input_hash},
            "events": state.snapshot()["events"],
            "resolution_status": state.resolution_status,
            "replay_data_status": signal["replay_data_status"],
        }

    entry = _extract_entry_context(base_context, token_payload)
    if entry.get("entry_price") is None:
        missing_evidence.append("entry_price")
    state.open_position(entry_time=entry["entry_time"], entry_price=entry.get("entry_price"))
    log_info("replay_position_opened", run_id=run_id, token_address=token_address, entry_time=entry["entry_time"])

    exit_payload = _resolve_exit(base_context, entry, token_payload, str(regime.get("regime_decision") or "SCALP").upper(), state)
    if exit_payload.get("warning"):
        log_warning("replay_unresolved", run_id=run_id, token_address=token_address, warning=exit_payload["warning"])
    elif exit_payload.get("exit_decision") == "FULL_EXIT":
        log_info("replay_full_exit", run_id=run_id, token_address=token_address, exit_reason=exit_payload.get("exit_reason_final"))

    if synthetic_assist_flag:
        replay_data_status = "synthetic_smoke"
    else:
        replay_data_status = "historical_partial" if missing_evidence or exit_payload.get("replay_data_status") == "historical_partial" else "historical"
    replay_resolution_status = exit_payload.get("resolution_status", "unresolved")

    trade_contract_fields = _build_replay_contract_fields(
        base_context=base_context,
        signal_artifact=signal_artifact,
        trade_artifact=trade_artifact,
        position_artifact=position_artifact,
    )
    trade = {
        "run_id": run_id,
        "trade_id": f"{run_id}:{token_address}",
        "token_address": token_address,
        "pair_address": pair_address,
        "symbol": base_context.get("symbol"),
        "side": "buy",
        "decision": historical_decision or entry_decision,
        "entry_decision": historical_decision or entry_decision,
        "entry_ts": entry["entry_time"],
        "entry_time": entry["entry_time"],
        "entry_price": entry.get("entry_price"),
        "exit_ts": exit_payload.get("exit_time"),
        "exit_time": exit_payload.get("exit_time"),
        "exit_price": exit_payload.get("exit_price"),
        "exit_decision": exit_payload.get("exit_decision"),
        "exit_reason_final": exit_payload.get("exit_reason_final"),
        "exit_flags": exit_payload.get("exit_flags"),
        "exit_warnings": exit_payload.get("exit_warnings"),
        "hold_sec": exit_payload.get("hold_sec"),
        "gross_pnl_pct": exit_payload.get("gross_pnl_pct"),
        "net_pnl_pct": exit_payload.get("net_pnl_pct"),
        "regime_decision": historical_regime_decision if historical_regime_decision is not None else regime.get("regime_decision"),
        "regime_confidence": historical_regime_confidence if historical_regime_confidence is not None else regime.get("regime_confidence"),
        "regime_reason_flags": historical_regime_reason_flags if historical_regime_reason_flags is not None else regime.get("regime_reason_flags"),
        "regime_blockers": historical_regime_blockers if historical_regime_blockers is not None else regime.get("regime_blockers"),
        "expected_hold_class": historical_expected_hold_class if historical_expected_hold_class is not None else regime.get("expected_hold_class"),
        **replay_score_metadata,
        **trade_contract_fields,
        "replay_input_origin": replay_input_origin,
        "replay_data_status": replay_data_status,
        "replay_resolution_status": replay_resolution_status,
        "synthetic_assist_flag": synthetic_assist_flag,
    }
    trade_observations = extract_price_observations(trade, *[path for path in token_payload.get("price_paths") or []])
    if trade_observations and entry.get("entry_price"):
        pnls = [((obs.price - entry["entry_price"]) / entry["entry_price"]) * 100.0 for obs in trade_observations]
        trade["mfe_pct"] = max(pnls)
        trade["mae_pct"] = min(pnls)
        trade["price_path"] = [{"offset_sec": obs.offset_sec, "price": obs.price} for obs in trade_observations]

    position.update({
        "status": "closed" if replay_resolution_status == "resolved" else "open",
        "resolution_status": replay_resolution_status,
        "opened_at": entry["entry_time"],
        "closed_at": exit_payload.get("exit_time"),
        "warnings": [*missing_evidence, *(exit_payload.get("exit_warnings") or [])],
        "entry_price": entry.get("entry_price"),
        "exit_price": exit_payload.get("exit_price"),
        "gross_pnl_pct": exit_payload.get("gross_pnl_pct"),
        "net_pnl_pct": exit_payload.get("net_pnl_pct"),
        "replay_data_status": replay_data_status,
        "synthetic_assist_flag": synthetic_assist_flag,
    })

    trade_feature_row = _build_trade_feature_row(
        run_id=run_id,
        wallet_weighting=wallet_weighting,
        dry_run=dry_run,
        config_hash=config_hash,
        base_context={**base_context, **trade},
        signal=signal,
        trade=trade,
        replay_data_status=replay_data_status,
        replay_resolution_status=replay_resolution_status,
        replay_input_origin=replay_input_origin,
        synthetic_assist_flag=synthetic_assist_flag,
    )

    return {
        "signal": signal,
        "trade": trade,
        "position": position,
        "trade_feature_row": trade_feature_row,
        "universe_row": {"run_id": run_id, "token_address": token_address, "pair_address": pair_address, "historical_input_hash": historical_input_hash},
        "backfill_row": {"run_id": run_id, "token_address": token_address, "status": replay_data_status, "historical_input_hash": historical_input_hash},
        "events": state.snapshot()["events"],
        "resolution_status": replay_resolution_status,
        "replay_data_status": replay_data_status,
    }


def _synthetic_smoke_payload(run_id: str) -> dict[str, Any]:
    return {
        "artifact_dir": "synthetic_smoke",
        "loaded_files": {},
        "token_inputs": {
            "token_smoke_1": {
                "token_address": "token_smoke_1",
                "pair_address": "pair_smoke_1",
                "warnings": [],
                "malformed_rows": 0,
                "scored_rows": [{
                    "token_address": "token_smoke_1",
                    "pair_address": "pair_smoke_1",
                    "symbol": "SMOKE",
                    "final_score": 90,
                    "regime_candidate": "ENTRY_CANDIDATE",
                    "rug_score": 0.1,
                    "rug_verdict": "PASS",
                    "buy_pressure": 0.86,
                    "first30s_buy_ratio": 0.80,
                    "bundle_cluster_score": 0.8,
                    "volume_velocity": 4.5,
                    "dev_sell_pressure_5m": 0.0,
                    "x_validation_score": 70,
                    "x_validation_delta": 2,
                    "holder_growth_5m": 26,
                    "smart_wallet_hits": 3,
                    "lp_burn_confirmed": True,
                    "mint_revoked": True,
                    "bundle_count_first_60s": 3,
                    "bundle_timing_from_liquidity_add_min": 0.7,
                    "bundle_success_rate": 0.75,
                    "bundle_composition_dominant": "buy-only",
                    "bundle_failure_retry_pattern": 1,
                    "bundle_wallet_clustering_score": 0.48,
                    "cluster_concentration_ratio": 0.35,
                    "num_unique_clusters_first_60s": 4,
                    "creator_in_cluster_flag": False,
                    "entry_confidence": 0.8,
                    "recommended_position_pct": 0.3,
                    "entry_price": 1.0,
                    "entry_time": _DEFAULT_TS,
                }],
                "entry_candidates": [{"token_address": "token_smoke_1", "pair_address": "pair_smoke_1", "entry_decision": "ENTER"}],
                "signals": [],
                "trades": [],
                "positions": [],
                "price_paths": [{"token_address": "token_smoke_1", "price_path": [
                    {"offset_sec": 0, "price": 1.0, "timestamp": _DEFAULT_TS},
                    {"offset_sec": 30, "price": 1.08, "timestamp": _DEFAULT_TS},
                    {"offset_sec": 60, "price": 1.12, "timestamp": _DEFAULT_TS},
                    {"offset_sec": 95, "price": 1.05, "timestamp": _DEFAULT_TS},
                ]}],
            }
        },
        "validation": {
            "warnings": ["synthetic_smoke_assist_used"],
            "historical_rows": 0,
            "partial_rows": 0,
            "malformed_tokens": 0,
            "token_status": {
                "token_smoke_1": {
                    "token_address": "token_smoke_1",
                    "missing_evidence": [],
                    "replay_data_status": "synthetic_smoke",
                    "warnings": ["synthetic_smoke_assist_used"],
                }
            },
        },
        "warnings": ["synthetic_smoke_assist_used"],
        "synthetic_assist": True,
        "run_id": run_id,
    }


def write_replay_outputs(*, run_id: str, artifacts: ReplayArtifacts, output_base_dir: str | Path) -> dict[str, str]:
    paths = make_run_paths(run_id, base_dir=str(output_base_dir))
    _jsonl_write(paths.signals_path, artifacts.signals)
    _jsonl_write(paths.trades_path, artifacts.trades)
    _jsonl_write(paths.universe_path, artifacts.universe)
    _jsonl_write(paths.backfill_path, artifacts.backfill)
    _jsonl_write(paths.run_dir / "trade_feature_matrix.jsonl", artifacts.trade_feature_matrix)
    _jsonl_write(paths.run_dir / "events.jsonl", artifacts.events)
    write_json(paths.positions_path, {"positions": artifacts.positions})
    write_json(paths.summary_json_path, artifacts.summary)
    paths.summary_md_path.write_text(artifacts.summary["summary_markdown"], encoding="utf-8")
    write_json(paths.manifest_path, artifacts.manifest)
    return {
        "run_dir": str(paths.run_dir),
        "signals": str(paths.signals_path),
        "trades": str(paths.trades_path),
        "positions": str(paths.positions_path),
        "summary": str(paths.summary_json_path),
        "manifest": str(paths.manifest_path),
    }


def run_historical_replay(
    *,
    artifact_dir: str | Path,
    run_id: str,
    config_path: str | Path | None = None,
    wallet_weighting: str = "off",
    dry_run: bool = False,
    output_base_dir: str | Path = _DEFAULT_OUTPUT_BASE,
    allow_synthetic_smoke: bool = False,
) -> dict[str, Any]:
    config = _load_config(config_path)
    settings = _build_settings(config, wallet_weighting)
    config_hash = _compute_config_hash(config, wallet_weighting, run_id)

    log_info("historical_replay_started", run_id=run_id, artifact_dir=str(artifact_dir), wallet_weighting=wallet_weighting)
    loaded_inputs = load_replay_inputs(artifact_dir=artifact_dir, wallet_weighting=wallet_weighting)
    synthetic_assist_flag = False
    replay_mode = "historical"
    input_origin = "historical"
    historical_input_hash = _compute_historical_input_hash(loaded_inputs) if loaded_inputs.get("token_inputs") else hash_config({"artifact_dir": str(artifact_dir)})
    rescore_metadata = {
        "rescored_rows": 0,
        "replay_score_source": "no_scored_artifact_passthrough",
        "wallet_mode_parity_status": "unavailable",
        "score_contract_version": None,
    }

    if not loaded_inputs.get("token_inputs"):
        if not allow_synthetic_smoke:
            log_warning("historical_replay_failed", run_id=run_id, warning="no_historical_inputs_found")
        synthetic_assist_flag = allow_synthetic_smoke
        loaded_inputs = _synthetic_smoke_payload(run_id) if allow_synthetic_smoke else loaded_inputs
        replay_mode = "synthetic_smoke" if allow_synthetic_smoke else "historical"
        input_origin = "synthetic_smoke" if allow_synthetic_smoke else "historical"
        historical_input_hash = _compute_historical_input_hash(loaded_inputs) if loaded_inputs.get("token_inputs") else historical_input_hash

    rescore_metadata = rescore_replay_inputs(
        loaded_inputs.get("token_inputs", {}),
        wallet_weighting=wallet_weighting,
        scored_input_kind=str(loaded_inputs.get("scored_input_kind") or "missing"),
    )

    log_info(
        "replay_inputs_loaded",
        run_id=run_id,
        token_count=len(loaded_inputs.get("token_inputs", {})),
        warnings=loaded_inputs.get("validation", {}).get("warnings", []),
        replay_score_source=rescore_metadata.get("replay_score_source"),
        wallet_mode_parity_status=rescore_metadata.get("wallet_mode_parity_status"),
    )

    results = [
        replay_token_lifecycle(
            token_payload=payload,
            run_id=run_id,
            wallet_weighting=wallet_weighting,
            dry_run=dry_run,
            config_hash=config_hash,
            historical_input_hash=historical_input_hash,
            settings=settings,
            replay_input_origin=input_origin,
            synthetic_assist_flag=synthetic_assist_flag,
        )
        for _token, payload in sorted(loaded_inputs.get("token_inputs", {}).items())
        if payload.get("token_address")
    ]

    signals = [result["signal"] for result in results]
    trades = [result["trade"] for result in results if result.get("trade")]
    positions = [result["position"] for result in results]
    trade_feature_matrix = [result["trade_feature_row"] for result in results if result.get("trade_feature_row")]
    universe = [result["universe_row"] for result in results]
    backfill = [result["backfill_row"] for result in results]
    events = [event for result in results for event in result.get("events", [])]

    historical_rows = sum(1 for result in results if result["replay_data_status"] == "historical")
    partial_rows = sum(1 for result in results if result["replay_data_status"] == "historical_partial")
    unresolved_rows = sum(1 for result in results if result["resolution_status"] in {"unresolved", "partial"})
    ignored_rows = sum(1 for result in results if result["resolution_status"] == "ignored")
    synthetic_used = synthetic_assist_flag
    if not replay_mode == "synthetic_smoke" and partial_rows:
        replay_mode = "historical_partial"

    warnings = list(dict.fromkeys([*(loaded_inputs.get("warnings") or []), *(loaded_inputs.get("validation", {}).get("warnings") or [])]))
    effective_modes = sorted({
        str(payload.get("wallet_weighting_effective_mode") or wallet_weighting)
        for payload in (loaded_inputs.get("token_inputs", {}) or {}).values()
        if payload.get("token_address")
    } or {wallet_weighting})
    summary_markdown = "\n".join([
        f"# Historical Replay Summary: {run_id}",
        "",
        f"- replay_mode: {replay_mode}",
        f"- input_origin: {input_origin}",
        f"- wallet_weighting_requested_mode: {wallet_weighting}",
        f"- wallet_weighting_effective_modes: {', '.join(effective_modes)}",
        f"- replay_score_source: {rescore_metadata.get('replay_score_source')}",
        f"- wallet_mode_parity_status: {rescore_metadata.get('wallet_mode_parity_status')}",
        f"- rescored_rows: {rescore_metadata.get('rescored_rows')}",
        f"- score_contract_version: {rescore_metadata.get('score_contract_version')}",
        f"- config_hash: {config_hash}",
        f"- historical_input_hash: {historical_input_hash}",
        f"- scored_input_file: {loaded_inputs.get('scored_input_file')}",
        f"- historical_rows_used: {historical_rows}",
        f"- partial_rows: {partial_rows}",
        f"- unresolved_rows: {unresolved_rows}",
        f"- ignored_rows: {ignored_rows}",
        f"- synthetic_fallback_used: {synthetic_used}",
        f"- signals: {len(signals)}",
        f"- trades: {len(trades)}",
        f"- trade_feature_matrix_rows: {len(trade_feature_matrix)}",
    ]) + "\n"

    summary = {
        "contract_version": _CONTRACT_VERSION,
        "run_id": run_id,
        "status": "ok",
        "replay_mode": replay_mode,
        "input_origin": input_origin,
        "wallet_weighting": wallet_weighting,
        "wallet_weighting_requested_mode": wallet_weighting,
        "wallet_weighting_effective_modes": effective_modes,
        "replay_score_source": rescore_metadata.get("replay_score_source"),
        "wallet_mode_parity_status": rescore_metadata.get("wallet_mode_parity_status"),
        "rescored_rows": rescore_metadata.get("rescored_rows"),
        "historical_input_hash": historical_input_hash,
        "score_contract_version": rescore_metadata.get("score_contract_version"),
        "scored_input_file": loaded_inputs.get("scored_input_file"),
        "config_hash": config_hash,
        "historical_rows_used": historical_rows,
        "partial_rows": partial_rows,
        "unresolved_rows": unresolved_rows,
        "ignored_rows": ignored_rows,
        "synthetic_fallback_used": synthetic_used,
        "signals": len(signals),
        "trades": len(trades),
        "trade_feature_matrix_rows": len(trade_feature_matrix),
        "warnings": warnings,
        "summary_markdown": summary_markdown,
    }
    manifest = {
        "contract_version": _CONTRACT_VERSION,
        "run_id": run_id,
        "replay_mode": replay_mode,
        "input_origin": input_origin,
        "wallet_weighting": wallet_weighting,
        "wallet_weighting_requested_mode": wallet_weighting,
        "wallet_weighting_effective_modes": effective_modes,
        "replay_score_source": rescore_metadata.get("replay_score_source"),
        "wallet_mode_parity_status": rescore_metadata.get("wallet_mode_parity_status"),
        "rescored_rows": rescore_metadata.get("rescored_rows"),
        "historical_input_hash": historical_input_hash,
        "score_contract_version": rescore_metadata.get("score_contract_version"),
        "scored_input_file": loaded_inputs.get("scored_input_file"),
        "config_hash": config_hash,
        "artifact_dir": str(artifact_dir),
        "synthetic_fallback_used": synthetic_used,
        "warnings": warnings,
        "artifacts": {
            "signals": "signals.jsonl",
            "trades": "trades.jsonl",
            "positions": "positions.json",
            "trade_feature_matrix": "trade_feature_matrix.jsonl",
            "replay_summary": "replay_summary.json",
            "replay_summary_md": "replay_summary.md",
            "manifest": "manifest.json",
        },
    }

    artifact_bundle = ReplayArtifacts(
        signals=signals,
        trades=trades,
        positions=positions,
        trade_feature_matrix=trade_feature_matrix,
        universe=universe,
        backfill=backfill,
        events=events,
        summary=summary,
        manifest=manifest,
    )
    outputs = write_replay_outputs(run_id=run_id, artifacts=artifact_bundle, output_base_dir=output_base_dir)
    log_info("historical_replay_completed", run_id=run_id, replay_mode=replay_mode, outputs=outputs)
    return {
        "inputs": loaded_inputs,
        "artifacts": artifact_bundle,
        "outputs": outputs,
        "summary": summary,
        "manifest": manifest,
    }
