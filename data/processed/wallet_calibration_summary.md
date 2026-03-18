# Wallet Weighting Calibration Summary

Compared modes: off, shadow, on

## Key metrics

| Mode | Tokens | Avg score Δ vs off | Top-N overlap | Expectancy | Winrate | Median pnl | False positive rate |
| --- | --- | --- | --- | --- | --- | --- | --- |
| off | 3 | - | - | 0.03 | 0.6 | 0.1 | 0.4 |
| shadow | 3 | 0.666667 | 3 | 0.072 | 0.6 | 0.12 | 0.4 |
| on | 3 | 1.166667 | 3 | 0.142 | 0.6 | 0.18 | 0.4 |

## Major trade-offs

- shadow_vs_off: Δexpectancy=0.042, Δfalse_positive_rate=0.0, Δmedian_pnl=0.02
- on_vs_off: Δexpectancy=0.112, Δfalse_positive_rate=0.0, Δmedian_pnl=0.08

## Recommendation

- Recommendation: **keep_shadow**
- Confidence: **low**
- Safe default mode: **shadow**

## Cautions / blocking risks

- No additional blocking risks were detected beyond standard conservative rollout policy.

## Next actions

- Keep `safe_default_mode=shadow` until the recommendation is explicitly reviewed.
- Set `next_mode=shadow` only after checking the machine-readable report and risks.
