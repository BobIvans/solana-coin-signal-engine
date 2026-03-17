from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class RunPaths:
    base_dir: Path
    run_dir: Path
    manifest_path: Path
    universe_path: Path
    backfill_path: Path
    signals_path: Path
    trades_path: Path
    positions_path: Path
    summary_json_path: Path
    summary_md_path: Path


JSONDict = dict[str, Any]
