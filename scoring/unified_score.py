
from __future__ import annotations

import argparse
import copy
import importlib
import json
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

DEFAULT_WALLET_WEIGHTING_MODE = "shadow"
WALLET_WEIGHTING_MODES = {"off", "shadow", "on"}
WALLET_ADJUSTMENT_CAP = 8.0
WALLET_ADJUSTMENT_CAP_TIER2 = 5.0
WALLET_ADJUSTMENT_CAP_TIER3 = 3.0
WALLET_ADJUSTMENT_CAP_WATCH_ONLY = 1.0

LEGACY_IMPORT_CANDIDATES: Sequence[Tuple[str, Sequence[str]]] = (
    ("src.scoring.unified_score", ("score_token", "build_scored_token", "compute_unified_score", "compute_score")),
    ("src.unified_score", ("score_token", "build_scored_token", "compute_unified_score", "compute_score")),
    ("analytics.unified_score", ("score_token", "build_scored_token", "compute_unified_score", "compute_score")),
)

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

def _round(value: float) -> float:
    return round(float(value), 6)

def _clip(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))

def _first_number(token: Mapping[str, Any], keys: Sequence[str], default: float = 0.0) -> float:
    for key in keys:
        if key in token and token[key] is not None:
            return _as_float(token[key], default)
    return default

def _first_present(token: Mapping[str, Any], keys: Sequence[str], default: Any = None) -> Any:
    for key in keys:
        if key in token and token[key] is not None:
            return token[key]
    return default

def token_key(token: Mapping[str, Any], ordinal: int = 0) -> str:
    for key in ("mint", "token_id", "id", "address", "pair_address", "symbol"):
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
        return [dict(item) for _, item in sorted(payload.items(), key=lambda kv: str(kv[0])) if isinstance(item, Mapping)]
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

def _normalize_fraction(value: float, *, max_value: float) -> float:
    if max_value <= 0:
        return 0.0
    return _clip(value / max_value, 0.0, 1.0)

def _normalize_score_hint(value: float) -> float:
    if value <= 1.0:
        return _clip(value, 0.0, 1.0)
    if value <= 10.0:
        return _clip(value / 10.0, 0.0, 1.0)
    return _clip(value / 100.0, 0.0, 1.0)

def _rug_strength(token: Mapping[str, Any]) -> float:
    safety = _first_number(token, ("rug_safety_score", "rug_score", "rug_score_total", "rug_safety_total"), 0.0)
    status = str(_first_present(token, ("rug_status", "rug_decision", "rug_label"), "")).lower()
    fail_closed = bool(_first_present(token, ("fail_closed", "rug_fail_closed"), False))
    norm = _normalize_score_hint(safety)
    if status in {"pass", "safe", "ok"}:
        return max(norm, 0.7)
    if status in {"warn", "warning", "caution"}:
        return min(norm, 0.5)
    if status in {"fail", "unsafe", "reject"}:
        return 0.0
    if fail_closed:
        return min(norm, 0.25)
    return norm

def compute_fallback_base_score(token: Mapping[str, Any]) -> Tuple[float, Dict[str, float]]:
    x_strength = _normalize_score_hint(
        _first_number(token, ("x_score", "x_validation_score", "x_confidence", "social_score", "organic_x_score"), 0.0)
    )
    liquidity_strength = max(
        _normalize_score_hint(_first_number(token, ("liquidity_score",), 0.0)),
        _normalize_fraction(_first_number(token, ("liquidity_usd",), 0.0), max_value=100000.0),
    )
    volume_strength = max(
        _normalize_score_hint(_first_number(token, ("volume_velocity_score", "volume_score"), 0.0)),
        _normalize_fraction(_first_number(token, ("volume_mcap_ratio",), 0.0), max_value=2.0),
    )
    buy_pressure_strength = max(
        _normalize_score_hint(_first_number(token, ("buy_pressure_score",), 0.0)),
        _clip(_first_number(token, ("buy_pressure",), 0.0), 0.0, 1.0),
    )
    holder_growth_strength = max(
        _normalize_score_hint(_first_number(token, ("holder_growth_score",), 0.0)),
        _normalize_fraction(_first_number(token, ("holder_growth_5m",), 0.0), max_value=100.0),
    )
    rug_strength = _rug_strength(token)
    components = {
        "x_strength": _round(x_strength * 40.0),
        "liquidity_strength": _round(liquidity_strength * 15.0),
        "volume_strength": _round(volume_strength * 10.0),
        "buy_pressure_strength": _round(buy_pressure_strength * 10.0),
        "holder_growth_strength": _round(holder_growth_strength * 10.0),
        "rug_strength": _round(rug_strength * 15.0),
    }
    score = sum(components.values())
    return _round(score), components

