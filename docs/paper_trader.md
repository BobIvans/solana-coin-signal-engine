# PR-9 Paper Trader

`paper_trader` simulates full lifecycle execution without sending transactions.

## Lifecycle

1. Process exits from `exit_decisions.json`.
2. Process entries from `entry_candidates.json`.
3. Mark all open positions to market.

## Friction model

Implemented in `trading/friction_model.py`:
- slippage (`compute_slippage_bps`)
- priority fee (`compute_priority_fee_sol`)
- failed tx probability (`compute_failed_tx_probability`)
- partial fill ratio (`compute_partial_fill_ratio`)

## Fill outcomes

Implemented in `trading/fill_model.py`:
- `full_fill`
- `partial_fill`
- `failed_fill`

Failed fills never mutate positions.

## Capital rules

- Starting capital from `PAPER_STARTING_CAPITAL_SOL`.
- Entry notional = `free_capital_sol * recommended_position_pct`.
- Duplicate open token positions are rejected.
- Max open positions enforced via `PAPER_MAX_CONCURRENT_POSITIONS`.

## Logging contracts

Append-only logs:
- `signals.jsonl`
- `trades.jsonl`

And state snapshots:
- `positions.json`
- `portfolio_state.json`

## PnL rules

`trading/pnl_engine.py` separates:
- realized PnL on exit fills
- unrealized PnL in mark-to-market
- fees tracked independently
