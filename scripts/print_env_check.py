"""Print resolved environment settings for PR-0 checks."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config.settings import load_settings


if __name__ == "__main__":
    settings = load_settings()
    payload = {
        "openclaw_enabled": settings.OPENCLAW_ENABLED,
        "openclaw_local_only": settings.OPENCLAW_LOCAL_ONLY,
        "openclaw_profile_path": settings.OPENCLAW_PROFILE_PATH,
        "openclaw_snapshots_dir": settings.OPENCLAW_SNAPSHOTS_DIR,
        "x_validation_enabled": settings.X_VALIDATION_ENABLED,
        "x_degraded_mode_allowed": settings.X_DEGRADED_MODE_ALLOWED,
        "x_search_test_query": settings.X_SEARCH_TEST_QUERY,
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
