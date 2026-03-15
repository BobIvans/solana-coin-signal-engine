# solana-memecoin-signal-engine

PR-3 extends the engine with OpenClaw-backed X-validation that runs fail-open and never breaks the pipeline on CAPTCHA/timeouts/login-expired errors.

## What PR-3 includes

- X query builder (`collectors/x_query_builder.py`) with capped + deduped query generation
- OpenClaw local X client (`collectors/openclaw_x_client.py`) with cache-first reads and degraded-safe failures
- Snapshot parser + token aggregation (`analytics/x_snapshot_parser.py`)
- X score engine (`analytics/x_validation_score.py`) with degraded fallback policy
- schema contract (`schemas/x_validation.schema.json`)
- smoke runner (`scripts/x_validation_smoke.py`)
- docs (`docs/x_validation.md`)

## Run X-validation smoke

```bash
python scripts/x_validation_smoke.py --shortlist data/processed/shortlist.json
```

## Run tests

```bash
pytest -q
```

## Data artifacts

Artifacts are created under `data/processed/`:

- `shortlist.json` (input from discovery)
- `x_validated.json`
- `x_validation_events.jsonl`

## Notes on OpenClaw + X

- Local OpenClaw only for this flow.
- Manual X login is expected in profile `openclaw`.
- Host browser target (`OPENCLAW_BROWSER_TARGET=host`) is the default.
