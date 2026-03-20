"""Dedicated continuation enrichment orchestration with provenance and fallback honesty."""

from __future__ import annotations

from typing import Any

from analytics.short_horizon_signals import (
    _parse_ts,
    compute_cluster_sell_concentration_120s,
    compute_liquidity_refill_ratio_120s,
    compute_liquidity_shock_recovery_sec,
    compute_net_unique_buyers_60s,
    compute_seller_reentry_ratio,
    compute_smart_wallet_dispersion_score,
    compute_x_author_velocity_5m,
)
from utils.clock import utc_now_iso
from utils.short_horizon_contract_fields import SHORT_HORIZON_SIGNAL_FIELDS

CONTINUATION_METADATA_FIELDS = [
    "continuation_status",
    "continuation_warning",
    "continuation_confidence",
    "continuation_metric_origin",
    "continuation_coverage_ratio",
    "continuation_inputs_status",
    "continuation_warnings",
    "continuation_available_evidence",
    "continuation_missing_evidence",
]
CONTINUATION_OUTPUT_FIELDS = [*SHORT_HORIZON_SIGNAL_FIELDS, *CONTINUATION_METADATA_FIELDS]

_TX_METRIC_FIELDS = {
    "net_unique_buyers_60s",
    "liquidity_refill_ratio_120s",
    "cluster_sell_concentration_120s",
    "seller_reentry_ratio",
    "liquidity_shock_recovery_sec",
}
_X_METRIC_FIELDS = {"x_author_velocity_5m"}
_WALLET_METRIC_FIELDS = {"smart_wallet_dispersion_score"}

_ALLOWED_ORIGINS = {
    frozenset(): "missing",
    frozenset({"tx"}): "computed_from_tx",
    frozenset({"x"}): "computed_from_x",
    frozenset({"wallet_registry"}): "computed_from_wallet_registry",
}


def _safe_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _is_tx_record(tx: Any) -> bool:
    return isinstance(tx, dict)


def _is_snapshot(snapshot: Any) -> bool:
    return isinstance(snapshot, dict)


def _safe_ratio(num: int, den: int) -> float:
    if den <= 0:
        return 0.0
    return round(num / den, 6)


def _coverage_bucket(ratio: float) -> str:
    if ratio >= 0.85:
        return "high"
    if ratio >= 0.45:
        return "medium"
    if ratio > 0:
        return "low"
    return "missing"


def _confidence_label(*, metric_count: int, coverage_ratio: float, warnings: list[str]) -> str:
    if metric_count <= 0 or coverage_ratio <= 0:
        return "low"
    penalty = 0
    if coverage_ratio < 0.45:
        penalty += 1
    if len(warnings) >= 2:
        penalty += 1
    if metric_count >= 5 and penalty == 0:
        return "high"
    if metric_count >= 3 and penalty <= 1:
        return "medium"
    return "low"


