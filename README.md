# solana-memecoin-signal-engine

PR-1 bootstraps the core infrastructure layer for future discovery, X-validation, on-chain enrichment, scoring, and paper-trading flows.

## What PR-1 includes

- project structure for app/config/collectors/analytics/trading/database/utils
- unified env-driven settings with validation
- deterministic JSON + append-only JSONL I/O helpers
- UTC clock + basic structured logger
- JSON contracts for token candidates, signals, trades, positions
- cache/retry/rate-limit skeletons for PR-2/PR-3 integration
- smoke bootstrap script producing data artifacts

## Run environment check

```bash
python scripts/print_env_check.py
```

## Run smoke bootstrap

```bash
python scripts/smoke_bootstrap.py
```

## Run healthcheck

```bash
python -m app.main
```

## Data artifacts

Artifacts are created under `data/`:

- `data/signals/signals.jsonl`
- `data/trades/trades.jsonl`
- `data/smoke/bootstrap_status.json`

## Notes on X/OpenClaw

X/OpenClaw integration is config-ready in PR-1 only. Full extraction/validation workflows are intentionally out of scope at this stage.
