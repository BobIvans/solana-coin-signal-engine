# Contract parity and docs sync

This document describes the repo's current contract-audit layer. It is intentionally pragmatic: it checks that major artifacts, helper-level contract field groups, and docs references stay aligned without rewriting business logic.

## What this layer checks

- declared helper-driven contract groups;
- major JSON / JSONL artifacts produced or consumed by the pipeline;
- required vs optional field presence;
- missing, malformed, empty, and additive-extra artifacts/fields;
- README / docs drift.

Parity checks live in:
- `tools/contract_parity.py`
- `tools/docs_sync_audit.py`
- `scripts/contract_parity_smoke.py`

Machine-readable output schema lives in:
- `schemas/contract_parity_report.schema.json`

## Status meanings

- `ok`: required fields are present and no visible drift was found for that artifact/group.
- `warning`: required fields are present, but optional fields are missing or additive extra fields appeared.
- `mismatch`: required fields are missing or docs drift is explicit.
- `missing`: expected artifact file is absent.
- `malformed`: artifact could not be parsed as valid JSON / JSONL.
- `empty`: artifact exists but yielded no usable rows.

## Contract groups

### core_shortlist
Artifact:
- `data/processed/shortlist.json`

Required fields:
- `token_address`

Optional examples:
- `symbol`
- `name`
- `pair_address`
- `age_sec`
- `liquidity_usd`
- `txns_m5`

### core_x_validation
Artifact:
- `data/processed/x_validated.json`

Required fields:
- `token_address`

Optional examples:
- `x_status`
- `x_validation_score`
- `x_validation_confidence`
- `x_validation_reason`

### core_enriched
Artifact:
- `data/processed/enriched_tokens.json`

Required fields:
- `token_address`
- `enrichment_status`
- `contract_version`
- `enriched_at`

This is the minimal enriched-token core contract. Additional fields can remain additive.

### bundle_cluster
Artifact:
- `data/processed/enriched_tokens.json`

Required fields come from:
- `utils/bundle_contract_fields.py`

Required bundle/cluster fields:
- `bundle_count_first_60s`
- `bundle_size_value`
- `unique_wallets_per_bundle_avg`
- `bundle_timing_from_liquidity_add_min`
- `bundle_success_rate`
- `bundle_composition_dominant`
- `bundle_tip_efficiency`
- `bundle_failure_retry_pattern`
- `cross_block_bundle_correlation`
- `bundle_wallet_clustering_score`
- `cluster_concentration_ratio`
- `num_unique_clusters_first_60s`
- `creator_in_cluster_flag`


## Canonical emitted provenance vocabulary

Bundle / cluster / linkage / wallet-family artifacts now share one canonical emitted vocabulary where applicable:

- `direct_evidence`
- `graph_evidence`
- `heuristic_evidence`
- `registry_evidence`
- `linkage_evidence`
- `mixed_evidence`
- `missing`

Legacy aliases such as `real_evidence`, `raw_bundles`, `graph_backed`, `heuristic`, and `heuristic_fallback` may be normalized internally at ingestion boundaries, but fresh artifact outputs must emit only canonical values. These aliases are ingestion-only migration shims and are not valid fresh emitted output.

`continuation_metric_origin` is intentionally excluded from this unification and keeps its existing composition-oriented vocabulary.

### bundle_provenance
Artifact:
- `data/processed/enriched_tokens.json`

Required fields come from:
- `utils/bundle_contract_fields.py`

Required bundle provenance fields:
- `bundle_evidence_status`
- `bundle_evidence_source`
- `bundle_evidence_confidence`
- `bundle_evidence_warning`
- `bundle_metric_origin`

These fields are audited as first-class evidence provenance, not treated as silent additive extras.

### cluster_provenance
Artifact:
- `data/processed/enriched_tokens.json`

Required cluster provenance fields:
- `cluster_evidence_status`
- `cluster_evidence_source`
- `cluster_evidence_confidence`
- `cluster_metric_origin`
- `graph_cluster_id_count`
- `graph_cluster_coverage_ratio`
- `creator_cluster_id`
- `dominant_cluster_id`