def _first_string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _extract_x_snapshots(token_ctx: dict[str, Any], x_snapshots: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    if x_snapshots is not None:
        return [snapshot for snapshot in x_snapshots if _is_snapshot(snapshot)]
    for key in (
        "x_snapshots",
        "x_snapshot_payloads",
        "x_snapshot_history",
        "x_snapshot_cards",
        "x_snapshot",
    ):
        value = token_ctx.get(key)
        if isinstance(value, list):
            return [snapshot for snapshot in value if _is_snapshot(snapshot)]
        if isinstance(value, dict):
            return [value]
    cards = token_ctx.get("cards")
    if isinstance(cards, list):
        return [{"cards": cards, "x_status": token_ctx.get("x_status", "ok")}]
    return []


def compute_continuation_metrics(
    *,
    token_ctx: dict[str, Any] | None = None,
    txs: list[dict[str, Any]] | None = None,
    x_snapshots: list[dict[str, Any]] | None = None,
    wallet_lookup: dict[str, Any] | None = None,
    hit_wallets: list[str] | tuple[str, ...] | None = None,
    pair_created_ts: int | None = None,
    creator_wallet: str | None = None,
) -> dict[str, Any]:
    token_ctx = dict(token_ctx or {})
    txs = [tx for tx in _safe_list(txs) if _is_tx_record(tx)]
    x_snapshots = _extract_x_snapshots(token_ctx, x_snapshots)
    wallet_lookup = dict(wallet_lookup or {})
    hit_wallets = [str(wallet).strip() for wallet in (hit_wallets or []) if str(wallet).strip()]

    pair_ts = pair_created_ts if pair_created_ts is not None else _parse_ts(token_ctx.get("pair_created_at"))
    creator = creator_wallet or _first_string(token_ctx.get("creator_wallet"))

    metrics: dict[str, Any] = {field: None for field in SHORT_HORIZON_SIGNAL_FIELDS}
    metric_sources: dict[str, str] = {}
    warnings: list[str] = []
    available_evidence: list[str] = []
    missing_evidence: list[str] = []
    inputs_status: dict[str, str] = {}
    events: list[dict[str, Any]] = []

    events.append(
        {
            "ts": utc_now_iso(),
            "event": "continuation_enrichment_started",
            "token_address": token_ctx.get("token_address"),
            "pair_address": token_ctx.get("pair_address"),
            "evidence_types_available": {
                "tx": bool(txs),
                "x": bool(x_snapshots),
                "wallet_registry": bool(wallet_lookup.get("validated_wallets")),
            },
        }
    )

    if pair_ts > 0 and txs:
        available_evidence.append("tx")
        inputs_status["tx"] = "ready"
        metrics["net_unique_buyers_60s"] = compute_net_unique_buyers_60s(pair_created_ts=pair_ts, txs=txs)
        metrics["liquidity_refill_ratio_120s"] = compute_liquidity_refill_ratio_120s(pair_created_ts=pair_ts, txs=txs)
        metrics["cluster_sell_concentration_120s"] = compute_cluster_sell_concentration_120s(
            pair_created_ts=pair_ts,
            txs=txs,
            creator_wallet=creator,
        )
        metrics["seller_reentry_ratio"] = compute_seller_reentry_ratio(pair_created_ts=pair_ts, txs=txs)
        metrics["liquidity_shock_recovery_sec"] = compute_liquidity_shock_recovery_sec(pair_created_ts=pair_ts, txs=txs)
        tx_metric_count = sum(metrics[field] is not None for field in _TX_METRIC_FIELDS)
        for field in _TX_METRIC_FIELDS:
            if metrics[field] is not None:
                metric_sources[field] = "tx"
        if tx_metric_count == 0:
            warnings.append("tx_evidence_present_but_continuation_metrics_unresolved")
            inputs_status["tx"] = "partial"
        elif tx_metric_count < len(_TX_METRIC_FIELDS):
            warnings.append("tx_continuation_metrics_partially_resolved")
            inputs_status["tx"] = "partial"
        events.append(
            {
                "ts": utc_now_iso(),
                "event": "continuation_tx_metrics_computed",
                "token_address": token_ctx.get("token_address"),
                "coverage_ratio": _safe_ratio(sum(metrics[field] is not None for field in _TX_METRIC_FIELDS), len(_TX_METRIC_FIELDS)),
            }
        )
    elif txs:
        available_evidence.append("tx")
        inputs_status["tx"] = "partial"
        warnings.append("pair_created_ts_missing_for_tx_continuation")
    else:
        missing_evidence.append("tx")
        inputs_status["tx"] = "missing"

    if x_snapshots:
        available_evidence.append("x")
        metrics["x_author_velocity_5m"] = compute_x_author_velocity_5m(x_snapshots)
        metric_sources.update({"x_author_velocity_5m": "x"} if metrics["x_author_velocity_5m"] is not None else {})
        inputs_status["x"] = "ready" if metrics["x_author_velocity_5m"] is not None else "partial"
        if metrics["x_author_velocity_5m"] is None:
            warnings.append("x_snapshot_evidence_incomplete_for_author_velocity")
        events.append(
            {
                "ts": utc_now_iso(),
                "event": "continuation_x_metrics_computed",
                "token_address": token_ctx.get("token_address"),
                "coverage_ratio": _safe_ratio(int(metrics["x_author_velocity_5m"] is not None), 1),
            }
        )
    else:
        missing_evidence.append("x")
        inputs_status["x"] = "missing"

    registry = wallet_lookup.get("validated_wallets") if isinstance(wallet_lookup.get("validated_wallets"), dict) else {}
    if registry and hit_wallets:
        available_evidence.append("wallet_registry")
        metrics["smart_wallet_dispersion_score"] = compute_smart_wallet_dispersion_score(hit_wallets, wallet_lookup)
        if metrics["smart_wallet_dispersion_score"] is not None:
            metric_sources["smart_wallet_dispersion_score"] = "wallet_registry"
            inputs_status["wallet_registry"] = "ready"
        else:
            inputs_status["wallet_registry"] = "partial"
            warnings.append("wallet_registry_matches_insufficient_for_dispersion")
        events.append(
            {
                "ts": utc_now_iso(),
                "event": "continuation_wallet_metrics_computed",
                "token_address": token_ctx.get("token_address"),
                "coverage_ratio": _safe_ratio(int(metrics["smart_wallet_dispersion_score"] is not None), 1),
            }
        )
    elif registry:
        available_evidence.append("wallet_registry")
        inputs_status["wallet_registry"] = "partial"
        warnings.append("smart_wallet_hits_missing_for_dispersion")
    else:
        missing_evidence.append("wallet_registry")
        inputs_status["wallet_registry"] = "missing"

    present_fields = [field for field, value in metrics.items() if value is not None]
    coverage_ratio = _safe_ratio(len(present_fields), len(SHORT_HORIZON_SIGNAL_FIELDS))
    confidence = _confidence_label(metric_count=len(present_fields), coverage_ratio=coverage_ratio, warnings=warnings)
    origin_key = frozenset(metric_sources[field] for field in present_fields if field in metric_sources)
    metric_origin = _ALLOWED_ORIGINS.get(origin_key, "mixed_evidence" if len(origin_key) > 1 else ("partial" if present_fields else "missing"))

    status_summary = summarize_continuation_status(
        metrics=metrics,
        inputs_status=inputs_status,
        warnings=warnings,
    )

    if status_summary["continuation_status"] == "partial":
        events.append(
            {
                "ts": utc_now_iso(),
                "event": "continuation_partial",
                "token_address": token_ctx.get("token_address"),
                "coverage_ratio": coverage_ratio,
                "confidence": confidence,
                "warnings": sorted(set(warnings)),
            }
        )
    elif status_summary["continuation_status"] == "missing":
        events.append(
            {
                "ts": utc_now_iso(),
                "event": "continuation_missing",
                "token_address": token_ctx.get("token_address"),
                "coverage_ratio": coverage_ratio,
                "confidence": confidence,
                "warnings": sorted(set(warnings)),
            }
        )

    events.append(
        {
            "ts": utc_now_iso(),
            "event": "continuation_completed",
            "token_address": token_ctx.get("token_address"),
            "coverage_ratio": coverage_ratio,
            "confidence": confidence,
            "status": status_summary["continuation_status"],
        }
    )

    return {
        **metrics,
        **status_summary,
        "continuation_confidence": confidence,
        "continuation_metric_origin": metric_origin,
        "continuation_coverage_ratio": coverage_ratio,
        "continuation_inputs_status": inputs_status,
        "continuation_warnings": sorted(set(warnings)),
        "continuation_available_evidence": sorted(set(available_evidence)),
        "continuation_missing_evidence": sorted(set(missing_evidence)),
        "continuation_metric_sources": metric_sources,
        "continuation_events": events,
    }


def summarize_continuation_status(
    *,
    metrics: dict[str, Any],
    inputs_status: dict[str, str],
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    warnings = list(warnings or [])
    present_count = sum(value is not None for value in metrics.values())
    ready_inputs = sum(status == "ready" for status in inputs_status.values())
    has_partial_inputs = any(status == "partial" for status in inputs_status.values())

    if present_count == 0:
        status = "missing"
    elif present_count == len(SHORT_HORIZON_SIGNAL_FIELDS) and not has_partial_inputs:
        status = "complete"
    else:
        status = "partial"

    if status == "missing":
        warning = "continuation_evidence_missing"
    elif has_partial_inputs or present_count < len(SHORT_HORIZON_SIGNAL_FIELDS):
        warning = "continuation_partial_evidence"
    else:
        warning = ""

    if ready_inputs == 0 and status != "missing":
        warning = warning or "continuation_inputs_degraded"

    return {
        "continuation_status": status,
        "continuation_warning": warning,
    }


def build_continuation_payload(
    *,
    token_ctx: dict[str, Any] | None = None,
    txs: list[dict[str, Any]] | None = None,
    x_snapshots: list[dict[str, Any]] | None = None,
    wallet_lookup: dict[str, Any] | None = None,
    hit_wallets: list[str] | tuple[str, ...] | None = None,
    pair_created_ts: int | None = None,
    creator_wallet: str | None = None,
    contract_version: str = "continuation_enrichment_v1",
    generated_at: str | None = None,
) -> dict[str, Any]:
    token_ctx = dict(token_ctx or {})
    result = compute_continuation_metrics(
        token_ctx=token_ctx,
        txs=txs,
        x_snapshots=x_snapshots,
        wallet_lookup=wallet_lookup,
        hit_wallets=hit_wallets,
        pair_created_ts=pair_created_ts,
        creator_wallet=creator_wallet,
    )
    generated = generated_at or utc_now_iso()
    return {
        "metadata": {
            "contract_version": contract_version,
            "generated_at": generated,
        },
        "token": {
            "token_address": token_ctx.get("token_address"),
            "pair_address": token_ctx.get("pair_address"),
            "symbol": token_ctx.get("symbol"),
            "name": token_ctx.get("name"),
            "pair_created_at": token_ctx.get("pair_created_at"),
        },
        "continuation_metrics": {field: result.get(field) for field in SHORT_HORIZON_SIGNAL_FIELDS},
        "provenance": {
            "continuation_status": result.get("continuation_status"),
            "continuation_warning": result.get("continuation_warning"),
            "continuation_confidence": result.get("continuation_confidence"),
            "continuation_metric_origin": result.get("continuation_metric_origin"),
            "continuation_coverage_ratio": result.get("continuation_coverage_ratio"),
            "continuation_inputs_status": result.get("continuation_inputs_status"),
            "continuation_warnings": result.get("continuation_warnings"),
            "continuation_available_evidence": result.get("continuation_available_evidence"),
            "continuation_missing_evidence": result.get("continuation_missing_evidence"),
        },
        "events": result.get("continuation_events", []),
    }


__all__ = [
    "CONTINUATION_METADATA_FIELDS",
    "CONTINUATION_OUTPUT_FIELDS",
    "build_continuation_payload",
    "compute_continuation_metrics",
    "summarize_continuation_status",
]
