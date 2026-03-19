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
