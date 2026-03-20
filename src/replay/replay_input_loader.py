from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_JSONL_FILE_NAMES = {
    "scored_rows": ["scored_tokens.jsonl", "scored_tokens.json"],
    "entry_candidates": ["entry_candidates.json", "entry_candidates.jsonl"],
    "signals": ["signals.jsonl", "signal_events.jsonl", "entry_events.jsonl"],
    "trades": ["trades.jsonl", "trade_events.jsonl"],
    "positions": ["positions.json"],
    "price_paths": ["price_paths.json", "price_paths.jsonl", "lifecycle_observations.jsonl"],
    "universe": ["universe.json", "universe.jsonl", "scored_tokens.json"],
}
_REQUIRED_TOKEN_KEY = "token_address"


def _ensure_list(payload: Any) -> list[Any]:
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ("items", "rows", "tokens", "entries", "positions", "price_paths", "signals", "trades"):
            if isinstance(payload.get(key), list):
                return payload[key]
    return []


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_no, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        row = json.loads(line)
        if isinstance(row, dict):
            row.setdefault("_source_file", str(path))
            row.setdefault("_source_line", line_no)
            rows.append(row)
    return rows


def _load_file(path: Path) -> list[dict[str, Any]]:
    if path.suffix == ".jsonl":
        return _read_jsonl(path)
    payload = _read_json(path)
    rows = _ensure_list(payload)
    output: list[dict[str, Any]] = []
    for idx, row in enumerate(rows, start=1):
        if isinstance(row, dict):
            row = dict(row)
            row.setdefault("_source_file", str(path))
            row.setdefault("_source_index", idx)
            output.append(row)
    return output


def _resolve_artifact_path(artifact_dir: Path, explicit_path: str | Path | None, candidates: list[str]) -> Path | None:
    if explicit_path:
        path = Path(explicit_path)
        return path if path.exists() else None
    for name in candidates:
        path = artifact_dir / name
        if path.exists():
            return path
    return None


def _canonical_token(row: dict[str, Any]) -> str | None:
    token_address = row.get("token_address") or row.get("mint") or row.get("address")
    return str(token_address) if token_address else None


def _canonical_pair(row: dict[str, Any]) -> str | None:
    pair_address = row.get("pair_address") or row.get("pool_address") or row.get("pair")
    return str(pair_address) if pair_address else None


