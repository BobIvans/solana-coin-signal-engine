# PR-8 Exit Engine

`exit_engine` consumes active paper positions plus current token state and emits deterministic machine-readable decisions:

- `HOLD`
- `PARTIAL_EXIT`
- `FULL_EXIT`

## Inputs

- `positions.json` (must include `entry_snapshot` and position state)
- merged market snapshot/current state

## Decision precedence

1. Hard safety exits (`kill_switch_triggered`, `dev_sell`, `rug_flag`, fail-closed missing data)
2. Regime hard stops
3. Regime deterioration full exits
4. `TREND` partial take-profit milestones
5. `HOLD`

Hard exits always win over partial-profit logic.

## Regime rules

### SCALP

- Hard exits:
  - stop-loss (`EXIT_SCALP_STOP_LOSS_PCT`)
  - liquidity breakdown (`EXIT_SCALP_LIQUIDITY_DROP_PCT`)
  - max hold timeout (`EXIT_SCALP_MAX_HOLD_SEC`)
  - global hard flags (`dev_sell`, `rug_flag`)
- Recheck at `EXIT_SCALP_RECHECK_SEC`:
  - this is a **re-evaluation threshold**, not a forced sell
  - if profitable and momentum/social confirmation decays, trigger `FULL_EXIT`
  - severe `cluster_dump_detected`, `bundle_failure_spike`, `creator_cluster_exit_risk`, or `linkage_risk_exit` may also force an immediate protective exit

### TREND

- Hard exits:
  - trend hard stop (`EXIT_TREND_HARD_STOP_PCT`)
  - buy-pressure floor break
  - liquidity breakdown
  - social/holder collapse
  - concentrated post-entry cluster dump / creator-cluster escalation
  - high-confidence creator/dev/funder linkage escalation confirmed by distribution-style or retry-style manipulation evidence (`linkage_risk_exit`)
  - global hard flags (`dev_sell`, `rug_flag`)
- Partial exits:
  - partial 1 at `EXIT_TREND_PARTIAL1_PCT` (`exit_fraction=0.33`)
  - partial 2 at `EXIT_TREND_PARTIAL2_PCT` (`exit_fraction=0.50`)
- partials are stateful and do not repeat (`partial_1_taken` / `partial_2_taken` or `partials_taken`)

## Current-state resilience

### Critical live field

- `price_usd_now`

### Degradable / sticky fields

- `buy_pressure_now`
- `volume_velocity_now`
- `liquidity_usd_now`
- `x_validation_score_now`
- `x_status_now`
- `bundle_cluster_score_now`
- `dev_sell_pressure_now`
- `rug_flag_now`

### Policy

- missing critical live field + `EXIT_ENGINE_FAILCLOSED=true` => `FULL_EXIT` with `exit_reason=missing_current_state_failclosed`
- missing degradable fields do **not** auto-liquidate the position
- the engine resolves degradable fields through current-payload aliases first, then `entry_snapshot` fallback where available
- degraded polls are labeled honestly with:
  - `exit_status=partial`
  - `exit_warnings` markers such as `degraded_current_state_fields`, `fallback_<field>`, and `missing_degradable_<field>`
- live price never falls back to `entry_snapshot`; this is graceful degradation, not silent optimism

## Snapshot contract

Each decision includes `exit_snapshot` with load-bearing fields:

- `price_usd`
- `buy_pressure_now`
- `volume_velocity_now`
- `liquidity_usd_now`
- `liquidity_drop_pct`
- `x_validation_score_now`
- `x_status_now`
- `bundle_cluster_score_now`
- `bundle_cluster_delta`
- `dev_sell_pressure_now`
- `rug_flag_now`
- optional bundle/cluster risk evidence such as `cluster_sell_concentration_120s`, `bundle_failure_retry_delta`, `creator_cluster_activity_now`, `linkage_risk_score_now`, and `smart_wallet_netflow_bias` when present

Protective exit families that should remain distinct in artifacts and replay/debugging include:

- `creator_cluster_exit_risk`
- `linkage_risk_exit`
- `cluster_dump_detected`
- `failed_liquidity_refill_exit`
- `shock_not_recovered_exit`
- `retry_manipulation_detected`

`linkage_risk_exit` is the canonical protective exit for high-confidence creator/dev/funder linkage risk that is confirmed by distribution-style or retry-style manipulation evidence. Its detection marker is `linkage_risk_detected`.

Optional attribution fields:

- `holder_growth_now`
- `smart_wallet_hits_now`
- `market_cap_now`

## Output artifacts

- `data/processed/exit_decisions.json`
- `data/processed/exit_events.jsonl`

Events include:

- `exit_evaluation_started`
- `exit_hard_rule_triggered` (policy-level hard exits)
- `exit_partial_triggered`
- `exit_full_triggered`
- `exit_hold_confirmed`
- `exit_completed`

## Fail-closed behavior

When the critical live field is missing and `EXIT_ENGINE_FAILCLOSED=true`, the engine emits a forced safe decision:

- `exit_decision=FULL_EXIT`
- `exit_reason=missing_current_state_failclosed`
- `exit_status=partial`

When only degradable fields are missing, the engine continues evaluation with alias / `entry_snapshot` fallback where possible and emits explicit degraded warnings instead of panic liquidation. This prevents optimistic silent `HOLD` on incomplete data.

## Kill switch liquidation

The kill switch is a global emergency control, not just an entry guard. When the configured kill-switch file is present, the exit engine immediately emits:

- `exit_decision=FULL_EXIT`
- `exit_reason=kill_switch_triggered`
- `exit_flags=["kill_switch_triggered"]`

This check runs before the other hard-exit branches so open positions are liquidated deterministically even if market signals would otherwise still look healthy. New entries remain blocked upstream by the promotion guards.
