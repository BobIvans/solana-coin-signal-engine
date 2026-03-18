"""Deterministic wallet weighting calibration for off/shadow/on rollouts."""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Any

from utils.io import append_jsonl, ensure_dir, read_json, write_json

CONTRACT_VERSION = "wallet_weighting_calibration_v1"
ALLOWED_RECOMMENDATIONS = {"keep_off", "keep_shadow", "promote_to_on", "rollback_to_off"}
SAFE_DEFAULT_MODE = "shadow"
_MODE_ORDER = ("off", "shadow", "on")
_PNL_KEYS = ("net_pnl_pct", "pnl_pct", "net_pnl_sol", "pnl_sol")
_GROSS_PNL_KEYS = ("gross_pnl_pct", "gross_pnl_sol")
_WALLET_DELTA_KEYS = (
    "wallet_score_delta",
    "wallet_adjustment_score",
    "wallet_bonus_score",
    "wallet_score_adjustment",
    "wallet_delta",
    "score_wallet_delta",
)
_REGISTRY_STATUS_KEYS = (
    "wallet_registry_status",
    "registry_status",
    "wallet_status",
)
_TIMESTAMP_KEYS = (
    "generated_at",
    "as_of",
    "timestamp",
    "ts",
    "scored_at",
    "opened_at",
    "closed_at",
    "entry_time_utc",
    "exit_time_utc",
    "time",
)


@dataclass(frozen=True)
class Thresholds:
    max_top_n: int = 25
    min_trades_medium_confidence: int = 20
    min_trades_high_confidence: int = 50
    promote_expectancy_margin: float = 0.01
    rollback_expectancy_margin: float = 0.01
    false_positive_tolerance: float = 0.05
    false_positive_rollback: float = 0.10
    outlier_concentration_limit: float = 0.65
    score_shift_concentration_limit: float = 0.80
    degraded_registry_limit: float = 0.50


