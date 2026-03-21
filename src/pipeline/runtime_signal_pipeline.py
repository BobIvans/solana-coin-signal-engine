from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

from collectors.discovery_engine import run_discovery_once
from scoring.unified_score import ensure_list, load_json, score_tokens, write_json, write_jsonl
from utils.clock import utc_now_iso
from utils.io import ensure_dir

from src.pipeline.entry_stage import run_stage as run_entry_stage
from src.pipeline.env import pipeline_env
from src.pipeline.onchain_enrichment_stage import run_stage as run_onchain_enrichment_stage
from src.pipeline.rug_stage import run_stage as run_rug_stage
from src.pipeline.x_validation_stage import run_stage as run_x_validation_stage

StageRunner = Callable[..., dict[str, Any]]


@dataclass(frozen=True)
class StageSpec:
    name: str
    artifact_name: str
    runner: StageRunner


def _artifact_path(processed_dir: Path, filename: str) -> Path:
    return processed_dir / filename


def _extract_rows(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        for key in ("tokens", "shortlist", "candidates", "items", "rows"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    return []


def _write_atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    ensure_dir(path.parent)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, sort_keys=True, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def _manifest_base(processed_dir: Path) -> dict[str, Any]:
    return {
        "pipeline_run_id": f"runtime_pipeline_{utc_now_iso()}",
        "pipeline_status": "ok",
        "generated_at": utc_now_iso(),
        "processed_dir": str(processed_dir),
        "stage_statuses": {},
        "stage_row_counts": {},
        "artifact_paths": {},
        "warnings": [],
        "selected_wallet_weighting_mode": os.environ.get("WALLET_WEIGHTING_MODE", "shadow"),
        "score_contract_version": None,
        "entry_contract_version": None,
    }


def _record_stage(manifest: dict[str, Any], *, name: str, artifact_path: Path, payload: dict[str, Any] | None, status: str, warning: str | None = None) -> None:
    rows = _extract_rows(payload) if payload is not None else []
    manifest["stage_statuses"][name] = status
    manifest["stage_row_counts"][name] = len(rows)
    manifest["artifact_paths"][name] = str(artifact_path)
    if warning:
        manifest["warnings"].append(f"{name}:{warning}")
    if payload and name == "scoring":
        manifest["score_contract_version"] = payload.get("contract_version")
    if payload and name == "entry":
        manifest["entry_contract_version"] = payload.get("contract_version")
    if status not in {"ok", "skipped"} and manifest["pipeline_status"] == "ok":
        manifest["pipeline_status"] = "partial"


def _load_rows_from_path(path: Path) -> list[dict[str, Any]]:
    payload = load_json(path)
    return ensure_list(payload)


def _run_discovery(*, processed_dir: Path) -> dict[str, Any]:
    with pipeline_env(processed_dir=processed_dir):
        result = run_discovery_once()
    return result["shortlist"]


def _run_scoring(*, processed_dir: Path, shortlist_path: Path, x_validated_path: Path, enriched_path: Path, rug_path: Path) -> dict[str, Any]:
    shortlist = _load_rows_from_path(shortlist_path)
    x_validated = _load_rows_from_path(x_validated_path)
    enriched = _load_rows_from_path(enriched_path)
    rug_assessed = _load_rows_from_path(rug_path)
    scored, events = score_tokens(shortlist, x_validated, enriched, rug_assessed)
    payload = {"generated_at": utc_now_iso(), "contract_version": "scored_tokens_v1", "tokens": scored}
    write_json(processed_dir / "scored_tokens.json", payload)
    write_jsonl(processed_dir / "score_events.jsonl", events)
    return payload


def run_runtime_signal_pipeline(
    *,
    processed_dir: str | Path = "data/processed",
    config_path: str | Path | None = None,
    discovery_enabled: bool = True,
    x_validation_enabled: bool = True,
    enrichment_enabled: bool = True,
    rug_enabled: bool = True,
    scoring_enabled: bool = True,
    entry_enabled: bool = True,
    stage_overrides: dict[str, str | Path] | None = None,
) -> dict[str, Any]:
    del config_path  # reserved for future config-aware orchestration
    overrides = {key: Path(value) for key, value in (stage_overrides or {}).items()}
    processed = ensure_dir(processed_dir)
    manifest = _manifest_base(processed)

    shortlist_path = overrides.get("shortlist", _artifact_path(processed, "shortlist.json"))
    x_validated_path = overrides.get("x_validated", _artifact_path(processed, "x_validated.json"))
    enriched_path = overrides.get("enriched", _artifact_path(processed, "enriched_tokens.json"))
    rug_path = overrides.get("rug", _artifact_path(processed, "rug_assessed_tokens.json"))
    scored_path = overrides.get("scored", _artifact_path(processed, "scored_tokens.json"))
    entry_path = overrides.get("entry", _artifact_path(processed, "entry_candidates.json"))

    if discovery_enabled and "shortlist" not in overrides:
        payload = _run_discovery(processed_dir=processed)
        _record_stage(manifest, name="discovery", artifact_path=shortlist_path, payload=payload, status="ok")
    elif shortlist_path.exists():
        payload = load_json(shortlist_path)
        _record_stage(manifest, name="discovery", artifact_path=shortlist_path, payload=payload, status="skipped")
    else:
        _record_stage(manifest, name="discovery", artifact_path=shortlist_path, payload=None, status="failed", warning="missing_shortlist_input")
        _write_atomic_json(processed / "runtime_signal_pipeline_manifest.json", manifest)
        return manifest

    if x_validation_enabled and "x_validated" not in overrides:
        payload = run_x_validation_stage(processed_dir=processed, shortlist_path=shortlist_path)
        _record_stage(manifest, name="x_validation", artifact_path=x_validated_path, payload=payload, status="ok")
    elif x_validated_path.exists():
        payload = load_json(x_validated_path)
        _record_stage(manifest, name="x_validation", artifact_path=x_validated_path, payload=payload, status="skipped")
    else:
        _record_stage(manifest, name="x_validation", artifact_path=x_validated_path, payload=None, status="failed", warning="missing_x_validated_input")
        _write_atomic_json(processed / "runtime_signal_pipeline_manifest.json", manifest)
        return manifest

    if enrichment_enabled and "enriched" not in overrides:
        payload = run_onchain_enrichment_stage(processed_dir=processed, shortlist_path=shortlist_path, x_validated_path=x_validated_path)
        _record_stage(manifest, name="enrichment", artifact_path=enriched_path, payload=payload, status="ok")
    elif enriched_path.exists():
        payload = load_json(enriched_path)
        _record_stage(manifest, name="enrichment", artifact_path=enriched_path, payload=payload, status="skipped")
    else:
        _record_stage(manifest, name="enrichment", artifact_path=enriched_path, payload=None, status="failed", warning="missing_enriched_input")
        _write_atomic_json(processed / "runtime_signal_pipeline_manifest.json", manifest)
        return manifest

    if rug_enabled and "rug" not in overrides:
        payload = run_rug_stage(processed_dir=processed, enriched_path=enriched_path)
        _record_stage(manifest, name="rug", artifact_path=rug_path, payload=payload, status="ok")
    elif rug_path.exists():
        payload = load_json(rug_path)
        _record_stage(manifest, name="rug", artifact_path=rug_path, payload=payload, status="skipped")
    else:
        _record_stage(manifest, name="rug", artifact_path=rug_path, payload=None, status="failed", warning="missing_rug_input")
        _write_atomic_json(processed / "runtime_signal_pipeline_manifest.json", manifest)
        return manifest

    if scoring_enabled and "scored" not in overrides:
        payload = _run_scoring(processed_dir=processed, shortlist_path=shortlist_path, x_validated_path=x_validated_path, enriched_path=enriched_path, rug_path=rug_path)
        _record_stage(manifest, name="scoring", artifact_path=scored_path, payload=payload, status="ok")
    elif scored_path.exists():
        payload = load_json(scored_path)
        _record_stage(manifest, name="scoring", artifact_path=scored_path, payload=payload, status="skipped")
    else:
        _record_stage(manifest, name="scoring", artifact_path=scored_path, payload=None, status="failed", warning="missing_scored_input")
        _write_atomic_json(processed / "runtime_signal_pipeline_manifest.json", manifest)
        return manifest

    if entry_enabled and "entry" not in overrides:
        payload = run_entry_stage(processed_dir=processed, scored_path=scored_path)
        _record_stage(manifest, name="entry", artifact_path=entry_path, payload=payload, status="ok")
    elif entry_path.exists():
        payload = load_json(entry_path)
        _record_stage(manifest, name="entry", artifact_path=entry_path, payload=payload, status="skipped")
    else:
        _record_stage(manifest, name="entry", artifact_path=entry_path, payload=None, status="failed", warning="missing_entry_input")

    _write_atomic_json(processed / "runtime_signal_pipeline_manifest.json", manifest)
    return manifest
