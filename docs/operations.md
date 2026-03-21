# Operations contract

This repo keeps JSON / JSONL artifacts as the truth layer, but long-running runtime and replay flows now also emit an indexed operational layer.

## Runtime outputs

Each runtime run should leave these canonical files under `runs/<run_id>/`:

- `runtime_manifest.json`
- `session_state.json`
- `positions.json`
- `daily_summary.json`
- `daily_summary.md`
- `runtime_health.json`
- `runtime_health.md`
- `artifact_manifest.json`
- `run_store.sqlite3`
- compatibility snapshots: `signals.jsonl`, `trades.jsonl`, `event_log.jsonl`, `decisions.jsonl`

## Segmented artifacts

Long-running append-only artifacts also support deterministic segmentation under:

- `runs/<run_id>/_segments/signals/`
- `runs/<run_id>/_segments/trades/`
- `runs/<run_id>/_segments/event_log/`
- `runs/<run_id>/_segments/decisions/`

Segments are day-keyed (`*.YYYY-MM-DD.jsonl`). The root `*.jsonl` files remain compatibility snapshots materialized from the segments.

## Health counters

`runtime_health.json` is the canonical operational quality surface for a runtime run. It includes:

- current-state live / fallback / stale counters and rates
- degraded-X attempted / opened / blocked counters
- tx window partial / truncated counters
- partial-evidence entry count
- fallback refresh failure count
- unresolved replay row count

## Durable run store

`run_store.sqlite3` is a lightweight helper/index layer. It stores:

- run identity (`run_id`, mode, config hash)
- start/end timestamps
- latest summary / health / manifest pointers
- checkpoint snapshots and counter payloads

The SQLite store is operationally useful for restart, inspection, and report lookup, but it does not replace the JSON / JSONL truth artifacts.

## Acceptance readiness

The acceptance gate should fail if required smoke outputs are missing, empty, or malformed. A green pytest run is not enough if the operational outputs were not produced.


## Runtime hardening counters

Long-running runtime summaries now also surface:

- `x_cooldown_skip_count`
- `runtime_market_cache_pruned_count`
- `runtime_market_cache_size`
- `runtime_market_cache_pinned_count`
- `http_session_enabled`

The event log also emits `x_snapshot_batch_skipped_cooldown`, `runtime_market_cache_pruned`, and `runtime_market_cache_prune_summary` so operators can distinguish real upstream fetches from intentional cooldown short-circuits and cache hygiene work.
