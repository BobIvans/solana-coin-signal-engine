"""Bootstrap local OpenClaw + X environment."""

from __future__ import annotations

import json
import shutil
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

    openclaw_path = shutil.which("openclaw")
    if not openclaw_path:
        print("[WARN] OpenClaw CLI was not found in PATH.")
        print("Install OpenClaw locally and re-run this setup script.")

    settings.profile_path.mkdir(parents=True, exist_ok=True)
    settings.snapshots_dir.mkdir(parents=True, exist_ok=True)

    status = {
        "openclaw_enabled": settings.OPENCLAW_ENABLED,
        "openclaw_local_only": settings.OPENCLAW_LOCAL_ONLY,
        "openclaw_found": bool(openclaw_path),
        "openclaw_path": openclaw_path,
        "profile_path": str(settings.profile_path),
        "profile_path_exists": settings.profile_path.exists(),
        "snapshots_dir": str(settings.snapshots_dir),
        "snapshots_dir_exists": settings.snapshots_dir.exists(),
        "x_validation_enabled": settings.X_VALIDATION_ENABLED,
        "status": "ready_for_manual_login",
        "timestamp_utc": _utc_now(),
    }

    _write_json(settings.snapshots_dir / "setup_status.json", status)
    _append_jsonl(settings.snapshots_dir / "setup_status_history.jsonl", status)

    print("\n=== PR-0 Local OpenClaw Setup ===")
    print("1) Run OpenClaw on your local machine (not in Codespaces).")
    print(f"2) Use dedicated profile: {settings.profile_path}")
    print("3) Open X (twitter.com/x.com) in that profile and login manually once.")
    print("4) Close browser without clearing profile data.")
    print("5) Run: python scripts/smoke_openclaw_x.py")
    print(f"\nWrote status to: {settings.snapshots_dir / 'setup_status.json'}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
