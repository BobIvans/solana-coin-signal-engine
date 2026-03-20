#!/usr/bin/env python3
"""Deterministic smoke runner for wallet family metadata fixtures."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
root_str = str(ROOT)
if root_str not in sys.path:
    sys.path.append(root_str)

from analytics.wallet_family_metadata import derive_wallet_family_metadata
from utils.io import write_json


SMOKE_WALLETS = [
    {
        "wallet": "wallet_alpha",
        "wallet_cluster_id": "cluster_core",
        "funder": "funder_core",
        "launch_group": ["launch_1", "launch_2"],
        "linkage_group": "linkage_core",
        "linked_wallets": ["wallet_beta"],
        "creator_linked": True,
    },
    {
        "wallet": "wallet_beta",
        "wallet_cluster_id": "cluster_core",
        "funder": "funder_core",
        "launch_group": ["launch_1", "launch_2"],
        "linkage_group": "linkage_core",
        "linked_wallets": ["wallet_alpha"],
        "creator_linked": True,
    },
    {
        "wallet": "wallet_gamma",
        "wallet_cluster_id": "cluster_loose",
    },
    {
        "wallet": "wallet_delta",
        "wallet_cluster_id": "cluster_loose",
    },
    {
        "wallet": "wallet_epsilon",
        "funder": "heuristic_funder",
    },
    {
        "wallet": "wallet_zeta",
        "funder": "heuristic_funder",
    },
    {
        "wallet": "wallet_eta",
        "creator_linked": True,
        "linkage_group": "creator_slice",
    },
    {
        "wallet": "wallet_theta",
        "creator_linked": True,
        "linkage_group": "creator_slice",
    },
    {
        "wallet": "wallet_iota",
    },
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", default="data/smoke")
    parser.add_argument("--generated-at", default="2024-01-02T00:00:00Z")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    out_dir = Path(args.out_dir).expanduser().resolve()
    metadata = derive_wallet_family_metadata(SMOKE_WALLETS, generated_at=args.generated_at)
    summary_payload = {
        "contract_version": metadata["contract_version"],
        "generated_at": metadata["generated_at"],
        "summary": metadata["summary"],
        "family_summaries": metadata["family_summaries"],
        "warnings": metadata["warnings"],
    }

    metadata_path = write_json(out_dir / "wallet_family_metadata.smoke.json", metadata)
    summary_path = write_json(out_dir / "wallet_family_summary.json", summary_payload)

    compact = {
        "wallet_count": metadata["summary"]["wallet_count"],
        "family_count": metadata["summary"]["family_count"],
        "independent_family_count": metadata["summary"]["independent_family_count"],
        "warning_count": metadata["summary"]["warning_count"],
        "metadata_path": str(metadata_path),
        "summary_path": str(summary_path),
    }
    print(json.dumps(compact, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
