from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
root_str = str(ROOT)
if root_str not in sys.path:
    sys.path.insert(0, root_str)

from analytics.unified_score import score_token
from collectors.discovery_engine import build_shortlist
from config.settings import load_settings
from trading.entry_logic import decide_entry
from utils.bundle_contract_fields import BUNDLE_CONTRACT_FIELDS, LINKAGE_CONTRACT_FIELDS
from utils.short_horizon_contract_fields import SHORT_HORIZON_SIGNAL_FIELDS


class DummyEntrySettings:
    ENTRY_SELECTOR_FAILCLOSED = True
    ENTRY_SCALP_SCORE_MIN = 82
    ENTRY_TREND_SCORE_MIN = 86
    ENTRY_SCALP_MAX_AGE_SEC = 480
    ENTRY_RUG_MAX_SCALP = 0.30
    ENTRY_RUG_MAX_TREND = 0.20
    ENTRY_BUY_PRESSURE_MIN_SCALP = 0.75
    ENTRY_BUY_PRESSURE_MIN_TREND = 0.65
    ENTRY_FIRST30S_BUY_RATIO_MIN = 0.65
    ENTRY_BUNDLE_CLUSTER_MIN = 0.55
    ENTRY_SCALP_MIN_X_SCORE = 50
    ENTRY_TREND_MIN_X_SCORE = 65
    ENTRY_HOLDER_GROWTH_MIN_TREND = 20
    ENTRY_SMART_WALLET_HITS_MIN_TREND = 2
    ENTRY_MAX_BASE_POSITION_PCT = 1.0
    ENTRY_DEGRADED_X_SIZE_MULTIPLIER = 0.5
    ENTRY_PARTIAL_DATA_SIZE_MULTIPLIER = 0.6
    ENTRY_CONTRACT_VERSION = "entry_selector_v1"
    RUG_DEV_SELL_PRESSURE_HARD = 0.25


def _bundle_values() -> dict[str, object]:
    return {
        "bundle_count_first_60s": 3,
        "bundle_size_value": 15420.5,
        "unique_wallets_per_bundle_avg": 2.5,
        "bundle_timing_from_liquidity_add_min": 0.8,
        "bundle_success_rate": 0.67,
        "bundle_composition_dominant": "buy-only",
        "bundle_tip_efficiency": 0.42,
        "bundle_failure_retry_pattern": 2,
        "cross_block_bundle_correlation": 0.19,
        "bundle_wallet_clustering_score": 0.54,
        "cluster_concentration_ratio": 0.61,
        "num_unique_clusters_first_60s": 2,
        "creator_in_cluster_flag": True,
    }




def _linkage_values() -> dict[str, object]:
    return {
        "creator_dev_link_score": 0.31,
        "creator_buyer_link_score": 0.74,
        "dev_buyer_link_score": 0.58,
        "shared_funder_link_score": 0.71,
        "creator_cluster_link_score": 0.62,
        "cluster_dev_link_score": 0.54,
        "linkage_risk_score": 0.49,
        "creator_funder_overlap_count": 1,
        "buyer_funder_overlap_count": 2,
        "funder_overlap_count": 2,
        "linkage_reason_codes": ["creator_buyer_same_funder"],
        "linkage_confidence": 0.66,
        "linkage_metric_origin": "mixed_evidence",
        "linkage_status": "ok",
        "linkage_warning": None,
    }

def _short_horizon_values() -> dict[str, object]:
    return {
        "net_unique_buyers_60s": 7,
        "liquidity_refill_ratio_120s": 0.85,
        "cluster_sell_concentration_120s": 0.58,
        "smart_wallet_dispersion_score": 0.44,
        "x_author_velocity_5m": 0.6,
        "seller_reentry_ratio": 0.33,
        "liquidity_shock_recovery_sec": 55,
    }


def _base_scored_token() -> dict[str, object]:
    return {
        "token_address": "So111",
        "symbol": "EX",
        "name": "Example",
        "regime_candidate": "ENTRY_CANDIDATE",
        "final_score": 90,
        "age_sec": 120,
        "rug_score": 0.1,
        "rug_verdict": "PASS",
        "buy_pressure": 0.8,
        "first30s_buy_ratio": 0.8,
        "bundle_cluster_score": 0.7,
        "volume_velocity": 4.5,
        "x_validation_score": 70,
        "x_validation_delta": 8,
        "x_status": "ok",
        "holder_growth_5m": 25,
        "smart_wallet_hits": 3,
        "dev_sell_pressure_5m": 0,
        "lp_burn_confirmed": True,
        "mint_revoked": True,
        "freeze_revoked": True,
    }


