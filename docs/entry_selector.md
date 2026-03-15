# PR-7 entry selector

`entry_selector` transforms `scored_tokens.json` into machine-readable entry decisions.

## Regime rules

Decision options:

- `SCALP`
- `TREND`
- `IGNORE`

Precedence:

1. hard safety overrides (`rug_verdict=IGNORE`, fail-closed missing mandatory fields, hard dev-sell risk)
2. `TREND`
3. `SCALP`
4. `IGNORE`

`TREND` is stricter than `SCALP` and requires stronger holder/X confirmation.

## Sizing logic

`recommended_position_pct = ENTRY_MAX_BASE_POSITION_PCT * entry_confidence`

Then multipliers are applied:

- degraded X: `ENTRY_DEGRADED_X_SIZE_MULTIPLIER`
- partial enrichment/rug data: `ENTRY_PARTIAL_DATA_SIZE_MULTIPLIER`

Caps:

- `SCALP <= 0.75`
- `TREND <= 1.00`

Hard zero:

- any `IGNORE` decision
- `rug_verdict=IGNORE`
- fail-closed mandatory field violations

## Confidence model

```
entry_confidence =
  0.34 * score_strength
  + 0.22 * momentum_strength
  + 0.18 * x_strength
  + 0.16 * safety_strength
  + 0.10 * data_quality_strength
```

Each component is normalized to `0..1`, final value clamped to `0..1`.

## Degraded/partial policy

- `x_status=degraded` can still produce `SCALP`/`TREND` when rule checks pass.
- Size must be reduced and `x_degraded_size_reduced` flag emitted.
- partial enrichment/rug status reduces size and emits `partial_data_size_reduced`.
- If fail-closed + mandatory fields missing, decision is forced to `IGNORE`.

## Entry snapshot contract

`build_entry_snapshot()` emits deterministic compact fields needed by PR-8/PR-9:

- `final_score`, `regime_candidate`, `age_sec`, `price_usd`
- `buy_pressure`, `volume_velocity`, `liquidity_growth`
- `first30s_buy_ratio`, `bundle_cluster_score`
- `x_validation_score`, `x_validation_delta`, `x_status`
- `holder_growth_5m`, `smart_wallet_hits`
- `dev_sell_pressure_5m`, `rug_score`

## Smoke runner

```bash
python scripts/entry_selector_smoke.py --scored data/processed/scored_tokens.json
```

Writes:

- `data/processed/entry_candidates.json`
- `data/processed/entry_candidates.smoke.json`
- `data/processed/entry_events.jsonl`
