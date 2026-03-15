"""Smoke runner for X-validation: fail-open with degraded output."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from analytics.x_snapshot_parser import aggregate_token_snapshots
from analytics.x_validation_score import score_x_validation
from collectors.openclaw_x_client import fetch_x_snapshots
from config.settings import load_settings
from utils.clock import utc_now_iso
from utils.io import append_jsonl, read_json, write_json


ALLOWED_STATUSES = {"ok", "empty", "degraded", "captcha", "login_required", "timeout", "blocked", "error"}


def _validate_record(record: dict) -> None:
    required = {"token_address", "x_status", "x_validation_score", "x_validation_delta", "contract_version"}
    missing = sorted(required - set(record.keys()))
    if missing:
        raise ValueError(f"x-validation schema violation: missing keys {missing}")
    if record["x_status"] not in ALLOWED_STATUSES:
        raise ValueError(f"x-validation schema violation: invalid x_status={record['x_status']}")
    score = float(record["x_validation_score"])
    if score < 0 or score > 100:
        raise ValueError("x-validation schema violation: score out of range")


def _load_shortlist(path: Path) -> list[dict]:
    payload = read_json(path, default={}) or {}
    shortlist = list(payload.get("shortlist", []))
    return shortlist


def run(shortlist_path: Path) -> dict:
    settings = load_settings()
    events_path = settings.PROCESSED_DATA_DIR / "x_validation_events.jsonl"
    append_jsonl(events_path, {"ts": utc_now_iso(), "event": "x_validation_started"})

    shortlist = _load_shortlist(shortlist_path)
    tokens = shortlist[: settings.X_MAX_TOKENS_PER_CYCLE]

    output_tokens: list[dict] = []
    for token in tokens:
        token_address = str(token.get("token_address", "") or "")
        if not token_address:
            append_jsonl(events_path, {
                "ts": utc_now_iso(),
                "event": "x_query_failed",
                "token_address": "",
                "error_code": "invalid_input",
                "error_detail": "missing token_address",
            })
            continue

        snapshots = fetch_x_snapshots(token)
        metrics = aggregate_token_snapshots(token, snapshots)
        scored = score_x_validation(metrics, settings)

        if scored.get("x_status") == "degraded":
            append_jsonl(events_path, {
                "ts": utc_now_iso(),
                "event": "x_validation_degraded",
                "token_address": token_address,
                "reason": "all_queries_failed_or_blocked",
            })

        _validate_record(scored)
        output_tokens.append(scored)

    payload = {
        "contract_version": settings.X_VALIDATION_CONTRACT_VERSION,
        "generated_at": utc_now_iso(),
        "tokens": output_tokens,
    }

    write_json(settings.PROCESSED_DATA_DIR / "x_validated.json", payload)
    append_jsonl(events_path, {"ts": utc_now_iso(), "event": "x_validation_completed", "token_count": len(output_tokens)})
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--shortlist", default="data/processed/shortlist.json")
    args = parser.parse_args()

    payload = run(Path(args.shortlist))
    print(json.dumps(payload, sort_keys=True, ensure_ascii=False))

    statuses = {token.get("x_status") for token in payload.get("tokens", [])}
    if statuses.issubset({"ok", "degraded", "empty"}):
        return 0
    return 0 if not statuses else 0


if __name__ == "__main__":
    raise SystemExit(main())
