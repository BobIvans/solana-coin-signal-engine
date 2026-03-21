from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from analytics.unified_score import score_token as analytics_score_token
from analytics.wallet_weighting import (
    DEFAULT_WALLET_WEIGHTING_MODE,
    WALLET_WEIGHTING_MODES,
    compute_wallet_weighting,
)
from config.settings import load_settings


def _as_float(value: Any, default: float = 0.0) -> float:
    if value is None:
        return default
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        text = value.strip().lower()
        if not text:
            return default
        if text in {"true", "yes", "y"}:
            return 1.0
        if text in {"false", "no", "n"}:
            return 0.0
        try:
            return float(text)
        except ValueError:
            return default
    return default


def _first_present(token: Mapping[str, Any], keys: Sequence[str], default: Any = None) -> Any:
    for key in keys:
        if key in token and token[key] is not None:
            return token[key]
    return default


def token_key(token: Mapping[str, Any], ordinal: int = 0) -> str:
    for key in (
        "token_address",
        "mint",
        "token_id",
        "id",
        "address",
        "pair_address",
        "symbol",
    ):
        value = token.get(key)
        if value:
            return str(value)
    return f"token_{ordinal:06d}"


def ensure_list(payload: Any) -> List[Dict[str, Any]]:
    if payload is None:
        return []
    if isinstance(payload, list):
        return [dict(item) for item in payload]
    if isinstance(payload, dict):
        if isinstance(payload.get("tokens"), list):
            return [dict(item) for item in payload["tokens"]]
        if isinstance(payload.get("items"), list):
            return [dict(item) for item in payload["items"]]
        return [
            dict(item)
            for _, item in sorted(payload.items(), key=lambda kv: str(kv[0]))
            if isinstance(item, Mapping)
        ]
    raise TypeError(f"Unsupported payload type: {type(payload)!r}")


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_jsonl(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, sort_keys=True) + "\n")


def merge_inputs(
    shortlist: Sequence[Mapping[str, Any]],
    x_validated: Sequence[Mapping[str, Any]],
    enriched: Sequence[Mapping[str, Any]],
    rug_assessed: Sequence[Mapping[str, Any]],
) -> List[Dict[str, Any]]:
    merged: Dict[str, Dict[str, Any]] = {}
    for dataset_name, dataset in (
        ("shortlist", shortlist),
        ("x_validated", x_validated),
        ("enriched", enriched),
        ("rug_assessed", rug_assessed),
    ):
        for ordinal, item in enumerate(dataset):
            key = token_key(item, ordinal)
            existing = merged.setdefault(key, {"token_key": key})
            existing.update(copy.deepcopy(dict(item)))
            sources = existing.setdefault("_source_presence", {})
            sources[dataset_name] = True
    return [merged[key] for key in sorted(merged)]


def _normalize_rug_verdict(value: Any) -> str | None:
    text = str(value or "").strip().lower()
    if text in {"pass", "safe", "ok"}:
        return "PASS"
    if text in {"warn", "warning", "watch", "caution"}:
        return "WATCH"
    if text in {"fail", "unsafe", "reject", "ignore"}:
        return "IGNORE"
    return None


def deterministic_event_timestamp(token: Mapping[str, Any]) -> str:
    for key in (
        "scored_at",
        "score_timestamp",
        "timestamp",
        "snapshot_ts",
        "snapshot_at",
        "as_of",
        "as_of_ts",
        "observed_at",
        "event_ts",
    ):
        value = token.get(key)
        if value:
            return str(value)
    return "1970-01-01T00:00:00Z"


def compute_wallet_adjustment(
    token: Mapping[str, Any],
    mode: str = DEFAULT_WALLET_WEIGHTING_MODE,
) -> Dict[str, Any]:
    settings = load_settings()
    canonical = canonicalize_scoring_input(token)
    return compute_wallet_weighting(canonical, settings, requested_mode=mode)


def canonicalize_scoring_input(token: Mapping[str, Any]) -> Dict[str, Any]:
    canonical = copy.deepcopy(dict(token))
    wallet_features = canonical.get("wallet_features")
    if not isinstance(wallet_features, Mapping):
        wallet_features = {}

    def assign_first(dest: str, *sources: str) -> None:
        if canonical.get(dest) is not None:
            return
        value = _first_present(canonical, sources, None)
        if value is None:
            value = _first_present(wallet_features, sources, None)
        if value is not None:
            canonical[dest] = value

    assign_first("token_address", "token_address", "mint", "token_id", "id", "address", "pair_address", "symbol")
    assign_first("x_validation_score", "x_validation_score", "x_score", "social_score", "organic_x_score")
    assign_first("x_validation_delta", "x_validation_delta", "x_delta")
    assign_first("first30s_buy_ratio", "first30s_buy_ratio", "buy_pressure")
    assign_first("wallet_registry_status", "wallet_registry_status")
    assign_first("smart_wallet_score_sum", "smart_wallet_score_sum")
    assign_first("smart_wallet_tier1_hits", "smart_wallet_tier1_hits")
    assign_first("smart_wallet_tier2_hits", "smart_wallet_tier2_hits")
    assign_first("smart_wallet_tier3_hits", "smart_wallet_tier3_hits")
    assign_first("smart_wallet_early_entry_hits", "smart_wallet_early_entry_hits")
    assign_first("smart_wallet_active_hits", "smart_wallet_active_hits")
    assign_first("smart_wallet_watch_hits", "smart_wallet_watch_hits")
    assign_first("smart_wallet_conviction_bonus", "smart_wallet_conviction_bonus")
    assign_first("smart_wallet_registry_confidence", "smart_wallet_registry_confidence")
    assign_first("smart_wallet_netflow_bias", "smart_wallet_netflow_bias")
    assign_first("smart_wallet_hits", "smart_wallet_hits")

    if canonical.get("smart_wallet_hits") is None:
        total_hits = int(_as_float(canonical.get("smart_wallet_tier1_hits"), 0.0))
        total_hits += int(_as_float(canonical.get("smart_wallet_tier2_hits"), 0.0))
        total_hits += int(_as_float(canonical.get("smart_wallet_tier3_hits"), 0.0))
        total_hits += int(_as_float(canonical.get("smart_wallet_active_hits"), 0.0))
        if total_hits > 0:
            canonical["smart_wallet_hits"] = total_hits

    if canonical.get("rug_verdict") is None:
        rug_verdict = _normalize_rug_verdict(
            _first_present(canonical, ("rug_status", "rug_decision", "rug_label"), None)
        )
        if rug_verdict is not None:
            canonical["rug_verdict"] = rug_verdict
    if canonical.get("x_status") is None and canonical.get("x_validation_score") is not None:
        canonical["x_status"] = "ok"
    if canonical.get("enrichment_status") is None:
        canonical["enrichment_status"] = "ok"
    if canonical.get("rug_status") is None and canonical.get("rug_verdict") is not None:
        canonical["rug_status"] = str(canonical["rug_verdict"]).lower()

    return canonical


