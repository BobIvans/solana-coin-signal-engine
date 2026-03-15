# PR-1 Core Contracts and Bootstrap Foundation

PR-1 establishes infrastructure-only foundations:

- unified settings loading and validation from `.env`
- deterministic JSON/JSONL I/O helpers
- UTC timestamp helpers
- base JSON contracts for token candidates, signals, trades, and positions
- global in-memory cache and rate-limit guardrails
- retry wrapper for network-bound tasks

## JSON contracts

### TokenCandidate
- `token_address: string`
- `pair_address: string`
- `symbol: string`
- `name: string`
- `chain: "solana"`
- `discovered_at_utc: string`

### SignalRecord
- `token_address: string`
- `timestamp_utc: string`
- `stage: string`
- `status: string`
- `payload: object`

### TradeRecord
- `token_address: string`
- `entry_time_utc: string`
- `exit_time_utc: string`
- `regime: string`
- `pnl_pct: number`
- `exit_reason: string`

### PositionRecord
- `token_address: string`
- `status: "open" | string`
- `entry_price: number`
- `entry_time_utc: string`
- `entry_snapshot: object`

## Scope boundaries

PR-1 intentionally excludes discovery/scoring/trading business logic.
