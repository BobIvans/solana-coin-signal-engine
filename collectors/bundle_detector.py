"""Lightweight first-window bundle enrichment for discovery candidates."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

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
        }
    except Exception as exc:  # pragma: no cover - defensive fail-open
        log_warning(
            "bundle_enrichment_failed",
            token_address=str(pair.get("token_address") or ""),
            pair_address=str(pair.get("pair_address") or ""),
            error=str(exc),
        )
        return safe_null_bundle_metrics(status="failed", warning=str(exc))
