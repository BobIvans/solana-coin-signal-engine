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

## Other smoke scripts

```bash
python scripts/onchain_enrichment_smoke.py
python scripts/unified_score_smoke.py
python scripts/entry_selector_smoke.py
python scripts/continuation_smoke.py
python scripts/linkage_smoke.py
python scripts/post_run_analyzer_smoke.py
```

## Tests

```bash
pytest -q
```

## Additional docs

- `docs/historical_replay_harness.md`
- `docs/unified_score.md`
- `docs/exit_engine.md`
- `docs/continuation_enricher.md`
- `docs/wallet_registry_replay.md`
