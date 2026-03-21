"""Offline-only bundle/cluster ML analysis helpers."""

from __future__ import annotations

import json
import math
import pickle
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from utils.io import ensure_dir, write_json

SCHEMA_VERSION = "bundle_cluster_ml.v1"
DEFAULT_TARGET_NAME = "profitable_trade_flag"
DEFAULT_MODEL_TYPE = "naive_bayes_histogram_classifier"
DEFAULT_MIN_TRAIN_ROWS = 200
DEFAULT_ENABLE_PREDICTIONS_OUTPUT = False
DEFAULT_MODEL_FILENAME = "bundle_cluster_model.pkl"
DEFAULT_MODEL_META_FILENAME = "bundle_cluster_model_meta.json"
DEFAULT_SUMMARY_FILENAME = "ml_model_summary.json"
DEFAULT_IMPORTANCE_FILENAME = "ml_feature_importance.json"
DEFAULT_PREDICTIONS_FILENAME = "ml_predictions.jsonl"
_MISSING_TOKEN = "__missing__"
_NUMERIC_BIN_LABELS = ["q0", "q1", "q2", "q3"]
_LEAKY_OUTCOME_FIELDS = {
    "net_pnl_pct",
    "gross_pnl_pct",
    "hold_sec",
    "exit_reason_final",
    "mfe_pct",
    "mae_pct",
    "mfe_pct_240s",
    "mae_pct_240s",
    "trend_survival_15m",
    "trend_survival_60m",
    "time_to_first_profit_sec",
    "exit_decision",
    "exit_flags",
    "exit_warnings",
}

NUMERIC_FEATURES = [
    "final_score",
    "regime_confidence",
    "onchain_core",
    "early_signal_bonus",
    "x_validation_bonus",
    "rug_penalty",
    "spam_penalty",
    "confidence_adjustment",
    "wallet_adjustment",
    "bundle_aggression_bonus",
    "organic_multi_cluster_bonus",
    "single_cluster_penalty",
    "creator_cluster_penalty",
    "bundle_sell_heavy_penalty",
    "retry_manipulation_penalty",
    "bundle_count_first_60s",
    "bundle_size_value",
    "unique_wallets_per_bundle_avg",
    "bundle_timing_from_liquidity_add_min",
    "bundle_success_rate",
    "bundle_tip_efficiency",
    "cross_block_bundle_correlation",
    "bundle_wallet_clustering_score",
    "cluster_concentration_ratio",
    "num_unique_clusters_first_60s",
    "liquidity_usd",
    "buy_pressure_entry",
    "volume_velocity_entry",
    "holder_growth_5m_entry",
    "smart_wallet_hits_entry",
    "net_unique_buyers_60s",
    "liquidity_refill_ratio_120s",
    "cluster_sell_concentration_120s",
    "smart_wallet_dispersion_score",
    "x_author_velocity_5m",
    "seller_reentry_ratio",
    "liquidity_shock_recovery_sec",
    "smart_wallet_score_sum",
    "smart_wallet_tier1_hits",
    "smart_wallet_early_entry_hits",
    "smart_wallet_netflow_bias",
    "x_validation_score_entry",
    "x_validation_delta_entry",
]

CATEGORICAL_FEATURES = [
    "regime_decision",
    "expected_hold_class",
    "bundle_composition_dominant",
    "bundle_failure_retry_pattern",
    "creator_in_cluster_flag",
    "x_status",
]


@dataclass(frozen=True)
class MLTrainingConfig:
    min_train_rows: int = DEFAULT_MIN_TRAIN_ROWS
    target_name: str = DEFAULT_TARGET_NAME
    model_type: str = DEFAULT_MODEL_TYPE
    enable_predictions_output: bool = DEFAULT_ENABLE_PREDICTIONS_OUTPUT


@dataclass(frozen=True)
class LoadedMatrix:
    rows: list[dict[str, Any]]
    source_paths: list[str]


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        raw = line.strip()
        if raw:
            rows.append(json.loads(raw))
    return rows


