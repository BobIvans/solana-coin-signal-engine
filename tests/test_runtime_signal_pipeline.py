from __future__ import annotations

from pathlib import Path

from utils.io import read_json, write_json
from src.pipeline.runtime_signal_pipeline import run_runtime_signal_pipeline


def _payload(tokens: list[dict], *, contract_version: str = "v1") -> dict:
    return {"generated_at": "2026-03-21T00:00:00Z", "contract_version": contract_version, "tokens": tokens}


def test_runtime_signal_pipeline_writes_canonical_artifacts(tmp_path):
    processed = tmp_path / "processed"

    shortlist = {"generated_at": "2026-03-21T00:00:00Z", "shortlist": [{"token_address": "So111", "pair_address": "Pair111"}]}
    x_validated = _payload([{"token_address": "So111", "x_status": "ok", "x_validation_score": 80, "x_validation_delta": 12, "contract_version": "x_validation_v1"}], contract_version="x_validation_v1")
    enriched = _payload([{"token_address": "So111", "pair_address": "Pair111", "smart_wallet_hits": 1}], contract_version="onchain_enrichment_v1")
    rug = _payload([{"token_address": "So111", "rug_score": 0.1, "rug_verdict": "WATCH"}], contract_version="rug_safety_v1")
    scored = _payload([{"token_address": "So111", "final_score": 55, "regime_candidate": "WATCHLIST"}], contract_version="scored_tokens_v1")
    entry = _payload([{"token_address": "So111", "entry_decision": "SCALP", "entry_confidence": 0.8, "recommended_position_pct": 0.3, "entry_reason": "fixture", "regime_confidence": 0.8, "regime_reason_flags": [], "regime_blockers": [], "expected_hold_class": "scalp", "entry_snapshot": {}}], contract_version="entry_selector_v1")

    write_json(processed / "shortlist.override.json", shortlist)
    write_json(processed / "x.override.json", x_validated)
    write_json(processed / "enriched.override.json", enriched)
    write_json(processed / "rug.override.json", rug)
    write_json(processed / "scored.override.json", scored)
    write_json(processed / "entry.override.json", entry)

    manifest = run_runtime_signal_pipeline(
        processed_dir=processed,
        discovery_enabled=False,
        x_validation_enabled=False,
        enrichment_enabled=False,
        rug_enabled=False,
        scoring_enabled=False,
        entry_enabled=False,
        stage_overrides={
            "shortlist": processed / "shortlist.override.json",
            "x_validated": processed / "x.override.json",
            "enriched": processed / "enriched.override.json",
            "rug": processed / "rug.override.json",
            "scored": processed / "scored.override.json",
            "entry": processed / "entry.override.json",
        },
    )

    manifest_path = processed / "runtime_signal_pipeline_manifest.json"
    assert manifest_path.exists()
    saved = read_json(manifest_path, default={})
    assert manifest["pipeline_status"] == "ok"
    assert saved["pipeline_status"] == "ok"
    assert saved["stage_statuses"]["discovery"] == "skipped"
    assert saved["stage_statuses"]["entry"] == "skipped"
    assert saved["artifact_paths"]["entry"].endswith("entry.override.json")


def test_runtime_signal_pipeline_marks_missing_stage_input_honestly(tmp_path):
    processed = tmp_path / "processed"
    manifest = run_runtime_signal_pipeline(
        processed_dir=processed,
        discovery_enabled=False,
        x_validation_enabled=False,
        enrichment_enabled=False,
        rug_enabled=False,
        scoring_enabled=False,
        entry_enabled=False,
        stage_overrides={},
    )
    assert manifest["pipeline_status"] == "partial"
    assert manifest["stage_statuses"]["discovery"] == "failed"
    assert "missing_shortlist_input" in manifest["warnings"][0]
