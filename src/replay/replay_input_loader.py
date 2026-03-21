from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from utils.io import list_jsonl_segments, read_jsonl

_GENERIC_SCORED_FILE_NAMES = ["scored_tokens.jsonl", "scored_tokens.json"]
_JSONL_FILE_NAMES = {
    "entry_candidates": ["entry_candidates.json", "entry_candidates.jsonl"],
    "signals": ["signals.jsonl", "signal_events.jsonl", "entry_events.jsonl", "trade_feature_matrix.jsonl"],
    "trades": ["trades.jsonl", "trade_events.jsonl"],
    "positions": ["positions.json"],
    "price_paths": ["price_paths.json", "price_paths.jsonl", "lifecycle_observations.jsonl", "chain_backfill.json", "chain_backfill.jsonl"],
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




def _load_file(path: Path) -> list[dict[str, Any]]:
    if path.suffix == ".jsonl":
        return read_jsonl(path)
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
        if path.exists() or list_jsonl_segments(path):
            return path
        return None
    for name in candidates:
        path = artifact_dir / name
        if path.exists() or list_jsonl_segments(path):
            return path
    return None



def _scored_mode_candidates(wallet_weighting: str | None) -> list[str]:
    mode = str(wallet_weighting or "").strip().lower()
    if mode in {"off", "shadow", "on"}:
        return [f"scored_tokens.{mode}.jsonl", f"scored_tokens.{mode}.json", *_GENERIC_SCORED_FILE_NAMES]
    return list(_GENERIC_SCORED_FILE_NAMES)



def _resolve_scored_artifact_path(
    artifact_dir: Path,
    explicit_path: str | Path | None,
    wallet_weighting: str | None,
) -> tuple[Path | None, str]:
    if explicit_path:
        path = Path(explicit_path)
        return (path if path.exists() else None, "explicit")
    candidates = _scored_mode_candidates(wallet_weighting)
    for idx, name in enumerate(candidates):
        path = artifact_dir / name
        if path.exists():
            if idx < 2 and str(wallet_weighting or "").lower() in {"off", "shadow", "on"}:
                return path, "mode_specific"
            return path, "generic"
    return None, "missing"



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
    normalized["truncated"] = bool(row.get("truncated"))
    normalized["missing"] = bool(row.get("missing"))
    normalized["price_path_status"] = row.get("price_path_status")
    return normalized



def _price_paths_have_observations(price_paths: list[dict[str, Any]]) -> bool:
    for row in price_paths:
        observations = row.get("price_path") if isinstance(row, dict) else None
        if isinstance(observations, list) and observations:
            return True
    return False



def validate_replay_inputs(loaded_inputs: dict[str, Any]) -> dict[str, Any]:
    warnings = list(loaded_inputs.get("warnings", []))
    malformed_rows = sum(1 for warning in warnings if "missing_token_address" in str(warning))
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
        if not price_paths or not _price_paths_have_observations(price_paths):
            missing.append("price_path")
        elif any(bool(path.get("truncated")) or str(path.get("price_path_status") or "") == "partial" for path in price_paths):
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
        nested = row.get("price_paths") if isinstance(row.get("price_paths"), list) else None
        candidate_rows = nested if nested else [row]
        for candidate in candidate_rows:
            merged = dict(row)
            if isinstance(candidate, dict):
                merged.update(candidate)
            normalized = _normalize_price_path_row(merged)
            token_address = normalized.get("token_address")
            if not token_address:
                continue
            by_token.setdefault(token_address, []).append(normalized)
    return by_token



def load_replay_inputs(
    *,
    artifact_dir: str | Path,
    wallet_weighting: str | None = None,
    scored_path: str | Path | None = None,
    entry_candidates_path: str | Path | None = None,
    signals_path: str | Path | None = None,
    trades_path: str | Path | None = None,
    positions_path: str | Path | None = None,
    price_paths_path: str | Path | None = None,
    universe_path: str | Path | None = None,
) -> dict[str, Any]:
    artifact_dir = Path(artifact_dir)
    scored_rows_path, scored_path_kind = _resolve_scored_artifact_path(artifact_dir, scored_path, wallet_weighting)
    loaded_files = {
        "scored_rows": scored_rows_path,
        "entry_candidates": _resolve_artifact_path(artifact_dir, entry_candidates_path, _JSONL_FILE_NAMES["entry_candidates"]),
        "signals": _resolve_artifact_path(artifact_dir, signals_path, _JSONL_FILE_NAMES["signals"]),
        "trades": _resolve_artifact_path(artifact_dir, trades_path, _JSONL_FILE_NAMES["trades"]),
        "positions": _resolve_artifact_path(artifact_dir, positions_path, _JSONL_FILE_NAMES["positions"]),
        "price_paths": _resolve_artifact_path(artifact_dir, price_paths_path, _JSONL_FILE_NAMES["price_paths"]),
        "universe": _resolve_artifact_path(artifact_dir, universe_path, _JSONL_FILE_NAMES["universe"]),
    }

    token_inputs: dict[str, dict[str, Any]] = {}
    warnings: list[str] = []

    def ensure_token(token_address: str, row: dict[str, Any] | None = None) -> dict[str, Any]:
        token_address = str(token_address)
        record = token_inputs.setdefault(
            token_address,
            {
                "token_address": token_address,
                "pair_address": _canonical_pair(row or {}) if row else None,
                "scored_rows": [],
                "entry_candidates": [],
                "signals": [],
                "trades": [],
                "positions": [],
                "price_paths": [],
                "warnings": [],
                "malformed_rows": 0,
            },
        )
        if row and not record.get("pair_address"):
            record["pair_address"] = _canonical_pair(row)
        return record

    scored_rows = _load_file(scored_rows_path) if scored_rows_path else []
    for row in scored_rows:
        token_address = _canonical_token(row)
        if not token_address:
            warnings.append(f"missing_token_address:scored_rows:{row.get('_source_file')}")
            continue
        ensure_token(token_address, row)["scored_rows"].append(row)

    for key in ("entry_candidates", "signals", "trades", "positions"):
        path = loaded_files.get(key)
        rows = _load_file(path) if path else []
        for row in rows:
            token_address = _canonical_token(row)
            if not token_address:
                warnings.append(f"missing_token_address:{key}:{row.get('_source_file')}")
                continue
            ensure_token(token_address, row)[key].append(row)

    for token_address, rows in load_replay_price_paths(artifact_dir=artifact_dir, loaded_files=loaded_files).items():
        ensure_token(token_address)["price_paths"].extend(rows)

    universe = load_replay_universe(artifact_dir=artifact_dir, loaded_files=loaded_files)
    for row in universe:
        token_address = _canonical_token(row)
        if not token_address:
            continue
        ensure_token(token_address, row)

    for token_address, payload in token_inputs.items():
        if not payload.get("pair_address"):
            payload["pair_address"] = next(
                (
                    _canonical_pair(item)
                    for key in ("scored_rows", "entry_candidates", "signals", "trades", "positions", "price_paths")
                    for item in payload.get(key, [])
                    if _canonical_pair(item)
                ),
                None,
            )

    loaded = {
        "artifact_dir": str(artifact_dir),
        "loaded_files": {key: str(value) if value else None for key, value in loaded_files.items()},
        "wallet_weighting_requested_mode": str(wallet_weighting or "off"),
        "scored_input_file": str(scored_rows_path) if scored_rows_path else None,
        "scored_input_kind": scored_path_kind,
        "token_inputs": token_inputs,
        "universe": universe,
        "warnings": warnings,
    }
    loaded["validation"] = validate_replay_inputs(loaded)
    return loaded
