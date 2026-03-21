from __future__ import annotations

from utils.io import append_jsonl, write_json
from src.promotion.runtime_signal_loader import load_latest_runtime_signal_batch, validate_runtime_signal_inputs


def test_loader_prefers_entry_candidates_over_lower_precedence(tmp_path):
    processed = tmp_path / "processed"
    write_json(
        processed / "entry_candidates.json",
        {
            "tokens": [
                {
                    "token_address": "So111",
                    "entry_decision": "SCALP",
                    "signal_ts": "2026-03-20T00:00:00+00:00",
                    "recommended_position_pct": 0.3,
                }
            ]
        },
    )
    write_json(processed / "scored_tokens.json", [{"token_address": "So222", "final_score": 80.0}])

    batch = load_latest_runtime_signal_batch(processed, stale_after_sec=None)

    assert batch["selected_origin"] == "entry_candidates"
    assert batch["origin_tier"] == "fallback"
    assert batch["selected_artifact"].endswith("entry_candidates.json")
    assert batch["signals"][0]["token_address"] == "So111"


def test_loader_uses_entry_events_when_candidates_missing(tmp_path):
    processed = tmp_path / "processed"
    append_jsonl(
        processed / "entry_events.jsonl",
        {
            "ts": "2026-03-20T00:00:00+00:00",
            "event": "entry_decision_made",
            "token_address": "So333",
            "entry_decision": "TREND",
            "recommended_position_pct": 0.4,
        },
    )

    batch = load_latest_runtime_signal_batch(processed, stale_after_sec=None)

    assert batch["selected_origin"] == "entry_events"
    assert batch["signals"][0]["token_address"] == "So333"


def test_validate_runtime_signal_inputs_marks_partial_rows(tmp_path):
    processed = tmp_path / "processed"
    write_json(processed / "entry_candidates.json", {"tokens": [{"entry_decision": "SCALP"}]})

    validation = validate_runtime_signal_inputs(processed, stale_after_sec=None)

    assert validation["overall_status"] == "degraded"
    selected = next(item for item in validation["artifacts"] if item["origin"] == "entry_candidates")
    assert selected["status"] == "partial"
    assert selected["usable_row_count"] == 0



def test_loader_uses_historical_replay_jsonl_when_higher_precedence_missing(tmp_path):
    processed = tmp_path / "processed"
    append_jsonl(
        processed / "trade_feature_matrix.jsonl",
        {
            "token_address": "SoReplay111",
            "final_score": 88.0,
            "signal_ts": "2026-03-20T00:00:00+00:00",
        },
    )

    batch = load_latest_runtime_signal_batch(processed, stale_after_sec=None)

    assert batch["selected_origin"] == "historical_replay"
    assert batch["origin_tier"] == "canonical"
    assert batch["selected_artifact"].endswith("trade_feature_matrix.jsonl")
    assert batch["signals"][0]["token_address"] == "SoReplay111"


def test_loader_prefers_historical_replay_jsonl_over_legacy_json(tmp_path):
    processed = tmp_path / "processed"
    append_jsonl(
        processed / "trade_feature_matrix.jsonl",
        {
            "token_address": "SoReplayCanonical",
            "final_score": 91.0,
            "signal_ts": "2026-03-20T00:00:00+00:00",
        },
    )
    write_json(
        processed / "trade_feature_matrix.json",
        [{"token_address": "SoReplayLegacy", "final_score": 60.0}],
    )

    batch = load_latest_runtime_signal_batch(processed, stale_after_sec=None)

    assert batch["selected_origin"] == "historical_replay"
    assert batch["selected_artifact"].endswith("trade_feature_matrix.jsonl")
    assert batch["signals"][0]["token_address"] == "SoReplayCanonical"


def test_loader_falls_back_to_legacy_historical_replay_json_when_jsonl_missing(tmp_path):
    processed = tmp_path / "processed"
    write_json(
        processed / "trade_feature_matrix.json",
        [{"token_address": "SoReplayLegacy", "final_score": 77.0}],
    )

    batch = load_latest_runtime_signal_batch(processed, stale_after_sec=None)

    assert batch["selected_origin"] == "historical_replay_legacy"
    assert batch["selected_artifact"].endswith("trade_feature_matrix.json")
    assert batch["signals"][0]["token_address"] == "SoReplayLegacy"


def test_loader_surfaces_pipeline_manifest_for_canonical_origin(tmp_path):
    processed = tmp_path / "processed"
    write_json(processed / "entry_candidates.json", {"tokens": [{"token_address": "So111", "entry_decision": "SCALP"}]})
    write_json(processed / "runtime_signal_pipeline_manifest.json", {"pipeline_run_id": "pipe123", "pipeline_status": "ok"})

    batch = load_latest_runtime_signal_batch(processed, stale_after_sec=None)

    assert batch["origin_tier"] == "fallback"
    assert batch["runtime_pipeline_origin"] == "fallback_loader"
    assert batch["runtime_pipeline_status"] == "ok"
    assert batch["runtime_pipeline_manifest"].endswith("runtime_signal_pipeline_manifest.json")


def test_loader_prefers_canonical_trade_feature_matrix_over_entry_candidates(tmp_path):
    processed = tmp_path / "processed"
    append_jsonl(
        processed / "trade_feature_matrix.jsonl",
        {
            "schema_version": "trade_feature_matrix.v1",
            "token_address": "SoCanonical111",
            "decision": "ENTER",
            "regime_decision": "SCALP",
            "replay_input_origin": "historical",
            "replay_data_status": "historical",
            "replay_resolution_status": "resolved",
            "signal_ts": "2026-03-20T00:00:00+00:00",
        },
    )
    write_json(
        processed / "entry_candidates.json",
        {"tokens": [{"token_address": "SoFallback111", "entry_decision": "SCALP", "signal_ts": "2026-03-20T00:00:00+00:00"}]},
    )

    batch = load_latest_runtime_signal_batch(processed, stale_after_sec=None)

    assert batch["selected_origin"] == "historical_replay"
    assert batch["origin_tier"] == "canonical"
    assert batch["signals"][0]["token_address"] == "SoCanonical111"