def load_trade_feature_matrix(paths: list[Path | str]) -> LoadedMatrix:
    loaded_rows: list[dict[str, Any]] = []
    source_paths: list[str] = []
    for raw_path in paths:
        path = Path(raw_path).expanduser().resolve()
        if not path.exists():
            continue
        rows = _read_jsonl(path)
        if not rows:
            continue
        source_paths.append(str(path))
        loaded_rows.extend({**dict(row), "_source_path": str(path)} for row in rows)
    return LoadedMatrix(rows=loaded_rows, source_paths=source_paths)


def _safe_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(number) or math.isinf(number):
        return None
    return number


def _safe_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text if text else None


def _normalize_categorical(value: Any) -> str | None:
    if isinstance(value, bool):
        return "true" if value else "false"
    return _safe_str(value)


def _row_sort_key(row: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(row.get("ts") or ""),
        str(row.get("position_id") or ""),
        str(row.get("token_address") or ""),
    )


def _derive_profitable_trade_flag(row: dict[str, Any]) -> int | None:
    net_pnl_pct = _safe_float(row.get("net_pnl_pct"))
    if net_pnl_pct is None:
        return None
    return 1 if net_pnl_pct > 0.0 else 0


def _derive_fast_failure_flag(row: dict[str, Any]) -> int | None:
    net_pnl_pct = _safe_float(row.get("net_pnl_pct"))
    hold_sec = _safe_float(row.get("hold_sec"))
    if net_pnl_pct is None or hold_sec is None:
        return None
    return 1 if hold_sec <= 300.0 and net_pnl_pct <= 0.0 else 0


def derive_targets(rows: list[dict[str, Any]], target_name: str) -> list[int | None]:
    if target_name == "profitable_trade_flag":
        return [_derive_profitable_trade_flag(row) for row in rows]
    if target_name == "fast_failure_flag":
        return [_derive_fast_failure_flag(row) for row in rows]
    raise ValueError(f"Unsupported ML target: {target_name}")


def _build_feature_row(row: dict[str, Any]) -> dict[str, Any]:
    record: dict[str, Any] = {}
    for feature in NUMERIC_FEATURES:
        if feature in _LEAKY_OUTCOME_FIELDS:
            continue
        record[feature] = _safe_float(row.get(feature))
    for feature in CATEGORICAL_FEATURES:
        if feature in _LEAKY_OUTCOME_FIELDS:
            continue
        record[feature] = _normalize_categorical(row.get(feature))
    return record


def build_training_dataframe(rows: list[dict[str, Any]], target_name: str) -> tuple[list[dict[str, Any]], list[int], list[dict[str, Any]]]:
    ordered_rows = sorted((dict(row) for row in rows), key=_row_sort_key)
    targets = derive_targets(ordered_rows, target_name)

    filtered_feature_rows: list[dict[str, Any]] = []
    filtered_targets: list[int] = []
    filtered_source_rows: list[dict[str, Any]] = []
    for row, target in zip(ordered_rows, targets):
        if target is None:
            continue
        filtered_feature_rows.append(_build_feature_row(row))
        filtered_targets.append(target)
        filtered_source_rows.append(row)
    return filtered_feature_rows, filtered_targets, filtered_source_rows


