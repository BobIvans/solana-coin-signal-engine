from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from analytics.offline_feature_importance import (  # noqa: E402
    compute_offline_feature_importance,
    load_feature_matrix,
    write_feature_importance_outputs,
)

FIXTURE_PATH = ROOT / "tests" / "fixtures" / "offline_feature_importance" / "healthy_mixed_replay_matrix.jsonl"
OUTPUT_DIR = ROOT / "data" / "smoke"


def main() -> int:
    matrix_payload = load_feature_matrix(FIXTURE_PATH)
    importance_payload = compute_offline_feature_importance(matrix_payload, generated_at="2026-03-20T00:00:00Z")
    outputs = write_feature_importance_outputs(
        importance_payload,
        OUTPUT_DIR,
        json_filename="offline_feature_importance.json",
        markdown_filename="offline_feature_importance_summary.md",
    )
    compact_summary = {
        "analysis_only": importance_payload["analysis_only"],
        "not_for_online_decisioning": importance_payload["not_for_online_decisioning"],
        "input_rows": importance_payload["input_artifact"]["row_count"],
        "excluded_rows": importance_payload["input_artifact"]["excluded_row_count"],
        "targets": {
            item["target_name"]: {
                "top_feature_group": item["grouped_importance"][0]["feature_group"] if item["grouped_importance"] else None,
                "top_feature": item["per_feature_importance"][0]["feature_name"] if item["per_feature_importance"] else None,
            }
            for item in importance_payload["targets"]
        },
        "outputs": outputs,
    }
    print(json.dumps(compact_summary, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
