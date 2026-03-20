from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any

_VALID_ENTRY_DECISIONS = {"SCALP", "TREND", "IGNORE"}
_VALID_REGIMES = {"SCALP", "TREND", "UNKNOWN", "IGNORE"}
_VALID_X_STATUS = {"healthy", "degraded", "missing", "error", "unknown"}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if str(item)]
    if isinstance(value, tuple):
        return [str(item) for item in value if str(item)]
    if isinstance(value, str):
        return [value] if value else []
    return [str(value)]


def _as_float(value: Any, *, default: float | None = None) -> float | None:
    try:
        if value in (None, ""):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _normalized_decision(row: dict[str, Any]) -> str:
    for key in ("entry_decision", "decision", "regime_decision"):
        value = str(row.get(key) or "").upper()
        if value in _VALID_ENTRY_DECISIONS:
            return value
    regime_candidate = str(row.get("regime_candidate") or row.get("regime") or "").upper()
    if regime_candidate in {"SCALP", "TREND", "IGNORE"} and row.get("recommended_position_pct") not in (None, ""):
        return regime_candidate
    return "IGNORE"


def _normalized_regime(row: dict[str, Any], decision: str) -> str:
    regime = str(row.get("regime") or row.get("regime_candidate") or decision or "UNKNOWN").upper()
    if regime not in _VALID_REGIMES:
        return "UNKNOWN"
    return regime


def _normalized_x_status(row: dict[str, Any]) -> str:
    status = str(row.get("x_status") or row.get("x_validation_status") or "unknown").lower()
    if status not in _VALID_X_STATUS:
        return "unknown"
    return status


def _build_signal_id(row: dict[str, Any], origin: str, ts: str, token_address: str) -> str:
    existing = str(row.get("signal_id") or "").strip()
    if existing:
        return existing
    digest = hashlib.sha1(f"{origin}:{token_address}:{ts}".encode("utf-8")).hexdigest()[:12]
    return f"runtime_{digest}"


def normalize_runtime_signal(
    row: dict[str, Any],
    *,
    runtime_signal_origin: str,
    source_artifact: str | None = None,
) -> dict[str, Any]:
    token_address = str(row.get("token_address") or row.get("mint") or row.get("token_key") or "").strip()
    decision = _normalized_decision(row)
    signal_ts = str(row.get("signal_ts") or row.get("decided_at") or row.get("ts") or _utc_now_iso())
    regime = _normalized_regime(row, decision)
    blockers = _as_list(row.get("blockers") or row.get("regime_blockers"))
    reason_flags = _as_list(row.get("reason_flags") or row.get("entry_flags") or row.get("regime_reason_flags"))
    warnings = _as_list(row.get("runtime_signal_warning") or row.get("entry_warnings"))
    regime_confidence = _as_float(row.get("regime_confidence"), default=0.0) or 0.0
    entry_confidence = _as_float(row.get("entry_confidence"), default=None)
    runtime_confidence = _as_float(row.get("runtime_signal_confidence"), default=entry_confidence)
    recommended_position_pct = _as_float(row.get("recommended_position_pct"), default=0.0) or 0.0

    partial_flag = False
    invalid_reasons: list[str] = []

    if not token_address:
        invalid_reasons.append("missing_token_address")
    if regime == "UNKNOWN":
        partial_flag = True
        warnings.append("unknown_regime")
    if decision == "IGNORE":
        warnings.append("entry_decision_ignore")
    if runtime_confidence is None:
        partial_flag = True
        warnings.append("missing_runtime_confidence")
        runtime_confidence = regime_confidence or 0.0
    if recommended_position_pct <= 0 and decision != "IGNORE":
        partial_flag = True
        warnings.append("missing_position_size")
    if not 0.0 <= recommended_position_pct <= 1.0:
        invalid_reasons.append("recommended_position_pct_out_of_range")
    if not 0.0 <= runtime_confidence <= 1.0:
        invalid_reasons.append("runtime_confidence_out_of_range")
    if not 0.0 <= regime_confidence <= 1.0:
        invalid_reasons.append("regime_confidence_out_of_range")

    status = "ok"
    effective_status = "eligible"
    if invalid_reasons:
        status = "invalid"
        effective_status = "invalid"
        partial_flag = True
        blockers = [*blockers, *invalid_reasons]
    elif partial_flag:
        status = "partial"
    if decision == "IGNORE":
        effective_status = "ignore"
    elif blockers:
        effective_status = "blocked"

    warning_text = "; ".join(dict.fromkeys(warnings)) if warnings else None
    normalized = {
        "signal_id": _build_signal_id(row, runtime_signal_origin, signal_ts, token_address),
        "token_address": token_address,
        "pair_address": row.get("pair_address"),
        "symbol": row.get("symbol"),
        "signal_ts": signal_ts,
        "regime": regime,
        "x_status": _normalized_x_status(row),
        "entry_decision": decision,
        "regime_confidence": round(regime_confidence, 4),
        "recommended_position_pct": round(recommended_position_pct, 4),
        "reason_flags": list(dict.fromkeys(reason_flags)),
        "blockers": list(dict.fromkeys(blockers)),
        "effective_signal_status": effective_status,
        "source_artifact": source_artifact,
        "runtime_signal_origin": runtime_signal_origin,
        "runtime_signal_status": status,
        "runtime_signal_warning": warning_text,
        "runtime_signal_confidence": round(runtime_confidence, 4),
        "runtime_signal_partial_flag": partial_flag,
        "entry_confidence": None if entry_confidence is None else round(entry_confidence, 4),
        "entry_reason": row.get("entry_reason") or row.get("reason"),
        "entry_snapshot": row.get("entry_snapshot") or {},
        "raw_signal": row,
    }
    return normalized


def adapt_runtime_signal(row: dict[str, Any], *, runtime_signal_origin: str, source_artifact: str | None = None) -> dict[str, Any]:
    return normalize_runtime_signal(row, runtime_signal_origin=runtime_signal_origin, source_artifact=source_artifact)


def adapt_runtime_signal_batch(
    rows: list[dict[str, Any]],
    *,
    runtime_signal_origin: str,
    source_artifact: str | None = None,
) -> list[dict[str, Any]]:
    return [
        adapt_runtime_signal(row, runtime_signal_origin=runtime_signal_origin, source_artifact=source_artifact)
        for row in rows
        if isinstance(row, dict)
    ]
