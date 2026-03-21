# solana-coin-signal-engine

This repository contains deterministic scoring, regime-selection, exit, replay, calibration, promotion, and smoke tooling for a Solana memecoin signal engine.

## PR-7 entry selector

PR-7 adds the deterministic entry-selection layer that turns `scored_tokens.json` into machine-readable entry decisions for downstream runtime, replay, and analyzer consumers.

Highlights:

- emits `SCALP`, `TREND`, or `IGNORE`
- keeps degraded-X and partial-data handling explicit instead of silently fabricating confidence
- produces compact `entry_snapshot` payloads for downstream consumers
- writes conservative decision and sizing outputs without bypassing hard blockers

Primary artifacts:

- `data/processed/entry_candidates.json`
- `data/processed/entry_candidates.smoke.json`
- `data/processed/entry_events.jsonl`

Run smoke:

```bash
python scripts/entry_selector_smoke.py --scored data/processed/scored_tokens.json
```

See `docs/entry_selector.md` for regime rules, confidence logic, degraded/partial handling, and the entry snapshot contract.

## Historical replay harness

The replay path is now evidence-first. `src/replay/historical_replay_harness.py` is the only supported replay entrypoint, and the old synthetic replay shim has been removed.

Historical replay uses recorded local artifacts such as scored rows, entry candidates, historical signals/trades/positions, and recorded price paths to reconstruct candidate, entry, position, and exit lifecycles.

### What makes replay historical

A replay run is historical when it is driven by persisted local artifacts under an artifact directory, typically `data/processed/` or a fixture directory. The harness prefers:

- `scored_tokens.jsonl`
- `entry_candidates.json` / `entry_candidates.jsonl`
- `signals.jsonl` / `entry_events.jsonl`
- `trades.jsonl`
- `positions.json`
- `price_paths.json` / `price_paths.jsonl`
- `universe.json` / `universe.jsonl`

Missing evidence is not silently turned into synthetic outcomes. Instead, rows are labeled as historical, partial, unresolved, or synthetic-smoke-assisted.

### Replay outputs

Each replay run writes artifacts under `runs/<run_id>/` by default:

- `signals.jsonl`
- `trades.jsonl`
- `positions.json`
- `trade_feature_matrix.jsonl`
- `replay_summary.json`
- `replay_summary.md`
- `manifest.json`

The summary reports:

- historical row count
- partial row count
- unresolved row count
- wallet-weighting mode
- config hash
- whether synthetic fallback was used

### Run historical replay

```bash
python scripts/replay_7d.py \
  --run-id example_replay \
  --config config/replay.default.yaml \
  --artifact-dir data/processed \
  --wallet-weighting off \
  --dry-run
```

### Compare wallet weighting modes

Wallet weighting now runs through the canonical unified scorer in all modes; `off`, `shadow`, and `on` only change post-base-score application semantics.

```bash
python scripts/replay_7d.py --run-id replay_off --artifact-dir data/processed --wallet-weighting off --dry-run
python scripts/replay_7d.py --run-id replay_on --artifact-dir data/processed --wallet-weighting on --dry-run
```

### Historical replay smoke

```bash
python scripts/historical_replay_smoke.py
```

This writes deterministic smoke outputs under `data/smoke/`.

Run the end-to-end golden smoke chain:

```bash
python scripts/e2e_golden_smoke.py
```

## PR-RUN-1 runtime signal consumption

This repository also contains the runtime promotion loop and related guards/reporting under `scripts/run_promotion_loop.py` and `src/promotion/`.

Runtime consumes local signal artifacts conservatively: missing or incomplete signal evidence should degrade safely and skip unusable rows rather than inventing paper trades. This replay PR does not change runtime promotion behavior, but it keeps the README section that would otherwise conflict when replay and runtime docs are merged together.

## PR-RUN-1 runtime real signal wiring

The runtime promotion loop now reads real local signal artifacts by default instead of using synthetic placeholder signals.

Primary artifact precedence:

