#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description="Runtime health smoke wrapper.")
    parser.add_argument("--base-dir", required=True)
    args = parser.parse_args()

    base_dir = Path(args.base_dir).expanduser().resolve()
    cmd = [sys.executable, "scripts/runtime_signal_smoke.py", "--base-dir", str(base_dir)]
    result = subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        print(result.stdout)
        print(result.stderr)
        return result.returncode

    runtime_health = base_dir / "runs" / "runtime_signal_smoke" / "runtime_health.json"
    artifact_manifest = base_dir / "runs" / "runtime_signal_smoke" / "artifact_manifest.json"
    payload = {
        "runtime_health_exists": runtime_health.exists(),
        "artifact_manifest_exists": artifact_manifest.exists(),
    }
    (base_dir / "runtime_health_smoke.json").write_text(json.dumps(payload, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, sort_keys=True))
    return 0 if all(payload.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
