# PR-SCORE-1b canonical unified scoring

This repository now uses a **single canonical unified scorer**.

## Source of truth

- `analytics/unified_score.py` is the only base-score and regime-routing engine.
- `analytics/wallet_weighting.py` is the shared wallet-weighting layer used by that engine.
- `scoring/unified_score.py` remains as a thin adapter for CLI/batch/smoke compatibility.

There is no separate fallback base-score math path anymore inside the adapter.

## Wallet weighting mode

`wallet_weighting_mode` supports:

- `off`: canonical base score is returned unchanged
- `shadow`: wallet component is computed and logged, but `final_score` stays equal to `final_score_pre_wallet`
- `on`: wallet component is computed, capped, and applied exactly once inside the canonical scorer

Default rollout mode is `shadow`.

## Honesty and degraded behavior

- Wallet evidence is consumed from scored token inputs and/or nested `wallet_features`
- If `wallet_registry_status != "validated"`, wallet adjustment is forced to zero and `wallet_weighting_effective_mode` becomes `degraded_zero`
- Wallet contribution is bounded so it cannot dominate the canonical base score
- `wallet_adjustment` remains as a compatibility shim for downstream readers and calibration utilities

## Deterministic `scored_at`

The canonical scorer resolves timestamps in this order:

1. explicit `scored_at` argument
2. token fields such as `scored_at`, `score_timestamp`, `timestamp`, `snapshot_ts`, `observed_at`, `as_of`
3. fallback to current UTC time

That keeps replay/smoke/tests deterministic while preserving live runtime behavior.

## Canonical scored fields

Each scored token now includes, in the main unified score contract:

- `final_score_pre_wallet`
- `final_score`
- `wallet_weighting_mode`
- `wallet_weighting_effective_mode`
- `wallet_registry_status`
- `wallet_score_component_raw`
- `wallet_score_component_applied`
- `wallet_score_component_applied_shadow`
- `wallet_score_component_capped`
- `wallet_score_component_reason`
- `wallet_score_explain`
- `wallet_adjustment`

Main schema:

- `schemas/unified_score.schema.json`

Compatibility schema:

- `schemas/unified_score.wallet_weighting.schema.json`

## Smoke example

```bash
python scripts/unified_score_smoke.py
```

Recommended rollout path:

1. `off`
2. `shadow`
3. `on`
