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
