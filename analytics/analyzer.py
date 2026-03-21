"""Post-run analyzer orchestration for paper-trading artifacts."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from analytics.analyzer_correlations import compute_metric_correlations
from analytics.analyzer_matrix import compute_matrix_analysis, merge_closed_positions_with_matrix, read_trade_feature_matrix
from analytics.analyzer_metrics import (
    compute_exit_reason_metrics,
    compute_friction_metrics,
    compute_portfolio_metrics,
    compute_regime_metrics,
)
from analytics.analyzer_recommendations import generate_recommendations
from analytics.analyzer_report_writer import write_markdown_report
from src.replay.calibration_metrics import derive_outcome_metrics
from analytics.analyzer_slices import bucketize_metric, compute_analyzer_slices, slice_positions
from analytics.config_suggestions import write_config_suggestions
from config.settings import Settings
from utils.io import append_jsonl, read_json, write_json

_REQUIRED_METRICS = [
    "bundle_cluster_score",
    "first30s_buy_ratio",
    "priority_fee_avg_first_min",
    "first50_holder_conc_est",
    "holder_entropy_est",
    "dev_sell_pressure_5m",
    "pumpfun_to_raydium_sec",
    "x_validation_score",
]


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        raw = line.strip()
        if not raw:
            continue
        import json

        rows.append(json.loads(raw))
    return rows


def _parse_ts(value: Any) -> datetime | None:
    if not value:
        return None
    text = str(value).replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _derive_lifecycle_from_trades(trades: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    flat_rows: list[dict[str, Any]] = []
    for trade in trades:
        pid = str(trade.get("position_id", ""))
        if pid:
            grouped[pid].append(trade)
        if trade.get("entry_time") and trade.get("exit_time") and trade.get("net_pnl_pct") is not None:
            flat_rows.append(trade)

    positions: list[dict[str, Any]] = []
    for pid, rows in grouped.items():
        entry = None
        exits: list[dict[str, Any]] = []
        had_failed_fill = False
        for row in rows:
            side = str(row.get("side", row.get("trade_type", ""))).lower()
            status = str(row.get("status", "")).lower()
            if status == "failed":
                had_failed_fill = True
            if side in {"buy", "entry"}:
                entry = row
            if side in {"sell", "exit"}:
                exits.append(row)

        if not entry or not exits:
            continue

        exits.sort(key=lambda x: _parse_ts(x.get("timestamp") or x.get("time") or x.get("exit_time")) or datetime.min.replace(tzinfo=timezone.utc))
        first_exit = exits[0]
        final_exit = exits[-1]
        entry_time = _parse_ts(entry.get("timestamp") or entry.get("time") or entry.get("entry_time"))
        exit_time = _parse_ts(final_exit.get("timestamp") or final_exit.get("time") or final_exit.get("exit_time"))
        hold_sec = int((exit_time - entry_time).total_seconds()) if entry_time and exit_time else 0

        net_pnl_sol = sum(float(e.get("net_pnl_sol", e.get("pnl_sol", 0.0))) for e in exits)
        gross_pnl_sol = sum(float(e.get("gross_pnl_sol", e.get("pnl_gross_sol", net_pnl_sol))) for e in exits)
        fees_paid = sum(float(e.get("fees_paid_sol", e.get("fee_sol", 0.0))) for e in exits)
        slippage = sum(float(e.get("slippage_cost_sol_est", 0.0)) for e in exits)

        entry_value = float(entry.get("size_sol", entry.get("notional_sol", 0.0)))
        net_pnl_pct = (net_pnl_sol / entry_value * 100) if entry_value > 0 else float(final_exit.get("net_pnl_pct", 0.0))

        snapshot = entry.get("entry_snapshot", {}) if isinstance(entry.get("entry_snapshot"), dict) else {}
        calibration_metrics = derive_outcome_metrics(entry, snapshot)

        positions.append(
            {
                "position_id": pid,
                "token_address": entry.get("token_address", ""),
                "regime": entry.get("regime", "unknown"),
                "opened_at": entry_time.isoformat().replace("+00:00", "Z") if entry_time else "",
                "closed_at": exit_time.isoformat().replace("+00:00", "Z") if exit_time else "",
                "hold_sec": hold_sec,
                "gross_pnl_sol": gross_pnl_sol,
                "net_pnl_sol": net_pnl_sol,
                "net_pnl_pct": net_pnl_pct,
                "fees_paid_sol": fees_paid,
                "slippage_cost_sol_est": slippage,
                "exit_reason_final": final_exit.get("exit_reason", "unknown"),
                "exit_reason": final_exit.get("exit_reason", "unknown"),
                "partial_exit_count": max(0, len(exits) - 1),
                "had_failed_fill": had_failed_fill,
                "entry_reason": entry.get("entry_reason", "unknown"),
                "x_status": entry.get("x_status", snapshot.get("x_status", "unknown")),
                "rug_score": entry.get("rug_score", snapshot.get("rug_score")),
                "liquidity_usd": entry.get("liquidity_usd", snapshot.get("liquidity_usd")),
                "final_score": entry.get("final_score", snapshot.get("final_score")),
                "entry_confidence": entry.get("entry_confidence", snapshot.get("entry_confidence")),
                "entry_snapshot": snapshot,
                **{metric: entry.get(metric, snapshot.get(metric)) for metric in _REQUIRED_METRICS},
                **{metric: entry.get(metric, snapshot.get(metric, calibration_metrics.get(metric))) for metric in calibration_metrics},
                "first_exit_reason": first_exit.get("exit_reason", "unknown"),
            }
        )

    if positions:
        return sorted(positions, key=lambda x: x["position_id"])

    flat_positions: list[dict[str, Any]] = []
    for row in flat_rows:
        snapshot = row.get("entry_snapshot", {}) if isinstance(row.get("entry_snapshot"), dict) else {}
        calibration_metrics = derive_outcome_metrics(row, snapshot)
        flat_positions.append(
            {
                "position_id": row.get("position_id", row.get("trade_id", "unknown")),
                "token_address": row.get("token_address", ""),
                "regime": row.get("regime_decision", row.get("regime", "unknown")),
                "opened_at": row.get("entry_time", ""),
                "closed_at": row.get("exit_time", ""),
                "hold_sec": int(row.get("hold_sec", 0) or 0),
                "gross_pnl_sol": float(row.get("gross_pnl_sol", 0.0) or 0.0),
                "net_pnl_sol": float(row.get("net_pnl_sol", 0.0) or 0.0),
                "net_pnl_pct": float(row.get("net_pnl_pct", 0.0) or 0.0),
                "fees_paid_sol": float(row.get("fees_paid_sol", 0.0) or 0.0),
                "slippage_cost_sol_est": float(row.get("slippage_cost_sol_est", 0.0) or 0.0),
                "exit_reason_final": row.get("exit_reason_final", row.get("exit_reason", "unknown")),
                "exit_reason": row.get("exit_reason_final", row.get("exit_reason", "unknown")),
                "partial_exit_count": int(row.get("partial_exit_count", 0) or 0),
                "had_failed_fill": bool(row.get("had_failed_fill", False)),
                "entry_reason": row.get("entry_reason", "unknown"),
                "x_status": row.get("x_status", snapshot.get("x_status", "unknown")),
                "rug_score": row.get("rug_score", snapshot.get("rug_score")),
                "liquidity_usd": row.get("liquidity_usd", snapshot.get("liquidity_usd")),
                "final_score": row.get("final_score", snapshot.get("final_score")),
                "entry_confidence": row.get("entry_confidence", snapshot.get("entry_confidence")),
                "entry_snapshot": snapshot,
                **{metric: row.get(metric, snapshot.get(metric)) for metric in _REQUIRED_METRICS},
                **{metric: row.get(metric, snapshot.get(metric, calibration_metrics.get(metric))) for metric in calibration_metrics},
            }
        )
    return sorted(flat_positions, key=lambda x: x["position_id"])


def _reconstruct_closed_positions(trades: list[dict[str, Any]], positions_state: list[dict[str, Any]]) -> list[dict[str, Any]]:
    reconstructed = _derive_lifecycle_from_trades(trades)
    if reconstructed:
        return reconstructed

    fallback: list[dict[str, Any]] = []
    for row in positions_state:
        if str(row.get("status", "")).lower() != "closed":
            continue
        snapshot = row.get("entry_snapshot", {}) if isinstance(row.get("entry_snapshot"), dict) else {}
        calibration_metrics = derive_outcome_metrics(row, snapshot)
        fallback.append(
            {
                "position_id": row.get("position_id", "unknown"),
                "token_address": row.get("token_address", ""),
                "regime": row.get("regime", "unknown"),
                "opened_at": row.get("opened_at", row.get("entry_time", "")),
                "closed_at": row.get("closed_at", row.get("exit_time", "")),
                "hold_sec": int(row.get("hold_sec", 0)),
                "gross_pnl_sol": float(row.get("gross_pnl_sol", 0.0)),
                "net_pnl_sol": float(row.get("net_pnl_sol", 0.0)),
                "net_pnl_pct": float(row.get("net_pnl_pct", 0.0)),
                "fees_paid_sol": float(row.get("fees_paid_sol", 0.0)),
                "slippage_cost_sol_est": float(row.get("slippage_cost_sol_est", 0.0)),
                "exit_reason_final": row.get("exit_reason_final", row.get("exit_reason", "unknown")),
                "exit_reason": row.get("exit_reason_final", row.get("exit_reason", "unknown")),
                "partial_exit_count": int(row.get("partial_exit_count", 0)),
                "had_failed_fill": bool(row.get("had_failed_fill", False)),
                "entry_reason": row.get("entry_reason", "unknown"),
                "x_status": row.get("x_status", "unknown"),
                "rug_score": row.get("rug_score"),
                "liquidity_usd": row.get("liquidity_usd"),
                "final_score": row.get("final_score"),
                "entry_confidence": row.get("entry_confidence"),
                "entry_snapshot": snapshot,
                **{metric: row.get(metric, snapshot.get(metric)) for metric in _REQUIRED_METRICS},
                **{metric: row.get(metric, snapshot.get(metric, calibration_metrics.get(metric))) for metric in calibration_metrics},
            }
        )
    return fallback


def run_post_run_analysis(settings: Settings) -> dict[str, Any]:
    if not settings.POST_RUN_ANALYZER_ENABLED:
        return {"status": "disabled"}

    trades_path = settings.TRADES_DIR / "trades.jsonl"
    signals_path = settings.SIGNALS_DIR / "signals.jsonl"
    positions_path = settings.POSITIONS_DIR / "positions.json"
    portfolio_path = settings.PROCESSED_DATA_DIR / "portfolio_state.json"

    for required_path in [trades_path, signals_path, positions_path, portfolio_path]:
        if not required_path.exists() and settings.POST_RUN_ANALYZER_FAILCLOSED:
            raise FileNotFoundError(f"Missing required input: {required_path}")

    events_path = settings.PROCESSED_DATA_DIR / "analyzer_events.jsonl"
    append_jsonl(events_path, {"ts": datetime.now(timezone.utc).isoformat(), "event": "analysis_started"})

    trades = _read_jsonl(trades_path)
    signals = _read_jsonl(signals_path)
    positions_state = read_json(positions_path, default=[])
    portfolio_state = read_json(portfolio_path, default={})
    matrix_path, trade_feature_matrix = read_trade_feature_matrix(settings)

    closed_positions = _reconstruct_closed_positions(trades, positions_state)
    matrix_analysis_rows = merge_closed_positions_with_matrix(closed_positions, trade_feature_matrix)
    append_jsonl(events_path, {"ts": datetime.now(timezone.utc).isoformat(), "event": "closed_positions_reconstructed", "count": len(closed_positions)})
    append_jsonl(
        events_path,
        {
            "ts": datetime.now(timezone.utc).isoformat(),
            "event": "trade_feature_matrix_loaded",
            "count": len(trade_feature_matrix),
            "path": str(matrix_path) if matrix_path else "",
            "usable_row_count": len(matrix_analysis_rows),
        },
    )

    portfolio_metrics = compute_portfolio_metrics(
        {
            **portfolio_state,
            "total_signals": portfolio_state.get("total_signals", len(signals)),
            "total_entries_attempted": portfolio_state.get("total_entries_attempted", len([t for t in trades if str(t.get("side", "")).lower() in {"buy", "entry"}])),
            "total_fills_successful": portfolio_state.get("total_fills_successful", len([t for t in trades if str(t.get("status", "filled")).lower() == "filled" and str(t.get("side", "")).lower() in {"buy", "entry"}])),
            "total_positions_open": portfolio_state.get("total_positions_open", len([p for p in positions_state if str(p.get("status", "")).lower() == "open"])),
        },
        closed_positions,
    )
    regime_metrics = compute_regime_metrics(closed_positions)
    exit_metrics = compute_exit_reason_metrics(closed_positions)
    friction_metrics = compute_friction_metrics(trades)
    append_jsonl(events_path, {"ts": datetime.now(timezone.utc).isoformat(), "event": "portfolio_metrics_computed"})

    correlations = compute_metric_correlations(closed_positions, _REQUIRED_METRICS, "net_pnl_pct", settings)
    append_jsonl(events_path, {"ts": datetime.now(timezone.utc).isoformat(), "event": "correlations_computed", "metric_count": len(_REQUIRED_METRICS), "target": "net_pnl_pct"})

    slices = {
        "regime": slice_positions(closed_positions, "regime"),
        "entry_reason": slice_positions(closed_positions, "entry_reason"),
        "exit_reason": slice_positions(closed_positions, "exit_reason"),
        "x_status": slice_positions(closed_positions, "x_status"),
        "rug_score_bucket": bucketize_metric(closed_positions, "rug_score", [(0.00, 0.15), (0.15, 0.30), (0.30, None)]),
        "liquidity_bucket": bucketize_metric(closed_positions, "liquidity_usd", [(0, 10000), (10000, 50000), (50000, None)]),
        "final_score_bucket": bucketize_metric(closed_positions, "final_score", [(80, 85), (85, 90), (90, None)]),
        "entry_confidence_bucket": bucketize_metric(closed_positions, "entry_confidence", [(0.50, 0.65), (0.65, 0.80), (0.80, None)]),
    }

    matrix_analysis = compute_matrix_analysis(matrix_analysis_rows, settings)

    slice_source_rows = matrix_analysis_rows or closed_positions
    analyzer_slices = compute_analyzer_slices(
        slice_source_rows,
        min_sample=int(settings.POST_RUN_MIN_TRADES_FOR_REGIME_COMPARISON),
        run_id=settings.PROCESSED_DATA_DIR.parent.name,
        source="trade_feature_matrix" if matrix_analysis_rows else "closed_positions",
        as_of=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    )
    slice_group_counts = {group: len(payload) for group, payload in analyzer_slices.get("slice_groups", {}).items()}
    required_evidence_quality_slices = [
        "partial_evidence_trades",
        "low_confidence_evidence_trades",
        "evidence_conflict_trades",
        "degraded_x_salvage_cases",
        "linkage_risk_underperformance",
    ]
    available_evidence_quality_slices = sorted((analyzer_slices.get("slice_groups", {}).get("evidence_quality") or {}).keys())
    missing_evidence_quality_slices = [
        name for name in required_evidence_quality_slices if name not in available_evidence_quality_slices
    ]
    append_jsonl(
        events_path,
        {
            "ts": datetime.now(timezone.utc).isoformat(),
            "event": "analyzer_slices_started",
            "run_id": settings.PROCESSED_DATA_DIR.parent.name,
            "source": analyzer_slices.get("metadata", {}).get("source"),
            "row_count": analyzer_slices.get("metadata", {}).get("row_count", 0),
        },
    )
    for group_name, event_name in [
        ("regime", "analyzer_regime_slices_computed"),
        ("cluster_bundle", "analyzer_cluster_bundle_slices_computed"),
        ("continuation", "analyzer_continuation_slices_computed"),
        ("degraded_x", "analyzer_degraded_x_slices_computed"),
        ("evidence_quality", "analyzer_evidence_quality_slices_computed"),
        ("exit_failure", "analyzer_exit_failure_slices_computed"),
    ]:
        group_payload = analyzer_slices.get("slice_groups", {}).get(group_name, {})
        low_sample_count = sum(1 for value in group_payload.values() if isinstance(value, dict) and value.get("status") == "insufficient_sample")
        append_jsonl(
            events_path,
            {
                "ts": datetime.now(timezone.utc).isoformat(),
                "event": event_name,
                "run_id": settings.PROCESSED_DATA_DIR.parent.name,
                "slice_group": group_name,
                "slice_count": len(group_payload),
                "low_sample_count": low_sample_count,
                "warnings": analyzer_slices.get("warnings", []),
            },
        )
        if low_sample_count:
            append_jsonl(
                events_path,
                {
                    "ts": datetime.now(timezone.utc).isoformat(),
                    "event": "analyzer_slice_low_sample",
                    "run_id": settings.PROCESSED_DATA_DIR.parent.name,
                    "slice_group": group_name,
                    "count": low_sample_count,
                },
            )

    warnings = ["correlation_not_causation"]
    if len(closed_positions) < settings.POST_RUN_MIN_TRADES_FOR_REGIME_COMPARISON:
        warnings.append("small_sample_warning")
    if friction_metrics.get("partial_fill_rate", 0.0) > 0.3:
        warnings.append("too_many_partial_fills")
    degraded_share = 0.0
    if closed_positions:
        degraded_share = len([p for p in closed_positions if str(p.get("x_status", "")) == "degraded"]) / len(closed_positions)
    if degraded_share > 0.5:
        warnings.append("degraded_x_dominates_sample")
    if portfolio_metrics.get("total_positions_open", 0) > 0:
        warnings.append("open_positions_bias")
    if settings.POST_RUN_OUTLIER_CLIP_PCT > 0:
        warnings.append("high_outlier_sensitivity")
    if not trade_feature_matrix:
        warnings.append("matrix_input_missing")
    elif not matrix_analysis_rows:
        warnings.append("matrix_input_unusable")
    warnings.extend(matrix_analysis.get("warnings", []))

    summary = {
        "as_of": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        **portfolio_metrics,
        **regime_metrics,
        **exit_metrics,
        "friction_summary": friction_metrics,
        "metric_correlations": correlations,
        "matrix_analysis_available": matrix_analysis.get("matrix_analysis_available", False),
        "matrix_row_count": matrix_analysis.get("matrix_row_count", 0),
        "bundle_cluster_correlations": matrix_analysis.get("bundle_cluster_correlations", []),
        "regime_confusion_summary": matrix_analysis.get("regime_confusion_summary", {}),
        "trend_failure_summary": matrix_analysis.get("trend_failure_summary", {}),
        "scalp_missed_trend_summary": matrix_analysis.get("scalp_missed_trend_summary", {}),
        "scalp_vs_trend_outcome_summary": matrix_analysis.get("scalp_vs_trend_outcome_summary", {}),
        "time_to_first_profit_summary": matrix_analysis.get("time_to_first_profit_summary", {}),
        "mfe_mae_summary": matrix_analysis.get("mfe_mae_summary", {}),
        "trend_survival_summary": matrix_analysis.get("trend_survival_summary", {}),
        "pattern_expectancy_slices": matrix_analysis.get("pattern_expectancy_slices", {}),
        "top_positive_feature_slices": matrix_analysis.get("top_positive_feature_slices", []),
        "top_negative_feature_slices": matrix_analysis.get("top_negative_feature_slices", []),
        "trade_feature_matrix_path": str(matrix_path) if matrix_path else "",
        "analyzer_slices_available": bool(analyzer_slices.get("slice_groups")),
        "analyzer_slice_source": analyzer_slices.get("metadata", {}).get("source", "closed_positions"),
        "analyzer_slices_overview": analyzer_slices.get("coverage", {}),
        "analyzer_slices_recommendation_inputs": analyzer_slices.get("recommendation_inputs", {}),
        "required_evidence_quality_slices": required_evidence_quality_slices,
        "available_evidence_quality_slices": available_evidence_quality_slices,
        "missing_evidence_quality_slices": missing_evidence_quality_slices,
        "warnings": warnings,
        "contract_version": settings.POST_RUN_CONTRACT_VERSION,
    }

    recs = generate_recommendations(summary, correlations, slices, settings, analyzer_slices=analyzer_slices)
    recommendations_payload = {"recommendations": recs, "contract_version": settings.POST_RUN_CONTRACT_VERSION, "analyzer_slices": analyzer_slices}
    append_jsonl(events_path, {"ts": datetime.now(timezone.utc).isoformat(), "event": "recommendations_generated", "count": len(recs)})

    summary_path = settings.PROCESSED_DATA_DIR / "post_run_summary.json"
    recommendations_path = settings.PROCESSED_DATA_DIR / "post_run_recommendations.json"
    report_path = settings.PROCESSED_DATA_DIR / "post_run_report.md"
    config_suggestions_path = settings.PROCESSED_DATA_DIR / "config_suggestions.json"
    analyzer_slices_path = settings.PROCESSED_DATA_DIR / "analyzer_slices.json"

    write_json(summary_path, summary)
    write_json(recommendations_path, recommendations_payload)
    write_json(analyzer_slices_path, analyzer_slices)
    write_config_suggestions(
        settings=settings,
        summary=summary,
        recommendations_payload=recommendations_payload,
        matrix_rows=matrix_analysis_rows,
        output_path=config_suggestions_path,
    )
    write_markdown_report(summary, recommendations_payload, str(report_path))

    append_jsonl(
        events_path,
        {
            "ts": datetime.now(timezone.utc).isoformat(),
            "event": "analyzer_slices_completed",
            "run_id": settings.PROCESSED_DATA_DIR.parent.name,
            "slice_group_counts": slice_group_counts,
            "summary_path": str(summary_path),
            "analyzer_slices_path": str(analyzer_slices_path),
        },
    )
    append_jsonl(events_path, {"ts": datetime.now(timezone.utc).isoformat(), "event": "analysis_completed", "summary_path": str(summary_path)})

    return {
        "summary_path": str(summary_path),
        "recommendations_path": str(recommendations_path),
        "config_suggestions_path": str(config_suggestions_path),
        "report_path": str(report_path),
        "analyzer_slices_path": str(analyzer_slices_path),
        "closed_positions": len(closed_positions),
    }
