from __future__ import annotations

from pathlib import Path
from typing import Any

from scripts.x_validation_smoke import run as run_x_validation

from src.pipeline.env import pipeline_env


def run_stage(*, processed_dir: str | Path, shortlist_path: str | Path) -> dict[str, Any]:
    with pipeline_env(processed_dir=processed_dir):
        return run_x_validation(Path(shortlist_path))