def _normalize_price_path_row(row: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(row)
    normalized["token_address"] = _canonical_token(row)
    normalized["pair_address"] = _canonical_pair(row)
    observations = row.get("price_path") or row.get("observations") or row.get("lifecycle_path") or []
    normalized["price_path"] = observations if isinstance(observations, list) else []
    return normalized


def validate_replay_inputs(loaded_inputs: dict[str, Any]) -> dict[str, Any]:
    warnings = list(loaded_inputs.get("warnings", []))
    malformed_rows = 0
    token_status: dict[str, dict[str, Any]] = {}

    for token, payload in loaded_inputs.get("token_inputs", {}).items():
        missing: list[str] = []
        scored = payload.get("scored_rows") or []
        entries = payload.get("entry_candidates") or []
        signals = payload.get("signals") or []
        trades = payload.get("trades") or []
        positions = payload.get("positions") or []
        price_paths = payload.get("price_paths") or []

        if not (scored or entries or signals or trades or positions):
            missing.append("candidate_context")
        if not price_paths:
            missing.append("price_path")
        elif any(bool(path.get("truncated")) for path in price_paths):
            missing.append("truncated_price_path")

        if payload.get("malformed_rows"):
            malformed_rows += int(payload["malformed_rows"])

        status = "historical"
        if missing:
            status = "historical_partial"
        if payload.get("malformed_rows") and not (scored or entries or signals or trades or positions):
            status = "malformed"
        token_status[token] = {
            "token_address": token,
            "missing_evidence": missing,
            "replay_data_status": status,
            "warnings": list(dict.fromkeys(payload.get("warnings", []))),
        }

    return {
        "warnings": warnings,
        "malformed_rows": malformed_rows,
        "token_status": token_status,
        "historical_rows": sum(1 for item in token_status.values() if item["replay_data_status"] == "historical"),
        "partial_rows": sum(1 for item in token_status.values() if item["replay_data_status"] == "historical_partial"),
        "malformed_tokens": sum(1 for item in token_status.values() if item["replay_data_status"] == "malformed"),
    }


def load_replay_universe(*, artifact_dir: str | Path, loaded_files: dict[str, Path] | None = None) -> list[dict[str, Any]]:
    base = Path(artifact_dir)
    path = (loaded_files or {}).get("universe") or _resolve_artifact_path(base, None, _JSONL_FILE_NAMES["universe"])
    rows = _load_file(path) if path else []
    universe: dict[str, dict[str, Any]] = {}
    for row in rows:
        token_address = _canonical_token(row)
        if not token_address:
            continue
        universe[token_address] = {
            "token_address": token_address,
            "pair_address": _canonical_pair(row),
            **row,
        }
    return [universe[key] for key in sorted(universe)]


def load_replay_price_paths(*, artifact_dir: str | Path, loaded_files: dict[str, Path] | None = None) -> dict[str, list[dict[str, Any]]]:
    base = Path(artifact_dir)
    path = (loaded_files or {}).get("price_paths") or _resolve_artifact_path(base, None, _JSONL_FILE_NAMES["price_paths"])
    rows = _load_file(path) if path else []
    by_token: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        normalized = _normalize_price_path_row(row)
        token_address = normalized.get("token_address")
        if not token_address:
            continue
        by_token.setdefault(token_address, []).append(normalized)
    return by_token


def load_replay_inputs(
    *,
    artifact_dir: str | Path,
    scored_path: str | Path | None = None,
    entry_candidates_path: str | Path | None = None,
    signals_path: str | Path | None = None,
    trades_path: str | Path | None = None,
    positions_path: str | Path | None = None,
    price_paths_path: str | Path | None = None,
    universe_path: str | Path | None = None,
) -> dict[str, Any]:
    artifact_dir = Path(artifact_dir)
    loaded_files = {
        "scored_rows": _resolve_artifact_path(artifact_dir, scored_path, _JSONL_FILE_NAMES["scored_rows"]),
        "entry_candidates": _resolve_artifact_path(artifact_dir, entry_candidates_path, _JSONL_FILE_NAMES["entry_candidates"]),
        "signals": _resolve_artifact_path(artifact_dir, signals_path, _JSONL_FILE_NAMES["signals"]),
        "trades": _resolve_artifact_path(artifact_dir, trades_path, _JSONL_FILE_NAMES["trades"]),
        "positions": _resolve_artifact_path(artifact_dir, positions_path, _JSONL_FILE_NAMES["positions"]),
        "price_paths": _resolve_artifact_path(artifact_dir, price_paths_path, _JSONL_FILE_NAMES["price_paths"]),
        "universe": _resolve_artifact_path(artifact_dir, universe_path, _JSONL_FILE_NAMES["universe"]),
    }

    token_inputs: dict[str, dict[str, Any]] = {}
    warnings: list[str] = []

    def add_row(bucket: str, row: dict[str, Any], *, create_missing: bool = True) -> None:
        token_address = _canonical_token(row)
        if not token_address:
            malformed_key = f"malformed::{bucket}::{len(token_inputs)}"
            token_inputs.setdefault(malformed_key, {
                "token_address": None,
                "warnings": [],
                "malformed_rows": 0,
                "scored_rows": [],
                "entry_candidates": [],
                "signals": [],
                "trades": [],
                "positions": [],
                "price_paths": [],
            })
            token_inputs[malformed_key]["malformed_rows"] += 1
            token_inputs[malformed_key]["warnings"].append(f"missing_token_address:{bucket}")
            warnings.append(f"missing_token_address:{bucket}")
            return
        if not create_missing and token_address not in token_inputs:
            return
        record = token_inputs.setdefault(
            token_address,
            {
                "token_address": token_address,
                "pair_address": _canonical_pair(row),
                "warnings": [],
                "malformed_rows": 0,
                "scored_rows": [],
                "entry_candidates": [],
                "signals": [],
                "trades": [],
                "positions": [],
                "price_paths": [],
            },
        )
        if record.get("pair_address") is None:
            record["pair_address"] = _canonical_pair(row)
        record[bucket].append(row)

    for bucket in ("entry_candidates", "signals", "trades", "positions"):
        path = loaded_files[bucket]
        if not path:
            continue
        for row in _load_file(path):
            add_row(bucket, row, create_missing=True)

    path = loaded_files["scored_rows"]
    if path:
        for row in _load_file(path):
            add_row("scored_rows", row, create_missing=False)

    for token_address, rows in load_replay_price_paths(artifact_dir=artifact_dir, loaded_files=loaded_files).items():
        record = token_inputs.setdefault(
            token_address,
            {
                "token_address": token_address,
                "pair_address": None,
                "warnings": [],
                "malformed_rows": 0,
                "scored_rows": [],
                "entry_candidates": [],
                "signals": [],
                "trades": [],
                "positions": [],
                "price_paths": [],
            },
        )
        record["price_paths"].extend(rows)

    universe = load_replay_universe(artifact_dir=artifact_dir, loaded_files=loaded_files)
    for row in universe:
        token_address = row["token_address"]
        if token_address not in token_inputs:
            continue
        if token_inputs[token_address].get("pair_address") is None:
            token_inputs[token_address]["pair_address"] = row.get("pair_address")

    payload = {
        "artifact_dir": str(artifact_dir),
        "loaded_files": {key: str(path) for key, path in loaded_files.items() if path},
        "token_inputs": dict(sorted(token_inputs.items(), key=lambda item: item[0])),
        "universe": universe,
        "warnings": list(dict.fromkeys(warnings)),
    }
    payload["validation"] = validate_replay_inputs(payload)
    return payload
