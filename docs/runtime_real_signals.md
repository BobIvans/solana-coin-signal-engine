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

## Artifact precedence

The runtime loader uses this precedence order:

1. `entry_candidates.json`
2. `entry_candidates.smoke.json`
3. `entry_events.jsonl`
4. `scored_tokens.json`
5. `trade_feature_matrix.jsonl`
6. `trade_feature_matrix.json` (legacy fallback only)

This keeps runtime aligned with the repo's existing entry-selection outputs first, while still allowing scored-token or replay-compatible artifacts to drive the loop only when they already provide enough decision-support fields. When both replay artifacts exist, the canonical `.jsonl` contract wins over the legacy `.json` fallback.

## Runtime signal contract

Normalized runtime signals carry additive provenance and safety fields, including:

- `runtime_signal_origin`
- `runtime_signal_status`
- `runtime_signal_warning`
- `runtime_signal_confidence`
- `runtime_signal_partial_flag`
- `effective_signal_status`
- `source_artifact`

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
