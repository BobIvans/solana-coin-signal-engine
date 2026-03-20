# Analyzer slices (PR-AN-2)

`analytics/analyzer_slices.py` extends the post-run analyzer with richer, reproducible failure-mode slices over replay/paper artifacts.

## What analyzer slices are

Analyzer slices are additive post-run summaries that group trades by a specific diagnostic pattern and then compute realized outcome metrics for that slice. They are designed to answer questions such as:

- which TREND promotions failed quickly;
- which SCALP trades looked trend-capable in hindsight;
- whether creator-linked or concentrated clusters underperformed;
- whether weak continuation signals aligned with poor outcomes;
- whether degraded X was broadly weak or merely mixed;
- whether certain exit/failure patterns consistently protected or hurt realized PnL.

This module is intentionally **not** an optimizer. It does not auto-apply settings changes.

## Slice families

The current analyzer writes compact machine-readable groups for:

- `regime`
  - `trend_promoted_but_failed_fast`
  - `scalp_should_have_been_trend`
  - `trend_vs_scalp_expectancy`
  - `trend_vs_scalp_winrate`
  - `trend_vs_scalp_median_pnl`
  - `regime_confidence_buckets`
  - `regime_blocker_frequency`
- `cluster_bundle`
  - `single_cluster_underperformance`
  - `multi_cluster_outperformance`
  - `creator_linked_underperformance`
  - `high_cluster_concentration_underperformance`
  - `bundle_sell_heavy_underperformance`
  - `retry_pattern_underperformance`
  - `cross_block_correlation_slices`
  - `bundle_tip_efficiency_slices`
- `continuation`
  - `failed_liquidity_refill_underperformance`
  - `weak_reentry_underperformance`
  - `shock_not_recovered_underperformance`
  - `cluster_distribution_failure_slices`
  - `organic_buyer_flow_positive_slices`
  - `smart_wallet_dispersion_supportive_slices`
  - `x_author_velocity_supportive_slices`
- `degraded_x`
  - `degraded_x_vs_healthy_x`
  - `degraded_x_salvage_cases`
  - `degraded_x_false_positive_rate`
  - `degraded_x_small_size_performance`
- `exit_failure`
  - `cluster_dump_exit_performance`
  - `creator_cluster_exit_risk_performance`
  - `bundle_failure_spike_exit_performance`
  - `retry_manipulation_exit_performance`
  - `partial_exit_vs_full_exit_outcomes`

## Sample-size honesty policy

Every slice emits explicit sample counts and keeps the distinction between **observed** and **recommended** evidence.

Rules:

- If a slice has no usable rows, it is `unavailable`.
- If a slice exists but has fewer rows than the configured minimum sample, it is `insufficient_sample` with `confidence=low`.
- Missing optional fields reduce coverage and add warnings instead of fabricating conclusions.
- Recommendation hints are only surfaced as manual-review guidance when the slice clears the minimum sample threshold.

This means tiny or partial slices can still be inspected, but they should not be treated as strong evidence.

## Output contract

The analyzer writes:

- `data/processed/analyzer_slices.json`
- `data/processed/post_run_summary.json`
- `data/processed/post_run_recommendations.json`
- `data/processed/post_run_report.md`

`analyzer_slices.json` is validated by the additive contract in `schemas/analyzer_slices.schema.json`.

Each slice aims to expose these machine-readable fields when applicable:

- `slice_name`
- `sample_size`
- `supporting_rows`
- `winrate`
- `expectancy`
- `median_pnl_pct`
- `mean_pnl_pct`
- `false_positive_rate`
- `confidence`
- `status`
- `warnings`
- `interpretation`
- `recommendation_hint`

Some comparison slices also include family-specific fields such as `expectancy_gap`, `trend_expectancy`, or `degraded_false_positive_rate`.

## Recommendation policy

Recommendations remain conservative and manual-only:

- no config values are auto-written back into runtime strategy logic;
- recommendation text is framed as a review hint, not a mandate;
- low-sample slices become warnings rather than strong actions;
- missing optional data never turns into synthetic confidence.

Typical hints look like:

- “consider tightening trend promotion when creator-linked evidence is present”
- “consider increasing caution for high cluster concentration”
- “consider keeping degraded X in reduced-size mode”
- “consider not promoting low-refill / weak-reentry cases to trend”

## Data-source behavior

The analyzer prefers merged `trade_feature_matrix.jsonl` rows when available because they contain richer regime, cluster, bundle, continuation, and degraded-X context.

Fallback behavior:

- if the feature matrix is missing, the analyzer falls back to reconstructed closed positions;
- if the matrix is partial, only the slices with usable fields are populated;
- if fields are malformed or missing, warnings are emitted and the slice remains partial or unavailable.

## Smoke script

Run the deterministic smoke fixture:

```bash
python scripts/analyzer_slices_smoke.py
```

This writes smoke artifacts under `data/smoke/` so the richer slice output can be inspected without replaying a full run.
