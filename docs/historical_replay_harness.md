# Historical replay harness

The historical replay harness is the only supported replay path in this repository. It replaces the old replay shim with an evidence-first path that reconstructs token lifecycles from recorded local artifacts.

## Removal of the stale synthetic simulator

The old synthetic replay helper at `src/replay/simulator.py` has been removed. Future contributors must not reintroduce a separate synthetic replay module as a default path, convenience fallback, or hidden import surface.

Any smoke or degraded replay behavior must continue to flow through `src/replay/historical_replay_harness.py`, with explicit provenance/status labeling in the emitted artifacts. Synthetic PnL, synthetic hold-time generation, and synthetic exit reasons must not return as an alternative replay engine beside the historical harness.

## What makes replay historical here

A run is treated as historical when the harness can load persisted local artifacts such as:

- scored token rows
- entry candidates or signal events
- historical trades or positions
- recorded price paths / lifecycle observations
- persisted bundle, linkage, continuation, wallet, or X-derived fields when present

The harness does **not** fabricate complete trade outcomes when the artifacts are incomplete.

## Input files

The loader looks for these files inside an artifact directory:

- `scored_tokens.jsonl`
- `entry_candidates.json` or `entry_candidates.jsonl`
- `signals.jsonl` or `entry_events.jsonl`
- `trades.jsonl`
- `positions.json`
- `price_paths.json` or `price_paths.jsonl`
- `universe.json` / `universe.jsonl`

Only the files that exist are used. Missing files become explicit partial/unresolved replay status rather than implicit synthetic completion.

## Lifecycle reconstruction

For each token, the harness:

1. loads recorded candidate/signal/trade/position context,
2. re-runs regime selection with the existing deterministic regime rules,
3. reconstructs entry only from recorded evidence,
4. walks the recorded historical price path through the existing exit rules,
5. emits a resolved, partial, ignored, or unresolved lifecycle.

Lifecycle state transitions are managed by `src/replay/replay_state_machine.py`.

## Partial replay policy

If the harness is missing any of the following, it degrades honestly:

- entry price
- price path
- exit observation coverage
- exit snapshots
- bundle / continuation / linkage context

Output rows are labeled with additive provenance fields:

- `replay_input_origin`
- `replay_data_status`
- `replay_resolution_status`
- `synthetic_assist_flag`

Typical statuses:

- `historical`
- `historical_partial`
- `synthetic_smoke`
- `mixed`

## Artifacts written

Each run writes:

- `signals.jsonl`
- `trades.jsonl`
- `positions.json`
- `trade_feature_matrix.jsonl`
- `replay_summary.json`
- `replay_summary.md`
- `manifest.json`

The summary explicitly includes:

- historical row count
- partial row count
- unresolved row count
- whether synthetic fallback was used
- wallet weighting mode
- config hash

## Comparative replay modes

The driver supports wallet weighting comparisons with:

- `off`
- `on`
- `shadow` (through the same canonical unified scorer contract, with wallet deltas logged but not applied)

## Smoke mode

`scripts/historical_replay_smoke.py` runs the harness against deterministic local fixtures and writes outputs under `data/smoke/`.

## Out of scope

This harness intentionally does **not**:

- place live orders
- integrate with exchanges
- introduce an alternative unified score truth path
- redesign regime logic
- redesign exit logic
- fabricate complete PnL when historical evidence is incomplete


Evidence-quality score penalties (`partial_evidence_penalty`, `low_confidence_evidence_penalty`) are now propagated into the replay trade feature matrix alongside existing evidence-quality summary fields.