def test_bundle_fields_propagate_from_shortlist_to_scored_token_to_entry_snapshot():
    candidate = {
        "token_address": "tok_bundle",
        "pair_address": "pair_bundle",
        "symbol": "BNDL",
        "name": "Bundle",
        "fast_prescore": 88.0,
        "age_sec": 45,
        "liquidity_usd": 25000.0,
        "buy_pressure": 0.83,
        "volume_mcap_ratio": 0.12,
        "source": "dexscreener",
        "first30s_buy_ratio": 0.8,
        "bundle_cluster_score": 0.65,
        "x_validation_score": 71,
        "x_validation_delta": 9,
        "x_status": "ok",
        "top20_holder_share": 0.42,
        "holder_growth_5m": 32,
        "smart_wallet_hits": 3,
        "dev_sell_pressure_5m": 0.05,
        "rug_score": 0.12,
        "rug_verdict": "PASS",
        "mint_revoked": True,
        "freeze_revoked": True,
        "lp_burn_confirmed": True,
        **_bundle_values(),
        **_linkage_values(),
        **_short_horizon_values(),
    }

    shortlist = build_shortlist([candidate], top_k=1)
    shortlisted = shortlist[0]
    for field, value in _bundle_values().items():
        assert shortlisted[field] == value

    settings = load_settings()
    scored = score_token(candidate, settings)
    for field, value in _bundle_values().items():
        assert scored[field] == value
    for field, value in _short_horizon_values().items():
        assert scored[field] == value
    for field, value in _linkage_values().items():
        assert scored[field] == value

    entry = decide_entry({**_base_scored_token(), **_bundle_values(), **_linkage_values(), **_short_horizon_values()}, DummyEntrySettings())
    for field, value in _bundle_values().items():
        assert entry[field] == value
        assert entry["entry_snapshot"][field] == value
    for field, value in _short_horizon_values().items():
        assert entry[field] == value
        assert entry["entry_snapshot"][field] == value


def test_bundle_fields_are_none_safe_when_missing():
    shortlist = build_shortlist(
        [
            {
                "token_address": "tok_missing",
                "pair_address": "pair_missing",
                "fast_prescore": 44.0,
                "volume_m5": 20.0,
            }
        ],
        top_k=1,
    )

    for field in BUNDLE_CONTRACT_FIELDS:
        assert field in shortlist[0]
        assert shortlist[0][field] is None

    entry = decide_entry(_base_scored_token(), DummyEntrySettings())
    for field in BUNDLE_CONTRACT_FIELDS:
        assert field in entry
        assert entry[field] is None
        assert field in entry["entry_snapshot"]
        assert entry["entry_snapshot"][field] is None
    for field in SHORT_HORIZON_SIGNAL_FIELDS:
        assert field in entry
        assert entry[field] is None
        assert field in entry["entry_snapshot"]
        assert entry["entry_snapshot"][field] is None


def test_replay_preserves_bundle_fields_when_missing_or_present():
    processed = ROOT / "data" / "processed"
    processed.mkdir(parents=True, exist_ok=True)
    (ROOT / "data" / "smart_wallets.registry.json").write_text(json.dumps({"wallets": []}), encoding="utf-8")

    run_id_missing = "bundle_contract_missing"
    missing_payload = [
        {
            "token_address": "tok_missing",
            "pair_address": "pair_missing",
            "decision": "paper_enter",
            "wallet_features": {},
            "entry_snapshot": {},
        }
    ]
    (processed / "entry_candidates.json").write_text(json.dumps(missing_payload), encoding="utf-8")
    subprocess.run(
        [sys.executable, "scripts/replay_7d.py", "--run-id", run_id_missing, "--dry-run"],
        check=True,
        cwd=ROOT,
    )

    missing_signal = json.loads((ROOT / "runs" / run_id_missing / "signals.jsonl").read_text(encoding="utf-8").splitlines()[0])
    missing_trade = json.loads((ROOT / "runs" / run_id_missing / "trades.jsonl").read_text(encoding="utf-8").splitlines()[0])
    for field in BUNDLE_CONTRACT_FIELDS:
        assert field in missing_signal
        assert field in missing_trade
        assert missing_signal[field] is None
        assert missing_trade[field] is None
    for field in SHORT_HORIZON_SIGNAL_FIELDS:
        assert field in missing_signal
        assert field in missing_trade
        assert missing_signal[field] is None
        assert missing_trade[field] is None

    run_id_present = "bundle_contract_present"
    present_payload = [
        {
            "token_address": "tok_present",
            "pair_address": "pair_present",
            "decision": "paper_enter",
            "wallet_features": {},
            "entry_snapshot": {**_bundle_values(), **_short_horizon_values()},
        }
    ]
    (processed / "entry_candidates.json").write_text(json.dumps(present_payload), encoding="utf-8")
    subprocess.run(
        [sys.executable, "scripts/replay_7d.py", "--run-id", run_id_present, "--dry-run"],
        check=True,
        cwd=ROOT,
    )

    present_signal = json.loads((ROOT / "runs" / run_id_present / "signals.jsonl").read_text(encoding="utf-8").splitlines()[0])
    present_trade = json.loads((ROOT / "runs" / run_id_present / "trades.jsonl").read_text(encoding="utf-8").splitlines()[0])
    for field, value in _bundle_values().items():
        assert present_signal[field] == value
        assert present_trade[field] == value
    for field, value in _short_horizon_values().items():
        assert present_signal[field] == value
        assert present_trade[field] == value
