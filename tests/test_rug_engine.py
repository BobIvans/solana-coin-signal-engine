import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from analytics.rug_engine import assess_rug_risk


class DummySettings:
    RUG_LP_BURN_OWNER_ALLOWLIST = "11111111111111111111111111111111"
    RUG_LP_LOCK_PROGRAM_ALLOWLIST_PATH = "config/lock_programs.json"
    RUG_TOP1_HOLDER_HARD_MAX = 0.2
    RUG_TOP20_HOLDER_HARD_MAX = 0.65
    RUG_DEV_SELL_PRESSURE_WARN = 0.10
    RUG_DEV_SELL_PRESSURE_HARD = 0.25
    RUG_IGNORE_THRESHOLD = 0.55
    RUG_WATCH_THRESHOLD = 0.35
    RUG_ENGINE_FAILCLOSED = True


def test_hard_fail_on_active_mint_authority():
    result = assess_rug_risk(
        {
            "token_address": "token",
            "mint_authority": "creator",
            "freeze_authority": None,
            "top1_holder_share": 0.05,
            "top20_holder_share": 0.4,
            "dev_sell_pressure_5m": 0.0,
        },
        DummySettings(),
    )
    assert result["rug_verdict"] == "IGNORE"


def test_partial_fail_closed_never_pass():
    result = assess_rug_risk({"token_address": "token", "mint_authority": None, "freeze_authority": None}, DummySettings())
    assert result["rug_status"] == "partial"
    assert result["rug_verdict"] in {"WATCH", "IGNORE"}


def test_bundle_warnings_are_non_breaking():
    result = assess_rug_risk(
        {
            "token_address": "token",
            "mint_authority": None,
            "freeze_authority": None,
            "top1_holder_share": 0.05,
            "top20_holder_share": 0.4,
            "dev_sell_pressure_5m": 0.0,
            "bundle_composition_dominant": "sell-only",
            "bundle_failure_retry_pattern": 3,
        },
        DummySettings(),
    )
    assert "bundle_sell_only_flow" in result["rug_warnings"]
    assert "bundle_retry_pattern_severe" in result["rug_warnings"]
    assert result["rug_verdict"] in {"PASS", "WATCH", "IGNORE"}
