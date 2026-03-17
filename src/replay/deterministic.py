from __future__ import annotations

import hashlib
import json
import random
from pathlib import Path
from typing import Any

from .types import RunPaths
from utils.io import ensure_dir


def stable_sort_records(records: list[dict[str, Any]], keys: tuple[str, ...]) -> list[dict[str, Any]]:
    return sorted(records, key=lambda row: tuple(str(row.get(k, "")) for k in keys))


def seed_everything(seed: int) -> None:
    random.seed(int(seed))


def hash_config(config_dict: dict[str, Any]) -> str:
    payload = json.dumps(config_dict, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def make_run_paths(run_id: str, base_dir: str = "runs") -> RunPaths:
    base = ensure_dir(Path(base_dir))
    run_dir = ensure_dir(base / run_id)
    return RunPaths(
        base_dir=base,
        run_dir=run_dir,
        manifest_path=run_dir / "manifest.json",
        universe_path=run_dir / "universe.jsonl",
        backfill_path=run_dir / "backfill.jsonl",
        signals_path=run_dir / "signals.jsonl",
        trades_path=run_dir / "trades.jsonl",
        positions_path=run_dir / "positions.json",
        summary_json_path=run_dir / "replay_summary.json",
        summary_md_path=run_dir / "replay_summary.md",
    )
