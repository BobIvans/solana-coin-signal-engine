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
