"""Paper trader lifecycle orchestration functions."""

from __future__ import annotations

from typing import Any

from trading.fill_model import simulate_entry_fill, simulate_exit_fill
from trading.position_book import (
    apply_partial_exit,
    ensure_state,
    get_open_position_by_id,
    get_open_position_by_token,
    mark_to_market,
    next_trade_id,
    open_position,
)
from trading.trade_logger_v2 import log_signal, log_trade
from utils.clock import utc_now_iso
from utils.wallet_family_contract_fields import copy_wallet_family_contract_fields


def _market_index(market_states: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for m in market_states:
        token = str(m.get("token_address") or "")
        if token:
            out[token] = m
    return out


def _sizing_fields(ctx: dict[str, Any]) -> dict[str, Any]:
    fields = (
        "recommended_position_pct",
        "base_position_pct",
        "effective_position_pct",
        "sizing_multiplier",
        "sizing_origin",
        "sizing_reason_codes",
        "sizing_confidence",
        "sizing_warning",
        "evidence_quality_score",
        "evidence_conflict_flag",
        "partial_evidence_flag",
        "evidence_coverage_ratio",
        "evidence_available",
        "evidence_scores",
    )
    return {field: ctx.get(field) for field in fields if field in ctx}


def process_exit_signals(exit_signals: list[dict[str, Any]], market_states: list[dict[str, Any]], state: dict[str, Any], settings: Any) -> dict[str, Any]:
    ensure_state(state, settings)
    markets = _market_index(market_states)
    paths = state["paths"]

    for signal in exit_signals:
        position = get_open_position_by_id(state, str(signal.get("position_id") or ""))
        log_signal(
            {
                "ts": utc_now_iso(),
                "event": "exit_signal",
                "token_address": signal.get("token_address"),
                "position_id": signal.get("position_id"),
                "decision": signal.get("exit_decision"),
                "reason": signal.get("exit_reason"),
                **copy_wallet_family_contract_fields(signal, fallback=position or {}),
                "contract_version": settings.PAPER_CONTRACT_VERSION,
            },
            paths,
        )

        if signal.get("exit_decision") == "HOLD":
            continue

        if not position:
            continue
        market = markets.get(position["token_address"], {})
        fill = simulate_exit_fill(position, signal, market, settings)
        trade_id = next_trade_id(state)

        if fill["tx_failed"]:
            log_trade(
                {
                    "ts": utc_now_iso(),
                    "event": "paper_fill_failed",
                    "trade_id": trade_id,
                    "position_id": position.get("position_id"),
                    "token_address": position.get("token_address"),
                    "side": "SELL",
                    "tx_failed": True,
                    "failure_reason": fill.get("failure_reason"),
                    **copy_wallet_family_contract_fields(position),
                    "contract_version": settings.PAPER_CONTRACT_VERSION,
                },
                paths,
            )
            continue

        fill_for_state = {
            **fill,
            "exit_flags": list(signal.get("exit_flags") or []),
            "exit_reason": signal.get("exit_reason"),
            "exit_status": signal.get("exit_status"),
            "exit_warnings": list(signal.get("exit_warnings") or []),
        }
        apply_partial_exit(position, fill_for_state, state)
        is_open = bool(position.get("is_open"))
        event = "paper_sell_partial" if is_open else "paper_sell_full"
        log_trade(
            {
                "ts": utc_now_iso(),
                "event": event,
                "trade_id": trade_id,
                "position_id": position.get("position_id"),
                "token_address": position.get("token_address"),
                "symbol": position.get("symbol"),
                "side": "SELL",
                **fill,
                "reason": signal.get("exit_reason"),
                **copy_wallet_family_contract_fields(signal, fallback=position),
                "contract_version": settings.PAPER_CONTRACT_VERSION,
            },
            paths,
        )

    return state


def process_entry_signals(entry_signals: list[dict[str, Any]], market_states: list[dict[str, Any]], state: dict[str, Any], settings: Any) -> dict[str, Any]:
    ensure_state(state, settings)
    markets = _market_index(market_states)
    paths = state["paths"]

    for signal in entry_signals:
        log_signal(
            {
                "ts": utc_now_iso(),
                "event": "entry_signal",
                "token_address": signal.get("token_address"),
                "symbol": signal.get("symbol"),
                "decision": signal.get("entry_decision"),
                "confidence": signal.get("entry_confidence"),
                "recommended_position_pct": signal.get("recommended_position_pct"),
                "reason": signal.get("entry_reason"),
                **copy_wallet_family_contract_fields(signal),
                "contract_version": settings.PAPER_CONTRACT_VERSION,
            },
            paths,
        )

        decision = signal.get("entry_decision")
        if decision == "IGNORE":
            continue

        duplicate = get_open_position_by_token(state, str(signal.get("token_address") or ""))
        portfolio = state["portfolio"]
        max_positions_reached = int(portfolio.get("open_positions") or 0) >= int(settings.PAPER_MAX_CONCURRENT_POSITIONS)
        if duplicate or max_positions_reached or float(portfolio.get("free_capital_sol") or 0.0) <= 0:
            log_signal(
                {
                    "ts": utc_now_iso(),
                    "event": "signal_rejected",
                    "token_address": signal.get("token_address"),
                    "decision": decision,
                    "reason": "duplicate_or_capital_limit",
                    **copy_wallet_family_contract_fields(signal),
                    "contract_version": settings.PAPER_CONTRACT_VERSION,
                },
                paths,
            )
            continue

        market = markets.get(signal.get("token_address"), {})
        fill = simulate_entry_fill(signal, market, portfolio, settings)
        trade_id = next_trade_id(state)
        if fill["tx_failed"]:
            log_trade(
                {
                    "ts": utc_now_iso(),
                    "event": "paper_fill_failed",
                    "trade_id": trade_id,
                    "position_id": None,
                    "token_address": signal.get("token_address"),
                    "symbol": signal.get("symbol"),
                    "side": "BUY",
                    "tx_failed": True,
                    "failure_reason": fill.get("failure_reason"),
                    **copy_wallet_family_contract_fields(signal),
                    "contract_version": settings.PAPER_CONTRACT_VERSION,
                },
                paths,
            )
            continue

        requested_effective_position_pct = float(signal.get("effective_position_pct") or signal.get("recommended_position_pct") or 0.0)
        actual_effective_position_pct = round(requested_effective_position_pct * float(fill.get("fill_ratio") or 0.0), 4)
        signal_for_position = {
            **signal,
            "requested_effective_position_pct": requested_effective_position_pct,
            "effective_position_pct": actual_effective_position_pct,
        }
        pos = open_position(fill, signal_for_position, state)
        log_trade(
            {
                "ts": utc_now_iso(),
                "event": "paper_buy",
                "trade_id": trade_id,
                "position_id": pos["position_id"],
                "token_address": pos["token_address"],
                "symbol": pos.get("symbol"),
                "side": "BUY",
                **fill,
                **_sizing_fields(pos),
                "requested_effective_position_pct": requested_effective_position_pct,
                "regime": signal.get("entry_decision"),
                "reason": "entry_signal_filled",
                **copy_wallet_family_contract_fields(signal, fallback=pos),
                "contract_version": settings.PAPER_CONTRACT_VERSION,
            },
            paths,
        )

    return state


def run_mark_to_market(state: dict[str, Any], market_states: list[dict[str, Any]], settings: Any) -> dict[str, Any]:
    ensure_state(state, settings)
    markets = _market_index(market_states)

    for pos in state.get("positions", []):
        if not pos.get("is_open"):
            continue
        mark_to_market(pos, markets.get(pos["token_address"], {}), state)

    return state
