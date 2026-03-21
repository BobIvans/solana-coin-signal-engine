from __future__ import annotations

from pathlib import Path
from typing import Any

from scripts.rug_engine_smoke import run as run_rug_engine

from src.pipeline.env import pipeline_env


def run_stage(*, processed_dir: str | Path, enriched_path: str | Path) -> dict[str, Any]:
    with pipeline_env(processed_dir=processed_dir):
        return run_rug_engine(Path(enriched_path))
