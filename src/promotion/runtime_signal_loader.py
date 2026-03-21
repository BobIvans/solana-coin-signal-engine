from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_ALLOWED_EVENT_TYPES = {"entry_decision_made", "entry_signal"}
_CANONICAL_ORIGINS = {"historical_replay"}
_PIPELINE_MANIFEST = "runtime_signal_pipeline_manifest.json"
_DEFAULT_PRECEDENCE = (
    {
        "origin": "historical_replay",
        "path": "trade_feature_matrix.jsonl",
        "kind": "jsonl",
        "required_fields": ("token_address", "schema_version"),
    },
    {
        "origin": "entry_candidates",
        "path": "entry_candidates.json",
        "kind": "json",
        "required_fields": ("token_address", "entry_decision"),
    },
    {
        "origin": "entry_candidates",
        "path": "entry_candidates.smoke.json",
        "kind": "json",
        "required_fields": ("token_address", "entry_decision"),
    },
    {
        "origin": "entry_events",
        "path": "entry_events.jsonl",
        "kind": "jsonl",
        "required_fields": ("token_address", "entry_decision"),
    },
    {
        "origin": "scored_tokens",
        "path": "scored_tokens.json",
        "kind": "json",
        "required_fields": ("token_address",),
    },
    {
        "origin": "historical_replay_legacy",
        "path": "trade_feature_matrix.json",
        "kind": "json",
        "required_fields": ("token_address",),
    },
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_timestamp(value: Any) -> datetime | None:
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _is_stale(ts_value: Any, stale_after_sec: int | None) -> bool:
    if stale_after_sec is None:
        return False
    parsed = _parse_timestamp(ts_value)
    if parsed is None:
        return False
    return (_utc_now() - parsed).total_seconds() > stale_after_sec


def _ensure_list(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in ("tokens", "signals", "items", "rows"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
    return []


def _load_json_rows(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return _ensure_list(payload)


def _load_jsonl_rows(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        payload = json.loads(stripped)
        if isinstance(payload, dict):
            rows.append(payload)
    return rows


def _load_rows(path: Path, kind: str) -> list[dict[str, Any]]:
    if kind == "jsonl":
        return _load_jsonl_rows(path)
    return _load_json_rows(path)


def _required_fields_coverage(rows: list[dict[str, Any]], fields: tuple[str, ...]) -> float:
    if not rows or not fields:
        return 0.0
    covered = 0
    for row in rows:
        if all(row.get(field) not in (None, "") for field in fields):
            covered += 1
    return covered / len(rows)


def _artifact_status(spec: dict[str, Any], base_dir: Path, stale_after_sec: int | None) -> dict[str, Any]:
    path = base_dir / spec["path"]
    status = {
        "origin": spec["origin"],
        "path": str(path),
        "kind": spec["kind"],
        "exists": path.exists(),
        "selected": False,
        "status": "missing",
        "row_count": 0,
        "usable_row_count": 0,
        "coverage": 0.0,
        "warning": None,
        "stale": False,
        "origin_tier": "canonical" if spec["origin"] in _CANONICAL_ORIGINS else "fallback",
    }
    if not path.exists():
        status["warning"] = "artifact_missing"
        return status

    try:
        rows = _load_rows(path, spec["kind"])
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        status["status"] = "malformed"
        status["warning"] = f"artifact_unreadable:{exc}"
        return status

    if spec["origin"] == "entry_events":
        rows = [row for row in rows if str(row.get("event") or "") in _ALLOWED_EVENT_TYPES]

    status["row_count"] = len(rows)
    coverage = _required_fields_coverage(rows, tuple(spec.get("required_fields") or ()))
    status["coverage"] = round(coverage, 4)
    status["usable_row_count"] = sum(
        1 for row in rows if all(row.get(field) not in (None, "") for field in spec.get("required_fields", ()))
    )
    timestamps = [
        row.get("signal_ts") or row.get("decided_at") or row.get("ts") or row.get("generated_at")
        for row in rows
    ]
    status["stale"] = bool(timestamps) and all(_is_stale(ts, stale_after_sec) for ts in timestamps if ts)

    if not rows:
        status["status"] = "empty"
        status["warning"] = "artifact_empty"
    elif status["usable_row_count"] == 0:
        status["status"] = "partial"
        status["warning"] = "artifact_has_no_usable_rows"
    elif coverage < 1.0:
        status["status"] = "partial"
        status["warning"] = "artifact_has_partial_rows"
    else:
        status["status"] = "ok"
        if status["stale"]:
            status["warning"] = "artifact_stale"
    return status




def _load_pipeline_manifest(base_dir: Path) -> dict[str, Any] | None:
    path = base_dir / _PIPELINE_MANIFEST
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError):
        return None
    if not isinstance(payload, dict):
        return None
    payload = dict(payload)
    payload["manifest_path"] = str(path)
    return payload

def validate_runtime_signal_inputs(
    base_dir: str | Path = "data/processed",
    *,
    stale_after_sec: int | None = 3600,
    precedence: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    root = Path(base_dir)
    specs = precedence or list(_DEFAULT_PRECEDENCE)
    artifacts = [_artifact_status(spec, root, stale_after_sec) for spec in specs]
    selected = next((artifact for artifact in artifacts if artifact["status"] in {"ok", "partial"}), None)
    overall = "ready" if selected else "missing"
    if selected and selected["status"] == "partial":
        overall = "degraded"
    warnings = [artifact["warning"] for artifact in artifacts if artifact.get("warning")]
    pipeline_manifest = _load_pipeline_manifest(root)
    selected_tier = selected.get("origin_tier") if selected else None
    return {
        "base_dir": str(root),
        "overall_status": overall,
        "selected_origin": selected["origin"] if selected else None,
        "selected_path": selected["path"] if selected else None,
        "selected_origin_tier": selected_tier,
        "artifact_precedence": [spec["origin"] for spec in specs],
        "canonical_truth_layer": "trade_feature_matrix.jsonl",
        "artifacts": artifacts,
        "warnings": warnings,
        "pipeline_manifest": pipeline_manifest,
    }


def _selected_spec(validation: dict[str, Any], precedence: list[dict[str, Any]]) -> dict[str, Any] | None:
    selected_path = validation.get("selected_path")
    if not selected_path:
        return None
    for spec in precedence:
        if str((Path(validation["base_dir"]) / spec["path"])) == selected_path:
            return spec
    return None


def load_latest_runtime_signal_batch(
    base_dir: str | Path = "data/processed",
    *,
    stale_after_sec: int | None = 3600,
    precedence: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    specs = precedence or list(_DEFAULT_PRECEDENCE)
    validation = validate_runtime_signal_inputs(base_dir, stale_after_sec=stale_after_sec, precedence=specs)
    spec = _selected_spec(validation, specs)
    pipeline_manifest = validation.get("pipeline_manifest") or {}
    if spec is None:
        return {
            "signals": [],
            "selected_origin": None,
            "selected_artifact": None,
            "batch_status": "missing",
            "origin_tier": None,
            "runtime_pipeline_origin": pipeline_manifest.get("pipeline_run_id") if pipeline_manifest else None,
            "runtime_pipeline_status": pipeline_manifest.get("pipeline_status") if pipeline_manifest else None,
            "runtime_pipeline_manifest": pipeline_manifest.get("manifest_path") if pipeline_manifest else None,
            "warnings": validation.get("warnings", []),
            "artifacts": validation.get("artifacts", []),
        }

    path = Path(validation["selected_path"])
    rows = _load_rows(path, spec["kind"])
    if spec["origin"] == "entry_events":
        deduped: dict[str, dict[str, Any]] = {}
        for row in rows:
            if str(row.get("event") or "") not in _ALLOWED_EVENT_TYPES:
                continue
            token = str(row.get("token_address") or row.get("mint") or "")
            key = token or str(row.get("signal_id") or row.get("ts") or len(deduped))
            deduped[key] = row
        rows = list(deduped.values())

    batch_status = "ok" if validation["overall_status"] == "ready" else "partial"
    origin_tier = "canonical" if spec["origin"] in _CANONICAL_ORIGINS else "fallback"
    runtime_pipeline_origin = "canonical_trade_feature_matrix" if spec["origin"] == "historical_replay" else ("canonical_runtime_pipeline" if origin_tier == "canonical" and pipeline_manifest else ("fallback_loader" if origin_tier == "fallback" else "local_entry_artifact"))
    return {
        "signals": rows,
        "selected_origin": spec["origin"],
        "selected_artifact": str(path),
        "batch_status": batch_status,
        "origin_tier": origin_tier,
        "runtime_pipeline_origin": runtime_pipeline_origin,
        "canonical_truth_layer": validation.get("canonical_truth_layer"),
        "runtime_pipeline_status": pipeline_manifest.get("pipeline_status") if pipeline_manifest else None,
        "runtime_pipeline_manifest": pipeline_manifest.get("manifest_path") if pipeline_manifest else None,
        "warnings": validation.get("warnings", []),
        "artifacts": validation.get("artifacts", []),
    }


def load_runtime_signals(
    base_dir: str | Path = "data/processed",
    *,
    stale_after_sec: int | None = 3600,
    precedence: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    batch = load_latest_runtime_signal_batch(base_dir, stale_after_sec=stale_after_sec, precedence=precedence)
    return {
        "signals": batch["signals"],
        "selected_origin": batch["selected_origin"],
        "selected_artifact": batch["selected_artifact"],
        "batch_status": batch["batch_status"],
        "origin_tier": batch.get("origin_tier"),
        "runtime_pipeline_origin": batch.get("runtime_pipeline_origin"),
        "canonical_truth_layer": batch.get("canonical_truth_layer"),
        "runtime_pipeline_status": batch.get("runtime_pipeline_status"),
        "runtime_pipeline_manifest": batch.get("runtime_pipeline_manifest"),
        "artifacts": batch["artifacts"],
        "warnings": batch["warnings"],
        "signal_count": len(batch["signals"]),
    }
