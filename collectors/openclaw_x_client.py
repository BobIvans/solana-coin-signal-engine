"""OpenClaw-backed X/Twitter query fetcher with fail-open degraded behavior."""

from __future__ import annotations

import json
import random
import shutil
import subprocess
import threading
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from config.settings import load_settings
from src.promotion.cooldowns import normalize_x_error_type, register_x_error
from utils.cache import cache_get, cache_set
from utils.clock import utc_now_iso
from utils.io import append_jsonl

_GLOBAL_SEMAPHORE = threading.Semaphore(2)



def classify_x_error(exc: Exception | dict[str, Any] | str) -> str:
    text = str(exc).lower()
    if isinstance(exc, dict):
        text = f"{exc.get('error_code', '')} {exc.get('error_detail', '')}".lower()

    if "captcha" in text:
        return "captcha"
    if "login" in text or "auth" in text or "session" in text:
        return "login_required"
    if "timeout" in text:
        return "timeout"
    if "blocked" in text or "soft-ban" in text or "soft ban" in text or "429" in text or "rate limit" in text:
        return "soft_ban"
    return "error"



def _event(event_path: str, event: str, payload: dict[str, Any]) -> None:
    append_jsonl(event_path, {"ts": utc_now_iso(), "event": event, **payload})



def _cache_ttl_for_status(settings, status: str) -> int:
    status = normalize_x_error_type(status)
    if status == "login_required":
        return 60
    if status in {"captcha", "timeout", "soft_ban", "degraded", "error"}:
        return 90
    return settings.OPENCLAW_X_CACHE_TTL_SEC



def _register_cooldown(snapshot: dict[str, Any], *, state: dict | None, config: dict | None) -> None:
    if state is None or not isinstance(config, dict):
        return
    error_code = normalize_x_error_type(str(snapshot.get("error_code") or snapshot.get("x_status") or ""))
    if error_code in {"captcha", "timeout", "soft_ban"}:
        event = register_x_error(error_code, state, config)
        if event:
            snapshot["cooldown_event"] = event



def fetch_single_query(query_obj: dict[str, Any]) -> dict[str, Any]:
    settings = load_settings()
    token_address = str(query_obj.get("token_address", "") or "")
    query = str(query_obj.get("query", "") or "")
    query_type = str(query_obj.get("query_type", "unknown") or "unknown")
    normalized_query = str(query_obj.get("normalized_query", "") or "")
    events_path = str(query_obj.get("events_path", settings.PROCESSED_DATA_DIR / "x_validation_events.jsonl"))

    cache_key = f"x:{token_address}:{normalized_query}"
    cached = cache_get("x", cache_key)
    if cached is not None:
        _event(events_path, "x_query_cache_hit", {"token_address": token_address, "query_type": query_type})
        return {**cached, "cache_hit": True}

    _event(events_path, "x_query_started", {"token_address": token_address, "query_type": query_type})

    openclaw_path = shutil.which("openclaw")
    if not openclaw_path or not settings.LOCAL_OPENCLAW_ONLY:
        snapshot = {
            "token_address": token_address,
            "query": query,
            "query_type": query_type,
            "fetched_at": utc_now_iso(),
            "x_status": "degraded",
            "page_url": "",
            "posts_visible": 0,
            "authors_visible": [],
            "cards": [],
            "error_code": "openclaw_unavailable",
            "error_detail": "openclaw cli not found or LOCAL_OPENCLAW_ONLY=false",
            "cache_hit": False,
        }
        cache_set("x", cache_key, snapshot, ttl_sec=_cache_ttl_for_status(settings, snapshot["x_status"]))
        _event(events_path, "x_query_failed", {"token_address": token_address, "query_type": query_type, "error_code": "openclaw_unavailable", "attempt": 1})
        return snapshot

    encoded_query = urllib.parse.quote(query)
    page_url = f"https://x.com/search?q={encoded_query}&src=typed_query&f=live"
    cmd = [
        openclaw_path,
        "search",
        "--provider",
        "x",
        "--query",
        query,
        "--profile",
        settings.OPENCLAW_BROWSER_PROFILE,
        "--target",
        settings.OPENCLAW_BROWSER_TARGET,
    ]

    try:
        timeout_sec = max(1, int(settings.OPENCLAW_X_PAGE_TIMEOUT_MS / 1000) + 2)
        result = subprocess.run(cmd, check=False, capture_output=True, text=True, timeout=timeout_sec)

        if result.returncode != 0:
            error_code = classify_x_error(result.stderr or result.stdout)
            snapshot = {
                "token_address": token_address,
                "query": query,
                "query_type": query_type,
                "fetched_at": utc_now_iso(),
                "x_status": error_code,
                "page_url": page_url,
                "posts_visible": 0,
                "authors_visible": [],
                "cards": [],
                "error_code": error_code,
                "error_detail": (result.stderr or result.stdout).strip()[:300],
                "cache_hit": False,
            }
            _event(events_path, "x_query_failed", {"token_address": token_address, "query_type": query_type, "error_code": error_code, "attempt": 1})
        else:
            cards: list[dict[str, Any]] = []
            try:
                payload = json.loads(result.stdout) if result.stdout.strip().startswith("{") else {}
                cards = list(payload.get("cards", []))
            except json.JSONDecodeError:
                cards = []

            authors = sorted({str(card.get("author_handle", "") or "") for card in cards if card.get("author_handle")})
            snapshot = {
                "token_address": token_address,
                "query": query,
                "query_type": query_type,
                "fetched_at": utc_now_iso(),
                "x_status": "ok" if cards else "empty",
                "page_url": page_url,
                "posts_visible": len(cards),
                "authors_visible": authors,
                "cards": cards[: settings.OPENCLAW_X_MAX_POSTS_PER_QUERY],
                "error_code": None,
                "error_detail": None,
                "cache_hit": False,
            }
            _event(events_path, "x_query_succeeded", {"token_address": token_address, "query_type": query_type, "posts_visible": snapshot["posts_visible"]})
    except Exception as exc:  # noqa: BLE001
        error_code = classify_x_error(exc)
        snapshot = {
            "token_address": token_address,
            "query": query,
            "query_type": query_type,
            "fetched_at": utc_now_iso(),
            "x_status": error_code,
            "page_url": page_url,
            "posts_visible": 0,
            "authors_visible": [],
            "cards": [],
            "error_code": error_code,
            "error_detail": str(exc)[:300],
            "cache_hit": False,
        }
        _event(events_path, "x_query_failed", {"token_address": token_address, "query_type": query_type, "error_code": error_code, "attempt": 1})

    cache_set("x", cache_key, snapshot, ttl_sec=_cache_ttl_for_status(settings, snapshot.get("x_status", "error")))
    return snapshot



