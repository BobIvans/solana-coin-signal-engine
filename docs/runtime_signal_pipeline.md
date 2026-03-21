# Runtime Signal Pipeline

`PR-RUN-2a` introduces a canonical orchestration command for producing runtime-consumable local artifacts.

Primary artifact chain:

- `shortlist.json`
- `x_validated.json`
- `enriched_tokens.json`
- `rug_assessed_tokens.json`
- `scored_tokens.json`
- `entry_candidates.json`

Canonical command:

```bash
python scripts/run_runtime_signal_pipeline.py --processed-dir data/processed
```

The command writes `runtime_signal_pipeline_manifest.json` with stage statuses, row counts, artifact paths, warnings, and generation metadata.
