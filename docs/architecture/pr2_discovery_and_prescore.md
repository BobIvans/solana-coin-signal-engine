# PR-2: DEX discovery and fast pre-score

## Scope

PR-2 introduces the first real discovery layer:

1. Fetch Solana pairs from DEXScreener.
2. Normalize pair payloads defensively.
3. Filter pairs using cheap and deterministic rules.
4. Compute a fast pre-score from DEX-only metrics.
5. Persist raw artifacts, processed candidates, shortlist, and smoke status.

Out of scope: browser automation, Helius/RPC enrichment, wallet intelligence, rug engine, and trading logic.

## Pipeline

`run_discovery_once()` performs one cycle:

- fetch raw pairs from provider
- append `data/raw/discovery_raw.jsonl`
- normalize each pair
- apply filtering (age, liquidity, txns, paid order)
- compute `fast_prescore`
- sort deterministically by score descending
- build top-k shortlist for next layers
- persist `discovery_candidates.json`, `shortlist.json`, `discovery_status.json`

## Fast pre-score

Current metrics:

- `volume_mcap_ratio`
- `volume_velocity_proxy`
- `buy_pressure`
- `liquidity_quality_norm`
- `age_freshness_norm`
- `boost_penalty`

Placeholders kept as `null` for future PRs:

- `bundle_cluster_score`
- `first30s_buy_ratio`
- `priority_fee_avg_first_min`
- `x_validation_score`
- `smart_wallet_hits`
- `rug_score`

Formula:

```python
fast_prescore = (
    0.28 * volume_mcap_ratio_norm +
    0.22 * buy_pressure_norm +
    0.18 * volume_velocity_proxy_norm +
    0.18 * liquidity_quality_norm +
    0.14 * age_freshness_norm
) * 100 - boost_penalty
```

## Degraded behavior

If provider returns an empty list or network fails, discovery does not crash:

- artifacts still get written
- smoke status becomes `degraded`
- process exits successfully in smoke mode
