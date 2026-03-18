# Wallet Weighting Calibration

`PR-SW-6` adds deterministic local calibration for wallet-aware unified scoring.

## Purpose

The calibration layer compares `wallet_weighting_mode=off`, `shadow`, and `on` using only local artifacts. It does **not** change entry logic, exit logic, paper execution, or live trading behavior. Its job is to answer one conservative question: should wallet weighting stay off, stay shadowed, be promoted to on, or be rolled back?

## Modes

- `off`: wallet-aware score contribution is disabled.
- `shadow`: wallet-aware contribution is evaluated and reported conservatively without automatic promotion.
- `on`: wallet-aware contribution is fully applied in the unified score layer.

`shadow` remains the safe default unless outcome evidence justifies promotion.

## What gets compared

### Token-level comparison

When scored token artifacts exist, calibration compares:

- score distribution shifts
- rank changes vs `off`
- top-N overlap
- promoted vs demoted token counts
- score-shift concentration
- degraded registry share when present

### Outcome-level comparison

When mode-specific post-run or closed-position artifacts exist, calibration also compares:

- expectancy
- winrate
- median pnl
- mean pnl
- false positive rate
- friction-adjusted expectancy
- drawdown proxy
- outlier concentration

If outcome-level data is unavailable, the report still emits token-level comparison, but the recommendation stays conservative.

## Confidence and outlier policy

Sample confidence is deterministic and based on closed trades:

- `low` if `< 20`
- `medium` if `>= 20 and < 50`
- `high` if `>= 50`

Promotion is blocked when improvements are dominated by a tiny number of trades, when score shifts are too concentrated, or when degraded registry behavior contaminates the sample.

## Recommendation rules

Allowed recommendation values:

- `keep_off`
- `keep_shadow`
- `promote_to_on`
- `rollback_to_off`

Conservative policy summary:

- `promote_to_on` only when `on` beats `off` on expectancy, does not materially worsen false positives or median pnl, has enough sample size, and is not driven by outliers.
- `keep_shadow` when wallet evidence looks promising but proof is incomplete or mixed.
- `rollback_to_off` when `on` materially worsens the sample, is unstable, or registry degradation is too high.
- `keep_off` when there is no stable wallet edge or the inputs are incomplete and shadow evidence is absent.

## Command examples

Basic smoke command:

```bash
python scripts/wallet_calibration_smoke.py \
  --processed-dir data/processed \
  --out-report data/processed/wallet_calibration_report.json \
  --out-md data/processed/wallet_calibration_summary.md \
  --out-recommendation data/processed/wallet_rollout_recommendation.json
```

Explicit mode artifacts:

```bash
python scripts/wallet_calibration_smoke.py \
  --processed-dir data/processed \
  --off-scored data/processed/scored_tokens.off.json \
  --shadow-scored data/processed/scored_tokens.shadow.json \
  --on-scored data/processed/scored_tokens.on.json \
  --off-base-dir data/processed/off \
  --shadow-base-dir data/processed/shadow \
  --on-base-dir data/processed/on
```

## Artifacts written

- `data/processed/wallet_calibration_report.json`
- `data/processed/wallet_calibration_events.jsonl`
- `data/processed/wallet_calibration_summary.md`
- `data/processed/wallet_rollout_recommendation.json`
