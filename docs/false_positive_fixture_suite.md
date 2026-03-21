# False-positive fixture suite

## Purpose

This suite adds a reusable adversarial fixture catalog for attractive-but-dangerous early-launch patterns that should not quietly promote into confident entries, healthy trend labels, or optimistic replay interpretations.

The focus is regression protection, not strategy redesign.

## Covered failure modes

The suite currently includes these named cases:

- `single_cluster_fake_strength`
- `creator_linked_early_buyers`
- `retry_heavy_sniper_loop`
- `sell_heavy_bundle_distribution`
- `fake_trend_weak_continuation`
- `degraded_x_ambiguous_onchain`
- `partial_evidence_false_confidence`

## Structure

The shared fixture catalog lives in `tests/fixtures/false_positive_cases.py`.

Each case documents:

- `case_name`
- `description`
- `payload`
- `expected_score_signals`
- `expected_regime_behavior`
- `expected_exit_behavior` when applicable
- `expected_replay_behavior`
- `notes`

The helper module also exposes deterministic builders and evaluators so the same adversarial case can be reused across score, regime, exit, replay, and smoke checks.

## Layers covered

The suite currently exercises these layers:

- unified scoring via `analytics.unified_score.score_token`
- regime and entry routing via `trading.entry_logic` / `trading.regime_rules`
- protective exits via `trading.exit_logic` / `trading.exit_rules`
- a compact fixture replay classification path used only for regression tests and smoke output

## Honesty notes

This suite is intentionally conservative about what the repository already does today.

In particular:

- degraded-X ambiguity is currently forced conservative mainly by score routing and entry gating
- partial-evidence caution is surfaced by score warnings, a narrow near-threshold WATCHLIST review path based on a review-only score basis, and fail-closed style entry behavior
- weak continuation is already visible in score and exit logic, but not every continuation metric is a first-class immediate regime gate yet

The fixture suite documents those realities instead of pretending every layer already consumes every signal equally.

For `partial_evidence_false_confidence`, the intended layering is explicit: the score layer should keep the token operator-visible as `WATCHLIST`, while the regime/entry layer must still block execution with `IGNORE`. The WATCHLIST visibility comes from the review-only `partial_review_score`, not from weakening `final_score` itself.

## Extending the suite

When adding a new adversarial case:

1. start from the shared base payload in `tests/fixtures/false_positive_cases.py`
2. override only the fields needed for the failure mode
3. document expected score, regime, exit, and replay behavior explicitly
4. prefer meaningful behavior assertions over brittle implementation trivia
5. keep the case deterministic and readable

## Smoke path

Run the dedicated smoke path with:

```bash
python scripts/false_positive_smoke.py
```

The smoke script writes:

- `data/smoke/false_positive_summary.json`
- `data/smoke/false_positive_summary.md`

## Test command

```bash
pytest -q \
  tests/test_false_positive_score_regressions.py \
  tests/test_false_positive_regime_regressions.py \
  tests/test_false_positive_exit_regressions.py \
  tests/test_false_positive_replay_regressions.py \
  tests/test_false_positive_smoke.py
```
