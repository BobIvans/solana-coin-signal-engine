#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.append(str(REPO_ROOT))

from src.wallets.registry import build_wallet_registry, load_raw_wallets, write_wallet_registry


def _coerce_scalar(value: str) -> Any:
    v = value.strip().strip('"').strip("'")
    if v.lower() in {"true", "false"}:
        return v.lower() == "true"
    try:
        if "." in v:
            return float(v)
        return int(v)
    except ValueError:
        return v


def _load_config(path: str) -> dict[str, Any]:
    target = Path(path)
    if not target.exists():
        return {}
    out: dict[str, Any] = {}
    stack: list[tuple[int, dict[str, Any]]] = [(-1, out)]
    for raw in target.read_text(encoding="utf-8").splitlines():
        line = raw.rstrip()
        if not line or line.lstrip().startswith("#"):
            continue
        indent = len(line) - len(line.lstrip(" "))
        key, _, value = line.strip().partition(":")
        while stack and indent <= stack[-1][0]:
            stack.pop()
        parent = stack[-1][1]
        if value.strip() == "":
            parent[key] = {}
            stack.append((indent, parent[key]))
        else:
            parent[key] = _coerce_scalar(value)
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config/wallets.default.yaml")
    parser.add_argument("--input")
    parser.add_argument("--output")
    parser.add_argument("--format", choices=["json", "jsonl", "csv"])
    parser.add_argument("--drop-inactive", action="store_true")
    parser.add_argument("--drop-quarantine", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    config = _load_config(args.config)
    in_cfg = config.get("input", {})
    reg_cfg = config.setdefault("registry", {})

    input_path = args.input or in_cfg.get("path", "data/smart_wallets.raw.json")
    output_path = args.output or reg_cfg.get("output_path", "data/smart_wallets.registry.json")
    fmt = args.format or in_cfg.get("format", "json")

    reg_cfg["drop_inactive"] = bool(args.drop_inactive or reg_cfg.get("drop_inactive", False))
    reg_cfg["drop_quarantine"] = bool(args.drop_quarantine or reg_cfg.get("drop_quarantine", True))

    raw = load_raw_wallets(input_path, fmt)
    print(f"[wallets] input_loaded count={len(raw)}")
    registry, invalid_count = build_wallet_registry(raw, config)
    print(f"[wallets] normalized valid={len(raw) - invalid_count} invalid={invalid_count}")
    print(f"[wallets] deduplicated unique={len(registry)}")

    if not args.dry_run:
        write_wallet_registry(output_path, registry)
        print(f"[wallets] registry_written path={output_path}")
    print("[wallets] done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
