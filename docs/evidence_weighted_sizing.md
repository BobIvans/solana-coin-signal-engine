# Evidence-weighted sizing

This repo now applies an additive **evidence-weighted sizing** layer after existing mode-policy and degraded-X policy checks.

## Intent

Sizing now uses the same shared evidence-quality summary helper as unified scoring (`analytics/evidence_quality.py`).
This avoids score/sizing drift while keeping sizing-specific multiplier logic separate.


The sizing layer does **not** redesign score, regime, or hard-guard logic.
It only refines allowed paper/runtime size conservatively when the evidence behind a signal is incomplete, degraded, conflicting, or risky.

Priority order:

1. hard guards remain authoritative
2. mode-level size policy stays in place
3. degraded-X policy stays compatible
4. evidence quality can only preserve or reduce size
5. weak or missing evidence never enlarges size

## What the sizing layer reads

When available, sizing uses additive evidence already emitted by the repo, including:

- `regime_confidence`
- `runtime_signal_confidence`
- `x_status` and `x_validation_score`
- `continuation_confidence` / `continuation_status`
- linkage fields such as `linkage_risk_score`, `creator_dev_link_score`, `creator_buyer_link_score`, and related overlap/link scores
- cluster and bundle context such as `bundle_wallet_clustering_score` and `cluster_concentration_ratio`
- wallet support fields such as `smart_wallet_hits`, `smart_wallet_tier1_hits`, and `smart_wallet_netflow_bias`
- partial-signal indicators such as `runtime_signal_partial_flag`

Missing evidence is treated honestly: the layer reduces confidence and can reduce size, but it does not invent supportive evidence.

## Conservative sizing policy

The layer starts from the already-allowed base size:

- runtime path: `recommended_position_pct * mode_position_scale`
- plus degraded-X reduction when the active mode policy already requires it
- entry path: `base_position_pct == recommended_position_pct` before evidence reductions

From there, evidence weighting may reduce size further for conditions such as:

- partial evidence
- very sparse evidence coverage
- conflicting evidence
- creator/dev/funder linkage risk
- weak continuation support
- low-confidence cluster evidence
- low runtime confidence
- generally poor evidence quality

Strong evidence can preserve the base size, but it does **not** increase size above current safe bounds.

## Output fields

Entry decisions, runtime decisions, paper-trading artifacts, and replay-compatible rows can now carry additive sizing fields such as:

- `base_position_pct`
- `effective_position_pct`
- `sizing_multiplier`
- `sizing_reason_codes`
- `sizing_confidence`
- `sizing_origin`
- `sizing_warning`
- `evidence_quality_score`
- `evidence_conflict_flag`
- `partial_evidence_flag`

Common reason codes include:

- `x_status_degraded_size_reduced`
- `partial_evidence_size_reduced`
- `missing_evidence_size_reduced`
- `creator_link_risk_size_reduced`
- `continuation_confidence_low_size_reduced`
- `cluster_evidence_low_confidence_size_reduced`
- `evidence_conflict_size_reduced`
- `evidence_support_preserved_base_size`

## Origins

`sizing_origin` is emitted to explain where the final size came from:

- `mode_policy_only`
- `degraded_x_policy`
- `evidence_weighted`
- `partial_evidence_reduced`
- `risk_reduced`

## Entry + runtime interaction

On the entry path, `trading/entry_sizing.py` now uses the same canonical sizing engine with `base_position_pct=recommended_position_pct`, so entry artifacts already carry `effective_position_pct` and the supporting sizing provenance fields.

In `run_promotion_loop.py`, the sizing layer runs only after a signal has been normalized and before a paper position is opened.
Hard blocks still reject the signal. The sizing layer cannot convert a blocked signal into an entry.

Structured runtime events include:

- `evidence_weighted_sizing_started`
- `evidence_quality_computed`
- `sizing_multiplier_computed`
- `sizing_reduced_partial_evidence`
- `sizing_reduced_degraded_x`
- `sizing_reduced_creator_link_risk`
- `evidence_weighted_sizing_completed`

## Smoke artifacts

Run:

```bash
python scripts/evidence_weighted_sizing_smoke.py
```

Artifacts are written to:

- `data/smoke/evidence_weighted_sizing_summary.json`
- `data/smoke/evidence_weighted_sizing_summary.md`

## Safety notes

- No Kelly sizing or portfolio optimization is introduced here.
- No weak evidence can increase size.
- Hard blockers stay hard blockers.
- If this layer is reverted, the repo can fall back to prior mode-policy and degraded-X behavior.
