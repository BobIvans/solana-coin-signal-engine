# solana-coin-signal-engine

This repository contains deterministic scoring, regime-selection, exit, replay, calibration, promotion, and smoke tooling for a Solana memecoin signal engine.

## Historical replay harness

The replay path is now evidence-first.

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

```bash
python scripts/replay_7d.py --run-id replay_off --artifact-dir data/processed --wallet-weighting off --dry-run
python scripts/replay_7d.py --run-id replay_on --artifact-dir data/processed --wallet-weighting on --dry-run
```

### Historical replay smoke

```bash
python scripts/historical_replay_smoke.py
```

This writes deterministic smoke outputs under `data/smoke/`.

## PR-RUN-1 runtime signal consumption

This repository also contains the runtime promotion loop and related guards/reporting under `scripts/run_promotion_loop.py` and `src/promotion/`.

Runtime consumes local signal artifacts conservatively: missing or incomplete signal evidence should degrade safely and skip unusable rows rather than inventing paper trades. This replay PR does not change runtime promotion behavior, but it keeps the README section that would otherwise conflict when replay and runtime docs are merged together.

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
- this PR does **not** claim identity certainty, and weak evidence stays low-confidence.
