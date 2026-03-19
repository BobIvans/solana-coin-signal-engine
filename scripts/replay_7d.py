#!/usr/bin/env python3
"""Deterministic replay shim with wallet-weighting toggles and required replay artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.append(str(REPO_ROOT))

from utils.io import ensure_dir, read_json, write_json
from utils.bundle_contract_fields import copy_bundle_contract_fields

_DEFAULT_WALLET_FEATURES = {
    "smart_wallet_hits": 0,
    "smart_wallet_score_sum": 0.0,
    "smart_wallet_tier1_hits": 0,
    "smart_wallet_tier2_hits": 0,
    "smart_wallet_unique_count": 0,
    "smart_wallet_early_entry_hits": 0,
    "smart_wallet_netflow_bias": 0.0,
}
_DEFAULT_TS = "2026-03-16T00:00:00Z"
_TRADE_FEATURE_MATRIX_SCHEMA_VERSION = "trade_feature_matrix.v1"
_TRADE_FEATURE_MATRIX_FIELDS = [
    "run_id",
    "ts",
    "token_address",
    "pair_address",
    "config_hash",
    "decision",
    "entry_decision",
    "regime_decision",
    "regime_confidence",
    "regime_reason_flags",
    "regime_blockers",
    "expected_hold_class",
    "final_score",
    "onchain_core",
    "early_signal_bonus",
    "x_validation_bonus",
    "rug_penalty",
    "spam_penalty",
    "confidence_adjustment",
    "wallet_adjustment",
    "bundle_aggression_bonus",
    "organic_multi_cluster_bonus",
    "single_cluster_penalty",
    "creator_cluster_penalty",
    "bundle_sell_heavy_penalty",
    "retry_manipulation_penalty",
    "age_sec",
    "age_minutes",
    "liquidity_usd",
    "buy_pressure_entry",
    "volume_velocity_entry",
    "holder_growth_5m_entry",
    "smart_wallet_hits_entry",
    "x_status",
    "x_validation_score_entry",
    "x_validation_delta_entry",
    "bundle_count_first_60s",
    "bundle_size_value",
    "unique_wallets_per_bundle_avg",
    "bundle_timing_from_liquidity_add_min",
    "bundle_success_rate",
    "bundle_composition_dominant",
    "bundle_tip_efficiency",
    "bundle_failure_retry_pattern",
    "cross_block_bundle_correlation",
    "bundle_wallet_clustering_score",
    "cluster_concentration_ratio",
    "num_unique_clusters_first_60s",
    "creator_in_cluster_flag",
    "smart_wallet_score_sum",
    "smart_wallet_tier1_hits",
    "smart_wallet_tier2_hits",
    "smart_wallet_unique_count",
    "smart_wallet_early_entry_hits",
    "smart_wallet_netflow_bias",
    "exit_decision",
    "exit_reason_final",
    "exit_flags",
    "exit_warnings",
    "hold_sec",
    "gross_pnl_pct",
    "net_pnl_pct",
    "mfe_pct",
    "mae_pct",
    "wallet_weighting",
    "dry_run",
    "synthetic_trade_flag",
    "schema_version",
]


def _safe_wallet_features(item: dict[str, Any]) -> dict[str, Any]:
    features = dict(_DEFAULT_WALLET_FEATURES)
    features.update(item.get("wallet_features") or {})
    return features


def _safe_bundle_fields(item: dict[str, Any]) -> dict[str, Any]:
    entry_snapshot = item.get("entry_snapshot") if isinstance(item.get("entry_snapshot"), dict) else {}
    return copy_bundle_contract_fields(item, fallback=entry_snapshot)


def _safe_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _first_present(sources: list[dict[str, Any]], *fields: str) -> Any:
    for field in fields:
        for source in sources:
            if field in source:
                return source.get(field)
    return None


def _normalize_wallet_adjustment(value: Any) -> Any:
    if not isinstance(value, dict):
        return value
    for key in ("applied_delta", "score_delta", "final_score_delta", "wallet_score_delta"):
        if key in value:
            return value.get(key)
    bonus = value.get("wallet_bonus_score")
    penalty = value.get("wallet_penalty_score")
    if bonus is not None or penalty is not None:
        return float(bonus or 0.0) - float(penalty or 0.0)
    return None


def build_trade_feature_row(
    *,
    args: argparse.Namespace,
    config_hash: str,
    item: dict[str, Any],
    signal: dict[str, Any],
    trade: dict[str, Any],
) -> dict[str, Any]:
    features = _safe_dict(item.get("features"))
    entry_snapshot = _safe_dict(item.get("entry_snapshot"))
    wallet_features = _safe_wallet_features(item)
    wallet_adjustment = _normalize_wallet_adjustment(
        _first_present(
            [_safe_dict(trade.get("wallet_adjustment")), _safe_dict(signal.get("wallet_adjustment")), _safe_dict(item.get("wallet_adjustment"))],
            "applied_delta",
            "score_delta",
            "final_score_delta",
            "wallet_score_delta",
        )
    )
    if wallet_adjustment is None:
        wallet_adjustment = _normalize_wallet_adjustment(
            _first_present([trade, signal, item], "wallet_adjustment")
        )

    sources = [
        trade,
        signal,
        item,
        features,
        entry_snapshot,
        wallet_features,
    ]
    row = {field: None for field in _TRADE_FEATURE_MATRIX_FIELDS}
    row.update(
        {
            "run_id": args.run_id,
            "ts": _first_present(sources, "ts") or args.start_ts or args.end_ts or _DEFAULT_TS,
            "token_address": _first_present(sources, "token_address"),
            "pair_address": _first_present(sources, "pair_address"),
            "config_hash": config_hash,
            "decision": _first_present(sources, "decision", "entry_decision"),
            "entry_decision": _first_present(sources, "entry_decision", "decision"),
            "regime_decision": _first_present(sources, "regime_decision", "regime_candidate"),
            "regime_confidence": _first_present(sources, "regime_confidence"),
            "regime_reason_flags": _first_present(sources, "regime_reason_flags", "reason_flags"),
            "regime_blockers": _first_present(sources, "regime_blockers"),
            "expected_hold_class": _first_present(sources, "expected_hold_class"),
            "final_score": _first_present(sources, "final_score"),
            "onchain_core": _first_present(sources, "onchain_core"),
            "early_signal_bonus": _first_present(sources, "early_signal_bonus"),
            "x_validation_bonus": _first_present(sources, "x_validation_bonus"),
            "rug_penalty": _first_present(sources, "rug_penalty"),
            "spam_penalty": _first_present(sources, "spam_penalty"),
            "confidence_adjustment": _first_present(sources, "confidence_adjustment"),
            "wallet_adjustment": wallet_adjustment,
            "bundle_aggression_bonus": _first_present(sources, "bundle_aggression_bonus"),
            "organic_multi_cluster_bonus": _first_present(sources, "organic_multi_cluster_bonus"),
            "single_cluster_penalty": _first_present(sources, "single_cluster_penalty"),
            "creator_cluster_penalty": _first_present(sources, "creator_cluster_penalty"),
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
            "bundle_count_first_60s": _first_present(sources, "bundle_count_first_60s"),
            "bundle_size_value": _first_present(sources, "bundle_size_value"),
            "unique_wallets_per_bundle_avg": _first_present(sources, "unique_wallets_per_bundle_avg"),
            "bundle_timing_from_liquidity_add_min": _first_present(sources, "bundle_timing_from_liquidity_add_min"),
            "bundle_success_rate": _first_present(sources, "bundle_success_rate"),
            "bundle_composition_dominant": _first_present(sources, "bundle_composition_dominant"),
            "bundle_tip_efficiency": _first_present(sources, "bundle_tip_efficiency"),
            "bundle_failure_retry_pattern": _first_present(sources, "bundle_failure_retry_pattern"),
            "cross_block_bundle_correlation": _first_present(sources, "cross_block_bundle_correlation"),
            "bundle_wallet_clustering_score": _first_present(sources, "bundle_wallet_clustering_score"),
            "cluster_concentration_ratio": _first_present(sources, "cluster_concentration_ratio"),
            "num_unique_clusters_first_60s": _first_present(sources, "num_unique_clusters_first_60s"),
            "creator_in_cluster_flag": _first_present(sources, "creator_in_cluster_flag"),
            "smart_wallet_score_sum": _first_present(sources, "smart_wallet_score_sum"),
            "smart_wallet_tier1_hits": _first_present(sources, "smart_wallet_tier1_hits"),
            "smart_wallet_tier2_hits": _first_present(sources, "smart_wallet_tier2_hits"),
            "smart_wallet_unique_count": _first_present(sources, "smart_wallet_unique_count"),
            "smart_wallet_early_entry_hits": _first_present(sources, "smart_wallet_early_entry_hits"),
            "smart_wallet_netflow_bias": _first_present(sources, "smart_wallet_netflow_bias"),
            "exit_decision": _first_present(sources, "exit_decision"),
            "exit_reason_final": _first_present(sources, "exit_reason_final"),
            "exit_flags": _first_present(sources, "exit_flags"),
            "exit_warnings": _first_present(sources, "exit_warnings"),
            "hold_sec": _first_present(sources, "hold_sec"),
            "gross_pnl_pct": _first_present(sources, "gross_pnl_pct"),
            "net_pnl_pct": _first_present(sources, "net_pnl_pct"),
            "mfe_pct": _first_present(sources, "mfe_pct"),
            "mae_pct": _first_present(sources, "mae_pct"),
            "wallet_weighting": args.wallet_weighting,
            "dry_run": args.dry_run,
            "synthetic_trade_flag": True,
            "schema_version": _TRADE_FEATURE_MATRIX_SCHEMA_VERSION,
        }
    )
    return row


def write_trade_feature_matrix(path: Path, rows: list[dict[str, Any]]) -> None:
    _jsonl_write(path, rows)


def _load_entry_candidates() -> list[dict[str, Any]]:
    raw = read_json(Path("data/processed/entry_candidates.json"), default=[])
    if isinstance(raw, dict):
        raw = raw.get("tokens") or raw.get("entries") or []
    if not isinstance(raw, list) or not raw:
        raw = [
            {
                "token_address": "token_smoke_1",
                "pair_address": "pair_smoke_1",
                "decision": "paper_enter",
                "x_status": "not_requested",
                "x_validation_score": 0.0,
                "features": {"age_minutes": 0, "liquidity_usd": 0},
                "wallet_features": {},
            }
        ]
    return [item for item in raw if isinstance(item, dict)]


def _jsonl_write(path: Path, rows: list[dict[str, Any]]) -> None:
    ensure_dir(path.parent)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n")


def _compute_config_hash(args: argparse.Namespace) -> str:
    payload = {
        "config": args.config,
        "days": args.days,
        "seed": args.seed,
        "wallet_weighting": args.wallet_weighting,
        "dry_run": args.dry_run,
        "start_ts": args.start_ts,
        "end_ts": args.end_ts,
    }
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config/replay.default.yaml")
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--wallet-weighting", choices=["on", "off"], default="off")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--start-ts", default=None)
    parser.add_argument("--end-ts", default=None)
    args = parser.parse_args()

    run_dir = ensure_dir(Path("runs") / args.run_id)
    entry_candidates = _load_entry_candidates()
    registry_payload = read_json("data/smart_wallets.registry.json", default={}) or {}
    registry_wallets = registry_payload.get("wallets", []) if isinstance(registry_payload, dict) else []

    weighting_enabled = args.wallet_weighting == "on"
    signals: list[dict[str, Any]] = []
    trades: list[dict[str, Any]] = []
    universe: list[dict[str, Any]] = []
    backfill: list[dict[str, Any]] = []
    trade_feature_matrix: list[dict[str, Any]] = []
    config_hash = _compute_config_hash(args)

    for idx, item in enumerate(entry_candidates, start=1):
        token_address = str(item.get("token_address") or f"token_{idx}")
        pair_address = str(item.get("pair_address") or f"pair_{idx}")
        wallet_features = _safe_wallet_features(item)
        ts = args.start_ts or args.end_ts or _DEFAULT_TS
        signal = {
            "run_id": args.run_id,
            "ts": ts,
            "token_address": token_address,
            "pair_address": pair_address,
            "decision": str(item.get("decision") or "paper_enter"),
            "x_status": str(item.get("x_status") or "not_requested"),
            "x_validation_score": float(item.get("x_validation_score") or 0.0),
            "features": item.get("features") or {},
            "wallet_features": wallet_features,
            "wallet_weighting": args.wallet_weighting,
            **_safe_bundle_fields(item),
        }
        trade = {
            "run_id": args.run_id,
            "ts": ts,
            "token_address": token_address,
            "pair_address": pair_address,
            "side": "buy",
            "qty": 1.0,
            "price": 1.0,
            "wallet_features": wallet_features,
            **_safe_bundle_fields(item),
        }
        universe.append({"run_id": args.run_id, "token_address": token_address, "pair_address": pair_address})
        backfill.append({"run_id": args.run_id, "token_address": token_address, "status": "synthetic"})
        signals.append(signal)
        trades.append(trade)
        trade_feature_matrix.append(
            build_trade_feature_row(
                args=args,
                config_hash=config_hash,
                item=item,
                signal=signal,
                trade=trade,
            )
        )

    applied_count = (
        sum(1 for item in signals if item["wallet_features"].get("smart_wallet_hits", 0) > 0)
        if weighting_enabled
        else 0
    )

    _jsonl_write(run_dir / "signals.jsonl", signals)
    _jsonl_write(run_dir / "trades.jsonl", trades)
    _jsonl_write(run_dir / "universe.jsonl", universe)
    _jsonl_write(run_dir / "backfill.jsonl", backfill)
    write_trade_feature_matrix(run_dir / "trade_feature_matrix.jsonl", trade_feature_matrix)

    positions_payload = {
        "positions": [
            {
                "run_id": args.run_id,
                "token_address": signal["token_address"],
                "status": "closed" if args.dry_run else "open",
                "opened_at": signal["ts"],
            }
            for signal in signals
        ]
    }
    write_json(run_dir / "positions.json", positions_payload)

    summary_payload = {
        "run_id": args.run_id,
        "status": "ok",
        "dry_run": args.dry_run,
        "wallet_weighting": args.wallet_weighting,
        "signals": len(signals),
        "trades": len(trades),
        "trade_feature_matrix_rows": len(trade_feature_matrix),
        "config_hash": config_hash,
    }
    write_json(run_dir / "replay_summary.json", summary_payload)
    (run_dir / "replay_summary.md").write_text(
        "\n".join(
            [
                f"# Replay Summary: {args.run_id}",
                "",
                f"- status: {summary_payload['status']}",
                f"- dry_run: {summary_payload['dry_run']}",
                f"- signals: {summary_payload['signals']}",
                f"- trades: {summary_payload['trades']}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    manifest_payload = {
        "run_id": args.run_id,
        "config": args.config,
        "days": args.days,
        "seed": args.seed,
        "start_ts": args.start_ts,
        "end_ts": args.end_ts,
        "dry_run": args.dry_run,
        "wallet_weighting": args.wallet_weighting,
        "config_hash": summary_payload["config_hash"],
    }
    write_json(run_dir / "manifest.json", manifest_payload)

    write_json(
        run_dir / "wallet_feature_stats.json",
        {
            "total_registry_wallets": len(registry_wallets),
            "active_wallets": sum(1 for item in registry_wallets if item.get("status") == "active"),
            "tier1_count": sum(1 for item in registry_wallets if item.get("tier") == "tier_1"),
            "tier2_count": sum(1 for item in registry_wallets if item.get("tier") == "tier_2"),
            "tier3_count": sum(1 for item in registry_wallets if item.get("tier") == "tier_3"),
            "signals_with_wallet_hits": applied_count,
            "trades_with_wallet_hits": applied_count,
            "avg_wallet_score_sum_per_signal": 0.0,
            "avg_wallet_score_sum_per_trade": 0.0,
        },
    )
    write_json(
        run_dir / "wallet_weighting_summary.json",
        {
            "wallet_weighting_enabled": weighting_enabled,
            "weighting_mode": "additive",
            "wallet_bonus_applied_count": applied_count,
            "wallet_penalty_applied_count": 0,
            "avg_bonus_score": 0.0,
            "avg_penalty_score": 0.0,
        },
    )

    print(f"[wallets] registry_loaded count={len(registry_wallets)}")
    print(f"[wallets] wallet_features_built signals={len(entry_candidates)}")
    if weighting_enabled:
        print(f"[wallets] wallet_weighting_applied count={applied_count}")
    print(f"[replay] done run_id={args.run_id} dry_run={args.dry_run}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
