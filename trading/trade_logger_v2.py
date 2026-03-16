"""Append-only deterministic log writer for paper trader."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from utils.io import append_jsonl


def log_signal(event: dict[str, Any], paths: dict[str, Path]) -> None:
    append_jsonl(paths["signals"], event)


def log_trade(event: dict[str, Any], paths: dict[str, Path]) -> None:
    append_jsonl(paths["trades"], event)
