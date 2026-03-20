# Bundle evidence

## What “real bundle evidence” means here

This repository now prefers explicit early-launch bundle evidence when the input payload includes structured bundle activity records such as `bundle_activity`, `bundle_events`, `bundle_flows`, `bundle_attempts`, or `bundle_evidence`. The collector normalizes those records into a stable schema with provenance, timestamps, actor linkage, landed/failed status, tips, retry linkage, and block context.

This is **evidence-first**, not evidence-only:

- if usable structured evidence is present, bundle metrics are derived from that evidence;
- if evidence is missing, malformed, partial, or too sparse, the system falls back to the prior heuristic detector;
- if neither source is usable, bundle fields stay `None` or neutral-safe.

## What remains heuristic

The repo does **not** claim complete institutional-grade landed bundle attribution.

Still heuristic in this PR:

- grouping raw `bundle_transactions` by slot or timestamp when real evidence is weak or absent;
- any bundle value/timing derived only from shallow transaction grouping;
- downstream interpretation of bundle aggression/risk that depends on partial source coverage.

## Normalized evidence schema

See `schemas/bundle_evidence.schema.json`.

Key top-level fields:

- `bundle_evidence_status`
- `bundle_evidence_source`
- `bundle_evidence_warning`
- `bundle_evidence_collected_at`
- `bundle_window_anchor_ts`
- `bundle_window_sec`
- `bundle_records`
- `bundle_evidence_summary`

Key per-record fields include:

- `record_id`, `group_id`, `attempt_id`, `retry_of`
- `token_address`, `pair_address`
- `slot`, `block`, `timestamp`
- `actor`, `wallet`
- `status` (`landed`, `failed`, `unknown`)
- `side`
- `notional`, `tip`, `priority_fee`
- `provenance`

## Routing behavior

`collectors.bundle_detector.detect_bundle_metrics_for_pair()` now routes as follows:

1. collect and normalize real evidence;
2. derive metrics from evidence when the evidence is usable;
3. otherwise run the legacy heuristic detector unchanged;
4. preserve existing bundle contract fields for downstream consumers;
5. add additive provenance/status fields.

## Output fields

Existing downstream bundle fields remain available:

- `bundle_count_first_60s`
- `bundle_size_value`
- `unique_wallets_per_bundle_avg`
- `bundle_timing_from_liquidity_add_min`
- `bundle_success_rate`
- `bundle_composition_dominant`
- `bundle_tip_efficiency`
- `bundle_failure_retry_pattern`
- `cross_block_bundle_correlation`
- `bundle_wallet_clustering_score`
- `cluster_concentration_ratio`
- `num_unique_clusters_first_60s`
- `creator_in_cluster_flag`

Additive provenance/status fields:

- `bundle_evidence_status`
- `bundle_evidence_source`
- `bundle_evidence_warning`
- `bundle_evidence_confidence`
- `bundle_metric_origin`

Allowed `bundle_metric_origin` values:

- `direct_evidence`
- `heuristic_evidence`
- `missing`

Legacy aliases such as `real_evidence`, `raw_bundles`, and `heuristic_fallback` may still be normalized internally during migration at ingestion boundaries, but fresh emitted artifacts must not use those aliases. Fresh emitted `bundle_metric_origin` values remain canonical-only.

## Smoke artifacts

Run:

```bash
python scripts/bundle_evidence_smoke.py
```

Artifacts:

- `data/smoke/bundle_evidence.smoke.json`
- `data/smoke/bundle_evidence_status.json`
- `data/smoke/bundle_evidence_events.jsonl`
