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
