"""Filesystem I/O helpers with deterministic JSON behavior."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def ensure_dir(path: Path | str) -> Path:
    resolved = Path(path).expanduser().resolve()
    resolved.mkdir(parents=True, exist_ok=True)
    return resolved


def write_json(path: Path | str, payload: dict[str, Any]) -> Path:
    target = Path(path).expanduser().resolve()
    ensure_dir(target.parent)
    target.write_text(json.dumps(payload, sort_keys=True, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return target


def read_json(path: Path | str, default: Any = None) -> Any:
    target = Path(path).expanduser().resolve()
    if not target.exists():
        return default
    return json.loads(target.read_text(encoding="utf-8"))


def append_jsonl(path: Path | str, payload: dict[str, Any]) -> Path:
    target = Path(path).expanduser().resolve()
    ensure_dir(target.parent)
    with target.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True, ensure_ascii=False) + "\n")
    return target
