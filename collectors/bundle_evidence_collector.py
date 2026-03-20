"""Bundle evidence collection and evidence-first metric derivation."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from analytics.wallet_clustering import compute_wallet_clustering_metrics
from utils.logger import log_info, log_warning

REAL_EVIDENCE_ORIGIN = "real_evidence"
HEURISTIC_FALLBACK_ORIGIN = "heuristic_fallback"
MISSING_BUNDLE_ORIGIN = "missing"

_EVIDENCE_STATUS_VALUES = {"landed", "failed", "unknown"}
_SIDE_KEYS = ("side", "direction", "swap_direction", "action", "action_label", "flow")
_TIP_KEYS = ("tip_amount", "tip", "jito_tip", "priority_fee_sol", "priority_fee", "bundle_tip")
_VALUE_KEYS = ("bundle_value", "bundleValue", "swap_usd_value", "usd_value", "value_usd", "value", "notional", "total_value")
_TS_KEYS = ("timestamp", "blockTime", "ts", "time", "block_time")
_BLOCK_KEYS = ("slot", "block", "block_slot", "block_number")
_ACTOR_KEYS = ("actor", "wallet", "wallet_address", "signer", "authority", "owner", "feePayer", "user")
_GROUP_KEYS = ("group_id", "group_key", "bundle_id", "record_group_id", "cohort_id", "window_id")
_ATTEMPT_KEYS = ("attempt_id", "attempt", "execution_id", "tx_signature", "signature")
_RETRY_KEYS = ("retry_of", "retry_parent_id", "retry_parent_attempt", "prior_attempt_id")
_SOURCE_ALIAS_MAP = {
    "inline": ("bundle_evidence", "bundle_evidence_records"),
    "activity": ("bundle_activity",),
    "events": ("bundle_events",),
    "flows": ("bundle_flows",),
    "attempts": ("bundle_attempts",),
}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _coerce_int(value: Any) -> int | None:
    try:
        if value in (None, ""):
            return None
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _coerce_float(value: Any) -> float | None:
    try:
        if value in (None, ""):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _extract_anchor_ts(pair: dict[str, Any]) -> int | None:
    for key in ("liquidity_added_at_ts", "pair_created_at_ts", "pairCreatedAt"):
        value = _coerce_int(pair.get(key))
        if value and value > 0:
            return value
    return None


def _first_present(payload: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        value = payload.get(key)
        if value not in (None, ""):
            return value
    return None


def _normalize_status(record: dict[str, Any]) -> tuple[str, str | None]:
    explicit_success = record.get("success")
    if explicit_success is True:
        return "landed", None
    if explicit_success is False:
        return "failed", None

    raw = _first_present(record, ("status", "result", "outcome", "execution_status"))
    if raw is None:
        return "unknown", None
    label = str(raw).strip().lower()
    if not label:
        return "unknown", None
    if any(token in label for token in ("land", "confirm", "success", "ok", "fill", "executed")):
        return "landed", None
    if any(token in label for token in ("fail", "retry", "drop", "reject", "expired", "error", "revert")):
        return "failed", None
    return "unknown", f"unrecognized status:{label}"


def _normalize_side(record: dict[str, Any]) -> str | None:
    for key in _SIDE_KEYS:
        raw = record.get(key)
        if raw in (None, ""):
            continue
        label = str(raw).strip().lower()
        if any(token in label for token in ("buy", "accumulate", "long")):
            return "buy"
        if any(token in label for token in ("sell", "dump", "short")):
            return "sell"

    token_delta = _coerce_float(record.get("token_delta"))
    if token_delta is not None:
        if token_delta > 0:
            return "buy"
        if token_delta < 0:
            return "sell"

    base_delta = _coerce_float(record.get("base_delta"))
    if base_delta is not None:
        if base_delta < 0:
            return "buy"
        if base_delta > 0:
            return "sell"
    return None


def _normalize_source_order(settings: Any) -> list[str]:
    raw = getattr(settings, "BUNDLE_EVIDENCE_SOURCE_ORDER", "inline,activity,events,flows,attempts")
    if isinstance(raw, (list, tuple)):
        items = [str(item).strip().lower() for item in raw]
    else:
        items = [part.strip().lower() for part in str(raw).split(",")]
    return [item for item in items if item in _SOURCE_ALIAS_MAP] or ["inline", "activity", "events", "flows", "attempts"]


def _flatten_source_records(pair: dict[str, Any], source_name: str) -> list[dict[str, Any]]:
    extracted: list[dict[str, Any]] = []
    for key in _SOURCE_ALIAS_MAP.get(source_name, ()): 
        value = pair.get(key)
        if isinstance(value, list):
            extracted.extend(item for item in value if isinstance(item, dict))
        elif isinstance(value, dict):
            nested_records = value.get("bundle_records") or value.get("records") or value.get("events")
            if isinstance(nested_records, list):
                extracted.extend(item for item in nested_records if isinstance(item, dict))
    return extracted


def normalize_bundle_evidence(
    raw_records: list[dict[str, Any]],
    *,
    pair: dict[str, Any],
    anchor_ts: int | None,
    window_sec: int,
    source: str,
    collected_at: str | None = None,
) -> dict[str, Any]:
    collected_at = collected_at or _utc_now_iso()
    warnings: list[str] = []
    normalized_records: list[dict[str, Any]] = []
    malformed_count = 0
    in_window_count = 0

    for index, raw_record in enumerate(raw_records):
        if not isinstance(raw_record, dict):
            malformed_count += 1
            warnings.append("non-dict evidence record dropped")
            continue

        timestamp = _coerce_int(_first_present(raw_record, _TS_KEYS))
        if timestamp is None:
            warnings.append("missing timestamp in evidence record")
        elif anchor_ts is not None and not (anchor_ts <= timestamp <= anchor_ts + window_sec):
            continue
        else:
            in_window_count += 1

        status, status_warning = _normalize_status(raw_record)
        if status_warning:
            warnings.append(status_warning)

        actor = _first_present(raw_record, _ACTOR_KEYS)
        actor_str = str(actor).strip() if actor is not None else ""
        notional = _coerce_float(_first_present(raw_record, _VALUE_KEYS))
        tip = _coerce_float(_first_present(raw_record, _TIP_KEYS))
        slot = _coerce_int(_first_present(raw_record, _BLOCK_KEYS))
        if status not in _EVIDENCE_STATUS_VALUES:
            status = "unknown"

        if not actor_str and timestamp is None and slot is None:
            malformed_count += 1
            warnings.append("record missing actor/timestamp/slot context")

        normalized_records.append(
            {
                "record_id": str(_first_present(raw_record, ("record_id", "id")) or f"{source}-{index}"),
                "group_id": _first_present(raw_record, _GROUP_KEYS) or (f"slot:{slot}" if slot is not None else None),
                "attempt_id": _first_present(raw_record, _ATTEMPT_KEYS),
                "retry_of": _first_present(raw_record, _RETRY_KEYS),
                "token_address": str(pair.get("token_address") or pair.get("baseToken", {}).get("address") or "").strip() or None,
                "pair_address": str(pair.get("pair_address") or pair.get("pairAddress") or "").strip() or None,
                "slot": slot,
                "block": slot,
                "timestamp": timestamp,
                "actor": actor_str or None,
                "wallet": actor_str or None,
                "status": status,
                "side": _normalize_side(raw_record),
                "notional": notional,
                "value": notional,
                "tip": tip,
                "priority_fee": tip,
                "provenance": {
                    "source": source,
                    "raw_index": index,
                    "raw_status": _first_present(raw_record, ("status", "result", "outcome", "execution_status")),
                    "raw_attempt_id": _first_present(raw_record, _ATTEMPT_KEYS),
                },
            }
        )

    actor_count = len({record["actor"] for record in normalized_records if record.get("actor")})
    explicit_group_count = len({record["group_id"] for record in normalized_records if record.get("group_id")})
    landed_count = sum(1 for record in normalized_records if record.get("status") == "landed")
    failed_count = sum(1 for record in normalized_records if record.get("status") == "failed")
    unknown_count = sum(1 for record in normalized_records if record.get("status") == "unknown")

    status = "ok"
    if not raw_records:
        status = "unavailable"
    elif malformed_count > 0 or unknown_count > 0 or len(normalized_records) < 2:
        status = "partial"

    warning_text = "; ".join(sorted(set(warnings))) if warnings else None
    if not normalized_records and raw_records:
        status = "partial"
        warning_text = warning_text or "no evidence records remained after normalization"

    return {
        "bundle_evidence_status": status,
        "bundle_evidence_source": source,
        "bundle_evidence_warning": warning_text,
        "bundle_evidence_collected_at": collected_at,
        "bundle_window_anchor_ts": anchor_ts,
        "bundle_window_sec": window_sec,
        "bundle_records": normalized_records,
        "bundle_evidence_summary": {
            "raw_record_count": len(raw_records),
            "normalized_record_count": len(normalized_records),
            "records_in_window": in_window_count,
            "malformed_record_count": malformed_count,
            "landed_record_count": landed_count,
            "failed_record_count": failed_count,
            "unknown_record_count": unknown_count,
            "actor_count": actor_count,
            "explicit_group_count": explicit_group_count,
        },
    }


def collect_bundle_evidence_for_pair(pair: dict[str, Any], now_ts: int, settings: Any) -> dict[str, Any]:
    if not getattr(settings, "BUNDLE_ENRICHMENT_ENABLED", True):
        return {
            "bundle_evidence_status": "disabled",
            "bundle_evidence_source": None,
            "bundle_evidence_warning": "bundle enrichment disabled",
            "bundle_evidence_collected_at": _utc_now_iso(),
            "bundle_window_anchor_ts": _extract_anchor_ts(pair),
            "bundle_window_sec": max(int(getattr(settings, "BUNDLE_ENRICHMENT_WINDOW_SEC", 60) or 60), 1),
            "bundle_records": [],
            "bundle_evidence_summary": {},
        }

    if not getattr(settings, "BUNDLE_EVIDENCE_ENABLED", True):
        return {
            "bundle_evidence_status": "disabled",
            "bundle_evidence_source": None,
            "bundle_evidence_warning": "bundle evidence disabled",
            "bundle_evidence_collected_at": _utc_now_iso(),
            "bundle_window_anchor_ts": _extract_anchor_ts(pair),
            "bundle_window_sec": max(int(getattr(settings, "BUNDLE_ENRICHMENT_WINDOW_SEC", 60) or 60), 1),
            "bundle_records": [],
            "bundle_evidence_summary": {},
        }

    anchor_ts = _extract_anchor_ts(pair)
    window_sec = max(
        int(
            getattr(settings, "BUNDLE_EVIDENCE_WINDOW_SEC", None)
            or getattr(settings, "BUNDLE_ENRICHMENT_WINDOW_SEC", 60)
            or 60
        ),
        1,
    )

    if anchor_ts is None:
        return {
            "bundle_evidence_status": "unavailable",
            "bundle_evidence_source": None,
            "bundle_evidence_warning": "missing liquidity/pair creation anchor",
            "bundle_evidence_collected_at": _utc_now_iso(),
            "bundle_window_anchor_ts": None,
            "bundle_window_sec": window_sec,
            "bundle_records": [],
            "bundle_evidence_summary": {},
        }

    if now_ts < anchor_ts:
        return {
            "bundle_evidence_status": "unavailable",
            "bundle_evidence_source": None,
            "bundle_evidence_warning": "anchor timestamp is in the future",
            "bundle_evidence_collected_at": _utc_now_iso(),
            "bundle_window_anchor_ts": anchor_ts,
            "bundle_window_sec": window_sec,
            "bundle_records": [],
            "bundle_evidence_summary": {},
        }

    log_info(
        "bundle_evidence_started",
        token_address=str(pair.get("token_address") or ""),
        pair_address=str(pair.get("pair_address") or pair.get("pairAddress") or ""),
        window_sec=window_sec,
    )

    max_records = max(int(getattr(settings, "BUNDLE_EVIDENCE_MAX_RECORDS", 200) or 200), 1)
    source_order = _normalize_source_order(settings)
    raw_records: list[dict[str, Any]] = []
    chosen_source: str | None = None

    for source_name in source_order:
        candidate_records = _flatten_source_records(pair, source_name)
        if candidate_records:
            raw_records = candidate_records[:max_records]
            chosen_source = source_name
            log_info(
                "bundle_evidence_source_loaded",
                token_address=str(pair.get("token_address") or ""),
                pair_address=str(pair.get("pair_address") or pair.get("pairAddress") or ""),
                source=source_name,
                raw_record_count=len(raw_records),
            )
            break

    if not raw_records:
        log_warning(
            "bundle_evidence_partial",
            token_address=str(pair.get("token_address") or ""),
            pair_address=str(pair.get("pair_address") or pair.get("pairAddress") or ""),
            warning="no real bundle evidence source records available",
        )
        return {
            "bundle_evidence_status": "unavailable",
            "bundle_evidence_source": None,
            "bundle_evidence_warning": "no real bundle evidence source records available",
            "bundle_evidence_collected_at": _utc_now_iso(),
            "bundle_window_anchor_ts": anchor_ts,
            "bundle_window_sec": window_sec,
            "bundle_records": [],
            "bundle_evidence_summary": {},
        }

    normalized = normalize_bundle_evidence(
        raw_records,
        pair=pair,
        anchor_ts=anchor_ts,
        window_sec=window_sec,
        source=chosen_source or "inline",
    )
    event_name = "bundle_evidence_normalized"
    if normalized["bundle_evidence_status"] == "partial":
        event_name = "bundle_evidence_partial"
        log_warning(
            event_name,
            token_address=str(pair.get("token_address") or ""),
            pair_address=str(pair.get("pair_address") or pair.get("pairAddress") or ""),
            source=normalized.get("bundle_evidence_source"),
            warning=normalized.get("bundle_evidence_warning"),
            normalized_record_count=normalized.get("bundle_evidence_summary", {}).get("normalized_record_count"),
        )
    else:
        log_info(
            event_name,
            token_address=str(pair.get("token_address") or ""),
            pair_address=str(pair.get("pair_address") or pair.get("pairAddress") or ""),
            source=normalized.get("bundle_evidence_source"),
            normalized_record_count=normalized.get("bundle_evidence_summary", {}).get("normalized_record_count"),
        )
    return normalized


def _group_records(records: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        key = (
            record.get("group_id")
            or record.get("attempt_id")
            or (f"slot:{record['slot']}" if record.get("slot") is not None else None)
            or (f"ts:{record['timestamp']}" if record.get("timestamp") is not None else None)
        )
        if key is None:
            continue
        grouped[str(key)].append(record)
    return [group for group in grouped.values() if len(group) >= 2]


def _classify_composition(records: list[dict[str, Any]]) -> str:
    buys = sum(1 for record in records if record.get("side") == "buy")
    sells = sum(1 for record in records if record.get("side") == "sell")
    if buys == 0 and sells == 0:
        return "unknown"
    if buys > 0 and sells == 0:
        return "buy-only"
    if sells > 0 and buys == 0:
        return "sell-only"
    return "mixed"


def _compute_tip_efficiency(records: list[dict[str, Any]], bundle_size_value: float | None) -> float | None:
    total_tip = sum(float(record.get("tip") or 0.0) for record in records if _coerce_float(record.get("tip")) is not None)
    record_values = [float(record["notional"]) for record in records if _coerce_float(record.get("notional")) not in (None, 0.0)]
    total_value = sum(record_values)
    if bundle_size_value is not None and bundle_size_value > 0:
        total_value = max(total_value, bundle_size_value)
    if total_tip <= 0 or total_value <= 0:
        return None
    return round(total_tip / total_value, 6)


def _compute_retry_pattern(records: list[dict[str, Any]], retry_window_sec: int = 90) -> int | None:
    attempts_by_actor: dict[str, list[tuple[int | None, bool, Any]]] = defaultdict(list)
    evidence_seen = False
    for record in records:
        actor = str(record.get("actor") or "").strip()
        if not actor:
            continue
        failed = record.get("status") == "failed"
        if failed or record.get("retry_of") is not None or record.get("status") in {"landed", "failed"}:
            evidence_seen = True
        attempts_by_actor[actor].append((record.get("timestamp"), failed, record.get("retry_of")))
    if not evidence_seen:
        return None

    retry_count = 0
    for attempts in attempts_by_actor.values():
        attempts.sort(key=lambda item: item[0] if item[0] is not None else 10**18)
        for index in range(1, len(attempts)):
            prev_ts, prev_failed, _prev_retry_of = attempts[index - 1]
            curr_ts, curr_failed, curr_retry_of = attempts[index]
            within_window = prev_ts is None or curr_ts is None or curr_ts - prev_ts <= retry_window_sec
            if curr_retry_of is not None and within_window:
                retry_count += 1
            elif within_window and (prev_failed or curr_failed):
                retry_count += 1
    return retry_count


def _compute_cross_block_correlation(records: list[dict[str, Any]], max_block_gap: int = 2) -> float | None:
    blocks_by_actor: dict[str, set[int]] = defaultdict(set)
    for record in records:
        actor = str(record.get("actor") or "").strip() or "__unknown_actor__"
        slot = _coerce_int(record.get("slot"))
        if slot is None:
            continue
        blocks_by_actor[actor].add(slot)
    if not blocks_by_actor:
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


def _clustering_metrics(pair: dict[str, Any], records: list[dict[str, Any]]) -> dict[str, Any]:
    participants: list[dict[str, Any]] = []
    participant_wallets: list[str] = []
    creator_wallet = str(
        pair.get("creator_wallet")
        or pair.get("deployer_wallet")
        or pair.get("mint_authority")
        or pair.get("update_authority")
        or ""
    ).strip() or None

    for record in records:
        actor = str(record.get("actor") or "").strip()
        if not actor:
            continue
        participant_wallets.append(actor)
        participants.append(
            {
                "wallet": actor,
                "group_id": record.get("group_id") or record.get("slot"),
                "funder": record.get("provenance", {}).get("funder") if isinstance(record.get("provenance"), dict) else None,
                "creator_linked": creator_wallet == actor if creator_wallet else None,
            }
        )

    return compute_wallet_clustering_metrics(
        participants,
        creator_wallet=creator_wallet,
        participant_wallets=sorted(set(participant_wallets)),
    )


def _compute_confidence(summary: dict[str, Any], bundle_count: int, records: list[dict[str, Any]]) -> float:
    confidence = 0.2
    normalized_count = int(summary.get("normalized_record_count") or 0)
    if normalized_count >= 2:
        confidence += 0.15
    if bundle_count >= 1:
        confidence += 0.2
    known_status_ratio_den = max(normalized_count, 1)
    known_status_ratio = (int(summary.get("landed_record_count") or 0) + int(summary.get("failed_record_count") or 0)) / known_status_ratio_den
    confidence += min(0.2, known_status_ratio * 0.2)
    if int(summary.get("explicit_group_count") or 0) >= 1:
        confidence += 0.1
    if any(_coerce_float(record.get("tip")) not in (None, 0.0) for record in records):
        confidence += 0.1
    if any(_coerce_int(record.get("slot")) is not None for record in records):
        confidence += 0.1
    if any(record.get("retry_of") is not None for record in records):
        confidence += 0.05
    return round(min(confidence, 0.9), 4)


def compute_bundle_metrics_from_evidence(normalized_evidence: dict[str, Any], *, pair: dict[str, Any] | None = None) -> dict[str, Any]:
    pair = pair or {}
    summary = normalized_evidence.get("bundle_evidence_summary") or {}
    records = [record for record in normalized_evidence.get("bundle_records", []) if isinstance(record, dict)]
    payload = {
        "bundle_count_first_60s": None,
        "bundle_size_value": None,
        "unique_wallets_per_bundle_avg": None,
        "bundle_timing_from_liquidity_add_min": None,
        "bundle_success_rate": None,
        "bundle_composition_dominant": None,
        "bundle_tip_efficiency": None,
        "bundle_failure_retry_pattern": None,
        "cross_block_bundle_correlation": None,
        "bundle_wallet_clustering_score": None,
        "cluster_concentration_ratio": None,
        "num_unique_clusters_first_60s": None,
        "creator_in_cluster_flag": None,
        "bundle_enrichment_status": normalized_evidence.get("bundle_evidence_status") or "unavailable",
        "bundle_enrichment_warning": normalized_evidence.get("bundle_evidence_warning"),
        "bundle_evidence_status": normalized_evidence.get("bundle_evidence_status") or "unavailable",
        "bundle_evidence_source": normalized_evidence.get("bundle_evidence_source"),
        "bundle_evidence_warning": normalized_evidence.get("bundle_evidence_warning"),
        "bundle_evidence_confidence": None,
        "bundle_metric_origin": MISSING_BUNDLE_ORIGIN,
        "bundle_records": records,
        "bundle_evidence_summary": summary,
        "bundle_evidence_collected_at": normalized_evidence.get("bundle_evidence_collected_at"),
        "bundle_window_anchor_ts": normalized_evidence.get("bundle_window_anchor_ts"),
        "bundle_window_sec": normalized_evidence.get("bundle_window_sec"),
    }

    if not records:
        return payload

    bundles = _group_records(records)
    if not bundles:
        payload["bundle_enrichment_warning"] = payload["bundle_enrichment_warning"] or "insufficient real evidence for bundle derivation"
        payload["bundle_evidence_warning"] = payload["bundle_enrichment_warning"]
        return payload

    anchor_ts = _coerce_int(normalized_evidence.get("bundle_window_anchor_ts"))
    bundle_values: list[float] = []
    wallet_counts: list[int] = []
    bundle_offsets_min: list[float] = []
    success_values: list[float] = []

    for bundle in bundles:
        wallets = {str(record.get("actor") or "").strip() for record in bundle if str(record.get("actor") or "").strip()}
        if wallets:
            wallet_counts.append(len(wallets))

        values = [float(record["notional"]) for record in bundle if _coerce_float(record.get("notional")) is not None]
        if values:
            bundle_values.append(sum(values))

        timestamps = [int(record["timestamp"]) for record in bundle if _coerce_int(record.get("timestamp")) is not None]
        if timestamps and anchor_ts is not None:
            bundle_offsets_min.append((min(timestamps) - anchor_ts) / 60.0)

        for record in bundle:
            if record.get("status") == "landed":
                success_values.append(1.0)
            elif record.get("status") == "failed":
                success_values.append(0.0)

    bundle_count = len(bundles)
    bundle_size_value = round(sum(bundle_values), 6) if bundle_values else None

    payload.update(
        {
            "bundle_count_first_60s": bundle_count,
            "bundle_size_value": bundle_size_value,
            "unique_wallets_per_bundle_avg": round(sum(wallet_counts) / len(wallet_counts), 6) if wallet_counts else None,
            "bundle_timing_from_liquidity_add_min": round(min(bundle_offsets_min), 6) if bundle_offsets_min else None,
            "bundle_success_rate": round(sum(success_values) / len(success_values), 6) if success_values else None,
            "bundle_composition_dominant": _classify_composition(records),
            "bundle_tip_efficiency": _compute_tip_efficiency(records, bundle_size_value),
            "bundle_failure_retry_pattern": _compute_retry_pattern(records),
            "cross_block_bundle_correlation": _compute_cross_block_correlation(records),
            "bundle_metric_origin": REAL_EVIDENCE_ORIGIN,
        }
    )
    payload.update(_clustering_metrics(pair, records))
    payload["bundle_evidence_confidence"] = _compute_confidence(summary, bundle_count, records)
    payload["bundle_enrichment_status"] = "ok"
    payload["bundle_evidence_status"] = normalized_evidence.get("bundle_evidence_status") or "ok"

    log_info(
        "bundle_evidence_completed",
        token_address=str(pair.get("token_address") or ""),
        pair_address=str(pair.get("pair_address") or pair.get("pairAddress") or ""),
        source=payload.get("bundle_evidence_source"),
        bundle_count=bundle_count,
        confidence=payload.get("bundle_evidence_confidence"),
    )
    return payload
