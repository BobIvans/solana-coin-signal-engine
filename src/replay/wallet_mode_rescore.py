from __future__ import annotations

from importlib import import_module
from typing import Any, Callable


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


def _load_scorer() -> tuple[str, Callable[..., dict[str, Any]] | None, Callable[..., dict[str, Any]] | None, Callable[..., dict[str, Any]] | None]:
    module = import_module("scoring.unified_score")

    base_fn = getattr(module, "compute_base_scored_token", None)
    wallet_fn = getattr(module, "compute_wallet_adjustment", None)
    score_fn = getattr(module, "score_token", None)

    if callable(base_fn) and callable(wallet_fn):
        return "split", base_fn, wallet_fn, score_fn if callable(score_fn) else None
    if callable(score_fn):
        return "single", None, None, score_fn

    raise ImportError(
        "scoring.unified_score does not expose "
        "(compute_base_scored_token + compute_wallet_adjustment) or score_token"
    )


_SCORER_STYLE, _BASE_FN, _WALLET_FN, _SCORE_FN = _load_scorer()


def _call_single_score_token(score_input: dict[str, Any], wallet_weighting: str) -> dict[str, Any]:
    score_fn = _SCORE_FN
    assert score_fn is not None

    attempts = (
        lambda: score_fn(dict(score_input), wallet_weighting_mode=wallet_weighting),
        lambda: score_fn(dict(score_input), wallet_weighting),
        lambda: score_fn(token=dict(score_input), wallet_weighting_mode=wallet_weighting),
        lambda: score_fn(token=dict(score_input), wallet_weighting=wallet_weighting),
    )

    last_error: Exception | None = None
    for attempt in attempts:
        try:
            result = attempt()
            if isinstance(result, dict):
                return dict(result)
            return dict(result or {})
        except TypeError as exc:
            last_error = exc
            continue

    if last_error is not None:
        raise last_error
    raise TypeError("Unable to call scoring.unified_score.score_token with wallet weighting mode")


def _build_rescored_row(score_input: dict[str, Any], wallet_weighting: str) -> dict[str, Any]:
    scorer_contract_version = "wallet_weighted_unified_score.v1"

    existing_pre_wallet = score_input.get("final_score_pre_wallet")
    existing_final = score_input.get("final_score")

    if existing_pre_wallet is not None or existing_final is not None:
        final_score_pre_wallet = _as_float(existing_pre_wallet, _as_float(existing_final, 0.0))

        wallet = None
        if _SCORER_STYLE == "split" and callable(_WALLET_FN):
            wallet = _WALLET_FN(dict(score_input), wallet_weighting)
        elif callable(_SCORE_FN):
            scored = _call_single_score_token(dict(score_input), wallet_weighting)
            wallet = {
                "wallet_weighting_mode": scored.get("wallet_weighting_mode", wallet_weighting),
                "wallet_weighting_effective_mode": scored.get("wallet_weighting_effective_mode", wallet_weighting),
                "wallet_score_component_raw": scored.get("wallet_score_component_raw", 0.0),
                "wallet_score_component_applied": scored.get("wallet_score_component_applied", 0.0),
                "wallet_score_component_applied_shadow": scored.get(
                    "wallet_score_component_applied_shadow",
                    scored.get("wallet_score_component_applied", 0.0),
                ),
                "wallet_score_component_reason": scored.get("wallet_score_component_reason"),
                "wallet_registry_status": scored.get("wallet_registry_status"),
                "wallet_score_explain": scored.get("wallet_score_explain"),
            }
        else:
            wallet = {
                "wallet_weighting_mode": wallet_weighting,
                "wallet_weighting_effective_mode": wallet_weighting,
                "wallet_score_component_raw": 0.0,
                "wallet_score_component_applied": 0.0,
                "wallet_score_component_applied_shadow": 0.0,
                "wallet_score_component_reason": None,
                "wallet_registry_status": score_input.get("wallet_registry_status"),
                "wallet_score_explain": score_input.get("wallet_score_explain"),
            }

        final_score = final_score_pre_wallet + _as_float(wallet.get("wallet_score_component_applied"), 0.0)
        if wallet.get("wallet_weighting_mode") in {"off", "shadow"} or wallet.get("wallet_weighting_effective_mode") == "degraded_zero":
            final_score = final_score_pre_wallet

        return {
            **dict(score_input),
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
            "score_contract_version": str(
                score_input.get("contract_version") or scorer_contract_version
            ),
        }

    if _SCORER_STYLE == "split" and callable(_BASE_FN) and callable(_WALLET_FN):
        base_scored = _BASE_FN(score_input)
        wallet = _WALLET_FN(base_scored, wallet_weighting)

        final_score_pre_wallet = _as_float(
            base_scored.get("final_score_pre_wallet"),
            _as_float(base_scored.get("final_score")),
        )
        final_score = final_score_pre_wallet + _as_float(wallet.get("wallet_score_component_applied"), 0.0)
        if wallet.get("wallet_weighting_mode") in {"off", "shadow"} or wallet.get("wallet_weighting_effective_mode") == "degraded_zero":
            final_score = final_score_pre_wallet

        return {
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
            "score_contract_version": str(
                base_scored.get("contract_version")
                or score_input.get("contract_version")
                or scorer_contract_version
            ),
        }

    rescored = _call_single_score_token(score_input, wallet_weighting)
    final_score_pre_wallet = _as_float(
        rescored.get("final_score_pre_wallet"),
        _as_float(rescored.get("final_score")),
    )
    final_score = _as_float(rescored.get("final_score"), final_score_pre_wallet)

    rescored.setdefault("wallet_weighting_requested_mode", wallet_weighting)
    rescored.setdefault("wallet_weighting_effective_mode", rescored.get("wallet_weighting_mode", wallet_weighting))
    rescored.setdefault("wallet_score_component_raw", 0.0)
    rescored.setdefault("wallet_score_component_applied", 0.0)
    rescored.setdefault("wallet_score_component_applied_shadow", rescored.get("wallet_score_component_applied", 0.0))
    rescored.setdefault("wallet_score_component_reason", None)
    rescored.setdefault("wallet_registry_status", rescored.get("wallet_registry_status"))
    rescored.setdefault("wallet_score_explain", rescored.get("wallet_score_explain"))
    rescored["final_score_pre_wallet"] = _round(final_score_pre_wallet)
    rescored["final_score"] = _round(final_score)
    rescored["score_contract_version"] = str(
        rescored.get("contract_version") or score_input.get("contract_version") or scorer_contract_version
    )
    return dict(rescored)


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

    for _token_address, payload in token_inputs.items():
        score_input = _canonical_score_input(payload)
        if not score_input:
            payload["rescored_row"] = None
            payload["replay_score_source"] = "no_scored_artifact_passthrough"
            payload["wallet_mode_parity_status"] = "unavailable"
            payload["wallet_weighting_requested_mode"] = wallet_weighting
            payload["wallet_weighting_effective_mode"] = wallet_weighting
            payload["score_contract_version"] = scorer_contract_version
            continue

        rescored = _build_rescored_row(dict(score_input), wallet_weighting)

        payload["rescored_row"] = rescored
        payload["replay_score_source"] = _score_source(scored_input_kind, True)
        payload["wallet_mode_parity_status"] = (
            "comparable" if scored_input_kind in {"mode_specific", "generic", "explicit"} else "partial"
        )
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
