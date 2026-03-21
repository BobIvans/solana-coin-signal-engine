from __future__ import annotations

from pathlib import Path
from typing import Any

from utils.io import append_jsonl as _append_jsonl
from utils.io import materialize_jsonl as _materialize_jsonl
from utils.io import write_json as _write_json


def append_jsonl(path: str | Path, payload: dict[str, Any], *, segment_key: str | None = None) -> Path:
    return _append_jsonl(path, payload, segment_key=segment_key)


def materialize_jsonl(path: str | Path) -> Path:
    return _materialize_jsonl(path)


def write_json(path: str | Path, payload: dict[str, Any]) -> Path:
    return _write_json(path, payload)
