# Runtime real signals

`run_promotion_loop.py` now consumes real local pipeline artifacts by default instead of relying on synthetic placeholder signals.

## What counts as a real runtime signal

A runtime signal is considered real when it comes from an artifact already produced by the repo's pipeline, such as:

1. `data/processed/entry_candidates.json`
2. `data/processed/entry_candidates.smoke.json`
3. `data/processed/entry_events.jsonl`
4. `data/processed/scored_tokens.json` when it already carries decision-support fields
5. replay-compatible artifacts such as `trade_feature_matrix.jsonl` (canonical), with optional legacy fallback to `trade_feature_matrix.json` for older local fixtures

The runtime loader never fabricates missing signals. If an artifact exists but rows are malformed, those rows are marked partial or invalid and skipped safely.

## Official upstream command

The repo now provides one official upstream generator for runtime artifacts:

```bash
python scripts/run_runtime_signal_pipeline.py \
  --config config/promotion.default.yaml \
  --processed-dir data/processed
```

This command builds the canonical artifact chain through `entry_candidates.json`.

## Artifact precedence

The runtime loader uses this precedence order:

1. `entry_candidates.json`
2. `entry_candidates.smoke.json`
3. `entry_events.jsonl`
4. `scored_tokens.json`
5. `trade_feature_matrix.jsonl`
6. `trade_feature_matrix.json` (legacy fallback only)

This keeps runtime aligned with the repo's canonical entry-selection outputs first. `entry_candidates.json` and `entry_events.jsonl` are treated as canonical-tier origins, while `scored_tokens.json` and replay-compatible artifacts remain fallback/manual origins. When both replay artifacts exist, the canonical `.jsonl` contract wins over the legacy `.json` fallback.

## Runtime signal contract

Normalized runtime signals carry additive provenance and safety fields, including:

- `runtime_signal_origin`
- `runtime_signal_status`
- `runtime_signal_warning`
- `runtime_signal_confidence`
- `runtime_signal_partial_flag`
- `effective_signal_status`
- `source_artifact`
- `runtime_origin_tier`
- `runtime_pipeline_origin`
- `runtime_pipeline_status`
- `runtime_pipeline_manifest`

See `schemas/runtime_signal.schema.json` for the machine-readable contract.

## Degraded and missing artifact handling

When runtime artifacts are missing, stale, partial, or malformed:

- the loop emits structured events such as `runtime_real_signals_loaded`, `runtime_signal_partial`, `runtime_signal_invalid`, and `runtime_signal_skipped`
- invalid rows are skipped rather than converted into synthetic trades
- partial rows keep their warning/provenance fields
- the overall loop continues unless core runtime configuration is invalid

## Synthetic-dev mode

Synthetic signals still exist only as an explicit development fallback:

```bash
python scripts/run_promotion_loop.py \
  --config config/promotion.default.yaml \
  --mode shadow \
  --run-id demo-runtime \
  --signal-source synthetic-dev \
  --dry-run
```

When enabled, runtime summaries and events label the origin as `synthetic_dev` so it cannot be confused with real-signal mode.

## Smoke path

Use the dedicated smoke runner to write deterministic local entry-candidate fixtures and drive the runtime loop in real-signal mode:

```bash
python scripts/runtime_signal_smoke.py
```

The smoke script writes outputs under `data/smoke/runtime_signal/` and `runs/runtime_signal_smoke/`.

## PR-INFRA-1 provider-safe notes

- X/OpenClaw failures now use a canonical cooldown taxonomy: `captcha`, `timeout`, and `soft_ban` (legacy `blocked` is normalized to `soft_ban`).
- `fetch_x_snapshots()` no longer holds the whole token batch behind a single blocking section; query fetches run with bounded per-query concurrency.
- Status-specific cache TTL is applied at write time so degraded X states cool down faster than healthy snapshots.
- Operational callers can pass promotion state/config through the token payload (or explicit args) so X failures actually activate cooldown policy end-to-end.

## runtime truth layer

Runtime loading prefers replay-produced `trade_feature_matrix.jsonl` when it exists. Repo-produced `entry_candidates.json`, `entry_events.jsonl`, `scored_tokens.json`, and legacy `trade_feature_matrix.json` remain fallback inputs rather than the canonical truth layer.


## Market realism honesty

Runtime and replay-compatible artifacts may now carry explicit market-realism metadata for late discovery, incomplete first-window transaction coverage, realism-aware paper fills, and Token-2022 / transfer-fee safety. These fields are additive warnings and confidence markers; they are meant to prevent runtime and replay layers from presenting partial visibility as if it were native first-window truth.

## Additional market-realism outputs

Runtime entry and fill artifacts may now include:
- `discovery_source`
- `discovery_source_mode`
- `discovery_source_confidence`
- `discovery_lag_penalty_applied`
- `discovery_lag_blocked_trend`
- `discovery_lag_size_multiplier`
- `effective_liquidity_usd`
- `thin_depth_penalty_multiplier`
- `fill_status`
- `execution_warning`

These fields are intended to distinguish late discovery, thin-depth degradation, and catastrophic-liquidity execution from normal healthy paper-flow assumptions.


## Runtime hardening additions

- Active X cooldown now short-circuits `fetch_x_snapshots()` before worker threads start. Cooldown batches emit degraded snapshots with `error_code=cooldown_active` instead of continuing to hit X/OpenClaw.
- Runtime market-state cache is pruned with TTL and max-entry limits, while open-position tokens stay pinned so fallback pricing remains usable on resume.
- Runtime summaries expose `x_cooldown_skip_count`, `runtime_market_cache_pruned_count`, `runtime_market_cache_size`, `runtime_market_cache_pinned_count`, and `http_session_enabled=true`.
- `config/promotion.default.yaml` now includes `runtime_market_cache_ttl_sec` and `runtime_market_cache_max_entries` to bound session-state growth.