These fields distinguish graph-backed evidence from heuristic or partial evidence and must remain visible in parity reports.

### linkage_evidence
Artifact:
- `data/processed/enriched_tokens.json`

Required linkage evidence fields come from:
- `utils/bundle_contract_fields.py`

Required fields:
- `creator_dev_link_score`
- `creator_buyer_link_score`
- `dev_buyer_link_score`
- `shared_funder_link_score`
- `creator_cluster_link_score`
- `cluster_dev_link_score`
- `linkage_risk_score`
- `creator_funder_overlap_count`
- `buyer_funder_overlap_count`
- `funder_overlap_count`
- `linkage_reason_codes`
- `linkage_confidence`
- `linkage_metric_origin`
- `linkage_status`
- `linkage_warning`

These are audited as first-class evidence fields, not hidden additive extras.

### continuation
Artifact:
- `data/processed/enriched_tokens.json`

Required short-horizon metric fields come from:
- `utils/short_horizon_contract_fields.py`

Required metric fields:
- `net_unique_buyers_60s`
- `liquidity_refill_ratio_120s`
- `cluster_sell_concentration_120s`
- `smart_wallet_dispersion_score`
- `x_author_velocity_5m`
- `seller_reentry_ratio`
- `liquidity_shock_recovery_sec`

Required continuation provenance/status fields:
- `continuation_status`
- `continuation_warning`
- `continuation_confidence`
- `continuation_metric_origin`
- `continuation_coverage_ratio`
- `continuation_inputs_status`
- `continuation_warnings`
- `continuation_available_evidence`
- `continuation_missing_evidence`

These checks validate presence and visibility. They do not claim that continuation signals are complete or non-heuristic.

### wallet_family_summary
Artifact(s):
- `data/processed/enriched_tokens.json`
- `data/processed/scored_tokens.json`
- `data/processed/entry_candidates.json`
- `trade_feature_matrix.jsonl`

Required token-facing wallet-family summary fields come from:
- `utils/wallet_family_contract_fields.py`

Required fields:
- `smart_wallet_family_ids`
- `smart_wallet_independent_family_ids`
- `smart_wallet_family_origins`
- `smart_wallet_family_statuses`
- `smart_wallet_family_reason_codes`
- `smart_wallet_family_unique_count`
- `smart_wallet_independent_family_unique_count`
- `smart_wallet_family_confidence_max`
- `smart_wallet_family_member_count_max`
- `smart_wallet_family_shared_funder_flag`
- `smart_wallet_family_creator_link_flag`

These fields are aggregated token-facing summaries of matched smart-wallet families. They must stay null-safe and must not be replaced with a fake singular token-level `wallet_family_id`.

High-level continuation semantics:
- tx-derived continuation metrics are success-gated (`success is True`)
- raw tx evidence presence (`continuation_available_evidence`) is distinct from usable tx-lane readiness (`continuation_inputs_status["tx"]`)
- if all txs are failed / reverted / unknown-success, `continuation_available_evidence` should still include `"tx"`, but `continuation_inputs_status["tx"]` must be `"partial"`, not `"ready"`
- LP/pool/router/vault/system-like actors must not silently count as organic buyers or sellers
- ambiguous same-tx role attribution should degrade continuation honesty rather than inflate strength

### core_rug_assessed
Artifact:
- `data/processed/rug_assessed_tokens.json`

Required fields:
- `token_address`
- `rug_score`
- `rug_status`

Optional examples:
- `rug_flags`
- `rug_warnings`
- `lp_burn_confirmed`
- `lp_locked_flag`

### core_scored
Artifact:
- `data/processed/scored_tokens.json`

Required fields:
- `token_address`
- `onchain_core`
- `early_signal_bonus`
- `x_validation_bonus`
- `rug_penalty`
- `spam_penalty`
- `confidence_adjustment`
- `final_score`
- `regime_candidate`

