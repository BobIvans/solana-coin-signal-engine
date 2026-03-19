"""Lightweight first-window bundle enrichment for discovery candidates."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from analytics.wallet_clustering import compute_wallet_clustering_metrics
from collectors.helius_client import HeliusClient
from utils.bundle_contract_fields import BUNDLE_CONTRACT_FIELDS
from utils.logger import log_warning
from utils.rate_limit import acquire

MVP_BUNDLE_FIELDS = [
    "bundle_count_first_60s",
    "bundle_size_value",
    "unique_wallets_per_bundle_avg",
    "bundle_timing_from_liquidity_add_min",
    "bundle_success_rate",
]


def _null_bundle_metrics() -> dict[str, Any]:
    return {field: None for field in MVP_BUNDLE_FIELDS}


def safe_null_bundle_metrics(
    *,
    status: str,
    warning: str | None = None,
) -> dict[str, Any]:
    payload = {
        **_null_bundle_metrics(),
        "bundle_enrichment_status": status,
        "bundle_enrichment_warning": warning,
    }
    for field in BUNDLE_CONTRACT_FIELDS:
        payload.setdefault(field, None)
    return payload


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
    for key in ("liquidity_added_at_ts", "pair_created_at_ts"):
        value = _coerce_int(pair.get(key))
        if value and value > 0:
            return value
    return None


def _extract_timestamp(tx: dict[str, Any]) -> int | None:
    for key in ("timestamp", "blockTime"):
        value = _coerce_int(tx.get(key))
        if value and value > 0:
            return value
    return None


def _extract_group_key(tx: dict[str, Any], timestamp: int) -> str:
    slot = _coerce_int(tx.get("slot"))
    if slot is not None and slot >= 0:
        return f"slot:{slot}"
    return f"ts:{timestamp}"


def _extract_wallets(tx: dict[str, Any]) -> list[str]:
    wallets: set[str] = set()
    for key in ("feePayer", "signer", "owner", "user"):
        value = str(tx.get(key) or "").strip()
        if value:
            wallets.add(value)

    for transfer in tx.get("nativeTransfers", []) if isinstance(tx.get("nativeTransfers"), list) else []:
        if not isinstance(transfer, dict):
            continue
        for key in ("fromUserAccount", "toUserAccount"):
            value = str(transfer.get(key) or "").strip()
            if value:
                wallets.add(value)

    for transfer in tx.get("tokenTransfers", []) if isinstance(tx.get("tokenTransfers"), list) else []:
        if not isinstance(transfer, dict):
            continue
        for key in ("fromUserAccount", "toUserAccount", "userAccount"):
            value = str(transfer.get(key) or "").strip()
            if value:
                wallets.add(value)

    return sorted(wallets)


def _extract_value(tx: dict[str, Any]) -> float | None:
    for key in ("bundle_value", "bundleValue", "swap_usd_value", "usd_value", "value_usd", "value"):
        value = _coerce_float(tx.get(key))
        if value is not None:
            return value

    native_transfers = tx.get("nativeTransfers")
    if not isinstance(native_transfers, list) or not native_transfers:
        return None

    lamports = 0
    for transfer in native_transfers:
        if not isinstance(transfer, dict):
            continue
        amount = _coerce_int(transfer.get("amount"))
        if amount:
            lamports += abs(amount)
    if lamports <= 0:
        return None
    return lamports / 1_000_000_000


def _extract_success(tx: dict[str, Any]) -> bool | None:
    for key in ("success", "isSuccess"):
        value = tx.get(key)
        if isinstance(value, bool):
            return value
    if tx.get("transactionError") in (None, "", False):
        return True
    return False


def _load_bundle_transactions(pair: dict[str, Any], settings: Any) -> tuple[list[dict[str, Any]], str | None]:
    inline = pair.get("bundle_transactions")
    if isinstance(inline, list):
        return [item for item in inline if isinstance(item, dict)], None

    if not getattr(settings, "BUNDLE_ENRICHMENT_ENABLED", True):
        return [], "bundle enrichment disabled"

    if not getattr(settings, "HELIUS_API_KEY", ""):
        return [], "helius api key missing"

    source_addr = str(pair.get("pair_address") or pair.get("token_address") or "").strip()
    if not source_addr:
        return [], "missing pair/token address for bundle lookup"

    acquire("helius")
    helius = HeliusClient(settings.HELIUS_API_KEY)
    txs = helius.get_transactions_by_address(source_addr, getattr(settings, "HELIUS_TX_ADDR_LIMIT", 40))
    if not txs and pair.get("pair_address"):
        txs = helius.get_transactions_by_address(str(pair.get("token_address") or ""), getattr(settings, "HELIUS_TX_ADDR_LIMIT", 40))
    return txs, None if txs else "no bundle transactions available"


def detect_bundle_metrics_for_pair(pair: dict[str, Any], now_ts: int, settings: Any) -> dict[str, Any]:
    """Infer first-window bundle metrics from available transaction data.

    This MVP uses a conservative heuristic: transactions in the first configured
    window are grouped by slot when present, otherwise by exact second. Only
    groups with at least 2 transactions are treated as inferred bundles.
    """

    if not getattr(settings, "BUNDLE_ENRICHMENT_ENABLED", True):
        return safe_null_bundle_metrics(status="disabled", warning="bundle enrichment disabled")

    anchor_ts = _extract_anchor_ts(pair)
    if anchor_ts is None:
        return safe_null_bundle_metrics(status="unavailable", warning="missing liquidity/pair creation anchor")

    if now_ts < anchor_ts:
        return safe_null_bundle_metrics(status="unavailable", warning="anchor timestamp is in the future")

    try:
        txs, source_warning = _load_bundle_transactions(pair, settings)
        if source_warning and not txs:
            return safe_null_bundle_metrics(status="unavailable", warning=source_warning)

        window_sec = max(int(getattr(settings, "BUNDLE_ENRICHMENT_WINDOW_SEC", 60) or 60), 1)
        window_end = anchor_ts + window_sec

        first_window = []
        for tx in txs:
            timestamp = _extract_timestamp(tx)
            if timestamp is None or timestamp < anchor_ts or timestamp > window_end:
                continue
            first_window.append(
                {
                    "timestamp": timestamp,
                    "group_key": _extract_group_key(tx, timestamp),
                    "wallets": _extract_wallets(tx),
                    "value": _extract_value(tx),
                    "success": _extract_success(tx),
                    "funder": str(tx.get("funder") or tx.get("funding_source") or tx.get("funded_by") or "").strip() or None,
                }
            )

        if not first_window:
            return safe_null_bundle_metrics(status="ok", warning="no first-window transactions found")

        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for tx in first_window:
            grouped[tx["group_key"]].append(tx)

        inferred_bundles = [group for group in grouped.values() if len(group) >= 2]
        if not inferred_bundles:
            return {
                **safe_null_bundle_metrics(status="ok", warning="no inferred bundles detected in first window"),
                "bundle_count_first_60s": 0,
            }

        bundle_count = len(inferred_bundles)
        wallet_counts: list[int] = []
        bundle_values: list[float] = []
        bundle_offsets_min: list[float] = []
        success_values: list[float] = []
        clustering_participants, participant_wallets, creator_wallet = _extract_clustering_participants(pair, first_window)
        clustering_metrics = compute_wallet_clustering_metrics(
            clustering_participants,
            creator_wallet=creator_wallet,
            participant_wallets=participant_wallets,
            settings=settings,
            persist_artifacts=True,
            artifact_scope={
                "token_address": str(pair.get("token_address") or ""),
                "pair_address": str(pair.get("pair_address") or ""),
            },
        )

        for bundle in inferred_bundles:
            wallets = {wallet for tx in bundle for wallet in tx["wallets"]}
            wallet_counts.append(len(wallets))

            values = [value for value in (tx["value"] for tx in bundle) if value is not None]
            if values:
                bundle_values.append(sum(values))

            timestamps = [int(tx["timestamp"]) for tx in bundle]
            bundle_offsets_min.append((min(timestamps) - anchor_ts) / 60.0)

            successes = [tx["success"] for tx in bundle if tx["success"] is not None]
            if successes:
                success_values.extend(1.0 if flag else 0.0 for flag in successes)

        return {
            **safe_null_bundle_metrics(status="ok"),
            "bundle_count_first_60s": bundle_count,
            "bundle_size_value": round(sum(bundle_values), 6) if bundle_values else None,
            "unique_wallets_per_bundle_avg": round(sum(wallet_counts) / len(wallet_counts), 6) if wallet_counts else None,
            "bundle_timing_from_liquidity_add_min": round(min(bundle_offsets_min), 6) if bundle_offsets_min else None,
            "bundle_success_rate": round(sum(success_values) / len(success_values), 6) if success_values else None,
            "bundle_enrichment_warning": source_warning,
            **clustering_metrics,
        }
    except Exception as exc:  # pragma: no cover - defensive fail-open
        log_warning(
            "bundle_enrichment_failed",
            token_address=str(pair.get("token_address") or ""),
            pair_address=str(pair.get("pair_address") or ""),
            error=str(exc),
        )
        return safe_null_bundle_metrics(status="failed", warning=str(exc))




def _creator_wallet_from_payload(payload: dict[str, Any]) -> str | None:
    for key in ("creator_wallet", "deployer_wallet", "mint_authority", "update_authority", "dev_wallet_est"):
        value = str(payload.get(key) or "").strip()
        if value:
            return value
    return None


def _extract_clustering_participants(
    payload: dict[str, Any],
    first_window: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[str], str | None]:
    participants: dict[str, dict[str, Any]] = {}
    participant_wallets: set[str] = set()

    def ensure(wallet: str) -> dict[str, Any]:
        return participants.setdefault(wallet, {"wallet": wallet})

    def merge(wallet: str, **extra: Any) -> None:
        participant_wallets.add(wallet)
        bucket = ensure(wallet)
        for key, value in extra.items():
            if value in (None, "", [], {}):
                continue
            if isinstance(value, list):
                merged = list(bucket.get(key) or [])
                for item in value:
                    if item not in merged:
                        merged.append(item)
                bucket[key] = merged
            else:
                bucket[key] = value

    for tx in first_window:
        group_key = str(tx.get("group_key") or "").strip() or None
        tx_funder = str(tx.get("funder") or "").strip() or None
        for wallet in tx.get("wallets", []):
            wallet_value = str(wallet).strip()
            if not wallet_value:
                continue
            merge(wallet_value, group_id=[group_key] if group_key else None, funder=tx_funder)

    creator_wallet = _creator_wallet_from_payload(payload)

    list_keys = (
        "early_buyers",
        "early_participants",
        "bundle_participants",
        "bundle_wallets",
        "first_window_buyers",
        "first_window_participants",
        "buyers_first_60s",
    )
    for key in list_keys:
        values = payload.get(key)
        if not isinstance(values, list):
            continue
        for item in values:
            if isinstance(item, dict):
                wallet = str(
                    item.get("wallet")
                    or item.get("wallet_address")
                    or item.get("address")
                    or item.get("owner")
                    or item.get("signer")
                    or item.get("actor")
                    or ""
                ).strip()
                if not wallet:
                    continue
                merge(
                    wallet,
                    group_id=[item.get("group_id") or item.get("group_key") or item.get("bundle_id")] if (item.get("group_id") or item.get("group_key") or item.get("bundle_id")) else None,
                    funder=item.get("funder") or item.get("funding_source") or item.get("funded_by"),
                    launch_id=[item.get("launch_id") or item.get("launch_group") or item.get("same_launch_tag")] if (item.get("launch_id") or item.get("launch_group") or item.get("same_launch_tag")) else None,
                    creator_linked=item.get("creator_linked") or item.get("creator_overlap") or item.get("dev_linked"),
                )
            elif isinstance(item, str) and item.strip():
                merge(item.strip())

    advanced_records = _extract_advanced_bundle_records(payload)
    for record in advanced_records:
        wallet = _advanced_normalized_actor(record)
        if not wallet:
            continue
        merge(
            wallet,
            group_id=[str(_advanced_record_block(record))] if _advanced_record_block(record) is not None else None,
            funder=_advanced_first_present(record, ("funder", "funding_source", "source_wallet", "funded_by")),
            launch_id=[_advanced_first_present(record, ("launch_id", "launch_group", "same_launch_tag"))] if _advanced_first_present(record, ("launch_id", "launch_group", "same_launch_tag")) is not None else None,
            creator_linked=record.get("creator_linked") or record.get("creator_overlap") or record.get("dev_linked"),
        )

    creator_funder = str(payload.get("creator_funder") or payload.get("creator_funding_source") or "").strip() or None
    if creator_wallet and (creator_funder or creator_wallet in participants):
        merge(creator_wallet, funder=creator_funder, creator_linked=True)

    return sorted(participants.values(), key=lambda item: str(item.get("wallet") or "")), sorted(participant_wallets), creator_wallet

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


def _iter_advanced_bundle_lists(payload: dict[str, Any] | None) -> list[dict[str, Any]]:
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
            extracted.extend(_iter_advanced_bundle_lists(nested))

    return extracted


def _extract_advanced_bundle_records(*payloads: dict[str, Any] | None) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for payload in payloads:
        records.extend(_iter_advanced_bundle_lists(payload))
    return records


def _advanced_as_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _advanced_as_int(value: Any) -> int | None:
    numeric = _advanced_as_float(value)
    if numeric is None:
        return None
    return int(numeric)


def _advanced_first_present(record: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        if key in record and record.get(key) not in (None, ""):
            return record.get(key)
    return None


def _advanced_normalized_actor(record: dict[str, Any]) -> str | None:
    actor = _advanced_first_present(record, _ACTOR_KEYS)
    if actor is None:
        return None
    value = str(actor).strip()
    return value or None


def _advanced_record_ts(record: dict[str, Any]) -> int | None:
    return _advanced_as_int(_advanced_first_present(record, _TS_KEYS))


def _advanced_record_block(record: dict[str, Any]) -> int | None:
    return _advanced_as_int(_advanced_first_present(record, _BLOCK_KEYS))


def _advanced_record_failed(record: dict[str, Any]) -> bool:
    explicit = record.get("success")
    if explicit is not None:
        return not bool(explicit)

    status_value = _advanced_first_present(record, _STATUS_KEYS)
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


def _advanced_infer_side(record: dict[str, Any]) -> str | None:
    for key in _SIDE_KEYS:
        raw_value = record.get(key)
        if raw_value in (None, ""):
            continue
        label = str(raw_value).strip().lower()
        if any(token in label for token in ("buy", "accumulate", "long")):
            return "buy"
        if any(token in label for token in ("sell", "dump", "short")):
            return "sell"

    token_delta = _advanced_as_float(record.get("token_delta"))
    if token_delta is not None:
        if token_delta > 0:
            return "buy"
        if token_delta < 0:
            return "sell"

    base_delta = _advanced_as_float(record.get("base_delta"))
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
        side = _advanced_infer_side(record)
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

    external_value = _advanced_as_float(bundle_size_value)
    if external_value is not None and external_value > 0:
        total_value += external_value
        value_seen = True

    for record in bundle_records:
        tip_value = _advanced_as_float(_advanced_first_present(record, _TIP_KEYS))
        if tip_value is not None:
            total_tip += tip_value
            tip_seen = True

        record_value = _advanced_as_float(_advanced_first_present(record, _VALUE_KEYS))
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
        actor = _advanced_normalized_actor(record)
        if actor is None:
            continue
        failed = _advanced_record_failed(record)
        if failed or record.get("success") is not None or _advanced_first_present(record, _STATUS_KEYS) is not None:
            evidence_seen = True
        attempts_by_actor.setdefault(actor, []).append((_advanced_record_ts(record), failed))

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
        actor = _advanced_normalized_actor(record)
        block = _advanced_record_block(record)
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
    bundle_records = _extract_advanced_bundle_records(candidate, raw_pair)

    return {
        "bundle_composition_dominant": classify_bundle_composition(bundle_records),
        "bundle_tip_efficiency": compute_bundle_tip_efficiency(bundle_records, candidate.get("bundle_size_value")),
        "bundle_failure_retry_pattern": detect_bundle_failure_retry_pattern(bundle_records),
        "cross_block_bundle_correlation": compute_cross_block_bundle_correlation(bundle_records),
    }
