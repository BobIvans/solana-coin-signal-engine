#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.replay.historical_replay_harness import run_historical_replay
from utils.io import ensure_dir, write_json


def main() -> int:
    output_base = ensure_dir(Path("data") / "smoke")
    result = run_historical_replay(
        artifact_dir=Path("tests") / "fixtures" / "historical_replay" / "full_win",
        run_id="historical_replay_smoke",
        config_path="config/replay.default.yaml",
        wallet_weighting="off",
        dry_run=True,
        output_base_dir=output_base,
        allow_synthetic_smoke=False,
    )
    run_dir = Path(result["outputs"]["run_dir"])
    summary = result["summary"].copy()
    summary.pop("summary_markdown", None)
    write_json(output_base / "historical_replay_summary.json", summary)
    (output_base / "historical_replay_summary.md").write_text(result["summary"]["summary_markdown"], encoding="utf-8")
    (output_base / "historical_trade_feature_matrix.jsonl").write_text(
        (run_dir / "trade_feature_matrix.jsonl").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
