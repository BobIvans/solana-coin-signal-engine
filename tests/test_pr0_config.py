import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config.settings import load_settings


def test_load_settings_defaults(monkeypatch):
    monkeypatch.delenv("OPENCLAW_ENABLED", raising=False)
    monkeypatch.delenv("OPENCLAW_LOCAL_ONLY", raising=False)
    monkeypatch.delenv("OPENCLAW_PROFILE_PATH", raising=False)
    monkeypatch.delenv("OPENCLAW_SNAPSHOTS_DIR", raising=False)
    monkeypatch.delenv("X_VALIDATION_ENABLED", raising=False)
    monkeypatch.delenv("X_DEGRADED_MODE_ALLOWED", raising=False)
    monkeypatch.delenv("X_SEARCH_TEST_QUERY", raising=False)

    settings = load_settings()

    assert settings.OPENCLAW_ENABLED is True
    assert settings.OPENCLAW_LOCAL_ONLY is True
    assert Path(settings.OPENCLAW_PROFILE_PATH).is_absolute()
    assert Path(settings.OPENCLAW_SNAPSHOTS_DIR).is_absolute()
    assert settings.X_VALIDATION_ENABLED is True
    assert settings.X_DEGRADED_MODE_ALLOWED is True
    assert settings.X_SEARCH_TEST_QUERY == "solana memecoin"


def test_load_settings_env_override(monkeypatch):
    monkeypatch.setenv("OPENCLAW_ENABLED", "false")
    monkeypatch.setenv("X_SEARCH_TEST_QUERY", "custom query")

    settings = load_settings()

    assert settings.OPENCLAW_ENABLED is False
    assert settings.X_SEARCH_TEST_QUERY == "custom query"
