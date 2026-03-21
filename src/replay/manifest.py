from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .deterministic import hash_config
from utils.io import write_json


def _utc_now() -> str:
    return datetime.now(tz=timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')


def build_manifest(config: dict[str, Any], args: Any) -> dict[str, Any]:
    return {
        "run_id": args.run_id,
        "mode": "historical_replay",
        "chain": config.get("chain", "solana"),
        "start_ts": args.start_ts,
        "end_ts": args.end_ts,
        "days": int(args.days),
        "seed": int(args.seed),
        "config_path": str(args.config),
        "config_hash": hash_config(config),
        "x_mode": str(config.get("x_mode", {}).get("status", "degraded")),
        "x_validation_score_baseline": int(config.get("x_mode", {}).get("baseline_score", 45)),
        "wallet_weighting": bool(args.wallet_weighting == "on"),
        "artifact_truth_layer": "trade_feature_matrix.jsonl",
        "created_at": _utc_now(),
    }


def write_manifest(path: str | Path, manifest: dict[str, Any]) -> Path:
    return write_json(path, manifest)
