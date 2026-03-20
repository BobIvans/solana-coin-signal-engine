#!/usr/bin/env python3
"""Deterministic evidence-weighted sizing smoke runner."""

from __future__ import annotations

import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.promotion.guards import compute_position_sizing, evaluate_entry_guards, should_block_entry
from utils.io import ensure_dir, write_json

SMOKE_DIR = REPO_ROOT / "data" / "smoke"
OUTPUT_JSON = SMOKE_DIR / "evidence_weighted_sizing_summary.json"
OUTPUT_MD = SMOKE_DIR / "evidence_weighted_sizing_summary.md"

BASE_CONFIG = {
    "modes": {
        "expanded_paper": {
            "open_positions": True,
            "max_open_positions": 3,
            "max_trades_per_day": 20,
            "allow_regimes": ["SCALP", "TREND"],
            "position_size_scale": 1.0,
        },
        "constrained_paper": {
            "open_positions": True,
            "max_open_positions": 1,
            "max_trades_per_day": 10,
            "allow_regimes": ["SCALP"],
            "position_size_scale": 0.5,
        },
    },
    "safety": {"max_daily_loss_pct": 8.0, "max_consecutive_losses": 4, "kill_switch_file": str(SMOKE_DIR / "kill.flag")},
    "degraded_x": {"constrained_policy": "watchlist_only", "expanded_policy": "reduced_size"},
}


def build_fixture_signals() -> list[dict]:
    return [
        {
            "name": "strong_healthy_confirmation",
            "mode": "expanded_paper",
            "state": {"active_mode": "expanded_paper", "open_positions": [], "counters": {}, "consecutive_losses": 0},
            "signal": {
                "signal_id": "fixture_strong",
                "token_address": "SoStrong111",
                "entry_decision": "TREND",
                "regime": "TREND",
                "recommended_position_pct": 0.42,
                "regime_confidence": 0.86,
                "runtime_signal_confidence": 0.88,
                "continuation_confidence": 0.79,
                "continuation_status": "confirmed",
                "linkage_confidence": 0.82,
                "linkage_risk_score": 0.14,
                "bundle_wallet_clustering_score": 0.74,
                "cluster_concentration_ratio": 0.22,
                "smart_wallet_hits": 4,
                "smart_wallet_tier1_hits": 1,
                "smart_wallet_netflow_bias": 0.45,
                "x_status": "healthy",
                "x_validation_score": 84,
                "entry_snapshot": {"creator_dev_link_score": 0.12},
            },
        },
        {
            "name": "degraded_x_otherwise_decent",
            "mode": "expanded_paper",
            "state": {"active_mode": "expanded_paper", "open_positions": [], "counters": {}, "consecutive_losses": 0},
            "signal": {
                "signal_id": "fixture_degraded_x",
                "token_address": "SoDeg111",
                "entry_decision": "SCALP",
                "regime": "SCALP",
                "recommended_position_pct": 0.40,
                "regime_confidence": 0.77,
                "runtime_signal_confidence": 0.73,
                "continuation_confidence": 0.63,
                "continuation_status": "confirmed",
                "linkage_confidence": 0.70,
                "linkage_risk_score": 0.18,
                "bundle_wallet_clustering_score": 0.68,
                "cluster_concentration_ratio": 0.31,
                "x_status": "degraded",
                "x_validation_score": 52,
            },
        },
        {
            "name": "partial_evidence",
            "mode": "expanded_paper",
            "state": {"active_mode": "expanded_paper", "open_positions": [], "counters": {}, "consecutive_losses": 0},
            "signal": {
                "signal_id": "fixture_partial",
                "token_address": "SoPartial111",
                "entry_decision": "SCALP",
                "regime": "SCALP",
                "recommended_position_pct": 0.35,
                "regime_confidence": 0.71,
                "runtime_signal_confidence": 0.58,
                "runtime_signal_partial_flag": True,
                "continuation_status": "missing",
                "linkage_status": "partial",
                "x_status": "healthy",
                "x_validation_score": 68,
            },
        },
        {
            "name": "creator_linkage_risk",
            "mode": "expanded_paper",
            "state": {"active_mode": "expanded_paper", "open_positions": [], "counters": {}, "consecutive_losses": 0},
            "signal": {
                "signal_id": "fixture_link_risk",
                "token_address": "SoRisk111",
                "entry_decision": "TREND",
                "regime": "TREND",
                "recommended_position_pct": 0.45,
                "regime_confidence": 0.83,
                "runtime_signal_confidence": 0.79,
                "continuation_confidence": 0.74,
                "continuation_status": "confirmed",
                "linkage_confidence": 0.80,
                "linkage_risk_score": 0.81,
                "creator_dev_link_score": 0.86,
                "creator_buyer_link_score": 0.77,
                "cluster_concentration_ratio": 0.48,
                "bundle_wallet_clustering_score": 0.71,
                "x_status": "healthy",
                "x_validation_score": 82,
            },
        },
        {
            "name": "conflicting_evidence",
            "mode": "expanded_paper",
            "state": {"active_mode": "expanded_paper", "open_positions": [], "counters": {}, "consecutive_losses": 0},
            "signal": {
                "signal_id": "fixture_conflict",
                "token_address": "SoConflict111",
                "entry_decision": "TREND",
                "regime": "TREND",
                "recommended_position_pct": 0.38,
                "regime_confidence": 0.84,
                "runtime_signal_confidence": 0.81,
                "continuation_confidence": 0.32,
                "continuation_status": "weak",
                "linkage_confidence": 0.78,
                "linkage_risk_score": 0.59,
                "bundle_wallet_clustering_score": 0.43,
                "cluster_concentration_ratio": 0.73,
                "x_status": "healthy",
                "x_validation_score": 75,
            },
        },
        {
            "name": "hard_blocked_case",
            "mode": "constrained_paper",
            "state": {"active_mode": "constrained_paper", "open_positions": [{"position_id": "open1"}], "counters": {}, "consecutive_losses": 0},
            "signal": {
                "signal_id": "fixture_blocked",
                "token_address": "SoBlocked111",
                "entry_decision": "TREND",
                "regime": "TREND",
                "recommended_position_pct": 0.40,
                "regime_confidence": 0.82,
                "runtime_signal_confidence": 0.80,
                "continuation_confidence": 0.70,
                "linkage_risk_score": 0.20,
                "x_status": "healthy",
                "x_validation_score": 80,
            },
        },
        {
            "name": "missing_evidence",
            "mode": "expanded_paper",
            "state": {"active_mode": "expanded_paper", "open_positions": [], "counters": {}, "consecutive_losses": 0},
            "signal": {
                "signal_id": "fixture_missing",
                "token_address": "SoMissing111",
                "entry_decision": "SCALP",
                "regime": "SCALP",
                "recommended_position_pct": 0.28,
                "x_status": "unknown",
                "runtime_signal_partial_flag": True,
            },
        },
    ]