def _call_legacy_scorer(token: Mapping[str, Any]) -> Optional[Dict[str, Any]]:
    for module_name, fn_names in LEGACY_IMPORT_CANDIDATES:
        try:
            module = importlib.import_module(module_name)
        except Exception:
            continue
        for fn_name in fn_names:
            fn = getattr(module, fn_name, None)
            if fn is None:
                continue
            try:
                result = fn(copy.deepcopy(dict(token)))
            except TypeError:
                try:
                    result = fn(token=copy.deepcopy(dict(token)))
                except Exception:
                    continue
            except Exception:
                continue
            if isinstance(result, Mapping):
                return dict(result)
    return None

def compute_base_scored_token(token: Mapping[str, Any]) -> Dict[str, Any]:
    candidate = dict(token)
    existing_score = _first_present(candidate, ("final_score_pre_wallet", "final_score", "base_score"), None)
    if existing_score is not None:
        pre_wallet = _as_float(existing_score)
        fallback_components = {}
        legacy_token = dict(candidate)
    else:
        legacy_token = _call_legacy_scorer(candidate)
        if legacy_token:
            pre_wallet = _as_float(_first_present(legacy_token, ("final_score", "final_score_pre_wallet", "base_score"), 0.0))
            fallback_components = {}
        else:
            pre_wallet, fallback_components = compute_fallback_base_score(candidate)
            legacy_token = dict(candidate)

    scored = dict(candidate)
    scored.update(legacy_token)
    scored["final_score_pre_wallet"] = _round(pre_wallet)
    if fallback_components and "base_score_components" not in scored:
        scored["base_score_components"] = fallback_components
    return scored

def _confidence_strength(value: Any) -> float:
    text = str(value or "").strip().lower()
    if text == "high":
        return 1.0
    if text == "medium":
        return 0.5
    if text == "low":
        return 0.15
    return 0.0

def _wallet_cap_from_hits(t1: int, t2: int, t3: int, active: int, watch: int) -> float:
    if t1 > 0 and active > 0:
        return WALLET_ADJUSTMENT_CAP
    if t2 > 0 and active > 0:
        return WALLET_ADJUSTMENT_CAP_TIER2
    if t3 > 0 and active > 0:
        return WALLET_ADJUSTMENT_CAP_TIER3
    if watch > 0:
        return WALLET_ADJUSTMENT_CAP_WATCH_ONLY
    return 0.0

def compute_wallet_adjustment(token: Mapping[str, Any], mode: str) -> Dict[str, Any]:
    requested_mode = mode if mode in WALLET_WEIGHTING_MODES else DEFAULT_WALLET_WEIGHTING_MODE
    registry_status = str(token.get("wallet_registry_status") or "missing").lower()

    score_sum = max(_first_number(token, ("smart_wallet_score_sum",), 0.0), 0.0)
    tier1_hits = int(_as_float(token.get("smart_wallet_tier1_hits"), 0.0))
    tier2_hits = int(_as_float(token.get("smart_wallet_tier2_hits"), 0.0))
    tier3_hits = int(_as_float(token.get("smart_wallet_tier3_hits"), 0.0))
    early_hits = int(_as_float(token.get("smart_wallet_early_entry_hits"), 0.0))
    active_hits = int(_as_float(token.get("smart_wallet_active_hits"), 0.0))
    watch_hits = int(_as_float(token.get("smart_wallet_watch_hits"), 0.0))
    conviction_bonus = max(_first_number(token, ("smart_wallet_conviction_bonus",), 0.0), 0.0)
    registry_confidence = token.get("smart_wallet_registry_confidence")
    confidence_strength = _confidence_strength(registry_confidence)
    netflow_bias = token.get("smart_wallet_netflow_bias")

    explain = {
        "smart_wallet_score_sum": _round(score_sum),
        "smart_wallet_tier1_hits": tier1_hits,
        "smart_wallet_tier2_hits": tier2_hits,
        "smart_wallet_tier3_hits": tier3_hits,
        "smart_wallet_early_entry_hits": early_hits,
        "smart_wallet_active_hits": active_hits,
        "smart_wallet_watch_hits": watch_hits,
        "smart_wallet_conviction_bonus": _round(conviction_bonus),
        "smart_wallet_registry_confidence": registry_confidence,
        "wallet_adjustment_cap": 0.0,
        "degraded_wallet_registry": registry_status != "validated",
        "smart_wallet_netflow_bias": netflow_bias,
    }

    if requested_mode == "off":
        explain["wallet_adjustment_cap"] = 0.0
        return {
            "wallet_weighting_mode": requested_mode,
            "wallet_weighting_effective_mode": "off",
            "wallet_registry_status": registry_status,
            "wallet_score_component_raw": 0.0,
            "wallet_score_component_applied": 0.0,
            "wallet_score_component_applied_shadow": 0.0,
            "wallet_score_component_capped": False,
            "wallet_score_component_reason": "wallet weighting disabled",
            "wallet_score_explain": explain,
        }

    if registry_status != "validated":
        explain["wallet_adjustment_cap"] = 0.0
        return {
            "wallet_weighting_mode": requested_mode,
            "wallet_weighting_effective_mode": "degraded_zero",
            "wallet_registry_status": registry_status,
            "wallet_score_component_raw": 0.0,
            "wallet_score_component_applied": 0.0,
            "wallet_score_component_applied_shadow": 0.0,
            "wallet_score_component_capped": False,
            "wallet_score_component_reason": f"wallet registry status={registry_status}; wallet adjustment forced to zero",
            "wallet_score_explain": explain,
        }

    normalized_sum = _normalize_fraction(score_sum, max_value=20.0)
    tier_weighted_hits = (3.0 * tier1_hits) + (1.75 * tier2_hits) + (0.75 * tier3_hits)
    tier_hit_strength = _normalize_fraction(tier_weighted_hits, max_value=6.0)
    early_entry_strength = _normalize_fraction(float(early_hits), max_value=2.0)
    conviction_bonus_strength = _normalize_fraction(conviction_bonus, max_value=3.0)

    raw_unit = (
        (0.40 * normalized_sum)
        + (0.20 * tier_hit_strength)
        + (0.15 * early_entry_strength)
        + (0.15 * conviction_bonus_strength)
        + (0.10 * confidence_strength)
    )
    cap = _wallet_cap_from_hits(tier1_hits, tier2_hits, tier3_hits, active_hits, watch_hits)
    applied_shadow = _round(min(raw_unit * cap, cap)) if cap > 0 else 0.0
    capped = cap > 0 and raw_unit * cap > cap
    effective_mode = requested_mode
    applied = applied_shadow if requested_mode == "on" else 0.0
    reason = (
        f"wallet evidence scored from validated enrichment; "
        f"tier_hits=({tier1_hits},{tier2_hits},{tier3_hits}), active_hits={active_hits}, watch_hits={watch_hits}, "
        f"confidence={registry_confidence or 'missing'}"
    )

    if watch_hits > 0 and active_hits <= 0 and tier1_hits <= 0 and tier2_hits <= 0 and tier3_hits <= 0:
        reason = "watch-only wallet evidence receives minimal capped impact"

    explain["wallet_adjustment_cap"] = _round(cap)

    return {
        "wallet_weighting_mode": requested_mode,
        "wallet_weighting_effective_mode": effective_mode,
        "wallet_registry_status": registry_status,
        "wallet_score_component_raw": _round(raw_unit),
        "wallet_score_component_applied": _round(applied),
        "wallet_score_component_applied_shadow": _round(applied_shadow),
        "wallet_score_component_capped": capped,
        "wallet_score_component_reason": reason,
        "wallet_score_explain": explain,
    }

