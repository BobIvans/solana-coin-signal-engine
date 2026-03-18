# Wallet Registry Layer

This PR builds a deterministic wallet registry from the PR-SW-1 manual normalization artifact at `data/registry/normalized_wallet_candidates.json`.

## Purpose

The registry layer turns normalized manual wallet candidates into three separate outputs:

- `smart_wallets.json`: the full stored registry, including rejected rows for auditability.
- `active_watchlist.json`: a bounded monitoring subset for routine free-first wallet tracking.
- `hot_wallets.json`: a very small high-priority subset suitable for the most focused monitoring budget.

## Free-first policy

Storing up to roughly **5000** wallet records is acceptable because the stored registry is just a deterministic local artifact.

Monitoring **5000 hot wallets is not acceptable** because hot monitoring is the expensive subset. This PR therefore keeps the persistent registry large while bounding the actively monitored sets:

- default `max_active = 250`
- default `max_watchlist = 500`
- default `max_hot = 100`

That split preserves broad local coverage while keeping the expensive hot path intentionally small.

## Inputs

Only PR-SW-1 normalized manual candidates are used.

- Input artifact: `data/registry/normalized_wallet_candidates.json`
- No network validation
- No external repository integrations
- No replay promotion
- No enrichment integration
- No unified score integration

## Deterministic scoring

`registry_score` is local-only and deterministic:

```text
registry_score =
  0.45 * manual_priority_score
+ 0.20 * source_count_score
+ 0.15 * tag_quality_score
+ 0.10 * notes_quality_score
+ 0.10 * format_confidence_score
```

Scoring inputs:

- `manual_priority_score = 1.0` for manual seeds, else `0.0`
- `source_count_score = min(source_count, 3) / 3`
- `tag_quality_score` uses deterministic recognized tags and caps the combined tag score at `1.0`
- `notes_quality_score = 1.0` when notes are present, else `0.0`
- `format_confidence_score = 1.0` only for normalized plausible Solana wallet strings

Recognized deterministic tags:

- `high_conviction`: `+0.30`
- `replay_winner`: `+0.25`
- `scalp_candidate`: `+0.15`
- `trend_candidate`: `+0.15`
- `tier1_hint`: `+0.10`
- `tier2_hint`: `+0.05`
- `manual_bulk`: `+0.00`

## Regime fit

This PR also computes two deterministic local regime-fit values from tags and notes only:

- `regime_fit_scalp`
- `regime_fit_trend`

Examples:

- `scalp_candidate` lifts scalp fit
- `trend_candidate` lifts trend fit
- `replay_winner` lifts both slightly
- missing tags/notes remain low-confidence and near neutral

## Filtering rules

1. Invalid wallet format -> `rejected`
2. Sparse but valid manual seeds are preserved as `watch`
3. Manual seeds default toward `watch` unless promoted by score and rank
4. No wallet reaches `tier_1` without `high_conviction` or `replay_winner`
5. Rejections are still logged in `filter_events.jsonl`

## Tier rules

Default deterministic thresholds:

- `tier_1`: `registry_score >= 0.80` **and** explicit `high_conviction` or `replay_winner`
- `tier_2`: `registry_score >= 0.60`
- `tier_3`: `registry_score >= 0.35`, or sparse valid manual seed retention
- `rejected`: invalid or below threshold

## Status rules

- `active`: bounded top-scored subset of valid candidates with enough score to be promotion-eligible later
- `watch`: valid records that are retained but not currently promoted into the active subset
- `rejected`: invalid or too-low-confidence rows

## Ordering and subset selection

`hot_wallets.json` is sorted by:

1. tier strength (`tier_1`, `tier_2`, `tier_3`)
2. `hot_priority` descending
3. `registry_score` descending
4. wallet ascending

`active_watchlist.json` is sorted by:

1. status (`active` before `watch`)
2. `watch_priority` descending
3. `registry_score` descending
4. wallet ascending

## Output contracts

Added schemas:

- `schemas/smart_wallet_registry.schema.json`
- `schemas/active_watchlist.schema.json`
- `schemas/hot_wallets.schema.json`

Added artifacts:

- `data/registry/smart_wallets.json`
- `data/registry/filter_events.jsonl`
- `data/registry/active_watchlist.json`
- `data/registry/hot_wallets.json`

## CLI

```bash
python scripts/build_wallet_registry.py \
  --in data/registry/normalized_wallet_candidates.json \
  --out data/registry/smart_wallets.json \
  --watch-out data/registry/active_watchlist.json \
  --hot-out data/registry/hot_wallets.json
```

Optional bounds:

- `--max-active 250`
- `--max-watchlist 500`
- `--max-hot 100`
- `--event-log data/registry/filter_events.jsonl`
- `--generated-at 2024-01-01T00:00:00Z`

## What this PR does not do yet

- No on-chain enrichment changes
- No changes to `analytics/smart_wallet_hits.py`
- No unified score integration
- No replay evaluation or replay-based promotion/demotion
- No scheduler/background monitoring
- No entry or exit logic changes
- No live trading behavior changes
