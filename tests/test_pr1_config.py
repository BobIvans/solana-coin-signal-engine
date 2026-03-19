import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config.settings import load_settings


def test_settings_load_and_validate(monkeypatch):
    monkeypatch.setenv("APP_ENV", "dev")
    monkeypatch.setenv("LOG_LEVEL", "INFO")
    monkeypatch.setenv("X_MAX_TOKENS_PER_CYCLE", "5")
    monkeypatch.setenv("X_MAX_CONCURRENCY", "2")
    monkeypatch.setenv("X_CACHE_TTL_SEC", "600")
    monkeypatch.setenv("DEX_CACHE_TTL_SEC", "60")
    monkeypatch.setenv("HELIUS_CACHE_TTL_SEC", "120")
    monkeypatch.setenv("OPENCLAW_ENABLED", "true")
    monkeypatch.setenv("OPENCLAW_LOCAL_ONLY", "true")
    monkeypatch.setenv("X_VALIDATION_ENABLED", "true")
    monkeypatch.setenv("X_DEGRADED_MODE_ALLOWED", "true")
    monkeypatch.setenv("GLOBAL_RATE_LIMIT_ENABLED", "true")
    monkeypatch.setenv("UNIFIED_SCORING_ENABLED", "true")
    monkeypatch.setenv("UNIFIED_SCORING_FAILOPEN", "false")
    monkeypatch.setenv("UNIFIED_SCORING_REQUIRE_X", "false")
    monkeypatch.setenv("UNIFIED_SCORE_ENTRY_THRESHOLD", "82")
    monkeypatch.setenv("UNIFIED_SCORE_WATCH_THRESHOLD", "68")
    monkeypatch.setenv("ENTRY_SELECTOR_ENABLED", "true")
    monkeypatch.setenv("ENTRY_SELECTOR_FAILCLOSED", "true")

    settings = load_settings()

    assert settings.APP_ENV == "dev"
    assert settings.OPENCLAW_ENABLED is True
    assert settings.X_VALIDATION_ENABLED is True
    assert settings.X_MAX_TOKENS_PER_CYCLE > 0
    assert settings.X_MAX_CONCURRENCY > 0
    assert settings.X_CACHE_TTL_SEC > 0
    assert settings.UNIFIED_SCORING_ENABLED is True
    assert settings.UNIFIED_SCORING_FAILOPEN is False
    assert settings.UNIFIED_SCORING_REQUIRE_X is False
    assert settings.UNIFIED_SCORE_HEURISTIC_CONFIDENCE_FLOOR > 0
    assert (
        settings.UNIFIED_SCORE_ENTRY_THRESHOLD > settings.UNIFIED_SCORE_WATCH_THRESHOLD
    )
    assert settings.ENTRY_SELECTOR_ENABLED is True
    assert settings.ENTRY_SCALP_SCORE_MIN > 0


def test_directories_resolve_to_absolute():
    settings = load_settings()
    assert Path(settings.DATA_DIR).is_absolute()
    assert Path(settings.RAW_DATA_DIR).is_absolute()
    assert Path(settings.PROCESSED_DATA_DIR).is_absolute()


def test_unified_and_entry_settings_coexist():
    settings = load_settings()
    assert isinstance(settings.UNIFIED_SCORING_ENABLED, bool)
    assert isinstance(settings.UNIFIED_SCORING_FAILOPEN, bool)
    assert isinstance(settings.UNIFIED_SCORING_REQUIRE_X, bool)
    assert settings.UNIFIED_SCORE_WATCH_THRESHOLD > 0
    assert isinstance(settings.ENTRY_SELECTOR_ENABLED, bool)
    assert settings.ENTRY_TREND_SCORE_MIN >= settings.ENTRY_SCALP_SCORE_MIN


def test_paper_settings_validate(monkeypatch):
    monkeypatch.setenv("PAPER_STARTING_CAPITAL_SOL", "0.1")
    monkeypatch.setenv("PAPER_MAX_SLIPPAGE_BPS", "1200")
    monkeypatch.setenv("PAPER_PRIORITY_FEE_SPIKE_MULTIPLIER", "1.75")
    settings = load_settings()
    assert settings.PAPER_STARTING_CAPITAL_SOL > 0
    assert settings.PAPER_MAX_SLIPPAGE_BPS > 0
    assert settings.PAPER_PRIORITY_FEE_SPIKE_MULTIPLIER > 0


def test_invalid_paper_settings_raise(monkeypatch):
    monkeypatch.setenv("PAPER_STARTING_CAPITAL_SOL", "0")
    try:
        load_settings()
    except ValueError as exc:
        assert "PAPER_STARTING_CAPITAL_SOL" in str(exc)
    else:
        raise AssertionError("Expected ValueError for PAPER_STARTING_CAPITAL_SOL")


def test_exit_settings_load(monkeypatch):
    monkeypatch.setenv("EXIT_ENGINE_ENABLED", "true")
    monkeypatch.setenv("EXIT_ENGINE_FAILCLOSED", "true")
    monkeypatch.setenv("EXIT_SCALP_BUY_PRESSURE_FLOOR", "0.60")
    monkeypatch.setenv("EXIT_TREND_BUY_PRESSURE_FLOOR", "0.50")
    settings = load_settings()
    assert settings.EXIT_ENGINE_ENABLED is True
    assert settings.EXIT_ENGINE_FAILCLOSED is True
    assert 0 <= settings.EXIT_SCALP_BUY_PRESSURE_FLOOR <= 1
    assert 0 <= settings.EXIT_TREND_BUY_PRESSURE_FLOOR <= 1


def test_invalid_exit_poll_interval_raises(monkeypatch):
    monkeypatch.setenv("EXIT_POLL_INTERVAL_SEC", "0")
    try:
        load_settings()
    except ValueError as exc:
        assert "EXIT_POLL_INTERVAL_SEC" in str(exc)
    else:
        raise AssertionError("Expected ValueError for EXIT_POLL_INTERVAL_SEC")


def test_exit_and_paper_settings_coexist(monkeypatch):
    monkeypatch.setenv("EXIT_ENGINE_ENABLED", "true")
    monkeypatch.setenv("PAPER_TRADER_ENABLED", "true")
    settings = load_settings()
    assert settings.EXIT_ENGINE_ENABLED is True
    assert settings.PAPER_TRADER_ENABLED is True


def test_bundle_cluster_unified_score_settings_exist_and_are_bounded():
    settings = load_settings()
    assert settings.UNIFIED_SCORE_BUNDLE_AGGRESSION_MAX > 0
    assert settings.UNIFIED_SCORE_MULTI_CLUSTER_BONUS_MAX > 0
    assert settings.UNIFIED_SCORE_SINGLE_CLUSTER_PENALTY_MAX > 0
    assert settings.UNIFIED_SCORE_CREATOR_CLUSTER_PENALTY > 0
    assert settings.UNIFIED_SCORE_BUNDLE_SELL_HEAVY_PENALTY_MAX > 0
    assert settings.UNIFIED_SCORE_RETRY_MANIPULATION_PENALTY_MAX > 0
    assert (
        settings.UNIFIED_SCORE_BUNDLE_AGGRESSION_MAX
        < settings.UNIFIED_SCORE_ENTRY_THRESHOLD
    )