def run_smoke() -> dict:
    ensure_dir(SMOKE_DIR)
    cases: list[dict] = []
    for fixture in build_fixture_signals():
        signal = fixture["signal"]
        state = fixture["state"]
        guards = evaluate_entry_guards(signal, state, BASE_CONFIG)
        sizing = compute_position_sizing(signal, state, BASE_CONFIG)
        cases.append(
            {
                "name": fixture["name"],
                "mode": fixture["mode"],
                "signal_id": signal["signal_id"],
                "token_address": signal["token_address"],
                "hard_block": guards["hard_block"],
                "hard_block_reasons": guards["hard_block_reasons"],
                "soft_reasons": guards["soft_reasons"],
                "sizing": sizing,
                "would_open_position": (not should_block_entry(guards)) and float(sizing["effective_position_scale"]) > 0,
            }
        )

    payload = {
        "contract_version": "evidence_weighted_sizing_smoke.v1",
        "case_count": len(cases),
        "cases": cases,
    }
    write_json(OUTPUT_JSON, payload)

    lines = [
        "# Evidence-weighted sizing smoke",
        "",
        "| case | hard_block | base_pct | effective_pct | multiplier | origin | reasons |",
        "| --- | --- | ---: | ---: | ---: | --- | --- |",
    ]
    for case in cases:
        sizing = case["sizing"]
        lines.append(
            f"| {case['name']} | {str(case['hard_block']).lower()} | {sizing['base_position_pct']:.4f} | {sizing['effective_position_pct']:.4f} | {sizing['sizing_multiplier']:.4f} | {sizing['sizing_origin']} | {', '.join(sizing['sizing_reason_codes'])} |"
        )
    OUTPUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return payload


if __name__ == "__main__":
    summary = run_smoke()
    print(json.dumps(summary, sort_keys=True, indent=2))
