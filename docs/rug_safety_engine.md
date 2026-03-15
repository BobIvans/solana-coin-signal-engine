# Rug safety engine (PR-5)

PR-5 adds a deterministic safety layer over `enriched_tokens.json` and outputs `rug_assessed_tokens.json`.

## Threshold policy

- `PASS` if `rug_score < RUG_WATCH_THRESHOLD`.
- `WATCH` if `RUG_WATCH_THRESHOLD <= rug_score < RUG_IGNORE_THRESHOLD`.
- `IGNORE` if `rug_score >= RUG_IGNORE_THRESHOLD`.
- Hard-fail overrides force `IGNORE` (active mint authority, extreme top1 concentration, hard dev sell pressure, explicit recoverable LP).

## Burn vs lock semantics

- `lp_burn_confirmed` and `lp_locked_flag` are independent fields.
- Lock evidence never auto-converts to burn evidence.
- Ambiguous LP state emits warnings (`lp_state_ambiguous`, `lock detected but burn not confirmed`).

## Hard-fail rules

Token is forced to `IGNORE` when any critical hard-fail condition is detected:

- mint authority is active,
- top1 holder share is `>= 0.30`,
- dev sell pressure reaches hard threshold with acceptable confidence,
- LP appears creator-recoverable.

## Partial/fail-closed behavior

When critical fields are missing, result is `rug_status=partial` and warnings include missing fields.
With `RUG_ENGINE_FAILCLOSED=true`, partial results cannot end as `PASS` and are degraded to `WATCH` minimum.

## Outputs

- `data/processed/rug_assessed_tokens.json`
- `data/processed/rug_events.jsonl`
- Smoke helper: `data/processed/rug_assessed.smoke.json`
