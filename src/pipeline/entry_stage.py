from __future__ import annotations

from pathlib import Path
from typing import Any

from scripts.entry_selector_smoke import run as run_entry_selector

from src.pipeline.env import pipeline_env


def run_stage(*, processed_dir: str | Path, scored_path: str | Path) -> dict[str, Any]:
    with pipeline_env(processed_dir=processed_dir):
        return run_entry_selector(Path(scored_path))
