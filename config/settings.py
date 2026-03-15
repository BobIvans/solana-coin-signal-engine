"""Application settings for OpenClaw/X bootstrap."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


TRUE_VALUES = {"1", "true", "t", "yes", "y", "on"}



def _as_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in TRUE_VALUES


def _load_local_dotenv(dotenv_path: str = ".env") -> None:
    path = Path(dotenv_path)
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


@dataclass(frozen=True)
class Settings:
    OPENCLAW_ENABLED: bool
    OPENCLAW_LOCAL_ONLY: bool
    OPENCLAW_PROFILE_PATH: str
    OPENCLAW_SNAPSHOTS_DIR: str
    X_VALIDATION_ENABLED: bool
    X_DEGRADED_MODE_ALLOWED: bool
    X_SEARCH_TEST_QUERY: str

    @property
    def profile_path(self) -> Path:
        return Path(self.OPENCLAW_PROFILE_PATH).expanduser().resolve()

    @property
    def snapshots_dir(self) -> Path:
        return Path(self.OPENCLAW_SNAPSHOTS_DIR).expanduser().resolve()


def load_settings() -> Settings:
    _load_local_dotenv()

    return Settings(
        OPENCLAW_ENABLED=_as_bool(os.getenv("OPENCLAW_ENABLED"), True),
        OPENCLAW_LOCAL_ONLY=_as_bool(os.getenv("OPENCLAW_LOCAL_ONLY"), True),
        OPENCLAW_PROFILE_PATH=os.getenv("OPENCLAW_PROFILE_PATH", "~/.openclaw/x-profile"),
        OPENCLAW_SNAPSHOTS_DIR=os.getenv("OPENCLAW_SNAPSHOTS_DIR", "./data/smoke"),
        X_VALIDATION_ENABLED=_as_bool(os.getenv("X_VALIDATION_ENABLED"), True),
        X_DEGRADED_MODE_ALLOWED=_as_bool(os.getenv("X_DEGRADED_MODE_ALLOWED"), True),
        X_SEARCH_TEST_QUERY=os.getenv("X_SEARCH_TEST_QUERY", "solana memecoin"),
    )
