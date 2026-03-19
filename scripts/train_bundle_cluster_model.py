"""Train an offline-only bundle/cluster analysis model from replay matrices."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from analytics.ml_model import MLTrainingConfig, load_trade_feature_matrix, train_model, write_ml_outputs


def _default_run_dir(run_id: str) -> Path:
    return Path("runs") / run_id


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", help="Run identifier under runs/<run_id>")
    parser.add_argument("--matrix-path", action="append", default=[], help="Explicit trade_feature_matrix.jsonl path(s)")
    parser.add_argument("--history-glob", default="", help="Optional glob for additional historical matrix files")
    parser.add_argument("--output-dir", default="", help="Directory for ML analysis artifacts")
    parser.add_argument("--model-dir", default="models", help="Directory for optional saved model artifacts")
    parser.add_argument("--min-train-rows", type=int, default=int(os.getenv("ML_MIN_TRAIN_ROWS", "200")))
    parser.add_argument("--target-name", default=os.getenv("ML_TARGET_NAME", "profitable_trade_flag"))
    parser.add_argument("--model-type", default=os.getenv("ML_MODEL_TYPE", "naive_bayes_histogram_classifier"))
    parser.add_argument(
        "--enable-predictions-output",
        action="store_true",
        default=os.getenv("ML_ENABLE_PREDICTIONS_OUTPUT", "false").strip().lower() in {"1", "true", "yes", "on"},
    )
    return parser.parse_args()


def _resolve_matrix_paths(args: argparse.Namespace) -> list[Path]:
    matrix_paths: list[Path] = []
    if args.run_id:
        matrix_paths.append(_default_run_dir(args.run_id) / "trade_feature_matrix.jsonl")
    matrix_paths.extend(Path(path) for path in args.matrix_path)
    if args.history_glob:
        matrix_paths.extend(sorted(Path().glob(args.history_glob)))

    unique_paths: list[Path] = []
    seen: set[Path] = set()
    for path in matrix_paths:
        resolved = path.expanduser().resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        unique_paths.append(resolved)
    return unique_paths


def main() -> int:
    args = _parse_args()
    matrix_paths = _resolve_matrix_paths(args)

    if args.output_dir:
        output_dir = Path(args.output_dir)
    elif args.run_id:
        output_dir = _default_run_dir(args.run_id)
    else:
        output_dir = Path("runs") / "ml_analysis"

    loaded = load_trade_feature_matrix(matrix_paths)
    config = MLTrainingConfig(
        min_train_rows=args.min_train_rows,
        target_name=args.target_name,
        model_type=args.model_type,
        enable_predictions_output=args.enable_predictions_output,
    )
    result = train_model(loaded.rows, config)
    if not loaded.source_paths and result.get("training_skipped"):
        result["skip_reason"] = "matrix_input_missing"
        result["source_paths"] = []
    result["requested_matrix_paths"] = [str(path) for path in matrix_paths]

    output_paths = write_ml_outputs(result, output_dir, model_dir=args.model_dir if not result.get("training_skipped") else None)
    printable = {k: v for k, v in {**result, **output_paths}.items() if k not in {"feature_importance", "model_bundle"}}
    print(json.dumps(printable, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
