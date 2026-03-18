# PR-SW-5 wallet-aware unified scoring

This repository now supports wallet-aware weighting for unified score in a **bounded**, **deterministic**, and **feature-flagged** way.

## Wallet weighting mode

`wallet_weighting_mode` supports:

- `off`: legacy-like score path; wallet adjustment is forced to zero
- `shadow`: wallet adjustment is computed and logged, but `final_score` stays equal to `final_score_pre_wallet`
- `on`: wallet adjustment is computed, capped, and applied

Default rollout mode is `shadow`.

## Honesty and degraded behavior

- Wallet evidence is consumed only from `enriched_tokens.json`
- No direct registry-artifact dependency is introduced in the scoring layer
- If `wallet_registry_status != "validated"`, wallet adjustment is forced to zero and `wallet_weighting_effective_mode` becomes `degraded_zero`
- `smart_wallet_netflow_bias` is passed through for explainability only; it is not directionally inferred when null
- Wallet contribution is bounded so it cannot dominate the base score

## New scored fields

Each scored token now includes:

- `final_score_pre_wallet`
- `wallet_weighting_mode`
- `wallet_weighting_effective_mode`
- `wallet_score_component_raw`
- `wallet_score_component_applied`
- `wallet_score_component_capped`
- `wallet_score_component_reason`
- `wallet_registry_status`
- `wallet_score_explain`

A supplemental schema for the wallet-weighted output is provided at:

- `schemas/unified_score.wallet_weighting.schema.json`

## Smoke example

```bash
python scripts/unified_score_smoke.py \
  --shortlist data/processed/shortlist.json \
  --x-validated data/processed/x_validated.json \
  --enriched data/processed/enriched_tokens.json \
  --rug-assessed data/processed/rug_assessed_tokens.json \
  --wallet-weighting-mode shadow
```

Recommended rollout path:

1. `off`
2. `shadow`
3. `on`

