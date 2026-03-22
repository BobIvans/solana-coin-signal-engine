"""Helpers for sanitizing common upstream funding sources.

Safe-default policy: common exchange / aggregator / bridge/system funders are
not treated as strong manipulation evidence by default.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

DEFAULT_FUNDER_IGNORELIST: set[str] = {
    "11111111111111111111111111111111",
    "binance",
    "coinbase",
    "bybit",
    "okx",
    "kraken",
    "kucoin",
    "mexc",
    "gate",
    "gateio",
    "bitget",
    "changenow",
    "fixedfloat",
    "simpleswap",
    "jupiter",
    "wormhole",
    "portal",
    "allbridge",
    "debridge",
}

_FUNDER_CLASS_KEYWORDS: dict[str, tuple[str, ...]] = {
    "trusted_exchange": (
        "binance",
        "coinbase",
        "bybit",
        "okx",
        "kraken",
        "kucoin",
        "mexc",
        "gate",
        "bitget",
        "htx",
        "huobi",
    ),
    "aggregator": (
        "changenow",
        "fixedfloat",
        "simpleswap",
        "jupiter",
        "aggregator",
        "swap",
    ),
    "bridge_or_router": (
        "wormhole",
        "portal",
        "allbridge",
        "debridge",
        "router",
        "bridge",
        "system",
    ),
}


def normalize_funder(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _normalize_compare(value: Any) -> str:
    text = normalize_funder(value)
    return (text or "").strip().lower()


def load_funder_ignorelist(path: str | Path | None = None) -> set[str]:
    ignored = set(DEFAULT_FUNDER_IGNORELIST)
    if not path:
        return {item.lower() for item in ignored}
    file_path = Path(path)
    if not file_path.exists():
        return {item.lower() for item in ignored}
    try:
        payload = json.loads(file_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {item.lower() for item in ignored}

    values: list[Any]
    if isinstance(payload, dict):
        values = list(payload.get("funders") or payload.get("ignorelist") or payload.values())
    elif isinstance(payload, list):
        values = payload
    else:
        values = []
    for item in values:
        text = normalize_funder(item)
        if text:
            ignored.add(text)
    return {item.lower() for item in ignored}


def classify_funder(
    funder: str | None,
    *,
    ignored_funders: Iterable[str] | None = None,
    sanitize_common_sources: bool = True,
) -> str:
    if not sanitize_common_sources:
        return "unknown"
    normalized = _normalize_compare(funder)
    if not normalized:
        return "unknown"
    ignored = {str(item).strip().lower() for item in (ignored_funders or []) if str(item).strip()}
    if normalized in ignored:
        for funder_class, keywords in _FUNDER_CLASS_KEYWORDS.items():
            if any(keyword in normalized for keyword in keywords):
                return funder_class
        return "trusted_exchange" if normalized == "11111111111111111111111111111111" else "bridge_or_router"
    for funder_class, keywords in _FUNDER_CLASS_KEYWORDS.items():
        if any(keyword in normalized for keyword in keywords):
            return funder_class
    return "unknown"


def sanitize_funder_set(
    funders: Iterable[str] | None,
    *,
    ignored_funders: Iterable[str] | None = None,
    sanitize_common_sources: bool = True,
) -> dict[str, Any]:
    sanitized: set[str] = set()
    ignored: set[str] = set()
    classes: dict[str, str] = {}
    for raw in funders or []:
        funder = normalize_funder(raw)
        if not funder:
            continue
        funder_class = classify_funder(
            funder,
            ignored_funders=ignored_funders,
            sanitize_common_sources=sanitize_common_sources,
        )
        if funder_class == "unknown":
            sanitized.add(funder)
            classes[funder] = funder_class
        else:
            ignored.add(funder)
            classes[funder] = funder_class
    return {
        "sanitized_funders": sanitized,
        "ignored_funders": ignored,
        "funder_classes": classes,
        "funder_sanitization_applied": bool(ignored),
    }
