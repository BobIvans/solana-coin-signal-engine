from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from src.wallets.normalize import normalize_wallet_record
from utils.io import write_json


def load_raw_wallets(path: str | Path, fmt: str) -> list[dict[str, Any]]:
    target = Path(path)
    if not target.exists():
        return []
    fmt_l = fmt.lower()
    if fmt_l == "json":
        payload = json.loads(target.read_text(encoding="utf-8"))
        return list(payload) if isinstance(payload, list) else []
    if fmt_l == "jsonl":
        out: list[dict[str, Any]] = []
        for line in target.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                out.append(json.loads(line))
        return out
    if fmt_l == "csv":
        with target.open("r", encoding="utf-8", newline="") as handle:
            return list(csv.DictReader(handle))
    raise ValueError(f"Unsupported wallet format: {fmt}")


def deduplicate_wallets(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: dict[str, dict[str, Any]] = {}
    for record in records:
        wallet = str(record.get("wallet_address") or "")
        if wallet not in deduped:
            deduped[wallet] = {**record, "sources": sorted({str(record.get("source") or "unknown")})}
            continue
        current = deduped[wallet]
        if float(record.get("score") or 0.0) > float(current.get("score") or 0.0):
            current["score"] = float(record.get("score") or 0.0)
            current["tier"] = record.get("tier", current.get("tier"))
            current["status"] = record.get("status", current.get("status"))
        current["sources"] = sorted(set(current.get("sources", [])) | {str(record.get("source") or "unknown")})
        first_seen = sorted([x for x in [current.get("first_seen_at"), record.get("first_seen_at")] if x])
        last_seen = sorted([x for x in [current.get("last_seen_at"), record.get("last_seen_at")] if x])
        if first_seen:
            current["first_seen_at"] = first_seen[0]
        if last_seen:
            current["last_seen_at"] = last_seen[-1]
    return [deduped[key] for key in sorted(deduped)]


def build_wallet_registry(records: list[dict[str, Any]], config: dict[str, Any]) -> tuple[list[dict[str, Any]], int]:
    normalized: list[dict[str, Any]] = []
    invalid_count = 0
    for record in records:
        item = normalize_wallet_record(record)
        if item.get("_invalid_reason"):
            invalid_count += 1
            continue
        normalized.append(item)

    if bool(config.get("registry", {}).get("drop_inactive")):
        normalized = [item for item in normalized if item.get("status") != "inactive"]
    if bool(config.get("registry", {}).get("drop_quarantine", True)):
        normalized = [item for item in normalized if item.get("status") != "quarantine"]

    if bool(config.get("registry", {}).get("deduplicate", True)):
        normalized = deduplicate_wallets(normalized)

    return normalized, invalid_count


def write_wallet_registry(path: str | Path, registry: list[dict[str, Any]]) -> None:
    write_json(path, {"wallets": sorted(registry, key=lambda item: item["wallet_address"])})
