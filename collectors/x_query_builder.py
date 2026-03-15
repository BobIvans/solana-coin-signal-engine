"""Build and normalize limited X/Twitter search queries for token validation."""

from __future__ import annotations

import re
from typing import Any

from config.settings import load_settings

_MINT_RE = re.compile(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$")
_SAFE_TEXT_RE = re.compile(r"[^\w\s\-$]")
_MULTI_SPACE_RE = re.compile(r"\s+")


def _clean_text(value: str) -> str:
    cleaned = _SAFE_TEXT_RE.sub(" ", value or "")
    cleaned = _MULTI_SPACE_RE.sub(" ", cleaned).strip()
    return cleaned


def normalize_query(q: str) -> str:
    normalized = _MULTI_SPACE_RE.sub(" ", (q or "").strip().lower())
    return normalized


def _valid_mint(value: str) -> bool:
    return bool(_MINT_RE.match((value or "").strip()))


def build_queries(token: dict[str, Any]) -> list[dict[str, str]]:
    settings = load_settings()

    symbol_raw = str(token.get("symbol", "") or "")
    name_raw = str(token.get("name", "") or "")
    token_address = str(token.get("token_address", "") or "")

    symbol = _clean_text(symbol_raw).upper()
    name = _clean_text(name_raw)

    candidates: list[tuple[str, str]] = []
    if symbol:
        candidates.append((f"${symbol}", "cashtag"))
    if symbol and name:
        candidates.append((f'"{symbol}" "{name}"', "symbol_name"))
    if _valid_mint(token_address):
        candidates.append((f'"{token_address}"', "contract"))
    if name:
        candidates.append((f'"{name}" solana', "exact_name"))

    seen: set[str] = set()
    built: list[dict[str, str]] = []
    for query, query_type in candidates:
        n_query = normalize_query(query)
        if not n_query or n_query in seen:
            continue
        seen.add(n_query)
        built.append({"query": query, "query_type": query_type, "normalized_query": n_query})
        if len(built) >= settings.OPENCLAW_X_QUERY_MAX:
            break
    return built
