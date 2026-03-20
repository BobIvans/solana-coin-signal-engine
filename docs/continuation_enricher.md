# Continuation enricher

## Purpose

The continuation enricher turns the repo's short-horizon continuation contract into a reusable evidence layer. It does **not** redesign downstream scoring, regime, or exit logic. It makes the existing continuation fields real end-to-end by producing them consistently, attaching provenance, and degrading safely when evidence is incomplete.

Primary module:

- `analytics/continuation_enricher.py`

Primary outputs:

- continuation metrics
- continuation provenance/status/confidence fields
- structured continuation events
- smoke artifacts under `data/smoke/`

## Continuation metrics by evidence type

### Transaction-derived

Computed from launch-window transaction evidence:

- `net_unique_buyers_60s`
- `liquidity_refill_ratio_120s`
- `cluster_sell_concentration_120s`
- `seller_reentry_ratio`
- `liquidity_shock_recovery_sec`

These are still calculated by helper logic in `analytics/short_horizon_signals.py`, but orchestration now lives in the continuation enricher.

Transfer-derived continuation metrics use **only explicitly successful transactions** (`success is True`). Failed, reverted, or unknown-success transactions are intentionally ignored so the layer does not fabricate organic buyer flow, cluster distribution, or seller re-entry from unconfirmed execution attempts.

Transaction-side participant roles are also filtered through continuation participant hygiene. LP/pool/router/vault/system-like actors do not count as organic buyers or sellers by default, and wallets that appear on both sides of the same transaction are treated conservatively as ambiguous for that transaction instead of silently boosting continuation strength.

### X-derived

Computed when usable X snapshot/card timestamps are present:

- `x_author_velocity_5m`

If X snapshots are missing or malformed, the enricher leaves the metric as `null`, marks the input as missing/partial, and preserves fail-open behavior.

### Wallet-registry-derived

Computed when both validated wallet-registry evidence and matching hit wallets are available:

- `smart_wallet_dispersion_score`

If wallet registry evidence is absent or too thin, the metric is left unset instead of fabricated.

## Provenance and honesty fields

The continuation layer adds these fields additively:

- `continuation_status`
- `continuation_warning`
- `continuation_confidence`
- `continuation_metric_origin`
- `continuation_coverage_ratio`
- `continuation_inputs_status`
- `continuation_warnings`
- `continuation_available_evidence`
- `continuation_missing_evidence`

Typical semantics:

- `complete`: all continuation metrics were produced with ready inputs.
- `partial`: some metrics were produced, but at least one evidence lane is missing or degraded.
- `missing`: no continuation metrics could be honestly produced.

`continuation_metric_origin` stays conservative:

- `computed_from_tx`
- `computed_from_x`
- `computed_from_wallet_registry`
- `mixed_evidence`
- `partial`
- `missing`

## Fallback behavior

The continuation enricher is intentionally fail-open.

It does **not**:

- invent tx-derived continuation strength when transaction evidence is absent
- treat missing X evidence as negative momentum by default
- pretend wallet-registry support exists without validated matches
- crash the enrichment stage on sparse or malformed payloads

Instead it:

- leaves unavailable metrics as `null`
- emits explicit warnings/status
- lowers confidence when evidence is sparse
- preserves downstream contract compatibility
- prefers honest partial evidence over counting ambiguous or technical transfer actors as organic continuation

## Artifacts

### Enrichment pipeline

`scripts/onchain_enrichment_smoke.py` now routes continuation production through the continuation enricher and appends continuation lifecycle events to `data/processed/onchain_enrichment_events.jsonl`.

### Dedicated smoke

Run:

```bash
python scripts/continuation_smoke.py
```

Artifacts written:

- `data/smoke/continuation_enrichment.smoke.json`
- `data/smoke/continuation_status.json`
- `data/smoke/continuation_events.jsonl`

## Schema

Machine-readable payload schema:

- `schemas/continuation_enrichment.schema.json`

This schema covers:

- metadata / contract version / generated timestamp
- token + pair linkage
- continuation metrics
- provenance / warnings / confidence
- event records

## Known limitations

- Continuation confidence is still evidence-limited; it is a conservative summary, not a calibrated probabilistic estimate.
- `x_author_velocity_5m` depends on timestamped X cards being available upstream.
- `smart_wallet_dispersion_score` depends on validated wallet-registry coverage and matched hit wallets.
- The continuation layer remains heuristic in places because upstream public evidence is often incomplete.