def _safe_failed_snapshot(token_address: str, query_obj: dict[str, Any], exc: Exception) -> dict[str, Any]:
    error_code = classify_x_error(exc)
    return {
        "token_address": token_address,
        "query": str(query_obj.get("query") or ""),
        "query_type": str(query_obj.get("query_type") or "unknown"),
        "fetched_at": utc_now_iso(),
        "x_status": error_code,
        "page_url": "",
        "posts_visible": 0,
        "authors_visible": [],
        "cards": [],
        "error_code": error_code,
        "error_detail": str(exc)[:300],
        "cache_hit": False,
    }



def fetch_x_snapshots(token: dict[str, Any], *, state: dict | None = None, config: dict | None = None) -> list[dict[str, Any]]:
    from collectors.x_query_builder import build_queries

    settings = load_settings()
    queries = build_queries(token)[: settings.OPENCLAW_X_QUERY_MAX]
    token_address = str(token.get("token_address", "") or "")
    token_queries = [
        {**q, "token_address": token_address, "events_path": str(settings.PROCESSED_DATA_DIR / "x_validation_events.jsonl")}
        for q in queries
    ]

    operational_state = state if state is not None else token.get("promotion_state")
    operational_config = config if config is not None else token.get("promotion_config")

    max_workers = max(1, int(settings.OPENCLAW_X_TOKEN_MAX_CONCURRENCY or 1))
    snapshots: list[dict[str, Any] | None] = [None] * len(token_queries)

    def _worker(index: int, query_obj: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        with _GLOBAL_SEMAPHORE:
            time.sleep(random.uniform(0.05, 0.2))
            return index, fetch_single_query(query_obj)

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(_worker, index, query_obj) for index, query_obj in enumerate(token_queries)]
        for future in futures:
            try:
                index, snapshot = future.result()
            except Exception as exc:  # noqa: BLE001
                index = 0
                query_obj = token_queries[0] if token_queries else {"query_type": "unknown", "query": ""}
                snapshot = _safe_failed_snapshot(token_address, query_obj, exc)
            _register_cooldown(snapshot, state=operational_state if isinstance(operational_state, dict) else None, config=operational_config if isinstance(operational_config, dict) else None)
            if 0 <= index < len(snapshots):
                snapshots[index] = snapshot

    return [snapshot for snapshot in snapshots if isinstance(snapshot, dict)]
