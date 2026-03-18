"""Deterministic bundle enrichment helpers for discovery candidates."""

from __future__ import annotations

from typing import Any

COMPOSITION_UNKNOWN = "unknown"
COMPOSITION_BUY_ONLY = "buy-only"
COMPOSITION_MIXED = "mixed"
COMPOSITION_SELL_ONLY = "sell-only"

_BUNDLE_EVENT_KEYS = (
    "bundle_events",
    "bundle_activity",
    "bundle_flows",
    "bundles",
    "bundle_attempts",
)
_NESTED_BUNDLE_KEYS = ("bundle_data", "bundle_metrics", "bundle_insights", "bundle_analysis", "metadata")
_SIDE_KEYS = ("side", "direction", "swap_direction", "action", "action_label", "flow")
_TIP_KEYS = ("tip_amount", "tip", "jito_tip", "priority_fee_sol", "priority_fee", "bundle_tip")
_VALUE_KEYS = ("bundle_value", "value", "notional", "usd_value", "total_value")
_ACTOR_KEYS = ("actor", "wallet", "wallet_address", "signer", "authority", "owner")
_STATUS_KEYS = ("status", "result", "outcome", "execution_status")
_TS_KEYS = ("timestamp", "ts", "time", "block_time")
_BLOCK_KEYS = ("slot", "block", "block_slot", "block_number")


