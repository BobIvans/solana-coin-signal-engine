# solana-coin-signal-engine

PR-0 introduces a local OpenClaw + X bootstrap layer for smoke validation.

## Quick start

```bash
python scripts/print_env_check.py
python scripts/setup_openclaw.py
python scripts/smoke_openclaw_x.py
```

## Important runtime note

OpenClaw browser automation for X must run **locally only**.
Do **not** use Codespaces as the browser runtime for this flow.
