"""Run a smoke query for X via OpenClaw with degrade-safe behavior."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config.settings import load_settings


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _append_jsonl(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(data, sort_keys=True) + "\n")


def main() -> int:
    settings = load_settings()
    timestamp = _utc_now()

    payload = {
        "query": settings.X_SEARCH_TEST_QUERY,
        "timestamp_utc": timestamp,
        "status": "degraded",
        "snapshot_saved": False,
        "degraded": True,
        "notes": "X unavailable or session invalid",
    }

    try:
        if not settings.X_VALIDATION_ENABLED:
            payload["notes"] = "X validation disabled by configuration"
            return _finish(settings.snapshots_dir, payload)

        openclaw_path = shutil.which("openclaw")
        if not openclaw_path:
            payload["notes"] = "OpenClaw CLI is not installed locally"
            return _finish(settings.snapshots_dir, payload)

        cmd = [
            openclaw_path,
            "search",
            "--provider",
            "x",
            "--query",
            settings.X_SEARCH_TEST_QUERY,
            "--profile",
            str(settings.profile_path),
        ]

        result = subprocess.run(cmd, check=False, capture_output=True, text=True, timeout=60)

        if result.returncode == 0:
            payload["status"] = "ok"
            payload["snapshot_saved"] = True
            payload["degraded"] = False
            payload["notes"] = "Smoke search succeeded"
            payload["raw_output"] = result.stdout.strip()
        else:
            payload["notes"] = (
                "X unavailable or session invalid"
                f" (openclaw exit={result.returncode}: {result.stderr.strip()[:240]})"
            )

    except Exception as exc:  # noqa: BLE001
        payload["status"] = "failed" if not settings.X_DEGRADED_MODE_ALLOWED else "degraded"
        payload["degraded"] = settings.X_DEGRADED_MODE_ALLOWED
        payload["snapshot_saved"] = False
        payload["notes"] = f"Smoke execution error: {exc}"

    return _finish(settings.snapshots_dir, payload)


def _finish(snapshots_dir: Path, payload: dict) -> int:
    _write_json(snapshots_dir / "x_snapshot_example.json", payload)
    _append_jsonl(snapshots_dir / "smoke_status_history.jsonl", payload)
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload["status"] in {"ok", "degraded"} else 1


if __name__ == "__main__":
    sys.exit(main())