def deterministic_event_timestamp(token: Mapping[str, Any]) -> str:
    for key in (
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

def score_token(token: Mapping[str, Any], wallet_weighting_mode: str = DEFAULT_WALLET_WEIGHTING_MODE) -> Dict[str, Any]:
    scored = compute_base_scored_token(token)
    wallet = compute_wallet_adjustment(scored, wallet_weighting_mode)
    final_pre_wallet = _as_float(scored.get("final_score_pre_wallet"), 0.0)
    final_score = final_pre_wallet + _as_float(wallet["wallet_score_component_applied"], 0.0)
    if wallet["wallet_weighting_mode"] in {"off", "shadow"} or wallet["wallet_weighting_effective_mode"] == "degraded_zero":
        final_score = final_pre_wallet
    scored.update(
        {
            "wallet_weighting_mode": wallet["wallet_weighting_mode"],
            "wallet_weighting_effective_mode": wallet["wallet_weighting_effective_mode"],
            "wallet_score_component_raw": _round(wallet["wallet_score_component_raw"]),
            "wallet_score_component_applied": _round(wallet["wallet_score_component_applied"]),
            "wallet_score_component_capped": bool(wallet["wallet_score_component_capped"]),
            "wallet_score_component_reason": wallet["wallet_score_component_reason"],
            "wallet_registry_status": wallet["wallet_registry_status"],
            "wallet_score_explain": wallet["wallet_score_explain"],
            "final_score_pre_wallet": _round(final_pre_wallet),
            "final_score": _round(final_score),
        }
    )
    return scored

def score_event_row(token: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        "timestamp": deterministic_event_timestamp(token),
        "token_id": _first_present(token, ("token_id", "mint", "id", "symbol"), ""),
        "mint": _first_present(token, ("mint", "token_id", "id"), ""),
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
    events = [score_event_row(token) for token in scored_tokens]
    return scored_tokens, events

def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="PR-SW-5 wallet-aware unified scoring smoke runner")
    parser.add_argument("--shortlist", required=True)
    parser.add_argument("--x-validated", required=True, dest="x_validated")
    parser.add_argument("--enriched", required=True)
    parser.add_argument("--rug-assessed", required=True, dest="rug_assessed")
    parser.add_argument("--wallet-weighting-mode", default=DEFAULT_WALLET_WEIGHTING_MODE, choices=sorted(WALLET_WEIGHTING_MODES))
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
