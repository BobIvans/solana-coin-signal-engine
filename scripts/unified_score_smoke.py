from __future__ import annotations

from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scoring.unified_score import main as _pr_sw5_main

if __name__ == "__main__":
    raise SystemExit(_pr_sw5_main())

"""Smoke runner for unified scoring contract (PR-6)."""


import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from analytics.unified_score import score_tokens
from config.settings import load_settings
from utils.clock import utc_now_iso
from utils.io import append_jsonl, read_json


def _extract_tokens(payload: dict | list | None) -> list[dict]:
    if payload is None:
        return []
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        raw = payload.get("tokens", [])
        return [item for item in raw if isinstance(item, dict)] if isinstance(raw, list) else []
    return []


def _merge_by_address(*datasets: list[dict]) -> list[dict]:
    merged: dict[str, dict] = {}
    for data in datasets:
        for token in data:
            addr = str(token.get("token_address") or "")
            if not addr:
                continue
            merged.setdefault(addr, {"token_address": addr})
            merged[addr].update(token)
    return [merged[key] for key in sorted(merged.keys())]


def _validate_scored(record: dict) -> None:
    required = {
        "token_address",
        "onchain_core",
        "early_signal_bonus",
        "x_validation_bonus",
        "rug_penalty",
        "spam_penalty",
        "confidence_adjustment",
        "final_score",
        "regime_candidate",
    }
    missing = sorted(required - set(record.keys()))
    if missing:
        raise ValueError(f"schema violation: missing {missing}")
    if record["regime_candidate"] not in {"IGNORE", "WATCHLIST", "ENTRY_CANDIDATE"}:
        raise ValueError("impossible routing state")


def run(shortlist: Path, x_validated: Path, enriched: Path, rug_assessed: Path) -> dict:
    settings = load_settings()
    tokens = _merge_by_address(
        _extract_tokens(read_json(shortlist, default={})),
        _extract_tokens(read_json(x_validated, default={})),
        _extract_tokens(read_json(enriched, default={})),
        _extract_tokens(read_json(rug_assessed, default={})),
    )

    events_path = settings.PROCESSED_DATA_DIR / "score_events.jsonl"
    append_jsonl(events_path, {"ts": utc_now_iso(), "event": "score_started", "tokens": len(tokens)})

    scored = []
    for token in tokens:
        append_jsonl(events_path, {"ts": utc_now_iso(), "event": "score_started", "token_address": token.get("token_address", "")})
        item = score_tokens([token], settings)[0]
        append_jsonl(
            events_path,
            {
                "ts": utc_now_iso(),
                "event": "score_components_computed",
                "token_address": item["token_address"],
                "onchain_core": item["onchain_core"],
                "early_signal_bonus": item["early_signal_bonus"],
                "x_validation_bonus": item["x_validation_bonus"],
                "rug_penalty": item["rug_penalty"],
                "spam_penalty": item["spam_penalty"],
                "confidence_adjustment": item["confidence_adjustment"],
            },
        )
        append_jsonl(events_path, {"ts": utc_now_iso(), "event": "score_routed", "token_address": item["token_address"], "regime_candidate": item["regime_candidate"], "final_score": item["final_score"]})
        if "hard_rug_override" in item.get("score_flags", []):
            append_jsonl(events_path, {"ts": utc_now_iso(), "event": "score_hard_override", "token_address": item["token_address"]})
        if any(w.startswith("entry_downgraded") for w in item.get("score_warnings", [])):
            append_jsonl(events_path, {"ts": utc_now_iso(), "event": "score_downgraded", "token_address": item["token_address"]})
        append_jsonl(events_path, {"ts": utc_now_iso(), "event": "score_completed", "token_address": item["token_address"]})
        _validate_scored(item)
        scored.append(item)

    payload = {"contract_version": settings.UNIFIED_SCORE_CONTRACT_VERSION, "generated_at": utc_now_iso(), "tokens": scored}
    out = settings.PROCESSED_DATA_DIR / "scored_tokens.json"
    smoke_out = settings.PROCESSED_DATA_DIR / "scored_tokens.smoke.json"
    out.write_text(json.dumps(payload, sort_keys=True, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    smoke_out.write_text(json.dumps(payload, sort_keys=True, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--shortlist", default="data/processed/shortlist.json")
    parser.add_argument("--x-validated", default="data/processed/x_validated.json")
    parser.add_argument("--enriched", default="data/processed/enriched_tokens.json")
    parser.add_argument("--rug-assessed", default="data/processed/rug_assessed_tokens.json")
    args = parser.parse_args()

    payload = run(Path(args.shortlist), Path(args.x_validated), Path(args.enriched), Path(args.rug_assessed))
    print(json.dumps(payload.get("tokens", [{}])[0] if payload.get("tokens") else {}, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
