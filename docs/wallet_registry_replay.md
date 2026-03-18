# Wallet Registry Replay Validation

This PR adds a deterministic replay-validation layer for the wallet registry built in PR-SW-2.

## What replay validation does

Replay validation loads the existing registry from `data/registry/smart_wallets.json`, then evaluates locally available replay, paper-trading, or post-run artifacts to determine whether each wallet has wallet-specific evidence that supports a stronger tier, a weaker tier, or no change.

The output is **validation only**:

- it produces validated registry artifacts
- it emits append-only promotion/demotion decision events
- it does **not** modify live entry logic, exit logic, or any scheduler behavior

## Inputs

Required:

- `data/registry/smart_wallets.json`
- at least one local replay-style artifact with wallet-specific attribution

Supported local replay inputs include:

- `data/processed/scored_tokens.json`
- `data/processed/paper_trades.json`
- `data/processed/paper_trades.jsonl`
- `data/processed/post_run_analysis.json`
- `data/processed/replay_*.json`
- `data/processed/*.csv`
- other local `.json` / `.jsonl` replay-style artifacts already present in `data/processed`

The loader prioritizes the common artifact names above, but also scans other local `.json`, `.jsonl`, and `.csv` files in `data/processed` so failures can report what was actually inspected.

If no usable wallet-specific replay evidence exists, the CLI fails clearly instead of silently writing misleading outputs.

## Wallet-specific vs aggregate evidence

Promotion and demotion decisions require **wallet-specific** evidence.

Examples of wallet-specific evidence:

- a replay token row with `wallets`, `wallet_hits`, or `matched_wallets`
- a processed trade row with wallet lists nested under `wallet_features`
- per-wallet enrichment carried into local replay artifacts

Examples that are **not enough** by themselves:

- `smart_wallet_hit_count`
- `wallet_hit_count`
- any aggregate count that does not identify which wallet was involved

If a local replay record only proves that *some* smart wallet hit the token, but does not identify *which* wallet, the record is ignored for wallet-specific promotion decisions.

## Why sparse evidence does not imply rejection

Sparse replay evidence means the wallet has not yet earned wallet-specific confidence. It does **not** imply the wallet is bad.

This PR therefore uses `watch_pending_validation` when a wallet is structurally valid but lacks enough wallet-specific replay data.

That status means:

- keep the wallet in the registry
- do not silently promote it
- wait for stronger wallet-level evidence before escalating trust

## Replay evidence model

For each wallet, the validator computes a deterministic `replay_evidence` object with fields including:

- `wallet`
- `replay_tokens_seen`
- `replay_hits`
- `positive_outcome_hits`
- `negative_outcome_hits`
- `median_pnl_pct`
- `mean_pnl_pct`
- `winrate`
- `false_positive_rate`
- `expectancy`
- `avg_hold_sec`
- `evidence_score`
- `evidence_confidence`
- `promotion_decision`
- `promotion_reason`
- `last_validated_at`

Null-safe defaults are used when optional replay fields are unavailable.

## Evidence score

The evidence score is deterministic and bounded:

```text
evidence_score = confidence_cap * (
  0.35 * normalized_expectancy
+ 0.25 * normalized_winrate
+ 0.20 * normalized_median_pnl
+ 0.10 * normalized_sample_size
+ 0.10 * inverse_false_positive_rate
)
```

Confidence caps prevent low-sample overconfidence:

- `low` confidence: sample `< 5`
- `medium` confidence: sample `>= 5` and `< 15`
- `high` confidence: sample `>= 15`

## Promotion rules

Deterministic promotion policy:

1. `tier_2 -> tier_1` only if all of the following are true:
   - wallet-specific confidence is `medium` or `high`
   - `replay_tokens_seen >= 10`
   - `expectancy > 0`
   - `false_positive_rate <= 0.35`
   - `evidence_score >= 0.80`
2. `tier_3 -> tier_2` only if:
   - `replay_tokens_seen >= 5`
   - `expectancy >= 0`
   - `evidence_score >= 0.60`

No wallet may be promoted from import tags alone.

## Demotion rules

Deterministic demotion policy:

1. `tier_1 -> tier_2` if `replay_tokens_seen >= 8` and any of the following are true:
   - `expectancy <= 0`
   - `false_positive_rate > 0.45`
   - `evidence_score < 0.65`
2. `tier_2 -> tier_3` if `replay_tokens_seen >= 5` and either:
   - `evidence_score < 0.45`
   - `expectancy < 0`

## Status model

Validated registry statuses are:

- `active`
- `watch`
- `watch_pending_validation`
- `rejected`

Validated tiers remain:

- `tier_1`
- `tier_2`
- `tier_3`
- `rejected`

## Outputs

Artifacts written by replay validation:

- `data/registry/replay_validation_report.json`
- `data/registry/promotion_events.jsonl`
- `data/registry/smart_wallets.validated.json`
- `data/registry/hot_wallets.validated.json`
- `schemas/replay_validation_report.schema.json`
- `schemas/smart_wallet_registry_validated.schema.json`

`promotion_events.jsonl` is append-only and records every explicit replay-based decision. There is no silent promotion path.

## Hot wallet validated output

`hot_wallets.validated.json` contains only wallets with `new_status=active`.

The validated hot set is bounded and sorted by:

1. tier strength (`tier_1`, `tier_2`, `tier_3`)
2. evidence confidence (`high`, `medium`, `low`)
3. `evidence_score` descending
4. `registry_score` descending
5. wallet ascending

Default bound:

- `max_hot = 100`

## Commands

```bash
python scripts/eval_wallet_registry_replay.py \
  --registry data/registry/smart_wallets.json \
  --processed-dir data/processed \
  --out-report data/registry/replay_validation_report.json \
  --out-registry data/registry/smart_wallets.validated.json \
  --out-hot data/registry/hot_wallets.validated.json
```

Optional flags:

- `--event-log data/registry/promotion_events.jsonl`
- `--generated-at 2026-03-18T00:00:00Z`
- `--max-hot 100`
- `--min-sample-tier2 5`
- `--min-sample-tier1 10`

## What this PR does not do yet

- no changes to PR-4 enrichment logic
- no changes to `analytics/smart_wallet_hits.py`
- no unified score integration
- no entry or exit logic changes
- no live execution
- no scheduler or background loop
- no automatic external refresh
- no ML or retraining
