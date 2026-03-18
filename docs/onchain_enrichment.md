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
- **Validated wallet registry (PR-SW-3)**
  - `data/registry/smart_wallets.validated.json`
  - `data/registry/hot_wallets.validated.json`

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

## Wallet-registry-aware enrichment
PR-SW-4 keeps the existing PR-4 raw smart-wallet hit detector and adds a deterministic registry-aware overlay.
The validated registry affects enrichment only. It does **not** change PR-6 unified score, entry selection, exit logic, paper runner, or live execution in this PR.

New per-token fields:
- `wallet_registry_status`
- `wallet_registry_hot_set_size`
- `wallet_registry_validated_size`
- `smart_wallet_score_sum`
- `smart_wallet_tier1_hits`
- `smart_wallet_tier2_hits`
- `smart_wallet_tier3_hits`
- `smart_wallet_early_entry_hits`
- `smart_wallet_active_hits`
- `smart_wallet_watch_hits`
- `smart_wallet_hit_tiers`
- `smart_wallet_hit_statuses`
- `smart_wallet_netflow_bias`
- `smart_wallet_conviction_bonus`
- `smart_wallet_registry_confidence`

Interpretation notes:
- `smart_wallet_hits` and `smart_wallet_hit_wallets` remain the existing raw PR-4 hit outputs.
- Registry-aware counts and scores are computed from the intersection of those raw hit wallets with the validated registry.
- `smart_wallet_netflow_bias` stays `null` unless token-level wallet directionality is honestly available.
- `smart_wallet_early_entry_hits` stays `0` unless an explicit replay-derived early-entry-positive marker exists on the validated wallet record.

## Degraded wallet-registry mode
If `smart_wallets.validated.json` is absent, enrichment does **not** crash.
Instead it runs with:
- `wallet_registry_status=degraded_missing_registry`
- zero wallet-registry sizes
- zero registry-aware scores/counts
- `smart_wallet_registry_confidence=low`

If the validated registry file exists but contains zero usable wallets, enrichment runs with:
- `wallet_registry_status=degraded_empty_registry`
- the same safe registry-aware defaults

This degraded mode is logged explicitly in `data/processed/onchain_enrichment_events.jsonl` through:
- `wallet_registry_loaded`
- `wallet_registry_missing_degraded`
- `wallet_registry_empty_degraded`
- `token_wallet_hits_computed`

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
- Missing validated wallet registry => degraded registry mode, no crash.

## Smoke commands
Without explicit registry args:

```bash
python scripts/onchain_enrichment_smoke.py   --shortlist data/processed/shortlist.json   --x-validated data/processed/x_validated.json
```

With explicit validated registry artifacts:

```bash
python scripts/onchain_enrichment_smoke.py   --shortlist data/processed/shortlist.json   --x-validated data/processed/x_validated.json   --validated-registry data/registry/smart_wallets.validated.json   --hot-registry data/registry/hot_wallets.validated.json
```

- Runner returns non-crash `0` for normal/partial flow.