def _label_distribution(labels: list[int]) -> dict[str, int]:
    return {
        "negative": sum(1 for label in labels if int(label) == 0),
        "positive": sum(1 for label in labels if int(label) == 1),
    }


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _stddev(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    mean = _mean(values)
    variance = sum((value - mean) ** 2 for value in values) / len(values)
    return math.sqrt(variance)


def _quantile(sorted_values: list[float], ratio: float) -> float:
    if not sorted_values:
        return 0.0
    if len(sorted_values) == 1:
        return sorted_values[0]
    position = ratio * (len(sorted_values) - 1)
    lower = int(math.floor(position))
    upper = int(math.ceil(position))
    if lower == upper:
        return sorted_values[lower]
    weight = position - lower
    return sorted_values[lower] * (1.0 - weight) + sorted_values[upper] * weight


def _compute_numeric_spec(values: list[float]) -> dict[str, Any]:
    ordered = sorted(values)
    return {
        "median": _quantile(ordered, 0.5),
        "boundaries": [_quantile(ordered, 0.25), _quantile(ordered, 0.5), _quantile(ordered, 0.75)],
    }


def _numeric_token(value: float | None, spec: dict[str, Any]) -> str:
    if value is None:
        return _MISSING_TOKEN
    boundaries = [float(boundary) for boundary in spec.get("boundaries", [])]
    if not boundaries:
        return _NUMERIC_BIN_LABELS[0]
    for index, boundary in enumerate(boundaries):
        if value <= boundary:
            return _NUMERIC_BIN_LABELS[index]
    return _NUMERIC_BIN_LABELS[len(boundaries)]


def _feature_token(feature_name: str, value: Any, model_bundle: dict[str, Any]) -> str:
    feature_specs = model_bundle["feature_specs"]
    kind = feature_specs[feature_name]["kind"]
    if kind == "numeric":
        return _numeric_token(_safe_float(value), feature_specs[feature_name])
    normalized = _normalize_categorical(value)
    return normalized if normalized is not None else _MISSING_TOKEN


def _fit_naive_bayes_histogram_model(train_rows: list[dict[str, Any]], train_labels: list[int]) -> dict[str, Any]:
    feature_specs: dict[str, dict[str, Any]] = {}
    feature_token_counts: dict[str, dict[str, dict[str, int]]] = {}

    for feature in NUMERIC_FEATURES:
        present_values = [float(row[feature]) for row in train_rows if row.get(feature) is not None]
        numeric_spec = _compute_numeric_spec(present_values) if present_values else {"median": 0.0, "boundaries": []}
        feature_specs[feature] = {"kind": "numeric", **numeric_spec}
    for feature in CATEGORICAL_FEATURES:
        categories = sorted({str(row.get(feature)) for row in train_rows if row.get(feature) is not None})
        feature_specs[feature] = {"kind": "categorical", "categories": categories}

    for feature in NUMERIC_FEATURES + CATEGORICAL_FEATURES:
        feature_token_counts[feature] = {"positive": {}, "negative": {}}

    for row, label in zip(train_rows, train_labels):
        target_key = "positive" if label == 1 else "negative"
        for feature in NUMERIC_FEATURES + CATEGORICAL_FEATURES:
            token = _feature_token(feature, row.get(feature), {"feature_specs": feature_specs})
            current = feature_token_counts[feature][target_key].get(token, 0)
            feature_token_counts[feature][target_key][token] = current + 1

    prior_positive = (sum(train_labels) + 1.0) / (len(train_labels) + 2.0)
    return {
        "model_type": DEFAULT_MODEL_TYPE,
        "feature_specs": feature_specs,
        "feature_token_counts": feature_token_counts,
        "prior_positive": prior_positive,
        "train_row_count": len(train_rows),
    }


def _predict_probability(model_bundle: dict[str, Any], row: dict[str, Any]) -> tuple[float, dict[str, float]]:
    prior_positive = float(model_bundle["prior_positive"])
    log_odds = math.log(prior_positive / max(1e-9, 1.0 - prior_positive))
    contributions: dict[str, float] = {}

    for feature in NUMERIC_FEATURES + CATEGORICAL_FEATURES:
        token = _feature_token(feature, row.get(feature), model_bundle)
        counts = model_bundle["feature_token_counts"][feature]
        positive_counts = counts["positive"]
        negative_counts = counts["negative"]
        vocabulary = sorted(set(positive_counts) | set(negative_counts) | {_MISSING_TOKEN})
        alpha = 1.0
        positive_total = sum(positive_counts.values())
        negative_total = sum(negative_counts.values())
        positive_prob = (positive_counts.get(token, 0) + alpha) / (positive_total + alpha * len(vocabulary))
        negative_prob = (negative_counts.get(token, 0) + alpha) / (negative_total + alpha * len(vocabulary))
        contribution = math.log(max(1e-9, positive_prob) / max(1e-9, negative_prob))
        contributions[feature] = contribution
        log_odds += contribution

    probability = 1.0 / (1.0 + math.exp(-max(min(log_odds, 30.0), -30.0)))
    return probability, contributions


def _compute_classification_metrics(y_true: list[int], y_pred: list[int], y_prob: list[float]) -> dict[str, Any]:
    true_positive = sum(1 for actual, predicted in zip(y_true, y_pred) if actual == 1 and predicted == 1)
    true_negative = sum(1 for actual, predicted in zip(y_true, y_pred) if actual == 0 and predicted == 0)
    false_positive = sum(1 for actual, predicted in zip(y_true, y_pred) if actual == 0 and predicted == 1)
    false_negative = sum(1 for actual, predicted in zip(y_true, y_pred) if actual == 1 and predicted == 0)
    total = len(y_true)
    accuracy = (true_positive + true_negative) / total if total else 0.0
    precision = true_positive / (true_positive + false_positive) if (true_positive + false_positive) else 0.0
    recall = true_positive / (true_positive + false_negative) if (true_positive + false_negative) else 0.0
    f1 = (2.0 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    brier = sum((actual - probability) ** 2 for actual, probability in zip(y_true, y_prob)) / total if total else 0.0
    return {
        "validation_row_count": total,
        "accuracy": accuracy,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "brier_score": brier,
    }


def _compute_numeric_feature_importance(rows: list[dict[str, Any]], labels: list[int], feature: str) -> dict[str, Any]:
    positive_values = [float(row[feature]) for row, label in zip(rows, labels) if label == 1 and row.get(feature) is not None]
    negative_values = [float(row[feature]) for row, label in zip(rows, labels) if label == 0 and row.get(feature) is not None]
    all_values = positive_values + negative_values
    scale = _stddev(all_values) or 1.0
    importance = abs(_mean(positive_values) - _mean(negative_values)) / scale if all_values else 0.0
    present_count = len(all_values)
    return {
        "feature_name": feature,
        "kind": "numeric",
        "importance": float(importance),
        "present_count": present_count,
        "missing_count": len(rows) - present_count,
        "positive_mean": _mean(positive_values),
        "negative_mean": _mean(negative_values),
    }


def _compute_categorical_feature_importance(rows: list[dict[str, Any]], labels: list[int], feature: str) -> dict[str, Any]:
    base_rate = _mean([float(label) for label in labels])
    grouped: dict[str, list[int]] = {}
    missing_count = 0
    for row, label in zip(rows, labels):
        token = _normalize_categorical(row.get(feature))
        if token is None:
            missing_count += 1
            token = _MISSING_TOKEN
        grouped.setdefault(token, []).append(label)

    weighted_gap = 0.0
    category_rates: list[dict[str, Any]] = []
    for token, token_labels in sorted(grouped.items()):
        rate = _mean([float(label) for label in token_labels])
        weight = len(token_labels) / len(rows) if rows else 0.0
        weighted_gap += abs(rate - base_rate) * weight
        category_rates.append({"category": token, "count": len(token_labels), "positive_rate": rate})

    return {
        "feature_name": feature,
        "kind": "categorical",
        "importance": float(weighted_gap),
        "present_count": len(rows) - missing_count,
        "missing_count": missing_count,
        "category_rates": category_rates,
    }


def compute_feature_importance(rows: list[dict[str, Any]], labels: list[int]) -> list[dict[str, Any]]:
    ranked = [
        *[_compute_numeric_feature_importance(rows, labels, feature) for feature in NUMERIC_FEATURES],
        *[_compute_categorical_feature_importance(rows, labels, feature) for feature in CATEGORICAL_FEATURES],
    ]
    ranked.sort(key=lambda item: (-float(item["importance"]), item["feature_name"]))
    return ranked


def _training_feature_stats(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    stats: dict[str, dict[str, Any]] = {}
    for feature in NUMERIC_FEATURES:
        present_count = sum(1 for row in rows if row.get(feature) is not None)
        stats[feature] = {"kind": "numeric", "present_count": present_count, "missing_count": len(rows) - present_count}
    for feature in CATEGORICAL_FEATURES:
        values = [row.get(feature) for row in rows if row.get(feature) is not None]
        stats[feature] = {
            "kind": "categorical",
            "present_count": len(values),
            "missing_count": len(rows) - len(values),
            "distinct_values": sorted({str(value) for value in values}),
        }
    return stats


def _validation_split_index(row_count: int) -> int:
    validation_count = max(1, int(round(row_count * 0.2)))
    validation_count = min(validation_count, row_count - 1)
    return row_count - validation_count


def _build_skip_summary(
    *,
    config: MLTrainingConfig,
    train_row_count: int,
    source_paths: list[str],
    feature_names: list[str] | None = None,
    skip_reason: str,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "model_type": config.model_type,
        "target_name": config.target_name,
        "train_row_count": train_row_count,
        "feature_names": feature_names or [],
        "source_paths": source_paths,
        "training_skipped": True,
        "skip_reason": skip_reason,
        "top_feature_importance": [],
        "feature_importance": [],
        "evaluation_metrics": {},
    }
    if extra:
        summary.update(extra)
    return summary


def train_model(rows: list[dict[str, Any]], config: MLTrainingConfig) -> dict[str, Any]:
    features, labels, source_rows = build_training_dataframe(rows, config.target_name)
    base_feature_names = NUMERIC_FEATURES + CATEGORICAL_FEATURES
    source_paths = sorted({str(row.get("_source_path")) for row in source_rows if row.get("_source_path")})

    if config.model_type != DEFAULT_MODEL_TYPE:
        return _build_skip_summary(
            config=config,
            train_row_count=len(features),
            source_paths=source_paths,
            feature_names=base_feature_names,
            skip_reason="unsupported_model_type",
        )

    if not features:
        return _build_skip_summary(
            config=config,
            train_row_count=0,
            source_paths=source_paths,
            feature_names=base_feature_names,
            skip_reason="no_labeled_rows",
        )

    label_distribution = _label_distribution(labels)
    feature_stats = _training_feature_stats(features)

    if len(features) < config.min_train_rows:
        return _build_skip_summary(
            config=config,
            train_row_count=len(features),
            source_paths=source_paths,
            feature_names=base_feature_names,
            skip_reason="insufficient_samples",
            extra={"label_distribution": label_distribution, "feature_stats": feature_stats},
        )

    if min(label_distribution.values()) == 0:
        return _build_skip_summary(
            config=config,
            train_row_count=len(features),
            source_paths=source_paths,
            feature_names=base_feature_names,
            skip_reason="single_class_target",
            extra={"label_distribution": label_distribution, "feature_stats": feature_stats},
        )

    split_index = _validation_split_index(len(features))
    x_train = features[:split_index]
    x_valid = features[split_index:]
    y_train = labels[:split_index]
    y_valid = labels[split_index:]
    valid_source_rows = source_rows[split_index:]

    if not x_train or not x_valid:
        return _build_skip_summary(
            config=config,
            train_row_count=len(features),
            source_paths=source_paths,
            feature_names=base_feature_names,
            skip_reason="insufficient_split_rows",
            extra={"label_distribution": label_distribution, "feature_stats": feature_stats},
        )

    if len(set(y_train)) < 2 or len(set(y_valid)) < 2:
        return _build_skip_summary(
            config=config,
            train_row_count=len(features),
            source_paths=source_paths,
            feature_names=base_feature_names,
            skip_reason="insufficient_class_variation_after_split",
            extra={"label_distribution": label_distribution, "feature_stats": feature_stats},
        )

    model_bundle = _fit_naive_bayes_histogram_model(x_train, y_train)
    feature_importance = compute_feature_importance(x_train, y_train)
    probabilities: list[float] = []
    predictions: list[int] = []
    prediction_rows: list[dict[str, Any]] = []

    for source_row, feature_row, actual_label in zip(valid_source_rows, x_valid, y_valid):
        probability, contributions = _predict_probability(model_bundle, feature_row)
        predicted_label = 1 if probability >= 0.5 else 0
        probabilities.append(probability)
        predictions.append(predicted_label)
        if config.enable_predictions_output:
            sorted_contributions = sorted(contributions.items(), key=lambda item: (-abs(item[1]), item[0]))[:5]
            prediction_rows.append(
                {
                    "position_id": source_row.get("position_id"),
                    "token_address": source_row.get("token_address"),
                    "ts": source_row.get("ts"),
                    "target_name": config.target_name,
                    "actual_label": int(actual_label),
                    "predicted_label": predicted_label,
                    "predicted_probability": probability,
                    "top_contributors": [
                        {"feature_name": name, "log_odds_contribution": contribution}
                        for name, contribution in sorted_contributions
                    ],
                }
            )

    evaluation_metrics = _compute_classification_metrics(y_valid, predictions, probabilities)

    return {
        "schema_version": SCHEMA_VERSION,
        "model_type": config.model_type,
        "target_name": config.target_name,
        "train_row_count": len(features),
        "feature_names": base_feature_names,
        "source_paths": source_paths,
        "training_skipped": False,
        "skip_reason": None,
        "label_distribution": label_distribution,
        "feature_stats": feature_stats,
        "validation_split": {
            "train_rows": len(x_train),
            "validation_rows": len(x_valid),
            "method": "time_ordered_tail_split",
        },
        "evaluation_metrics": evaluation_metrics,
        "top_feature_importance": feature_importance[:20],
        "feature_importance": feature_importance,
        "model_bundle": {
            **model_bundle,
            "prediction_rows": prediction_rows,
        },
    }


def _build_importance_payload(summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "model_type": summary.get("model_type"),
        "target_name": summary.get("target_name"),
        "train_row_count": summary.get("train_row_count", 0),
        "training_skipped": summary.get("training_skipped", False),
        "skip_reason": summary.get("skip_reason"),
        "feature_importance": summary.get("feature_importance", summary.get("top_feature_importance", [])),
    }


def write_ml_outputs(result: dict[str, Any], output_dir: Path | str, *, model_dir: Path | str | None = None) -> dict[str, str]:
    target_dir = ensure_dir(output_dir)
    summary = dict(result)
    model_bundle = summary.pop("model_bundle", None)
    prediction_rows = []
    if model_bundle:
        prediction_rows = list(model_bundle.get("prediction_rows", []))

    summary_path = write_json(target_dir / DEFAULT_SUMMARY_FILENAME, summary)
    importance_path = write_json(target_dir / DEFAULT_IMPORTANCE_FILENAME, _build_importance_payload(summary))

    output_paths = {
        "summary_path": str(summary_path),
        "feature_importance_path": str(importance_path),
    }

    if prediction_rows:
        predictions_path = target_dir / DEFAULT_PREDICTIONS_FILENAME
        predictions_path.write_text(
            "\n".join(json.dumps(row, sort_keys=True) for row in prediction_rows) + "\n",
            encoding="utf-8",
        )
        output_paths["predictions_path"] = str(predictions_path)

    if model_bundle and model_dir is not None:
        model_target_dir = ensure_dir(model_dir)
        model_path = model_target_dir / DEFAULT_MODEL_FILENAME
        with model_path.open("wb") as handle:
            pickle.dump(model_bundle, handle)
        model_meta_payload = {
            "schema_version": SCHEMA_VERSION,
            "model_type": summary.get("model_type"),
            "target_name": summary.get("target_name"),
            "train_row_count": summary.get("train_row_count", 0),
            "feature_names": summary.get("feature_names", []),
            "top_feature_importance": summary.get("top_feature_importance", []),
            "evaluation_metrics": summary.get("evaluation_metrics", {}),
            "training_skipped": False,
        }
        model_meta_path = write_json(model_target_dir / DEFAULT_MODEL_META_FILENAME, model_meta_payload)
        output_paths["model_path"] = str(model_path)
        output_paths["model_meta_path"] = str(model_meta_path)

    return output_paths
