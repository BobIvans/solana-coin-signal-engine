from __future__ import annotations

from typing import Any

from scoring.unified_score import compute_base_scored_token, compute_wallet_adjustment

_CANONICAL_PARITY_FIELDS = {
    "wallet_weighting_requested_mode",
    "wallet_weighting_effective_mode",
    "wallet_score_component_raw",
    "wallet_score_component_applied",
    "wallet_score_component_applied_shadow",
    "wallet_score_component_reason",
    "wallet_registry_status",
    "wallet_score_explain",
    "final_score_pre_wallet",
    "final_score",
    "score_contract_version",
}


def _as_float(value: Any, default: float = 0.0) -> float:
    if value is None or value == "":
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _round(value: float) -> float:
    return round(float(value), 6)


def _canonical_score_input(payload: dict[str, Any]) -> dict[str, Any] | None:
    scored_rows = payload.get("scored_rows") or []
    if scored_rows:
        return dict(scored_rows[0])

    for bucket in ("entry_candidates", "signals", "trades", "positions"):
        rows = payload.get(bucket) or []
        if rows:
            return dict(rows[0])
    return None


def _score_source(kind: str, score_input_present: bool) -> str:
    if kind == "mode_specific":
        return "mode_specific_scored_artifact"
    if kind in {"generic", "explicit"} and score_input_present:
        return "generic_scored_artifact_rescored"
    return "no_scored_artifact_passthrough"


def rescore_replay_inputs(
    token_inputs: dict[str, dict[str, Any]],
    *,
    wallet_weighting: str,
    scored_input_kind: str = "missing",
) -> dict[str, Any]:
    rescored_rows = 0
    score_source = _score_source(scored_input_kind, bool(token_inputs))
    parity_status = "unavailable"
    scorer_contract_version = "wallet_weighted_unified_score.v1"

    for token_address, payload in token_inputs.items():
        score_input = _canonical_score_input(payload)
        if not score_input:
            payload["rescored_row"] = None
            payload["replay_score_source"] = "no_scored_artifact_passthrough"
            payload["wallet_mode_parity_status"] = "unavailable"
            payload["wallet_weighting_requested_mode"] = wallet_weighting
            payload["wallet_weighting_effective_mode"] = wallet_weighting
            payload["score_contract_version"] = scorer_contract_version
            continue

        base_scored = compute_base_scored_token(score_input)
        wallet = compute_wallet_adjustment(base_scored, wallet_weighting)
        final_score_pre_wallet = _as_float(base_scored.get("final_score_pre_wallet"), _as_float(base_scored.get("final_score")))
        final_score = final_score_pre_wallet + _as_float(wallet.get("wallet_score_component_applied"), 0.0)
        if wallet.get("wallet_weighting_mode") in {"off", "shadow"} or wallet.get("wallet_weighting_effective_mode") == "degraded_zero":
            final_score = final_score_pre_wallet

        rescored = {
            **dict(score_input),
            **dict(base_scored),
            "wallet_weighting_requested_mode": wallet.get("wallet_weighting_mode", wallet_weighting),
            "wallet_weighting_effective_mode": wallet.get("wallet_weighting_effective_mode", wallet_weighting),
            "wallet_score_component_raw": _round(wallet.get("wallet_score_component_raw", 0.0)),
            "wallet_score_component_applied": _round(wallet.get("wallet_score_component_applied", 0.0)),
            "wallet_score_component_applied_shadow": _round(wallet.get("wallet_score_component_applied_shadow", 0.0)),
            "wallet_score_component_reason": wallet.get("wallet_score_component_reason"),
            "wallet_registry_status": wallet.get("wallet_registry_status"),
            "wallet_score_explain": wallet.get("wallet_score_explain"),
            "final_score_pre_wallet": _round(final_score_pre_wallet),
            "final_score": _round(final_score),
            "score_contract_version": str(base_scored.get("contract_version") or score_input.get("contract_version") or scorer_contract_version),
        }
        payload["rescored_row"] = rescored
        payload["replay_score_source"] = _score_source(scored_input_kind, True)
        payload["wallet_mode_parity_status"] = "comparable" if scored_input_kind in {"mode_specific", "generic", "explicit"} else "partial"
        payload["wallet_weighting_requested_mode"] = rescored["wallet_weighting_requested_mode"]
        payload["wallet_weighting_effective_mode"] = rescored["wallet_weighting_effective_mode"]
        payload["score_contract_version"] = rescored["score_contract_version"]
        rescored_rows += 1

    if rescored_rows:
        parity_status = "comparable" if scored_input_kind in {"mode_specific", "generic", "explicit"} else "partial"

    return {
        "rescored_rows": rescored_rows,
        "replay_score_source": score_source if rescored_rows else "no_scored_artifact_passthrough",
        "wallet_mode_parity_status": parity_status,
        "score_contract_version": scorer_contract_version,
    }
