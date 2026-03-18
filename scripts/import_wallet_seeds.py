#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.append(str(REPO_ROOT))

from collectors.wallet_seed_import import import_wallet_seeds


def main() -> int:
    parser = argparse.ArgumentParser(description="Import manual wallet seeds into canonical normalized candidates.")
    parser.add_argument("--manual-dir", default="data/registry/raw/manual")
    parser.add_argument("--out", default="data/registry/normalized_wallet_candidates.json")
    parser.add_argument("--event-log", default="data/registry/import_events.jsonl")
    args = parser.parse_args()

    artifact = import_wallet_seeds(args.manual_dir, args.out, args.event_log)
    print(json.dumps(artifact["input_summary"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
