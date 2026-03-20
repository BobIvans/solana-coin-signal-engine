from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURES_DIR = REPO_ROOT / "tests" / "fixtures"

for candidate in (REPO_ROOT, FIXTURES_DIR):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from false_positive_cases import build_false_positive_smoke_summary, render_false_positive_summary_md


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-json", default="data/smoke/false_positive_summary.json")
    parser.add_argument("--out-md", default="data/smoke/false_positive_summary.md")
    args = parser.parse_args()

    out_json = Path(args.out_json)
    out_md = Path(args.out_md)

    summary = build_false_positive_smoke_summary()

    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_md.parent.mkdir(parents=True, exist_ok=True)

    out_json.write_text(
        json.dumps(summary, sort_keys=True, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    out_md.write_text(render_false_positive_summary_md(summary), encoding="utf-8")

    concise = {
        "total_cases": summary["total_cases"],
        "status": summary["status"],
        "case_names": summary["case_names"],
    }
    print(json.dumps(concise, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
