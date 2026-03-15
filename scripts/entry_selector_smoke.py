"""Smoke runner for PR-7 entry selector."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config.settings import load_settings
from trading.entry_logic import decide_entries
from utils.clock import utc_now_iso
from utils.io import append_jsonl, read_json, write_json

_REQUIRED_KEYS = {
    "token_address",
    "entry_decision",
    "entry_confidence",
    "recommended_position_pct",
    "entry_reason",
    "entry_snapshot",
}


def _validate_record(record: dict) -> None:
    missing = sorted(_REQUIRED_KEYS - set(record.keys()))
    if missing:
        raise ValueError(f"entry schema violation: missing keys {missing}")
    if record.get("entry_decision") not in {"SCALP", "TREND", "IGNORE"}:
        raise ValueError("entry schema violation: bad entry_decision")


def run(scored_path: Path, token_override: str | None = None) -> dict:
    settings = load_settings()
    raw = read_json(scored_path, default={}) or {}
    tokens = raw.get("tokens", raw if isinstance(raw, list) else [])

    if token_override:
        tokens = [item for item in tokens if str(item.get("token_address") or "") == token_override]

    events_path = settings.PROCESSED_DATA_DIR / "entry_events.jsonl"
    append_jsonl(events_path, {"ts": utc_now_iso(), "event": "entry_selection_started", "count": len(tokens)})

    results = []
    for token in tokens:
        token_address = str(token.get("token_address") or "")
        append_jsonl(events_path, {"ts": utc_now_iso(), "event": "entry_regime_checked", "token_address": token_address})
        decision = decide_entries([token], settings)[0]
        _validate_record(decision)

        if decision["recommended_position_pct"] < decision["entry_confidence"] and decision["entry_decision"] != "IGNORE":
            append_jsonl(events_path, {"ts": utc_now_iso(), "event": "entry_size_reduced", "token_address": token_address, "entry_flags": decision.get("entry_flags", [])})

        event_type = "entry_decision_made" if decision["entry_decision"] != "IGNORE" else "entry_ignored"
        append_jsonl(
            events_path,
            {
                "ts": utc_now_iso(),
                "event": event_type,
                "token_address": token_address,
                "entry_decision": decision["entry_decision"],
                "entry_confidence": decision["entry_confidence"],
                "recommended_position_pct": decision["recommended_position_pct"],
                "entry_reason": decision["entry_reason"],
            },
        )
        results.append(decision)

    payload = {"contract_version": settings.ENTRY_CONTRACT_VERSION, "generated_at": utc_now_iso(), "tokens": results}
    write_json(settings.PROCESSED_DATA_DIR / "entry_candidates.json", payload)
    write_json(settings.PROCESSED_DATA_DIR / "entry_candidates.smoke.json", payload)

    append_jsonl(events_path, {"ts": utc_now_iso(), "event": "entry_completed", "count": len(results)})
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scored", default="data/processed/scored_tokens.json")
    parser.add_argument("--token", default=None)
    args = parser.parse_args()

    payload = run(Path(args.scored), token_override=args.token)
    print(json.dumps(payload.get("tokens", [{}])[0] if payload.get("tokens") else {}, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
