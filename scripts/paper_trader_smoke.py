"""Smoke test for paper trader lifecycle."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config.settings import load_settings
from paper_runner import run_paper_cycle
from utils.io import write_json


def main() -> int:
    settings = load_settings()
    out = settings.SMOKE_DIR
    out.mkdir(parents=True, exist_ok=True)

    write_json(out / "entry_candidates.json", [{
        "token_address": "So11111111111111111111111111111111111111112",
        "symbol": "EXAMPLE",
        "entry_decision": "SCALP",
        "entry_confidence": 0.83,
        "recommended_position_pct": 0.75,
        "entry_reason": "high_final_score_and_fast_early_momentum",
        "entry_snapshot": {"final_score": 84.2, "rug_score": 0.18},
        "contract_version": settings.PAPER_CONTRACT_VERSION,
    }])
    write_json(out / "exit_decisions.json", [{
        "position_id": "pos_0001",
        "token_address": "So11111111111111111111111111111111111111112",
        "exit_decision": "FULL_EXIT",
        "exit_fraction": 1.0,
        "exit_reason": "scalp_momentum_decay_after_recheck",
        "exit_snapshot": {"price_usd": 0.000138},
    }])
    write_json(out / "market_states.json", [{
        "token_address": "So11111111111111111111111111111111111111112",
        "price_usd": 0.000123,
        "liquidity_usd": 500000,
        "volatility": 0.8,
    }])

    settings.PROCESSED_DATA_DIR.mkdir(parents=True, exist_ok=True)
    # route smoke inputs through processed dir expected by runner
    for name in ["entry_candidates", "exit_decisions", "market_states"]:
        write_json(settings.PROCESSED_DATA_DIR / f"{name}.json", __import__("json").loads((out / f"{name}.json").read_text(encoding="utf-8")))

    state = run_paper_cycle(settings)

    write_json(out / "positions.smoke.json", {
        "positions": state.get("positions", []),
        "next_position_seq": state.get("next_position_seq", 1),
        "next_trade_seq": state.get("next_trade_seq", 1),
    })
    write_json(out / "portfolio_state.smoke.json", state.get("portfolio", {}))
    (out / "signals.smoke.jsonl").write_text((settings.PROCESSED_DATA_DIR / "signals.jsonl").read_text(encoding="utf-8"), encoding="utf-8")
    (out / "trades.smoke.jsonl").write_text((settings.PROCESSED_DATA_DIR / "trades.jsonl").read_text(encoding="utf-8"), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
