import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from analytics.unified_score import score_token
from config.settings import load_settings


def _base_token() -> dict:
    return {
        "token_address": "So11111111111111111111111111111111111111112",
        "symbol": "EXAMPLE",
        "name": "Example Coin",
        "fast_prescore": 88.0,
        "first30s_buy_ratio": 0.78,
        "bundle_cluster_score": 0.65,
        "priority_fee_avg_first_min": 0.0012,
        "x_validation_score": 79.0,
        "x_validation_delta": 12.0,
        "x_status": "ok",
        "top20_holder_share": 0.42,
        "first50_holder_conc_est": 0.57,
        "holder_entropy_est": 2.9,
        "holder_growth_5m": 40,
        "dev_sell_pressure_5m": 0.07,
        "pumpfun_to_raydium_sec": 140,
        "smart_wallet_hits": 4,
        "rug_score": 0.31,
        "rug_verdict": "WATCH",
        "mint_revoked": True,
        "freeze_revoked": True,
        "lp_burn_confirmed": True,
        "lp_locked_flag": False,
        "x_duplicate_text_ratio": 0.25,
        "x_promoter_concentration": 0.2,
        "x_unique_authors_visible": 10,
        "x_contract_mention_presence": 1,
        "enrichment_status": "ok",
        "rug_status": "ok",
    }


def test_unified_score_strong_token_watch_or_entry(monkeypatch):
    monkeypatch.setenv("UNIFIED_SCORE_ENTRY_THRESHOLD", "45")
    monkeypatch.setenv("UNIFIED_SCORE_WATCH_THRESHOLD", "35")
    settings = load_settings()
    out = score_token(_base_token(), settings)
    assert out["final_score"] >= 35
    assert out["regime_candidate"] in {"WATCHLIST", "ENTRY_CANDIDATE"}


def test_unified_score_x_degraded_flag(monkeypatch):
    monkeypatch.setenv("UNIFIED_SCORE_ENTRY_THRESHOLD", "45")
    monkeypatch.setenv("UNIFIED_SCORE_WATCH_THRESHOLD", "35")
    settings = load_settings()
    token = _base_token()
    token["x_status"] = "degraded"
    out = score_token(token, settings)
    assert "x_degraded" in out["score_flags"]
    assert out["regime_candidate"] in {"IGNORE", "WATCHLIST", "ENTRY_CANDIDATE"}


def test_unified_score_rug_ignore_hard_override(monkeypatch):
    settings = load_settings()
    token = _base_token()
    token["rug_verdict"] = "IGNORE"
    out = score_token(token, settings)
    assert out["regime_candidate"] == "IGNORE"
    assert out["final_score"] <= 35
