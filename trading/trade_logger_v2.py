"""Append-only deterministic log writer for paper trader."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from utils.io import append_jsonl


def _segment_key(event: dict[str, Any], paths: dict[str, Path | str | bool]) -> str | None:
    if not paths.get("segment_by_day"):
        return None
    ts = str(event.get("ts") or event.get("timestamp") or event.get("signal_ts") or "")
    return ts[:10] if len(ts) >= 10 else "active"


def log_signal(event: dict[str, Any], paths: dict[str, Path]) -> None:
    append_jsonl(paths["signals"], event, segment_key=_segment_key(event, paths))


def log_trade(event: dict[str, Any], paths: dict[str, Path]) -> None:
    append_jsonl(paths["trades"], event, segment_key=_segment_key(event, paths))
