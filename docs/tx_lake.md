# tx lake

PR-DATA-1 adds a local tx lake under `data/cache/tx_batches/` for deterministic transaction reuse.

## What is stored

Each batch is a normalized JSON artifact keyed by:

- provider (`helius`, `solana_rpc`)
- lookup type (`address`, `pair_address`, `signature_batch`, ...)
- lookup key

Artifacts include:

- contract version
- fetched / normalized timestamps
- freshness and batch status
- warnings and record count
- normalized transaction records

## Freshness and fallback

- `fresh_cache`: batch is within the configured TTL.
- `stale_cache_allowed`: batch is older than the fresh TTL but still inside stale allowance.
- `refresh_required`: batch is too old and should be refreshed.
- `upstream_failed_use_stale`: upstream failed and stale local data was reused explicitly.
- `missing`: neither fresh nor stale usable data was available.

Stale data is never silently labeled as fresh.
Missing data is never fabricated.

## Intended usage

Primary collectors should prefer `*_with_status()` helpers so downstream consumers can see:

- `tx_batch_status`
- `tx_batch_warning`
- `tx_batch_freshness`
- `tx_fetch_mode`

Legacy list-returning helpers still work for backward compatibility and simply return `records`.
