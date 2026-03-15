"""Smoke runner for PR-2 discovery pipeline."""

from __future__ import annotations

import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from collectors.discovery_engine import run_discovery_once


def main() -> int:
    try:
        result = run_discovery_once()
        status = result.get("status", {}).get("status", "failed")
        print(json.dumps(result.get("status", {}), sort_keys=True))
        return 0 if status in {"ok", "degraded"} else 1
    except Exception as exc:  # pragma: no cover - smoke should never crash silently
        failed = {"status": "failed", "error": str(exc)}
        print(json.dumps(failed, sort_keys=True))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