def _iter_bundle_lists(payload: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []

    extracted: list[dict[str, Any]] = []
    for key in _BUNDLE_EVENT_KEYS:
        value = payload.get(key)
        if isinstance(value, list):
            extracted.extend(item for item in value if isinstance(item, dict))

    for key in _NESTED_BUNDLE_KEYS:
        nested = payload.get(key)
        if isinstance(nested, dict):
            extracted.extend(_iter_bundle_lists(nested))

    return extracted


def _extract_bundle_records(*payloads: dict[str, Any] | None) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for payload in payloads:
        records.extend(_iter_bundle_lists(payload))
    return records


def _as_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_int(value: Any) -> int | None:
    numeric = _as_float(value)
    if numeric is None:
        return None
    return int(numeric)


def _first_present(record: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        if key in record and record.get(key) not in (None, ""):
            return record.get(key)
    return None


def _normalized_actor(record: dict[str, Any]) -> str | None:
    actor = _first_present(record, _ACTOR_KEYS)
    if actor is None:
        return None
    value = str(actor).strip()
    return value or None


def _record_ts(record: dict[str, Any]) -> int | None:
    return _as_int(_first_present(record, _TS_KEYS))


def _record_block(record: dict[str, Any]) -> int | None:
    return _as_int(_first_present(record, _BLOCK_KEYS))


def _record_failed(record: dict[str, Any]) -> bool:
    explicit = record.get("success")
    if explicit is not None:
        return not bool(explicit)

    status_value = _first_present(record, _STATUS_KEYS)
    if status_value is None:
        return False

    label = str(status_value).strip().lower()
    if not label:
        return False
    if any(token in label for token in ("fail", "revert", "drop", "reject", "retry", "expired", "error")):
        return True
    if any(token in label for token in ("success", "ok", "confirmed", "filled", "executed")):
        return False
    return False


def _infer_side(record: dict[str, Any]) -> str | None:
    for key in _SIDE_KEYS:
        raw_value = record.get(key)
        if raw_value in (None, ""):
            continue
        label = str(raw_value).strip().lower()
        if any(token in label for token in ("buy", "accumulate", "long")):
            return "buy"
        if any(token in label for token in ("sell", "dump", "short")):
            return "sell"

    token_delta = _as_float(record.get("token_delta"))
    if token_delta is not None:
        if token_delta > 0:
            return "buy"
        if token_delta < 0:
            return "sell"

    base_delta = _as_float(record.get("base_delta"))
    if base_delta is not None:
        if base_delta < 0:
            return "buy"
        if base_delta > 0:
            return "sell"

    return None


def classify_bundle_composition(bundle_records: list[dict[str, Any]]) -> str:
    buys = 0
    sells = 0
    for record in bundle_records:
        side = _infer_side(record)
        if side == "buy":
            buys += 1
        elif side == "sell":
            sells += 1

    if buys == 0 and sells == 0:
        return COMPOSITION_UNKNOWN
    if buys > 0 and sells == 0:
        return COMPOSITION_BUY_ONLY
    if sells > 0 and buys == 0:
        return COMPOSITION_SELL_ONLY
    return COMPOSITION_MIXED


def compute_bundle_tip_efficiency(bundle_records: list[dict[str, Any]], bundle_size_value: Any = None) -> float | None:
    total_tip = 0.0
    total_value = 0.0
    tip_seen = False
    value_seen = False

    external_value = _as_float(bundle_size_value)
    if external_value is not None and external_value > 0:
        total_value += external_value
        value_seen = True

    for record in bundle_records:
        tip_value = _as_float(_first_present(record, _TIP_KEYS))
        if tip_value is not None:
            total_tip += tip_value
            tip_seen = True

        record_value = _as_float(_first_present(record, _VALUE_KEYS))
        if record_value is not None and record_value > 0:
            total_value += record_value
            value_seen = True

    if not tip_seen or not value_seen or total_value <= 0:
        return None

    return round(total_tip / total_value, 6)


def detect_bundle_failure_retry_pattern(bundle_records: list[dict[str, Any]], retry_window_sec: int = 90) -> int | None:
    attempts_by_actor: dict[str, list[tuple[int | None, bool]]] = {}
    evidence_seen = False

    for record in bundle_records:
        actor = _normalized_actor(record)
        if actor is None:
            continue
        failed = _record_failed(record)
        if failed or record.get("success") is not None or _first_present(record, _STATUS_KEYS) is not None:
            evidence_seen = True
        attempts_by_actor.setdefault(actor, []).append((_record_ts(record), failed))

    if not evidence_seen:
        return None

    retries = 0
    for attempts in attempts_by_actor.values():
        attempts.sort(key=lambda item: item[0] if item[0] is not None else 10**18)
        for index in range(1, len(attempts)):
            prev_ts, prev_failed = attempts[index - 1]
            curr_ts, curr_failed = attempts[index]
            within_window = prev_ts is None or curr_ts is None or curr_ts - prev_ts <= retry_window_sec
            if within_window and (prev_failed or curr_failed):
                retries += 1
    return retries


def compute_cross_block_bundle_correlation(bundle_records: list[dict[str, Any]], max_block_gap: int = 2) -> float | None:
    blocks_by_actor: dict[str, set[int]] = {}
    block_evidence = False

    for record in bundle_records:
        actor = _normalized_actor(record)
        block = _record_block(record)
        if block is None:
            continue
        block_evidence = True
        bucket = blocks_by_actor.setdefault(actor or "__unknown_actor__", set())
        bucket.add(block)

    if not block_evidence:
        return None

    possible_pairs = 0
    correlated_pairs = 0
    for blocks in blocks_by_actor.values():
        ordered = sorted(blocks)
        if len(ordered) < 2:
            continue
        for prev, curr in zip(ordered, ordered[1:]):
            possible_pairs += 1
            gap = curr - prev
            if 1 <= gap <= max_block_gap:
                correlated_pairs += 1

    if possible_pairs == 0:
        return 0.0
    return round(correlated_pairs / possible_pairs, 6)


def compute_advanced_bundle_fields(*, candidate: dict[str, Any] | None = None, raw_pair: dict[str, Any] | None = None) -> dict[str, Any]:
    candidate = candidate or {}
    raw_pair = raw_pair or {}
    bundle_records = _extract_bundle_records(candidate, raw_pair)

    return {
        "bundle_composition_dominant": classify_bundle_composition(bundle_records),
        "bundle_tip_efficiency": compute_bundle_tip_efficiency(bundle_records, candidate.get("bundle_size_value")),
        "bundle_failure_retry_pattern": detect_bundle_failure_retry_pattern(bundle_records),
        "cross_block_bundle_correlation": compute_cross_block_bundle_correlation(bundle_records),
    }
