"""Post-run analyzer orchestration for paper-trading artifacts."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from analytics.analyzer_correlations import compute_metric_correlations
from analytics.analyzer_metrics import (
    compute_exit_reason_metrics,
    compute_friction_metrics,
    compute_portfolio_metrics,
    compute_regime_metrics,
)
from analytics.analyzer_recommendations import generate_recommendations
from analytics.analyzer_report_writer import write_markdown_report
from analytics.analyzer_slices import bucketize_metric, slice_positions
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
    for trade in trades:
        pid = str(trade.get("position_id", ""))
        if pid:
            grouped[pid].append(trade)

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
                "first_exit_reason": first_exit.get("exit_reason", "unknown"),
            }
        )

    return sorted(positions, key=lambda x: x["position_id"])


def _reconstruct_closed_positions(trades: list[dict[str, Any]], positions_state: list[dict[str, Any]]) -> list[dict[str, Any]]:
    reconstructed = _derive_lifecycle_from_trades(trades)
    if reconstructed:
        return reconstructed

    fallback: list[dict[str, Any]] = []
    for row in positions_state:
        if str(row.get("status", "")).lower() != "closed":
            continue
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
                "entry_snapshot": row.get("entry_snapshot", {}),
                **{metric: row.get(metric, row.get("entry_snapshot", {}).get(metric)) for metric in _REQUIRED_METRICS},
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

    closed_positions = _reconstruct_closed_positions(trades, positions_state)
    append_jsonl(events_path, {"ts": datetime.now(timezone.utc).isoformat(), "event": "closed_positions_reconstructed", "count": len(closed_positions)})

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

    summary = {
        "as_of": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        **portfolio_metrics,
        **regime_metrics,
        **exit_metrics,
        "friction_summary": friction_metrics,
        "metric_correlations": correlations,
        "warnings": warnings,
        "contract_version": settings.POST_RUN_CONTRACT_VERSION,
    }

    recs = generate_recommendations(summary, correlations, slices, settings)
    recommendations_payload = {"recommendations": recs, "contract_version": settings.POST_RUN_CONTRACT_VERSION}
    append_jsonl(events_path, {"ts": datetime.now(timezone.utc).isoformat(), "event": "recommendations_generated", "count": len(recs)})

    summary_path = settings.PROCESSED_DATA_DIR / "post_run_summary.json"
    recommendations_path = settings.PROCESSED_DATA_DIR / "post_run_recommendations.json"
    report_path = settings.PROCESSED_DATA_DIR / "post_run_report.md"

    write_json(summary_path, summary)
    write_json(recommendations_path, recommendations_payload)
    write_markdown_report(summary, recommendations_payload, str(report_path))

    append_jsonl(events_path, {"ts": datetime.now(timezone.utc).isoformat(), "event": "analysis_completed", "summary_path": str(summary_path)})

    return {
        "summary_path": str(summary_path),
        "recommendations_path": str(recommendations_path),
        "report_path": str(report_path),
        "closed_positions": len(closed_positions),
    }
