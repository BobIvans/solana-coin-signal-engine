import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from analytics.score_router import route_score
from config.settings import load_settings


def _token_base() -> dict:
    return {
        "token_address": "So11111111111111111111111111111111111111112",
        "fast_prescore": 80,
        "rug_score": 0.2,
        "rug_verdict": "PASS",
        "mint_revoked": True,
    }


def test_route_thresholds(monkeypatch):
    monkeypatch.setenv("UNIFIED_SCORE_ENTRY_THRESHOLD", "82")
    monkeypatch.setenv("UNIFIED_SCORE_WATCH_THRESHOLD", "68")
    settings = load_settings()

    base = _token_base()
    r1 = route_score(base, {"final_score": 50}, settings)
    r2 = route_score(base, {"final_score": 70}, settings)
    r3 = route_score(base, {"final_score": 90}, settings)

    assert r1["regime_candidate"] == "IGNORE"
    assert r2["regime_candidate"] == "WATCHLIST"
    assert r3["regime_candidate"] == "ENTRY_CANDIDATE"


def test_route_hard_overrides(monkeypatch):
    settings = load_settings()
    token = {**_token_base(), "rug_verdict": "IGNORE", "mint_revoked": False}
    out = route_score(token, {"final_score": 99}, settings)
    assert out["regime_candidate"] == "IGNORE"
    assert out["hard_override"] is True


def test_route_downgrade_on_degraded_x(monkeypatch):
    settings = load_settings()
    token = {**_token_base(), "x_status": "degraded"}
    out = route_score(token, {"final_score": 90, "heuristic_ratio": 0.2}, settings)
    assert out["regime_candidate"] == "WATCHLIST"
    assert out["downgraded"] is True
