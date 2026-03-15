"""Smoke runner for PR-5 rug safety engine."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from analytics.authority_checks import check_authorities
from analytics.concentration_checks import check_concentration
from analytics.dev_risk_checks import check_dev_risk
from analytics.lp_checks import check_lp_state
from analytics.rug_engine import assess_rug_risk
from config.settings import load_settings
from utils.clock import utc_now_iso
from utils.io import append_jsonl, read_json, write_json


def _validate_record(record: dict) -> None:
    required = {
        "token_address",
        "mint_revoked",
        "freeze_revoked",
        "lp_burn_confirmed",
        "lp_locked_flag",
        "top1_holder_share",
        "top20_holder_share",
        "dev_sell_pressure_5m",
        "rug_score",
        "rug_verdict",
    }
    missing = sorted(required - set(record.keys()))
    if missing:
        raise ValueError(f"rug schema violation: missing keys {missing}")


def run(enriched_path: Path, token_override: str | None = None) -> dict:
    settings = load_settings()
    enriched = read_json(enriched_path, default={}) or {}
    tokens = enriched.get("tokens", []) if isinstance(enriched, dict) else []
    if token_override:
        tokens = [item for item in tokens if str(item.get("token_address") or "") == token_override]

    events_path = settings.PROCESSED_DATA_DIR / "rug_events.jsonl"
    out: list[dict] = []

    for token in tokens:
        token_address = str(token.get("token_address") or "")
        append_jsonl(events_path, {"ts": utc_now_iso(), "event": "rug_assessment_started", "token_address": token_address})

        authority = check_authorities(token)
        append_jsonl(events_path, {"ts": utc_now_iso(), "event": "authority_checks_completed", "token_address": token_address, **authority})

        lp = check_lp_state(token, settings)
        lp_event = {"ts": utc_now_iso(), "event": "lp_checks_completed", "token_address": token_address, "lp_burn_confirmed": lp["lp_burn_confirmed"], "lp_locked_flag": lp["lp_locked_flag"]}
        if lp.get("lp_warnings"):
            lp_event["warning"] = "; ".join(lp["lp_warnings"])
        append_jsonl(events_path, lp_event)

        concentration = check_concentration(token, settings)
        append_jsonl(events_path, {"ts": utc_now_iso(), "event": "concentration_checks_completed", "token_address": token_address, **concentration})

        dev = check_dev_risk(token, settings)
        append_jsonl(events_path, {"ts": utc_now_iso(), "event": "dev_risk_checks_completed", "token_address": token_address, **dev})

        assessed = assess_rug_risk(token, settings)
        if assessed["rug_status"] == "partial":
            append_jsonl(events_path, {"ts": utc_now_iso(), "event": "rug_assessment_partial", "token_address": token_address, "rug_verdict": assessed["rug_verdict"]})

        append_jsonl(events_path, {"ts": utc_now_iso(), "event": "rug_assessment_completed", "token_address": token_address, "rug_verdict": assessed["rug_verdict"], "rug_score": assessed["rug_score"]})
        _validate_record(assessed)
        out.append(assessed)

    payload = {"contract_version": "rug_safety_v1", "generated_at": utc_now_iso(), "tokens": out}
    write_json(settings.PROCESSED_DATA_DIR / "rug_assessed_tokens.json", payload)
    write_json(settings.PROCESSED_DATA_DIR / "rug_assessed.smoke.json", payload)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--enriched", default="data/processed/enriched_tokens.json")
    parser.add_argument("--token", default=None)
    args = parser.parse_args()

    payload = run(Path(args.enriched), token_override=args.token)
    print(json.dumps(payload.get("tokens", [{}])[0] if payload.get("tokens") else {}, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
