"""Filesystem I/O helpers with deterministic JSON behavior and segmented JSONL support."""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any, Iterable

_SEGMENTS_DIRNAME = "_segments"
_JSONL_LOCKS: dict[str, threading.Lock] = {}
_JSONL_LOCKS_GUARD = threading.Lock()


def ensure_dir(path: Path | str) -> Path:
    resolved = Path(path).expanduser().resolve()
    resolved.mkdir(parents=True, exist_ok=True)
    return resolved


def _write_text_atomic(path: Path, text: str) -> Path:
    ensure_dir(path.parent)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)
    return path


def _jsonl_lock_for_path(path: Path | str) -> threading.Lock:
    resolved = Path(path).expanduser().resolve()
    key = str(resolved)
    with _JSONL_LOCKS_GUARD:
        lock = _JSONL_LOCKS.get(key)
        if lock is None:
            lock = threading.Lock()
            _JSONL_LOCKS[key] = lock
        return lock


def write_json(path: Path | str, payload: dict[str, Any]) -> Path:
    target = Path(path).expanduser().resolve()
    return _write_text_atomic(
        target,
        json.dumps(payload, sort_keys=True, ensure_ascii=False, indent=2) + "\n",
    )


def read_json(path: Path | str, default: Any = None) -> Any:
    target = Path(path).expanduser().resolve()
    if not target.exists():
        return default
    return json.loads(target.read_text(encoding="utf-8"))


def _segment_key_from_payload(payload: dict[str, Any], explicit: str | None = None) -> str:
    if explicit:
        return explicit
    ts = str(payload.get("ts") or payload.get("timestamp") or payload.get("signal_ts") or payload.get("date") or "")
    return ts[:10] if len(ts) >= 10 else "active"


def segmented_jsonl_dir(path: Path | str) -> Path:
    target = Path(path).expanduser().resolve()
    return ensure_dir(target.parent / _SEGMENTS_DIRNAME / target.stem)


def segmented_jsonl_path(path: Path | str, *, segment_key: str) -> Path:
    target = Path(path).expanduser().resolve()
    safe_key = str(segment_key).replace("/", "-")
    return segmented_jsonl_dir(target) / f"{target.stem}.{safe_key}.jsonl"


def list_jsonl_segments(path: Path | str) -> list[Path]:
    target = Path(path).expanduser().resolve()
    directory = target.parent / _SEGMENTS_DIRNAME / target.stem
    if not directory.exists():
        return []
    return sorted(p for p in directory.glob(f"{target.stem}.*.jsonl") if p.is_file())


def append_jsonl(
    path: Path | str,
    payload: dict[str, Any],
    *,
    segment_key: str | None = None,
) -> Path:
    target = Path(path).expanduser().resolve()
    if segment_key is not None:
        target = segmented_jsonl_path(target, segment_key=_segment_key_from_payload(payload, segment_key))
    line = json.dumps(payload, sort_keys=True, ensure_ascii=False) + "\n"
    lock = _jsonl_lock_for_path(target)
    with lock:
        ensure_dir(target.parent)
        with target.open("a", encoding="utf-8") as handle:
            handle.write(line)
    return target


def _read_jsonl_file(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    for line_no, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        row = json.loads(line)
        if isinstance(row, dict):
            row.setdefault("_source_file", str(path))
            row.setdefault("_source_line", line_no)
            rows.append(row)
    return rows


def read_jsonl(path: Path | str, *, include_segments: bool = True) -> list[dict[str, Any]]:
    target = Path(path).expanduser().resolve()
    segments = list_jsonl_segments(target) if include_segments else []
    if segments:
        rows: list[dict[str, Any]] = []
        for segment in segments:
            rows.extend(_read_jsonl_file(segment))
        return rows
    return _read_jsonl_file(target)


def materialize_jsonl(path: Path | str) -> Path:
    target = Path(path).expanduser().resolve()
    segments = list_jsonl_segments(target)
    if not segments:
        ensure_dir(target.parent)
        if not target.exists():
            _write_text_atomic(target, "")
        return target
    lines: list[str] = []
    for segment in segments:
        text = segment.read_text(encoding="utf-8")
        if text:
            lines.append(text.rstrip("\n"))
    payload = ("\n".join(lines) + "\n") if lines else ""
    return _write_text_atomic(target, payload)


def materialize_jsonl_many(paths: Iterable[Path | str]) -> list[Path]:
    return [materialize_jsonl(path) for path in paths]
