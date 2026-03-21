# Offline feature importance

PR-ML-1 adds an **offline-only** feature importance layer over replay-derived trade matrices such as `trade_feature_matrix.jsonl`.

## What it does

The offline analysis module:

- loads replay matrices conservatively
- derives explicit offline targets
- computes per-feature and grouped feature rankings
- reports sample size, missingness, exclusions, and caveats
- writes machine-readable JSON plus a markdown summary

## What it does not do

This layer is intentionally **not** an online model.

It does **not**:

- influence runtime entry, exit, or promotion decisions
- auto-tune configs
- auto-apply recommendations
- claim causal proof from associations

All outputs are marked with:

- `analysis_only = true`
- `not_for_online_decisioning = true`
- `association_only = true`

## Supported offline targets

### `profitable_trade_flag`
Binary target derived from positive `net_pnl_pct`.

### `trend_success_flag`
Binary target for stronger trend-like outcomes using a conservative combination of:

- `trend_survival_15m`
- `mfe_pct_240s`
- `net_pnl_pct`
- `time_to_first_profit_sec`

### `fast_failure_flag`
Binary target for rapid bad outcomes / false positives using a conservative combination of:

- negative `net_pnl_pct` with short `hold_sec`
- weak `mae_pct_240s`
- early-failure exit reason hints

These targets exist only for offline calibration and interpretation.

## Methods used

This PR keeps the methodology lightweight and reproducible:

- **numeric features:** absolute normalized mean gap between positive and negative target rows
- **categorical features:** weighted deviation from the baseline target rate by category

The output separates target definitions, per-feature rows, grouped summaries, and warnings so humans can inspect the evidence quality.

## Feature groups

At minimum the analysis groups features into:

- bundle features
- cluster features
- continuation features
- wallet features
- X features
- regime features
- exit features
- risk features
- friction features
- meta features

Grouped importance helps reviewers see whether signal families look broadly useful, weak, noisy, or suspicious.

## Honesty / caveats

Every output includes:

- sample size
- positive / negative class counts
- feature coverage ratio
- missing ratio
- excluded row counts
- malformed row counts
- warnings for low sample or low coverage

Important caveats:

- association does not imply causation
- sparse replay coverage can distort rankings
- imbalanced targets can overstate weak patterns
- low-coverage features should be treated as diagnostic hints only

## Artifacts

Typical output artifacts:

- `feature_importance.json`
- `feature_importance_summary.md`

Smoke outputs are written to:

- `data/smoke/offline_feature_importance.json`
- `data/smoke/offline_feature_importance_summary.md`

## Smoke path

Run the deterministic smoke path locally:

```bash
python scripts/offline_feature_importance_smoke.py
```

The smoke path uses fixture-backed replay matrix data, writes offline artifacts, and prints a compact JSON summary.

## Historical price context reminder

Offline feature analysis should treat replay price paths as externally collected historical context. Missing or truncated price history must remain explicit in artifacts instead of being reconstructed or silently invented downstream.

## canonical matrix contract

Offline ML and feature-importance workflows should use canonical `trade_feature_matrix.jsonl` rows. Legacy matrix JSON files are compatibility-only inputs for older local fixtures.
