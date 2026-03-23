# Price history provider

## Supported providers

- `price_history` for the legacy generic HTTP adapter.
- `geckoterminal_pool_ohlcv` for canonical pool-based on-chain OHLCV replay sourcing.

## GeckoTerminal pool OHLCV flow

`geckoterminal_pool_ohlcv` resolves `token_address -> canonical pool -> minute OHLCV` and then normalizes the rows into the replay contract consumed by `chain_backfill` and the historical replay harness.

Why pool OHLCV is preferred for replay determinism:

- token-routed OHLCV can follow the currently most liquid pool instead of the pool that best matches the original replay context,
- replay can seed a `pair_address` as a pool hint while still persisting the finally selected pool,
- minutely OHLCV with `include_empty_intervals=true` preserves stable offsets even when swaps are sparse.

## Provider behavior

- Pool resolution uses the token pools endpoint and deterministically picks a canonical pool by liquidity first and trading activity second.
- OHLCV fetches use `timeframe=minute` plus `aggregate=1`, `5`, or `15` depending on the requested interval.
- Backward pagination uses `before_timestamp` until the requested time window is covered or the provider stops returning rows.
- The config supports `request_version`, `currency`, `token` / `token_side`, `include_empty_intervals`, `pool_resolver`, `resolver_cache_ttl_sec`, and `max_ohlcv_limit`.
- Replay should budget around GeckoTerminal's public `30 calls/min` rate limit.

## Warnings

The provider can surface these warnings in replay rows:

- `pool_resolution_failed`
- `no_pool_ohlcv_rows`
- `provider_rate_limited`
- `provider_http_error`

## Provenance fields

Pool-aware backfill rows can include:

- `selected_pool_address`
- `pool_resolver_source`
- `pool_resolver_confidence`
- `pool_candidates_seen`
- `pool_resolution_status`

These fields are preserved even when the pool resolves successfully but OHLCV rows are empty, which makes diagnostics clearer when Birdeye quota is unavailable and GeckoTerminal becomes the fallback source.
