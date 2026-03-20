# solana-memecoin-signal-engine

PR-4 extends the engine with an on-chain enrichment layer that merges shortlist + X-validated tokens and computes fast holder/dev/launch-path/smart-wallet metrics.

## What PR-4 includes

- Solana RPC client wrappers (`collectors/solana_rpc_client.py`)
- Helius client wrappers (`collectors/helius_client.py`)
- Holder metrics (`analytics/holder_metrics.py`)
- Dev activity metrics (`analytics/dev_activity.py`)
- Launch path heuristics (`analytics/launch_path.py`)
- Smart wallet hit scoring (`analytics/smart_wallet_hits.py`)
- Schema contract (`schemas/enriched_token.schema.json`)
- Smoke runner (`scripts/onchain_enrichment_smoke.py`)
- docs (`docs/onchain_enrichment.md`)

## Run on-chain enrichment smoke

```bash
python scripts/onchain_enrichment_smoke.py \
  --shortlist data/processed/shortlist.json \
  --x-validated data/processed/x_validated.json
```

## Run tests

```bash
pytest -q
```

## Data artifacts

Artifacts are created under `data/processed/`:

- `shortlist.json`
- `x_validated.json`
- `enriched_tokens.json`
- `onchain_enrichment_events.jsonl`

## Metric honesty policy

- `top20_holder_share` is exact for top-20 accounts from RPC.
- `first50_holder_conc_est` and `holder_entropy_est` are **heuristics** by contract.
- launch-path stays heuristic (`*_est`, `*_score`) in this PR.


## PR-5 rug safety engine

PR-5 adds a deterministic rug safety layer over `enriched_tokens.json` and writes:

- `data/processed/rug_assessed_tokens.json`
- `data/processed/rug_events.jsonl`

Run smoke:

```bash
python scripts/rug_engine_smoke.py --enriched data/processed/enriched_tokens.json
```

Policy highlights:

- Burn and lock are separated (`lp_burn_confirmed` vs `lp_locked_flag`).
- Concentration uses top1/top20 only for MVP honesty.
- Fail-closed mode prevents partial assessments from defaulting to `PASS`.


## PR-6 unified scoring

PR-6 adds the unified scoring layer that merges:

- `shortlist.json`
- `x_validated.json`
- `enriched_tokens.json`
- `rug_assessed_tokens.json`

and produces deterministic outputs:

- `data/processed/scored_tokens.json`
- `data/processed/score_events.jsonl`

Run smoke:

```bash
python scripts/unified_score_smoke.py \
  --shortlist data/processed/shortlist.json \
  --x-validated data/processed/x_validated.json \
  --enriched data/processed/enriched_tokens.json \
  --rug-assessed data/processed/rug_assessed_tokens.json
```

## PR-7 entry selector

Both PR-6 and PR-7 sections are intentionally kept because PR-7 consumes `scored_tokens.json` from PR-6.

PR-7 adds entry routing on top of `scored_tokens.json`:

- decision outputs: `SCALP | TREND | IGNORE`
- independent `entry_confidence` and `recommended_position_pct`
- deterministic `entry_snapshot` for PR-8/PR-9
- append-only events log (`data/processed/entry_events.jsonl`)

Run smoke:

```bash
python scripts/entry_selector_smoke.py --scored data/processed/scored_tokens.json
```

## PR-10 post-run analyzer

PR-10 adds a post-run analytics layer over paper-trading artifacts:

- reconstructs closed position lifecycle from `trades.jsonl` + `positions.json`
- computes portfolio/regime/exit/friction metrics
- computes descriptive metric correlations vs PnL
- emits conservative machine-readable recommendations
- writes markdown report with caveats and sample warnings

Run smoke:

```bash
python scripts/post_run_analyzer_smoke.py --base-dir data/smoke/post_run
```

<<<<<<< HEAD
## PR-SIG-3 continuation enrichment

PR-SIG-3 adds the continuation evidence layer that sits between short-horizon helper computations and downstream score/exit consumers. It keeps continuation outputs explicit, additive, and fail-open when tx, X, or wallet-registry evidence is incomplete.

### Evidence lanes

Transaction-derived metrics:

- `net_unique_buyers_60s`
- `liquidity_refill_ratio_120s`
- `cluster_sell_concentration_120s`
- `seller_reentry_ratio`
- `liquidity_shock_recovery_sec`

X-derived metrics:

- `x_author_velocity_5m`

Wallet-registry-derived metrics:

- `smart_wallet_dispersion_score`

Additive provenance/status fields:

- `continuation_status`
- `continuation_warning`
- `continuation_confidence`
- `continuation_metric_origin`
- `continuation_coverage_ratio`
- `continuation_inputs_status`

### Missing-evidence policy

- Missing evidence remains missing; it is not silently converted into bullish or bearish continuation strength.
- Partial evidence is labeled `partial`, not treated as complete coverage.
- Downstream scoring can consume continuation fields, but low-confidence continuation evidence is intentionally damped.

### Continuation smoke

```bash
python scripts/continuation_smoke.py
```

Artifacts written under `data/smoke/`:

- `continuation_enrichment.smoke.json`
- `continuation_status.json`
- `continuation_events.jsonl`

See `docs/continuation_enricher.md` for the full contract, provenance semantics, and fallback behavior.
=======

<<<<<<< HEAD
## PR-CL-2 wallet graph clustering foundation

PR-CL-2 adds a graph-backed wallet clustering layer while preserving the original heuristic fallback.

New components:

- `analytics/wallet_graph_builder.py`
- `analytics/cluster_store.py`
- `schemas/wallet_graph.schema.json`
- `schemas/wallet_clusters.schema.json`
- `docs/wallet_graph_clustering.md`

Produced artifacts:

- `data/processed/wallet_graph.json`
- `data/processed/wallet_clusters.json`
- `data/processed/wallet_graph_events.jsonl`

Run smoke:

```bash
python scripts/wallet_graph_smoke.py
```

Behavior notes:

- graph evidence is used first when coverage is meaningful
- the legacy heuristic clustering path is still preserved as the safe fallback
- cluster provenance fields are additive and backward-compatible
- missing or malformed graph evidence does not hard-fail discovery/scoring
- implementation details and caveats live in `docs/wallet_graph_clustering.md`
=======
## PR-BDL-4 bundle evidence

PR-BDL-4 adds an evidence-first bundle collection layer for early launch analysis.

What is now real evidence in this repo:

- structured `bundle_activity` / `bundle_events` / `bundle_flows` / `bundle_attempts` / `bundle_evidence` payloads
- normalized provenance-aware bundle records with landed/failed/unknown status
- retry, tip, and cross-block evidence when present in the source

What is still heuristic:

- the legacy `bundle_transactions` grouping path
- any bundle derivation when structured evidence is too sparse or unavailable
- attribution quality when upstream source coverage is incomplete

Fallback policy:

- use real evidence first when it is usable
- fall back to the existing heuristic detector when evidence is missing, partial, malformed, or insufficient
- preserve fail-open behavior and keep bundle contract fields stable downstream

New additive output fields:

- `bundle_evidence_status`
- `bundle_evidence_source`
- `bundle_evidence_warning`
- `bundle_evidence_confidence`
- `bundle_metric_origin`

Run bundle evidence smoke:

```bash
python scripts/bundle_evidence_smoke.py
```

See `docs/bundle_evidence.md` for the honesty policy and routing details.
>>>>>>> origin/main
>>>>>>> origin/main
