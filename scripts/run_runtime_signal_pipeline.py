from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.pipeline.runtime_signal_pipeline import run_runtime_signal_pipeline


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Canonical runtime signal pipeline orchestrator")
    parser.add_argument("--processed-dir", default="data/processed")
    parser.add_argument("--config", default=None)
    parser.add_argument("--skip-discovery", action="store_true")
    parser.add_argument("--skip-x-validation", action="store_true")
    parser.add_argument("--skip-enrichment", action="store_true")
    parser.add_argument("--skip-rug", action="store_true")
    parser.add_argument("--skip-scoring", action="store_true")
    parser.add_argument("--skip-entry", action="store_true")
    parser.add_argument("--shortlist-path")
    parser.add_argument("--x-validated-path")
    parser.add_argument("--enriched-path")
    parser.add_argument("--rug-path")
    parser.add_argument("--scored-path")
    parser.add_argument("--entry-path")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    overrides = {
        key: value
        for key, value in {
            "shortlist": args.shortlist_path,
            "x_validated": args.x_validated_path,
            "enriched": args.enriched_path,
            "rug": args.rug_path,
            "scored": args.scored_path,
            "entry": args.entry_path,
        }.items()
        if value
    }
    manifest = run_runtime_signal_pipeline(
        processed_dir=Path(args.processed_dir),
        config_path=args.config,
        discovery_enabled=not args.skip_discovery,
        x_validation_enabled=not args.skip_x_validation,
        enrichment_enabled=not args.skip_enrichment,
        rug_enabled=not args.skip_rug,
        scoring_enabled=not args.skip_scoring,
        entry_enabled=not args.skip_entry,
        stage_overrides=overrides,
    )
    print(json.dumps(manifest, sort_keys=True, ensure_ascii=False))
    return 0 if manifest.get("pipeline_status") in {"ok", "partial"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