### core_entry_candidates
Artifact:
- `data/processed/entry_candidates.json`

Required fields:
- `token_address`
- `entry_decision`
- `entry_confidence`
- `recommended_position_pct`
- `base_position_pct`
- `effective_position_pct`
- `sizing_multiplier`
- `sizing_reason_codes`
- `sizing_confidence`
- `sizing_origin`
- `evidence_quality_score`
- `evidence_conflict_flag`
- `partial_evidence_flag`
- `entry_reason`
- `regime_confidence`
- `regime_reason_flags`
- `regime_blockers`
- `expected_hold_class`
- `entry_snapshot`

### replay_feature_matrix
Artifact:
- `trade_feature_matrix.jsonl`

Parity uses a pragmatic required subset derived from `analytics/analyzer_matrix.py`, including:
- `position_id`
- `regime_decision`
- `expected_hold_class`
- `x_status`
- `exit_reason_final`
- `hold_sec`
- `net_pnl_pct`
- `bundle_count_first_60s`

The replay feature matrix is also the preferred source for analyzer evidence-quality slices. When available, post-run analyzer diagnostics may consume existing fields such as:
- `partial_evidence_flag`
- `evidence_quality_score`
- `evidence_conflict_flag`
- `evidence_coverage_ratio`
- `partial_evidence_penalty`
- `low_confidence_evidence_penalty`
- `evidence_available`
- `evidence_scores`
- `sizing_confidence`
- `x_status`
- `linkage_risk_score`
- `bundle_evidence_status`
- `cluster_evidence_status`
- `continuation_status`

These fields remain analysis-only in the analyzer slice layer; they are not mutated by the analyzer itself.
- `bundle_size_value`
- `net_unique_buyers_60s`
- `liquidity_refill_ratio_120s`
- `cluster_sell_concentration_120s`
- `smart_wallet_dispersion_score`
- `x_author_velocity_5m`
- `seller_reentry_ratio`
- `liquidity_shock_recovery_sec`

Other replay/analyzer matrix columns remain additive and are reported rather than force-dropped.

### post_run_summary
Artifact:
- `data/processed/post_run_summary.json`

Required fields:
- `as_of`
- `contract_version`
- `warnings`

### post_run_recommendations
Artifact:
- `data/processed/post_run_recommendations.json`

Required fields:
- `contract_version`
- `recommendations`

## Docs sync scope

Docs sync checks currently verify that:
- `README.md` mentions the major current artifacts;
- `docs/contracts.md` mentions the same major artifacts and contract groups;
- merge-conflict markers and stale references are surfaced explicitly;
- parity tool entry points are referenced.

This is intentionally lightweight. It is not a full autogenerated documentation platform.

## Current honesty / limitation notes

- The parity layer checks field presence and documentation drift, not model quality.
- Optional/additive fields are visible in reports and are not silently treated as failures.
- Missing or malformed artifacts are explicit failures for audit purposes.
- Docs should describe what is current in the repo now, not what a future PR may eventually add.


## Replay wallet parity metadata

Fresh replay summary / manifest payloads and replay-emitted signal, trade, and `trade_feature_matrix.jsonl` artifacts expose the following additive parity fields:

- `final_score_pre_wallet`
- `wallet_weighting_requested_mode`
- `wallet_weighting_effective_mode`
- `wallet_score_component_raw`
- `wallet_score_component_applied`
- `wallet_score_component_applied_shadow`
- `replay_score_source`
- `wallet_mode_parity_status`
- `score_contract_version`
- `historical_input_hash`

## PR-INFRA-1 contract notes

- `tx_batch.contract_version` is part of freshness policy. Cache entries with a contract-version mismatch must be treated as `refresh_required`, even when TTL has not expired.
- Historical replay price context may be supplied either as standalone `price_paths.json(.l)` artifacts or as embedded `price_paths` arrays inside chain-backfill rows.
- X provider error taxonomy is canonicalized to `captcha`, `timeout`, `soft_ban`, `login_required`, `error`, with legacy `blocked` normalized before cooldown logic runs.