def _adapter_passthrough(adapter_input: Mapping[str, Any], scored: Mapping[str, Any]) -> Dict[str, Any]:
    enriched = dict(scored)
    for key in (
        "mint",
        "token_id",
        "id",
        "address",
        "pair_address",
        "token_key",
        "_source_presence",
    ):
        value = adapter_input.get(key)
        if value is not None:
            enriched[key] = value
    if enriched.get("mint") is None and adapter_input.get("token_address"):
        enriched["mint"] = adapter_input.get("token_address")
    if enriched.get("token_id") is None and adapter_input.get("token_address"):
        enriched["token_id"] = adapter_input.get("token_address")
    return enriched


def score_token(
    token: Mapping[str, Any],
    wallet_weighting_mode: str = DEFAULT_WALLET_WEIGHTING_MODE,
) -> Dict[str, Any]:
    settings = load_settings()
    canonical = canonicalize_scoring_input(token)
    scored = analytics_score_token(
        canonical,
        settings,
        wallet_weighting_mode=wallet_weighting_mode,
        scored_at=deterministic_event_timestamp(canonical),
    )
    return _adapter_passthrough(canonical, scored)


def score_event_row(token: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        "timestamp": deterministic_event_timestamp(token),
        "token_id": _first_present(token, ("token_id", "mint", "token_address", "id", "symbol"), ""),
        "mint": _first_present(token, ("mint", "token_address", "token_id", "id"), ""),
        "wallet_weighting_mode": token.get("wallet_weighting_mode"),
        "wallet_weighting_effective_mode": token.get("wallet_weighting_effective_mode"),
        "wallet_registry_status": token.get("wallet_registry_status"),
        "wallet_score_component_raw": token.get("wallet_score_component_raw"),
        "wallet_score_component_applied": token.get("wallet_score_component_applied"),
        "final_score_pre_wallet": token.get("final_score_pre_wallet"),
        "final_score": token.get("final_score"),
        "wallet_score_component_reason": token.get("wallet_score_component_reason"),
    }


def score_tokens(
    shortlist: Sequence[Mapping[str, Any]],
    x_validated: Sequence[Mapping[str, Any]],
    enriched: Sequence[Mapping[str, Any]],
    rug_assessed: Sequence[Mapping[str, Any]],
    wallet_weighting_mode: str = DEFAULT_WALLET_WEIGHTING_MODE,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    merged = merge_inputs(shortlist, x_validated, enriched, rug_assessed)
    scored_tokens = [score_token(token, wallet_weighting_mode=wallet_weighting_mode) for token in merged]
    scored_tokens.sort(key=lambda item: str(item.get("mint") or item.get("token_address") or ""))
    events = [score_event_row(token) for token in scored_tokens]
    return scored_tokens, events


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Canonical unified scoring adapter smoke runner")
    parser.add_argument("--shortlist", required=True)
    parser.add_argument("--x-validated", required=True, dest="x_validated")
    parser.add_argument("--enriched", required=True)
    parser.add_argument("--rug-assessed", required=True, dest="rug_assessed")
    parser.add_argument(
        "--wallet-weighting-mode",
        default=DEFAULT_WALLET_WEIGHTING_MODE,
        choices=sorted(WALLET_WEIGHTING_MODES),
    )
    parser.add_argument("--out", default="data/processed/scored_tokens.json")
    parser.add_argument("--events-out", default="data/processed/score_events.jsonl")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    shortlist = ensure_list(load_json(Path(args.shortlist)))
    x_validated = ensure_list(load_json(Path(args.x_validated)))
    enriched = ensure_list(load_json(Path(args.enriched)))
    rug_assessed = ensure_list(load_json(Path(args.rug_assessed)))
    scored, events = score_tokens(
        shortlist=shortlist,
        x_validated=x_validated,
        enriched=enriched,
        rug_assessed=rug_assessed,
        wallet_weighting_mode=args.wallet_weighting_mode,
    )
    write_json(Path(args.out), scored)
    write_jsonl(Path(args.events_out), events)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
