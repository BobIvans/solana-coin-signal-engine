"""I/O helpers for replay calibration artifacts."""

from __future__ import annotations

import json
from pathlib import Path

from utils.io import ensure_dir


REQUIRED_FILES = ("manifest.json", "signals.jsonl", "trades.jsonl", "replay_summary.json")


def _read_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def load_replay_artifacts(runs_dir: Path, replay_run_id: str) -> dict:
    base = runs_dir / replay_run_id
    for file_name in REQUIRED_FILES:
        if not (base / file_name).exists():
            raise FileNotFoundError(f"missing replay artifact: {base / file_name}")
    return {
        "manifest": json.loads((base / "manifest.json").read_text(encoding="utf-8")),
        "signals": _read_jsonl(base / "signals.jsonl"),
        "trades": _read_jsonl(base / "trades.jsonl"),
        "replay_summary": json.loads((base / "replay_summary.json").read_text(encoding="utf-8")),
    }


def write_json(path: Path, payload: dict | list) -> Path:
    ensure_dir(path.parent)
    path.write_text(json.dumps(payload, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return path
