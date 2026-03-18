"""Manual wallet seed import and normalization utilities."""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path
from typing import Any

from utils.clock import utc_now_iso
from utils.io import append_jsonl, ensure_dir, write_json

CONTRACT_VERSION = "wallet_seed_import.v1"
_BASE58_RE = re.compile(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$")


ParsedRecord = dict[str, Any]


def is_plausible_solana_wallet(value: Any) -> bool:
    wallet = str(value or "").strip()
    if not wallet:
        return False
    return bool(_BASE58_RE.fullmatch(wallet))


def _string_or_none(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _build_source_record(record: ParsedRecord) -> dict[str, Any]:
    return {
        "source_name": "manual",
        "source_type": record["source_type"],
        "file_path": record["file_path"],
        "observed_label": record.get("observed_label"),
        "observed_at": record.get("observed_at"),
        "raw_fields": record.get("raw_fields", {}),
    }


def _parse_csv(path: Path, file_path: str, issues: list[dict[str, Any]]) -> list[ParsedRecord]:
    rows: list[ParsedRecord] = []
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        headers = [h.strip() for h in (reader.fieldnames or []) if h is not None]
        if "wallet" not in headers:
            issues.append({
                "kind": "unsupported_file",
                "file_path": file_path,
                "reason": "csv_missing_wallet_header",
            })
            return rows

        for line_num, row in enumerate(reader, start=2):
            normalized_raw = {str(k or "").strip(): (v if v is not None else "") for k, v in row.items()}
            rows.append(
                {
                    "wallet": str(row.get("wallet") or "").strip(),
                    "tag": str(row.get("tag") or "").strip(),
                    "notes": str(row.get("notes") or "").strip(),
                    "source_type": "manual_csv",
                    "file_path": file_path,
                    "observed_label": str(row.get("tag") or "").strip() or None,
                    "observed_at": None,
                    "raw_fields": normalized_raw,
                    "line_number": line_num,
                }
            )
    return rows


def _parse_txt(path: Path, file_path: str) -> list[ParsedRecord]:
    rows: list[ParsedRecord] = []
    for line_num, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        wallet = line.strip()
        rows.append(
            {
                "wallet": wallet,
                "tag": "",
                "notes": "",
                "source_type": "manual_txt",
                "file_path": file_path,
                "observed_label": None,
                "observed_at": None,
                "raw_fields": {"line": line},
                "line_number": line_num,
            }
        )
    return rows


def _parse_json(path: Path, file_path: str, issues: list[dict[str, Any]]) -> list[ParsedRecord]:
    rows: list[ParsedRecord] = []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        issues.append({"kind": "unsupported_file", "file_path": file_path, "reason": "invalid_json"})
        return rows

    if not isinstance(payload, list):
        issues.append({"kind": "unsupported_file", "file_path": file_path, "reason": "json_not_list"})
        return rows

    for idx, item in enumerate(payload, start=1):
        if isinstance(item, str):
            rows.append(
                {
                    "wallet": item.strip(),
                    "tag": "",
                    "notes": "",
                    "source_type": "manual_json",
                    "file_path": file_path,
                    "observed_label": None,
                    "observed_at": None,
                    "raw_fields": {"value": item},
                    "line_number": idx,
                }
            )
            continue

        if isinstance(item, dict):
            rows.append(
                {
                    "wallet": str(item.get("wallet") or "").strip(),
                    "tag": str(item.get("tag") or "").strip(),
                    "notes": str(item.get("notes") or "").strip(),
                    "source_type": "manual_json",
                    "file_path": file_path,
                    "observed_label": str(item.get("tag") or "").strip() or None,
                    "observed_at": _string_or_none(item.get("observed_at")),
                    "raw_fields": item,
                    "line_number": idx,
                }
            )
            continue

        issues.append(
            {
                "kind": "invalid_row",
                "file_path": file_path,
                "line_number": idx,
                "reason": "json_item_unsupported",
                "raw_fields": {"value": item},
            }
        )
    return rows


def _parse_supported_file(path: Path, manual_dir: Path, issues: list[dict[str, Any]]) -> list[ParsedRecord]:
    rel_path = str(path.relative_to(manual_dir).as_posix())
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return _parse_csv(path, rel_path, issues)
    if suffix == ".txt":
        return _parse_txt(path, rel_path)
    if suffix == ".json":
        return _parse_json(path, rel_path, issues)

    issues.append({"kind": "unsupported_file", "file_path": rel_path, "reason": f"unsupported_extension:{suffix or 'none'}"})
    return []


def _empty_artifact(generated_at: str) -> dict[str, Any]:
    return {
        "contract_version": CONTRACT_VERSION,
        "generated_at": generated_at,
        "input_summary": {
            "total_rows_seen": 0,
            "valid_wallets": 0,
            "invalid_rows": 0,
            "duplicates_removed": 0,
            "files_seen": 0,
        },
        "candidates": [],
    }


def import_wallet_seeds(
    manual_dir: str | Path,
    out_path: str | Path,
    event_log_path: str | Path,
    *,
    generated_at: str | None = None,
) -> dict[str, Any]:
    timestamp = generated_at or utc_now_iso()
    root = Path(manual_dir)
    issues: list[dict[str, Any]] = []

    if not root.exists() or not root.is_dir():
        artifact = _empty_artifact(timestamp)
        write_json(out_path, artifact)
        append_jsonl(
            event_log_path,
            {
                "event": "wallet_seed_import",
                "status": "manual_dir_missing",
                "manual_dir": str(root.as_posix()),
                "generated_at": timestamp,
                "input_summary": artifact["input_summary"],
                "issues": [],
            },
        )
        return artifact

    parsed: list[ParsedRecord] = []
    files_seen = 0
    for path in sorted(p for p in root.iterdir() if p.is_file() and not p.name.startswith(".")):
        files_seen += 1
        parsed.extend(_parse_supported_file(path, root, issues))

    total_rows_seen = 0
    invalid_rows = 0
    by_wallet: dict[str, dict[str, Any]] = {}

    for row in parsed:
        total_rows_seen += 1
        wallet = str(row.get("wallet") or "").strip()
        if not is_plausible_solana_wallet(wallet):
            invalid_rows += 1
            issues.append(
                {
                    "kind": "invalid_row",
                    "file_path": row["file_path"],
                    "line_number": row.get("line_number"),
                    "reason": "invalid_wallet",
                    "wallet": wallet,
                    "raw_fields": row.get("raw_fields", {}),
                }
            )
            continue

        existing = by_wallet.get(wallet)
        source_record = _build_source_record(row)
        tag = str(row.get("tag") or "").strip()
        notes = str(row.get("notes") or "").strip()

        if existing is None:
            by_wallet[wallet] = {
                "wallet": wallet,
                "status": "candidate",
                "source_names": ["manual"],
                "source_count": 1,
                "source_records": [source_record],
                "first_seen_at": row.get("observed_at") or timestamp,
                "last_seen_at": row.get("observed_at") or timestamp,
                "imported_at": timestamp,
                "tags": [tag] if tag else [],
                "manual_priority": True,
                "notes": notes or None,
            }
            continue

        existing["source_records"].append(source_record)
        if row.get("observed_at"):
            existing["last_seen_at"] = row["observed_at"]
        if not existing["tags"] and tag:
            existing["tags"] = [tag]
        if not existing["notes"] and notes:
            existing["notes"] = notes

    candidates = sorted(by_wallet.values(), key=lambda item: (-int(bool(item.get("manual_priority"))), str(item.get("wallet", ""))))
    valid_wallets = len(candidates)
    duplicates_removed = max(0, total_rows_seen - invalid_rows - valid_wallets)

    artifact = {
        "contract_version": CONTRACT_VERSION,
        "generated_at": timestamp,
        "input_summary": {
            "total_rows_seen": total_rows_seen,
            "valid_wallets": valid_wallets,
            "invalid_rows": invalid_rows,
            "duplicates_removed": duplicates_removed,
            "files_seen": files_seen,
        },
        "candidates": candidates,
    }

    write_json(out_path, artifact)
    ensure_dir(Path(event_log_path).expanduser().resolve().parent)
    append_jsonl(
        event_log_path,
        {
            "event": "wallet_seed_import",
            "status": "ok",
            "manual_dir": str(root.as_posix()),
            "generated_at": timestamp,
            "input_summary": artifact["input_summary"],
            "issues": issues,
        },
    )
    return artifact
