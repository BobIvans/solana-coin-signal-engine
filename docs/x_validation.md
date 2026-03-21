# X-validation (PR-3)

## Purpose

`X-validation` validates top shortlist tokens by issuing a shallow set of X/Twitter search queries via local OpenClaw browser profile and converts visible results into deterministic metrics and score.

## Login flow

- Use manual login in OpenClaw browser profile `openclaw`.
- Keep X session active in that profile.
- Use host target (`OPENCLAW_BROWSER_TARGET=host`) to reduce anti-bot triggers.
- This layer never performs automated login.

## Configuration

See `.env.example`:

- `X_VALIDATION_ENABLED`, `X_DEGRADED_MODE_ALLOWED`, `LOCAL_OPENCLAW_ONLY`
- `OPENCLAW_BROWSER_PROFILE`, `OPENCLAW_BROWSER_TARGET`
- `OPENCLAW_X_QUERY_MAX`, `OPENCLAW_X_TOKEN_MAX_CONCURRENCY`
- `OPENCLAW_X_CACHE_TTL_SEC`, `OPENCLAW_X_PAGE_TIMEOUT_MS`, `OPENCLAW_X_NAV_TIMEOUT_MS`
- `OPENCLAW_X_MAX_SCROLLS`, `OPENCLAW_X_MAX_POSTS_PER_QUERY`
- `OPENCLAW_X_DEGRADED_SCORE`, `OPENCLAW_X_FAILOPEN`
- `X_VALIDATION_CONTRACT_VERSION`

## Degraded behavior

On CAPTCHA/login-expired/timeout/blocked/OpenClaw unavailable:

- returns `x_status=degraded` if all queries fail
- applies fallback score `OPENCLAW_X_DEGRADED_SCORE`
- emits structured event to `x_validation_events.jsonl`
- never crashes the pipeline

## Outputs

- `data/processed/x_validated.json`
- `data/processed/x_validation_events.jsonl`

`x_validated.json` follows `schemas/x_validation.schema.json`.

## Smoke

```bash
python scripts/x_validation_smoke.py --shortlist data/processed/shortlist.json
```

Exit code is `0` for `ok` and `degraded` outcomes. Non-zero only for unhandled code crash / schema violation.


## PR-SIG-2 additive field
- `x_author_velocity_5m`: distinct newly visible authors per minute over the first five minutes of timestamped visible posts. It remains `null` when OpenClaw-visible cards do not expose honest post timestamps.


## Cooldown short-circuit

When operational promotion state/config is present and X cooldown is active, `fetch_x_snapshots()` now skips the fetch path entirely:

- no thread pool is started
- no query worker is executed
- each planned query returns a degraded cooldown snapshot
- events `x_query_skipped_cooldown` and `x_snapshot_batch_skipped_cooldown` are written for operator visibility

Cooldown snapshots carry `x_status=degraded`, `error_code=cooldown_active`, `error_detail=x_cooldown_active`, `posts_visible=0`, and `cooldown_active=true`.
