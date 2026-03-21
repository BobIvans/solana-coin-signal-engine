from __future__ import annotations

from pathlib import Path
from typing import Any

from scripts.onchain_enrichment_smoke import run as run_onchain_enrichment

from src.pipeline.env import pipeline_env


def run_stage(*, processed_dir: str | Path, shortlist_path: str | Path, x_validated_path: str | Path) -> dict[str, Any]:
    with pipeline_env(processed_dir=processed_dir):
        return run_onchain_enrichment(Path(shortlist_path), Path(x_validated_path))
