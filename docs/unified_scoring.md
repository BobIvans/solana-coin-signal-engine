# PR-6 Unified scoring

`unified_scoring` merges outputs from shortlist, X-validation, enrichment, and rug assessment into a deterministic `final_score` and candidate route.

## Formula

```text
final_score =
  onchain_core
  + early_signal_bonus
  + x_validation_bonus
  - rug_penalty
  - spam_penalty
  + confidence_adjustment
```

`final_score` is clamped to `[0, 100]`.

## Component caps

- `onchain_core`: `0..45`
- `early_signal_bonus`: `0..25`
- `x_validation_bonus`: `0..14`
- `rug_penalty`: derived from `rug_score * 30` (+ verdict modifiers)
- `spam_penalty`: `0..8`

## Normalizers

- `normalize_unit_interval`
- `normalize_capped`
- `normalize_inverse`
- `normalize_log_scaled`

All normalizers are deterministic, safe on `None`, and capped to `[0, 1]`.

## Routing thresholds

- `IGNORE` if score below `UNIFIED_SCORE_WATCH_THRESHOLD`
- `WATCHLIST` if score in `[WATCH, ENTRY)`
- `ENTRY_CANDIDATE` if score >= `UNIFIED_SCORE_ENTRY_THRESHOLD`

## Downgrade and override rules

Hard overrides to `IGNORE`:

- `rug_verdict == IGNORE`
- `mint_revoked == false`
- `dev_sell_pressure_5m >= RUG_DEV_SELL_PRESSURE_HARD`
- critical fields missing when fail-open is disabled

Downgrades from `ENTRY_CANDIDATE` to `WATCHLIST`:

- degraded X status
- partial enrichment
- partial rug status
- heuristic-heavy score context

## Heuristic discount policy

Heuristic fields (`holder_entropy_est`, `first50_holder_conc_est`, and uncertain migration speed) receive a confidence multiplier defaulting to `0.75`, floored by `UNIFIED_SCORE_HEURISTIC_CONFIDENCE_FLOOR`.

## Artifacts

- `data/processed/scored_tokens.json`
- `data/processed/score_events.jsonl`

The event log is append-only and emits:

- `score_started`
- `score_components_computed`
- `score_routed`
- `score_downgraded`
- `score_hard_override`
- `score_completed`