1. `data/processed/entry_candidates.json`
2. `data/processed/entry_candidates.smoke.json`
3. `data/processed/entry_events.jsonl`
4. `data/processed/scored_tokens.json` when it already contains decision-support fields
5. replay-compatible artifacts such as `trade_feature_matrix.jsonl` (canonical), with optional legacy fallback to `trade_feature_matrix.json` when only old local fixtures exist

If artifacts are missing, stale, partial, or malformed, runtime degrades safely, records provenance/status fields, and skips unusable rows rather than inventing trades. Synthetic behavior is still available only through explicit `--signal-source synthetic-dev` opt-in.

Run the real-signal smoke path:

```bash
python scripts/runtime_signal_smoke.py
```

See `docs/runtime_real_signals.md` for the runtime signal contract and fallback behavior.

## PR-RISK-2 evidence-weighted sizing

PR-RISK-2 adds a conservative evidence-weighted sizing layer on top of the existing mode-policy and degraded-X sizing rules.

Highlights:

- preserves hard guards and mode restrictions
- keeps degraded-X reduced-size behavior compatible
- reduces paper/runtime size when evidence is partial, sparse, conflicting, or linkage-risky
- emits explainable sizing fields such as `base_position_pct`, `effective_position_pct`, `sizing_multiplier`, `sizing_reason_codes`, and `sizing_confidence`
- entry decisions now emit the same canonical sizing contract used by runtime guards
- paper execution now uses `effective_position_pct` first, falling back to `recommended_position_pct` only for legacy rows
- extends replay-compatible rows with additive sizing provenance fields

Strong evidence can preserve base size, but this layer does **not** increase size above current safe bounds. Missing evidence never fabricates confidence.

Run sizing smoke:

```bash
python scripts/evidence_weighted_sizing_smoke.py
```

See `docs/evidence_weighted_sizing.md` for the sizing policy, reason codes, event names, and emitted fields.

## PR-10 post-run analyzer

PR-10 adds a post-run analytics layer over paper-trading artifacts:

- reconstructs closed position lifecycle from `trades.jsonl` + `positions.json`
- computes portfolio/regime/exit/friction metrics
- computes descriptive metric correlations vs PnL
- emits conservative machine-readable recommendations
- writes markdown report with caveats and sample warnings

Run smoke:

```bash
python scripts/post_run_analyzer_smoke.py --base-dir data/smoke/post_run
```

## PR-AN-2 richer analyzer slices

PR-AN-2 extends the post-run analyzer with richer, additive diagnostic slices over replay/paper outputs.

Highlights:

- richer regime diagnostics for promotion failures, missed trend follow-through, confidence buckets, and blocker frequency
- richer cluster/bundle diagnostics for creator-linked, concentrated, sell-heavy, retry-heavy, and cross-block bundle behavior
- richer continuation diagnostics for refill, reentry, recovery, buyer-flow, wallet-dispersion, and X-velocity evidence
- degraded-X comparison slices with explicit salvage-case handling
- compact markdown sections plus machine-readable `analyzer_slices.json`
- conservative recommendation hints that stay manual-only and sample-size-aware

Artifacts:

- `data/processed/analyzer_slices.json`
- `data/processed/post_run_summary.json`
- `data/processed/post_run_recommendations.json`
- `data/processed/post_run_report.md`

Run analyzer slices smoke:

```bash
python scripts/analyzer_slices_smoke.py
```

See `docs/analyzer_slices.md` for the slice families, honesty policy, and output contract.

## PR-SIG-3 continuation enrichment

PR-SIG-3 adds the continuation evidence layer that sits between short-horizon helper computations and downstream score/exit consumers. It keeps continuation outputs explicit, additive, and fail-open when tx, X, or wallet-registry evidence is incomplete.

### Evidence lanes

Transaction-derived metrics:

- `net_unique_buyers_60s`
- `liquidity_refill_ratio_120s`
- `cluster_sell_concentration_120s`
- `seller_reentry_ratio`
- `liquidity_shock_recovery_sec`

X-derived metrics:

- `x_author_velocity_5m`

Wallet-registry-derived metrics:

- `smart_wallet_dispersion_score`

Additive provenance/status fields:

