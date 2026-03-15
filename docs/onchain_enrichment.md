# On-chain enrichment (PR-4)

## Source map

- **Solana RPC** (`collectors/solana_rpc_client.py`)
  - `getTokenLargestAccounts`
  - `getTokenSupply`
  - `getTokenAccountsByOwner`
  - `getAccountInfo`
  - `getSignaturesForAddress`
- **Helius** (`collectors/helius_client.py`)
  - `getAsset`
  - Enhanced tx by address
  - Enhanced tx by signature batch

## Heuristic policy

Exact/near-exact in v1:
- `top1_holder_share`
- `top20_holder_share`
- `unique_buyers_5m`
- `holder_growth_5m`
- `dev_sell_pressure_5m`
- `smart_wallet_hits`

Heuristics (explicit `_est`/`_score`):
- `first50_holder_conc_est`
- `holder_entropy_est`
- `pumpfun_to_raydium_sec`
- `dev_wallet_est`
- `launch_path_confidence_score`

Important honesty rule: standard `getTokenLargestAccounts` covers only top 20 token accounts, so first-50 and entropy are estimated in v1.

## Output schema

See `schemas/enriched_token.schema.json`.

Outputs:
- `data/processed/enriched_tokens.json`
- `data/processed/onchain_enrichment_events.jsonl`
- smoke helper: `data/processed/enriched_tokens.smoke.json`

## Partial/fail-open behavior

- Missing asset metadata => `enrichment_status=partial`, but holder/dev metrics still computed.
- Missing/failed enhanced tx batch => `partial`, no crash.
- Unknown launch path => `launch_path_label=unknown` + low confidence + warning.
- Runner returns non-crash `0` for normal/partial flow.
