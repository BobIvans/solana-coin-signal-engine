# Wallet Seed Import (Manual CSV/TXT/JSON)

This import pipeline creates a deterministic wallet-candidate universe from manually curated files only.

## What this does

- Reads supported manual files under `data/registry/raw/manual/`.
- Validates + normalizes wallet rows.
- Deduplicates by normalized wallet string.
- Preserves minimal lineage via `source_records`.
- Writes canonical output to `data/registry/normalized_wallet_candidates.json`.
- Appends one import event per run to `data/registry/import_events.jsonl`.

## What this does **not** do yet

- No scoring.
- No replay or promotion.
- No changes to entry/exit logic.
- No external API calls.

## Supported manual formats

- CSV header: `wallet`
- CSV header: `wallet,tag,notes`
- TXT: one wallet per line
- JSON:
  - `list[str]`
  - `list[object]` where each object includes `wallet` (optional `tag`, `notes`, `observed_at`)

Unsupported files are skipped and logged in `import_events.jsonl`.

## Validation and normalization rules

- Trim whitespace.
- Ignore empty/invalid wallet values.
- Lightweight Solana plausibility check only:
  - non-empty
  - base58-like characters only
  - length range 32..44
- No network validation.

Invalid rows are skipped and logged; there is no silent dropping.

## Dedupe + field preservation

- Deduplicate by exact normalized wallet string.
- Keep first non-empty `tag` as `tags: [tag]`.
- Keep first non-empty `notes`.
- Keep all lineage entries in `source_records`.

## Deterministic ordering

Candidates are sorted by:

1. `manual_priority` descending
2. `wallet` ascending

## CLI

```bash
python scripts/import_wallet_seeds.py \
  --manual-dir data/registry/raw/manual \
  --out data/registry/normalized_wallet_candidates.json
```

Optional:

- `--event-log data/registry/import_events.jsonl`

## Output contract

`normalized_wallet_candidates.json` contains:

- `contract_version` (`wallet_seed_import.v1`)
- `generated_at`
- `input_summary`
- `candidates`

Schema: `schemas/normalized_wallet_candidates.schema.json`.