- `continuation_status`
- `continuation_warning`
- `continuation_confidence`
- `continuation_metric_origin`
- `continuation_coverage_ratio`
- `continuation_inputs_status`

### Missing-evidence policy

- Missing evidence remains missing; it is not silently converted into bullish or bearish continuation strength.
- Partial evidence is labeled `partial`, not treated as complete coverage.
- Downstream scoring can consume continuation fields, but low-confidence continuation evidence is intentionally damped.

### Continuation smoke

```bash
python scripts/continuation_smoke.py
```

Artifacts written under `data/smoke/`:

- `continuation_enrichment.smoke.json`
- `continuation_status.json`
- `continuation_events.jsonl`

See `docs/continuation_enricher.md` for the full contract, provenance semantics, and fallback behavior.

## PR-CL-3 linkage scorer

PR-CL-3 adds a creator/dev/funder linkage layer that keeps the existing cluster heuristics but emits explicit evidence-backed linkage outputs for downstream scoring, regime checks, exits, replay, and future analyzer work.

Key points:

- linkage uses shared funders, shared cluster ids, shared launch groups, and direct creator/dev-linked participation hints;
- outputs remain additive and fail-open when creator/dev/funder evidence is missing or malformed;
- bundle-stage enrichment keeps linkage fields null-filled when evidence is unavailable so downstream contracts stay stable;
- confidence and provenance are exposed through `linkage_confidence`, `linkage_reason_codes`, `linkage_metric_origin`, and `linkage_status`;
- emitted provenance enums for bundle / cluster / linkage / wallet-family artifacts are normalized through `utils/provenance_enums.py` to keep runtime, replay, analyzer, and docs on one canonical vocabulary;
- this PR does **not** claim identity certainty, and weak evidence stays low-confidence.

## PR-WAL-7 wallet family metadata

PR-WAL-7 adds a deterministic wallet family metadata layer that enriches wallet-registry records without redesigning the registry or claiming hard real-world identity certainty.

Highlights:

- broader `wallet_family_id` plus stricter `independent_family_id`
- provenance-aware confidence via `wallet_family_origin`, `wallet_family_confidence`, `wallet_family_reason_codes`, and `wallet_family_status`
- additive registry integration through `scripts/build_wallet_registry.py`
- validated-registry propagation for downstream enrichment consumers
- runtime / replay propagation of aggregated token-facing wallet-family summary fields without forcing a singular token-level family id
- smoke outputs under `data/smoke/`

Evidence lanes include cluster overlap, shared funders, repeated launch overlap, registry hints, linkage-group hints, and creator/dev overlap flags.
Missing or malformed evidence degrades safely instead of inventing strong family assignments.

Run the wallet family smoke:

```bash
python scripts/wallet_family_metadata_smoke.py
```

Artifacts written by default:

- `data/smoke/wallet_family_metadata.smoke.json`
- `data/smoke/wallet_family_summary.json`

See `docs/wallet_family_metadata.md` for the evidence model, the difference between broad vs strict family ids, and the fallback policy.

## PR-ML-1 offline feature importance

PR-ML-1 adds an offline feature importance layer over replay-derived trade matrices such as `trade_feature_matrix.jsonl`.

Highlights:

- computes offline-only feature importance for explicit replay targets
- emits grouped and per-feature rankings
- reports sample size, missingness, malformed rows, and exclusions
- writes machine-readable JSON plus markdown summaries
- keeps outputs analysis-only and not for online decisioning

Supported offline targets:

- `profitable_trade_flag`
- `trend_success_flag`
- `fast_failure_flag`

Run the deterministic smoke path:

```bash
python scripts/offline_feature_importance_smoke.py
```

Artifacts written by the smoke path:

- `data/smoke/offline_feature_importance.json`
- `data/smoke/offline_feature_importance_summary.md`

See `docs/offline_feature_importance.md` for the target definitions, grouping logic, methods, caveats, and honesty policy.



- unified scoring now emits explicit evidence-quality penalties (`partial_evidence_penalty`, `low_confidence_evidence_penalty`) derived from a shared evidence-quality summary helper used by both score and sizing layers.
