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
    assert settings.UNIFIED_SCORE_HEURISTIC_CONFIDENCE_FLOOR > 0
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
    assert settings.UNIFIED_SCORE_WATCH_THRESHOLD > 0
    assert isinstance(settings.ENTRY_SELECTOR_ENABLED, bool)
    assert settings.ENTRY_TREND_SCORE_MIN >= settings.ENTRY_SCALP_SCORE_MIN