def _parse_ts(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    text = str(value).strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _deterministic_iso(rows: list[dict[str, Any]]) -> str:
    candidates: list[datetime] = []

    def _walk(node: Any) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if key in _TIMESTAMP_KEYS:
                    parsed = _parse_ts(value)
                    if parsed is not None:
                        candidates.append(parsed)
                _walk(value)
        elif isinstance(node, list):
            for item in node:
                _walk(item)

    for row in rows:
        _walk(row)
    if not candidates:
        return "1970-01-01T00:00:00Z"
    return max(candidates).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _extract_records(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in ("tokens", "positions", "records", "rows"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
    return []


def _read_jsonl(path: Path | None) -> list[dict[str, Any]]:
    if path is None or not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        raw = line.strip()
        if not raw:
            continue
        rows.append(json.loads(raw))
    return rows


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> Path:
    ensure_dir(path.parent)
    path.write_text("\n".join(json.dumps(row, sort_keys=True, ensure_ascii=False) for row in rows) + "\n", encoding="utf-8")
    return path


def _candidate_paths(base_dir: Path | None, names: list[str]) -> list[Path]:
    if base_dir is None:
        return []
    resolved = base_dir.expanduser().resolve()
    candidates: list[Path] = []
    for name in names:
        candidates.append(resolved / name)
        candidates.append(resolved / "processed" / name)
    return candidates


def _first_existing(paths: list[Path]) -> Path | None:
    for path in paths:
        if path.exists():
            return path
    return None


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _top_token_addresses(records: list[dict[str, Any]], max_top_n: int) -> list[str]:
    ranked = sorted(
        [record for record in records if str(record.get("token_address") or "")],
        key=lambda item: (-_safe_float(item.get("final_score")), str(item.get("token_address") or "")),
    )
    return [str(item.get("token_address")) for item in ranked[:max_top_n]]


def _rank_map(records: list[dict[str, Any]]) -> dict[str, int]:
    ranked = _top_token_addresses(records, len(records) or 1)
    return {token_address: idx + 1 for idx, token_address in enumerate(ranked)}


def _wallet_delta(record: dict[str, Any]) -> float:
    for key in _WALLET_DELTA_KEYS:
        if key in record:
            return _safe_float(record.get(key))
    wallet_adjustment = record.get("wallet_adjustment")
    if isinstance(wallet_adjustment, dict):
        for key in ("applied_delta", "score_delta", "final_score_delta", "wallet_score_delta"):
            if key in wallet_adjustment:
                return _safe_float(wallet_adjustment.get(key))
    return 0.0


def _registry_degraded(record: dict[str, Any]) -> bool:
    for key in _REGISTRY_STATUS_KEYS:
        status = str(record.get(key) or "").strip().lower()
        if status in {"degraded", "missing", "unavailable", "error"}:
            return True
    for key in ("wallet_registry_degraded", "registry_degraded", "wallet_features_degraded"):
        if bool(record.get(key)):
            return True
    wallet_adjustment = record.get("wallet_adjustment")
    if isinstance(wallet_adjustment, dict):
        status = str(wallet_adjustment.get("registry_status") or "").strip().lower()
        if status in {"degraded", "missing", "unavailable", "error"}:
            return True
        if bool(wallet_adjustment.get("registry_degraded")):
            return True
    return False


def _score_summary(records: list[dict[str, Any]], *, max_top_n: int) -> dict[str, Any]:
    top_addresses = _top_token_addresses(records, min(max_top_n, len(records) or max_top_n))
    wallet_deltas = [_wallet_delta(record) for record in records]
    degraded_count = sum(1 for record in records if _registry_degraded(record))
    return {
        "available": bool(records),
        "tokens_available": len(records),
        "top_token_addresses": top_addresses,
        "average_final_score": round(sum(_safe_float(r.get("final_score")) for r in records) / len(records), 6) if records else None,
        "average_wallet_delta": round(sum(wallet_deltas) / len(wallet_deltas), 6) if wallet_deltas else None,
        "degraded_registry_share": round(degraded_count / len(records), 6) if records else None,
    }


def compare_token_scores(
    baseline_records: list[dict[str, Any]],
    candidate_records: list[dict[str, Any]],
    *,
    max_top_n: int,
) -> dict[str, Any]:
    baseline_by_addr = {str(item.get("token_address")): item for item in baseline_records if str(item.get("token_address") or "")}
    candidate_by_addr = {str(item.get("token_address")): item for item in candidate_records if str(item.get("token_address") or "")}
    shared = sorted(set(baseline_by_addr) & set(candidate_by_addr))
    if not shared:
        return {
            "tokens_compared": 0,
            "overlap_top_n": 0,
            "promoted_tokens_count": 0,
            "demoted_tokens_count": 0,
            "average_score_delta_vs_off": None,
            "average_abs_rank_delta_vs_off": None,
            "score_shift_concentration": None,
            "share_of_positive_score_shifts": None,
            "wallet_delta_mean": None,
            "wallet_delta_positive_share": None,
            "degraded_registry_share": None,
        }
    baseline_ranks = _rank_map(baseline_records)
    candidate_ranks = _rank_map(candidate_records)
    deltas: list[float] = []
    abs_rank_deltas: list[float] = []
    promoted = 0
    demoted = 0
    positive_deltas: list[float] = []
    wallet_deltas: list[float] = []
    degraded = 0
    for address in shared:
        base = baseline_by_addr[address]
        cand = candidate_by_addr[address]
        delta = _safe_float(cand.get("final_score")) - _safe_float(base.get("final_score"))
        deltas.append(delta)
        abs_rank_deltas.append(abs(candidate_ranks.get(address, 0) - baseline_ranks.get(address, 0)))
        if delta > 0:
            promoted += 1
            positive_deltas.append(delta)
        elif delta < 0:
            demoted += 1
        wallet_deltas.append(_wallet_delta(cand))
        if _registry_degraded(cand):
            degraded += 1
    top_n = min(max_top_n, len(baseline_records), len(candidate_records))
    overlap = len(set(_top_token_addresses(baseline_records, top_n)) & set(_top_token_addresses(candidate_records, top_n)))
    sorted_positive = sorted((abs(value) for value in positive_deltas), reverse=True)
    positive_total = sum(sorted_positive)
    concentration = None
    if positive_total > 0:
        concentration = round(sum(sorted_positive[:2]) / positive_total, 6)
    positive_share = promoted / len(shared)
    wallet_positive_share = sum(1 for value in wallet_deltas if value > 0) / len(wallet_deltas) if wallet_deltas else None
    return {
        "tokens_compared": len(shared),
        "overlap_top_n": overlap,
        "promoted_tokens_count": promoted,
        "demoted_tokens_count": demoted,
        "average_score_delta_vs_off": round(sum(deltas) / len(deltas), 6),
        "average_abs_rank_delta_vs_off": round(sum(abs_rank_deltas) / len(abs_rank_deltas), 6),
        "score_shift_concentration": concentration,
        "share_of_positive_score_shifts": round(positive_share, 6),
        "wallet_delta_mean": round(sum(wallet_deltas) / len(wallet_deltas), 6) if wallet_deltas else None,
        "wallet_delta_positive_share": round(wallet_positive_share, 6) if wallet_positive_share is not None else None,
        "degraded_registry_share": round(degraded / len(shared), 6),
    }


def _closed_positions_from_positions(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    closed: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        status = str(row.get("status") or "").lower()
        if status and status != "closed":
            continue
        pnl = None
        pnl_key = None
        for key in _PNL_KEYS:
            if row.get(key) is not None:
                pnl = _safe_float(row.get(key))
                pnl_key = key
                break
        if pnl_key is None:
            continue
        gross = None
        for key in _GROSS_PNL_KEYS:
            if row.get(key) is not None:
                gross = _safe_float(row.get(key))
                break
        fees = _safe_float(row.get("fees_paid_sol"))
        slippage = _safe_float(row.get("slippage_cost_sol_est"))
        closed.append(
            {
                "position_id": str(row.get("position_id") or row.get("id") or f"pos_{len(closed)+1}"),
                "token_address": str(row.get("token_address") or ""),
                "pnl": pnl,
                "pnl_key": pnl_key,
                "gross_pnl": gross,
                "fees_paid": fees,
                "slippage_cost": slippage,
                "timestamp": str(row.get("closed_at") or row.get("timestamp") or row.get("exit_time") or ""),
            }
        )
    closed.sort(key=lambda item: (item["timestamp"], item["position_id"]))
    return closed


def _closed_positions_from_trades(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if not isinstance(row, dict):
            continue
        position_id = str(row.get("position_id") or "")
        if position_id:
            grouped[position_id].append(row)
    closed: list[dict[str, Any]] = []
    for position_id in sorted(grouped):
        trade_rows = grouped[position_id]
        sells = [row for row in trade_rows if str(row.get("side") or row.get("trade_type") or "").lower() in {"sell", "exit"}]
        if not sells:
            continue
        last_sell = sorted(sells, key=lambda row: str(row.get("timestamp") or row.get("time") or ""))[-1]
        pnl = None
        pnl_key = None
        for key in _PNL_KEYS:
            if last_sell.get(key) is not None:
                pnl = _safe_float(last_sell.get(key))
                pnl_key = key
                break
        if pnl_key is None:
            continue
        gross = None
        for key in _GROSS_PNL_KEYS:
            if last_sell.get(key) is not None:
                gross = _safe_float(last_sell.get(key))
                break
        closed.append(
            {
                "position_id": position_id,
                "token_address": str(last_sell.get("token_address") or ""),
                "pnl": pnl,
                "pnl_key": pnl_key,
                "gross_pnl": gross,
                "fees_paid": _safe_float(last_sell.get("fees_paid_sol")),
                "slippage_cost": _safe_float(last_sell.get("slippage_cost_sol_est")),
                "timestamp": str(last_sell.get("timestamp") or last_sell.get("time") or ""),
            }
        )
    closed.sort(key=lambda item: (item["timestamp"], item["position_id"]))
    return closed


def summarize_outcomes(closed_positions: list[dict[str, Any]]) -> dict[str, Any]:
    if not closed_positions:
        return {
            "available": False,
            "closed_trades": 0,
        }
    pnls = [float(item["pnl"]) for item in closed_positions]
    pnl_unit = closed_positions[0]["pnl_key"]
    gross_values = [item["gross_pnl"] for item in closed_positions if item.get("gross_pnl") is not None]
    wins = [value for value in pnls if value > 0]
    losses = [value for value in pnls if value <= 0]
    false_positive_rate = len(losses) / len(pnls)
    friction_adjusted = pnls[:]
    if pnl_unit.endswith("_sol"):
        if gross_values and len(gross_values) == len(pnls):
            friction_adjusted = pnls[:]
            mean_pnl = sum(gross_values) / len(gross_values)
        else:
            mean_pnl = sum(pnls) / len(pnls)
    else:
        mean_pnl = sum(gross_values) / len(gross_values) if gross_values and len(gross_values) == len(pnls) else sum(pnls) / len(pnls)
    cumulative = 0.0
    low_watermark = 0.0
    for value in pnls:
        cumulative += value
        low_watermark = min(low_watermark, cumulative)
    positive_total = sum(value for value in pnls if value > 0)
    top_positive = sorted((value for value in pnls if value > 0), reverse=True)
    top_two_share = None
    if positive_total > 0:
        top_two_share = round(sum(top_positive[:2]) / positive_total, 6)
    return {
        "available": True,
        "closed_trades": len(closed_positions),
        "pnl_unit": pnl_unit,
        "expectancy": round(sum(pnls) / len(pnls), 6),
        "winrate": round(len(wins) / len(pnls), 6),
        "median_pnl": round(float(median(pnls)), 6),
        "mean_pnl": round(float(mean_pnl), 6),
        "false_positive_rate": round(false_positive_rate, 6),
        "friction_adjusted_expectancy": round(sum(friction_adjusted) / len(friction_adjusted), 6),
        "drawdown_proxy": round(abs(low_watermark), 6),
        "outlier_top2_positive_share": top_two_share,
    }


def _summary_metrics(summary: dict[str, Any]) -> dict[str, Any]:
    metrics = {
        "available": bool(summary),
        "closed_trades": _safe_int(summary.get("total_positions_closed") or summary.get("closed_trades")),
        "pnl_unit": str(summary.get("pnl_unit") or "net_pnl_pct"),
        "expectancy": summary.get("expectancy"),
        "winrate": summary.get("winrate") if summary.get("winrate") is not None else summary.get("winrate_total"),
        "median_pnl": summary.get("median_pnl"),
        "mean_pnl": summary.get("mean_pnl"),
        "false_positive_rate": summary.get("false_positive_rate"),
        "friction_adjusted_expectancy": summary.get("friction_adjusted_expectancy"),
        "drawdown_proxy": summary.get("drawdown_proxy"),
        "outlier_top2_positive_share": summary.get("outlier_top2_positive_share"),
    }
    if metrics["closed_trades"] <= 0:
        metrics["available"] = False
    for key in ("expectancy", "winrate", "median_pnl", "mean_pnl", "false_positive_rate", "friction_adjusted_expectancy", "drawdown_proxy", "outlier_top2_positive_share"):
        if metrics[key] is not None:
            metrics[key] = round(_safe_float(metrics[key]), 6)
    return metrics


def _load_outcome_metrics(base_dir: Path | None) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, str]]:
    outcome_sources: dict[str, str] = {}
    if base_dir is None:
        return {"available": False, "closed_trades": 0}, [], outcome_sources
    summary_path = _first_existing(
        _candidate_paths(base_dir, ["post_run_analysis.json", "post_run_summary.json"])
    )
    if summary_path is not None:
        summary = read_json(summary_path, default={})
        outcome_sources["summary_path"] = str(summary_path)
        metrics = _summary_metrics(summary if isinstance(summary, dict) else {})
        if metrics.get("available"):
            return metrics, [], outcome_sources
    positions_path = _first_existing(_candidate_paths(base_dir, ["positions.json"]))
    if positions_path is not None:
        positions_payload = read_json(positions_path, default=[])
        positions = _extract_records(positions_payload) if isinstance(positions_payload, dict) else positions_payload
        closed = _closed_positions_from_positions([item for item in positions if isinstance(item, dict)])
        if closed:
            outcome_sources["positions_path"] = str(positions_path)
            return summarize_outcomes(closed), closed, outcome_sources
    trades_path = _first_existing(_candidate_paths(base_dir, ["trades.jsonl"]))
    if trades_path is not None:
        trades = _read_jsonl(trades_path)
        closed = _closed_positions_from_trades(trades)
        if closed:
            outcome_sources["trades_path"] = str(trades_path)
            return summarize_outcomes(closed), closed, outcome_sources
    return {"available": False, "closed_trades": 0}, [], outcome_sources


@dataclass(frozen=True)
class ModeArtifacts:
    mode: str
    scored_path: Path | None
    base_dir: Path | None
    scored_records: list[dict[str, Any]]
    score_summary: dict[str, Any]
    outcome_metrics: dict[str, Any]
    closed_positions: list[dict[str, Any]]
    sources: dict[str, str]


def load_mode_artifacts(
    *,
    mode: str,
    processed_dir: Path,
    scored_path: Path | None,
    base_dir: Path | None,
    thresholds: Thresholds,
) -> ModeArtifacts:
    resolved_scored = scored_path
    if resolved_scored is None:
        candidate = processed_dir / f"scored_tokens.{mode}.json"
        if candidate.exists():
            resolved_scored = candidate
    scored_payload = read_json(resolved_scored, default={}) if resolved_scored is not None else {}
    scored_records = _extract_records(scored_payload)
    score_summary = _score_summary(scored_records, max_top_n=thresholds.max_top_n)
    resolved_base_dir = base_dir
    if resolved_base_dir is None:
        candidate = processed_dir / mode
        if candidate.exists() and candidate.is_dir():
            resolved_base_dir = candidate
        else:
            resolved_base_dir = processed_dir
    outcome_metrics, closed_positions, outcome_sources = _load_outcome_metrics(resolved_base_dir)
    sources: dict[str, str] = {**outcome_sources}
    if resolved_scored is not None:
        sources["scored_path"] = str(resolved_scored)
    if resolved_base_dir is not None:
        sources["base_dir"] = str(resolved_base_dir)
    return ModeArtifacts(
        mode=mode,
        scored_path=resolved_scored,
        base_dir=resolved_base_dir,
        scored_records=scored_records,
        score_summary=score_summary,
        outcome_metrics=outcome_metrics,
        closed_positions=closed_positions,
        sources=sources,
    )


def _sample_size_confidence(closed_trades: int, thresholds: Thresholds) -> str:
    if closed_trades >= thresholds.min_trades_high_confidence:
        return "high"
    if closed_trades >= thresholds.min_trades_medium_confidence:
        return "medium"
    if closed_trades > 0:
        return "low"
    return "none"


def _confidence_notes(mode: str, artifacts: ModeArtifacts, thresholds: Thresholds) -> list[str]:
    notes: list[str] = []
    if not artifacts.scored_records:
        notes.append(f"{mode}: no scored token artifact found")
    if not artifacts.outcome_metrics.get("available"):
        notes.append(f"{mode}: outcome-level metrics unavailable")
    else:
        confidence = _sample_size_confidence(int(artifacts.outcome_metrics.get("closed_trades", 0)), thresholds)
        notes.append(f"{mode}: outcome sample confidence={confidence}")
    degraded_share = artifacts.score_summary.get("degraded_registry_share")
    if degraded_share is not None and degraded_share > thresholds.degraded_registry_limit:
        notes.append(f"{mode}: degraded registry share is elevated")
    return notes


def _pairwise_outcome_delta(candidate: dict[str, Any], baseline: dict[str, Any]) -> dict[str, Any]:
    if not candidate.get("available") or not baseline.get("available"):
        return {"available": False}
    fields = [
        "expectancy",
        "winrate",
        "median_pnl",
        "mean_pnl",
        "false_positive_rate",
        "friction_adjusted_expectancy",
        "drawdown_proxy",
    ]
    payload: dict[str, Any] = {"available": True}
    for field in fields:
        cand = candidate.get(field)
        base = baseline.get(field)
        if cand is None or base is None:
            payload[f"delta_{field}"] = None
        else:
            payload[f"delta_{field}"] = round(_safe_float(cand) - _safe_float(base), 6)
    payload["closed_trades_candidate"] = _safe_int(candidate.get("closed_trades"))
    payload["closed_trades_baseline"] = _safe_int(baseline.get("closed_trades"))
    return payload


def build_recommendation(
    *,
    modes: dict[str, ModeArtifacts],
    pairwise_scores: dict[str, dict[str, Any]],
    pairwise_outcomes: dict[str, dict[str, Any]],
    thresholds: Thresholds,
) -> dict[str, Any]:
    off = modes.get("off")
    shadow = modes.get("shadow")
    on = modes.get("on")
    if off is None:
        raise ValueError("off mode artifacts are required for recommendation")

    reasons: list[str] = []
    risks: list[str] = []
    shadow_vs_off = pairwise_scores.get("shadow_vs_off", {})
    on_vs_off = pairwise_scores.get("on_vs_off", {})
    shadow_outcome_delta = pairwise_outcomes.get("shadow_vs_off", {})
    on_outcome_delta = pairwise_outcomes.get("on_vs_off", {})

    closed_samples = [
        _safe_int(mode.outcome_metrics.get("closed_trades"))
        for mode in (off, shadow, on)
        if mode is not None and mode.outcome_metrics.get("available")
    ]
    sample_size = min(closed_samples) if closed_samples else 0
    sample_confidence = _sample_size_confidence(sample_size, thresholds)

    degraded_shares = [
        value
        for value in (
            off.score_summary.get("degraded_registry_share"),
            shadow.score_summary.get("degraded_registry_share") if shadow else None,
            on.score_summary.get("degraded_registry_share") if on else None,
        )
        if value is not None
    ]
    degraded_high = bool(degraded_shares) and max(degraded_shares) > thresholds.degraded_registry_limit
    if degraded_high:
        risks.append("degraded registry share is above conservative limit")

    outlier_values = [
        value
        for value in (
            shadow.outcome_metrics.get("outlier_top2_positive_share") if shadow else None,
            on.outcome_metrics.get("outlier_top2_positive_share") if on else None,
        )
        if value is not None
    ]
    outlier_flag = (
        sample_confidence in {"medium", "high"}
        and bool(outlier_values)
        and max(outlier_values) > thresholds.outlier_concentration_limit
    )
    if outlier_flag:
        risks.append("positive outcomes are concentrated in top 1-2 trades")

    concentration_candidates: list[float] = []
    for payload in (shadow_vs_off, on_vs_off):
        compared = _safe_int(payload.get("tokens_compared"))
        concentration = payload.get("score_shift_concentration")
        if compared >= 5 and concentration is not None:
            concentration_candidates.append(_safe_float(concentration))
    concentrated_score_shifts = bool(concentration_candidates) and max(concentration_candidates) > thresholds.score_shift_concentration_limit
    if concentrated_score_shifts:
        risks.append("wallet score shifts are overly concentrated in a tiny subset of tokens")

    has_shadow = shadow is not None and bool(shadow.scored_records)
    has_on = on is not None and bool(on.scored_records)
    shadow_outcomes = bool(shadow and shadow.outcome_metrics.get("available"))
    on_outcomes = bool(on and on.outcome_metrics.get("available"))
    off_outcomes = bool(off.outcome_metrics.get("available"))

    if not off.scored_records or not (has_shadow or has_on):
        raise ValueError("No usable off/shadow/on comparison inputs were found")

    if not has_on:
        reasons.append("on mode scored artifact is unavailable")
    if has_shadow and not shadow_outcomes:
        reasons.append("shadow comparison is scoring-level only")
    if has_on and not on_outcomes:
        reasons.append("on comparison is scoring-level only")

    shadow_positive = False
    if shadow_outcomes and shadow_outcome_delta.get("available"):
        shadow_positive = (
            _safe_float(shadow_outcome_delta.get("delta_expectancy")) >= 0.0
            and _safe_float(shadow_outcome_delta.get("delta_false_positive_rate")) <= thresholds.false_positive_tolerance
        )

    on_positive = False
    on_negative = False
    if on_outcomes and off_outcomes and on_outcome_delta.get("available"):
        delta_expectancy = _safe_float(on_outcome_delta.get("delta_expectancy"))
        delta_false_positive = _safe_float(on_outcome_delta.get("delta_false_positive_rate"))
        delta_median = _safe_float(on_outcome_delta.get("delta_median_pnl"))
        on_positive = (
            sample_confidence in {"medium", "high"}
            and _safe_int(on.outcome_metrics.get("closed_trades")) >= thresholds.min_trades_high_confidence
            and delta_expectancy > thresholds.promote_expectancy_margin
            and delta_false_positive <= thresholds.false_positive_tolerance
            and delta_median >= 0.0
            and shadow_positive
            and not outlier_flag
            and not degraded_high
            and not concentrated_score_shifts
        )
        on_negative = (
            (sample_confidence in {"medium", "high"} and delta_expectancy < -thresholds.rollback_expectancy_margin)
            or (sample_confidence in {"medium", "high"} and delta_false_positive > thresholds.false_positive_rollback)
            or (sample_confidence in {"medium", "high"} and delta_median < -0.01)
            or (sample_confidence in {"medium", "high"} and degraded_high)
            or (sample_confidence in {"medium", "high"} and concentrated_score_shifts)
        )

    recommendation = "keep_shadow"
    if on_outcomes and off_outcomes and on_negative:
        recommendation = "rollback_to_off"
        reasons.append("on materially worsens at least one conservative rollout metric")
    elif on_outcomes and off_outcomes and on_positive:
        recommendation = "promote_to_on"
        reasons.append("on improves expectancy without materially worsening false positives or median pnl")
    elif not on_outcomes or not off_outcomes:
        recommendation = "keep_shadow" if has_shadow else "keep_off"
        reasons.append("outcome-level proof is incomplete; remain conservative")
    elif sample_confidence == "low":
        recommendation = "keep_shadow" if has_shadow else "keep_off"
        reasons.append("sample size is below medium confidence threshold")
    elif shadow_positive:
        recommendation = "keep_shadow"
        reasons.append("wallet effect looks promising but evidence is not strong enough for promotion")
    else:
        recommendation = "keep_off"
        reasons.append("no stable positive wallet effect is observed")

    if not has_shadow and recommendation == "keep_shadow":
        recommendation = "keep_off"
        reasons.append("shadow artifact is unavailable, so safe default falls back to off for this comparison set")

    if recommendation == "promote_to_on":
        recommendation_confidence = "high" if sample_confidence == "high" else "medium"
    elif recommendation in {"rollback_to_off", "keep_off"}:
        recommendation_confidence = "medium" if risks or sample_confidence in {"medium", "high"} else "low"
    else:
        recommendation_confidence = "low" if sample_confidence in {"none", "low"} else "medium"

    next_mode = {
        "keep_off": "off",
        "rollback_to_off": "off",
        "keep_shadow": "shadow",
        "promote_to_on": "on",
    }[recommendation]

    return {
        "recommendation": recommendation,
        "recommendation_confidence": recommendation_confidence,
        "primary_reasons": list(dict.fromkeys(reasons)) or ["insufficient evidence"],
        "blocking_risks": list(dict.fromkeys(risks)),
        "next_mode": next_mode,
        "safe_default_mode": SAFE_DEFAULT_MODE,
        "sample_size_confidence": sample_confidence,
        "outlier_concentration_flag": outlier_flag,
        "generated_at": "1970-01-01T00:00:00Z",
    }


def _markdown_table_row(values: list[Any]) -> str:
    return "| " + " | ".join("-" if value is None else str(value) for value in values) + " |"


def build_markdown_summary(
    *,
    report: dict[str, Any],
    recommendation_payload: dict[str, Any],
) -> str:
    lines = [
        "# Wallet Weighting Calibration Summary",
        "",
        f"Compared modes: {', '.join(report['input_summary']['modes_available'])}",
        "",
        "## Key metrics",
        "",
        _markdown_table_row(["Mode", "Tokens", "Avg score Δ vs off", "Top-N overlap", "Expectancy", "Winrate", "Median pnl", "False positive rate"]),
        _markdown_table_row(["---", "---", "---", "---", "---", "---", "---", "---"]),
    ]
    for mode in _MODE_ORDER:
        if mode not in report["mode_comparison"]:
            continue
        block = report["mode_comparison"][mode]
        token_level = block.get("token_level", {})
        outcome = block.get("outcome_level", {})
        lines.append(
            _markdown_table_row(
                [
                    mode,
                    token_level.get("tokens_available", token_level.get("tokens_compared")),
                    token_level.get("average_score_delta_vs_off"),
                    token_level.get("overlap_top_n"),
                    outcome.get("expectancy"),
                    outcome.get("winrate"),
                    outcome.get("median_pnl"),
                    outcome.get("false_positive_rate"),
                ]
            )
        )
    lines.extend(
        [
            "",
            "## Major trade-offs",
            "",
        ]
    )
    pairwise = report["mode_comparison"].get("pairwise", {})
    for name, payload in pairwise.items():
        if not payload.get("available"):
            continue
        lines.append(
            f"- {name}: Δexpectancy={payload.get('delta_expectancy')}, Δfalse_positive_rate={payload.get('delta_false_positive_rate')}, Δmedian_pnl={payload.get('delta_median_pnl')}"
        )
    if not any(payload.get("available") for payload in pairwise.values()):
        lines.append("- Outcome-level comparison is unavailable; recommendation stays conservative.")
    lines.extend(
        [
            "",
            "## Recommendation",
            "",
            f"- Recommendation: **{recommendation_payload['recommendation']}**",
            f"- Confidence: **{recommendation_payload['recommendation_confidence']}**",
            f"- Safe default mode: **{recommendation_payload['safe_default_mode']}**",
            "",
            "## Cautions / blocking risks",
            "",
        ]
    )
    if recommendation_payload.get("blocking_risks"):
        lines.extend(f"- {risk}" for risk in recommendation_payload["blocking_risks"])
    else:
        lines.append("- No additional blocking risks were detected beyond standard conservative rollout policy.")
    lines.extend(
        [
            "",
            "## Next actions",
            "",
            f"- Keep `safe_default_mode={recommendation_payload['safe_default_mode']}` until the recommendation is explicitly reviewed.",
            f"- Set `next_mode={recommendation_payload['next_mode']}` only after checking the machine-readable report and risks.",
        ]
    )
    return "\n".join(lines).strip() + "\n"


def _emit_metric_events(
    *,
    events_path: Path,
    timestamp: str,
    mode: str,
    payload: dict[str, Any],
    event_type: str,
) -> None:
    for metric_name, metric_value in payload.items():
        if metric_name == "available":
            continue
        append_jsonl(
            events_path,
            {
                "timestamp": timestamp,
                "event_type": event_type,
                "mode": mode,
                "metric_name": metric_name,
                "metric_value": metric_value,
            },
        )


def run_wallet_weighting_calibration(
    *,
    processed_dir: Path,
    out_report: Path,
    out_md: Path,
    out_recommendation: Path,
    out_events: Path | None = None,
    off_scored: Path | None = None,
    shadow_scored: Path | None = None,
    on_scored: Path | None = None,
    off_base_dir: Path | None = None,
    shadow_base_dir: Path | None = None,
    on_base_dir: Path | None = None,
    max_top_n: int = 25,
    min_trades_medium_confidence: int = 20,
    min_trades_high_confidence: int = 50,
) -> dict[str, Any]:
    thresholds = Thresholds(
        max_top_n=max_top_n,
        min_trades_medium_confidence=min_trades_medium_confidence,
        min_trades_high_confidence=min_trades_high_confidence,
    )
    processed_dir = processed_dir.expanduser().resolve()
    out_report = out_report.expanduser().resolve()
    out_md = out_md.expanduser().resolve()
    out_recommendation = out_recommendation.expanduser().resolve()
    events_path = (out_events or (processed_dir / "wallet_calibration_events.jsonl")).expanduser().resolve()

    modes = {
        "off": load_mode_artifacts(mode="off", processed_dir=processed_dir, scored_path=off_scored, base_dir=off_base_dir, thresholds=thresholds),
        "shadow": load_mode_artifacts(mode="shadow", processed_dir=processed_dir, scored_path=shadow_scored, base_dir=shadow_base_dir, thresholds=thresholds),
        "on": load_mode_artifacts(mode="on", processed_dir=processed_dir, scored_path=on_scored, base_dir=on_base_dir, thresholds=thresholds),
    }
    if not modes["off"].scored_records or not (modes["shadow"].scored_records or modes["on"].scored_records):
        raise ValueError("No usable off/shadow/on comparison inputs were found")

    pairwise_scores = {
        "shadow_vs_off": compare_token_scores(modes["off"].scored_records, modes["shadow"].scored_records, max_top_n=thresholds.max_top_n) if modes["shadow"].scored_records else {"available": False},
        "on_vs_off": compare_token_scores(modes["off"].scored_records, modes["on"].scored_records, max_top_n=thresholds.max_top_n) if modes["on"].scored_records else {"available": False},
    }
    pairwise_outcomes = {
        "shadow_vs_off": _pairwise_outcome_delta(modes["shadow"].outcome_metrics, modes["off"].outcome_metrics),
        "on_vs_off": _pairwise_outcome_delta(modes["on"].outcome_metrics, modes["off"].outcome_metrics),
    }

    recommendation_payload = build_recommendation(
        modes=modes,
        pairwise_scores=pairwise_scores,
        pairwise_outcomes=pairwise_outcomes,
        thresholds=thresholds,
    )

    timestamp = _deterministic_iso(
        [
            {"records": modes[mode].scored_records, "closed_positions": modes[mode].closed_positions}
            for mode in _MODE_ORDER
        ]
    )
    recommendation_payload["generated_at"] = timestamp

    available_modes = [mode for mode in _MODE_ORDER if modes[mode].scored_records]
    sample_size_confidence = recommendation_payload["sample_size_confidence"]
    robustness_checks = {
        "sample_size_confidence": sample_size_confidence,
        "outlier_concentration_flag": recommendation_payload["outlier_concentration_flag"],
        "degraded_registry_share": {
            mode: modes[mode].score_summary.get("degraded_registry_share")
            for mode in _MODE_ORDER
            if modes[mode].scored_records
        },
        "score_shift_concentration": {
            name: payload.get("score_shift_concentration")
            for name, payload in pairwise_scores.items()
            if payload
        },
        "recommendation_confidence": recommendation_payload["recommendation_confidence"],
    }

    report: dict[str, Any] = {
        "contract_version": CONTRACT_VERSION,
        "generated_at": timestamp,
        "input_summary": {
            "processed_dir": str(processed_dir),
            "modes_available": available_modes,
            "score_inputs_found": {mode: bool(modes[mode].scored_records) for mode in _MODE_ORDER},
            "outcome_inputs_found": {mode: bool(modes[mode].outcome_metrics.get("available")) for mode in _MODE_ORDER},
            "sources": {mode: modes[mode].sources for mode in _MODE_ORDER},
            "max_top_n": thresholds.max_top_n,
        },
        "mode_comparison": {
            mode: {
                "token_level": (
                    modes[mode].score_summary
                    if mode == "off"
                    else compare_token_scores(modes["off"].scored_records, modes[mode].scored_records, max_top_n=thresholds.max_top_n)
                ),
                "outcome_level": modes[mode].outcome_metrics,
                "confidence_notes": _confidence_notes(mode, modes[mode], thresholds),
            }
            for mode in _MODE_ORDER
            if modes[mode].scored_records
        },
        "robustness_checks": robustness_checks,
        "recommendation": recommendation_payload,
        "notes": [],
    }
    report["mode_comparison"]["pairwise"] = pairwise_outcomes

    if not any(modes[mode].outcome_metrics.get("available") for mode in _MODE_ORDER if modes[mode].scored_records):
        report["notes"].append("Only scoring-level inputs were available; recommendation remains conservative.")
    if not modes["on"].scored_records:
        report["notes"].append("on mode inputs were not found; promote_to_on is blocked by design.")
    if modes["on"].scored_records and not modes["on"].outcome_metrics.get("available"):
        report["notes"].append("on mode lacked outcome-level artifacts; promotion is blocked until post-run evidence exists.")

    write_json(out_report, report)
    markdown = build_markdown_summary(report=report, recommendation_payload=recommendation_payload)
    ensure_dir(out_md.parent)
    out_md.write_text(markdown, encoding="utf-8")
    write_json(out_recommendation, recommendation_payload)

    _emit_metric_events(events_path=events_path, timestamp=timestamp, mode="off", payload=modes["off"].score_summary, event_type="token_level_metric")
    for mode in ("shadow", "on"):
        if mode in report["mode_comparison"]:
            _emit_metric_events(
                events_path=events_path,
                timestamp=timestamp,
                mode=mode,
                payload=report["mode_comparison"][mode]["token_level"],
                event_type="token_level_metric",
            )
            _emit_metric_events(
                events_path=events_path,
                timestamp=timestamp,
                mode=mode,
                payload=report["mode_comparison"][mode]["outcome_level"],
                event_type="outcome_level_metric",
            )
    append_jsonl(
        events_path,
        {
            "timestamp": timestamp,
            "event_type": "rollout_recommendation",
            "mode": recommendation_payload["next_mode"],
            "metric_name": "recommendation",
            "metric_value": recommendation_payload["recommendation"],
            "recommendation": recommendation_payload["recommendation"],
            "confidence": recommendation_payload["recommendation_confidence"],
        },
    )
    return report
