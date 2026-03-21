from __future__ import annotations

from pathlib import Path

from src.replay.replay_input_loader import load_replay_inputs, load_replay_price_paths, validate_replay_inputs

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "historical_replay"


def test_loader_reads_historical_fixture_inputs():
    payload = load_replay_inputs(artifact_dir=FIXTURES / "full_win")

    assert "tok_full_win" in payload["token_inputs"]
    token_payload = payload["token_inputs"]["tok_full_win"]
    assert len(token_payload["scored_rows"]) == 1
    assert len(token_payload["entry_candidates"]) == 1
    assert len(token_payload["price_paths"]) == 1
    assert payload["validation"]["historical_rows"] == 1


def test_loader_exposes_partial_and_malformed_status_explicitly():
    payload = load_replay_inputs(artifact_dir=FIXTURES / "malformed")
    validation = validate_replay_inputs(payload)

    assert validation["malformed_rows"] >= 1
    assert validation["token_status"]["tok_bad_ts"]["replay_data_status"] == "historical_partial"
    assert any("missing_token_address" in warning for warning in payload["warnings"])


def test_loader_reads_price_path_rows_without_inventing_data():
    price_paths = load_replay_price_paths(artifact_dir=FIXTURES / "partial_missing_exit")

    assert "tok_partial" in price_paths
    assert price_paths["tok_partial"][0]["price_path"][-1]["price"] == 1.09



def test_loader_supports_embedded_backfill_price_paths(tmp_path):
    import json

    row = {
        "token_address": "tok_backfill",
        "pair_address": "pair_backfill",
        "price_paths": [
            {
                "token_address": "tok_backfill",
                "pair_address": "pair_backfill",
                "price_path": [
                    {"offset_sec": 0, "price": 1.0, "timestamp": "2026-03-10T12:00:00Z"},
                    {"offset_sec": 60, "price": 1.1, "timestamp": "2026-03-10T12:01:00Z"},
                ],
            }
        ],
    }
    (tmp_path / "chain_backfill.jsonl").write_text(json.dumps(row) + "\n", encoding="utf-8")

    price_paths = load_replay_price_paths(artifact_dir=tmp_path)

    assert price_paths["tok_backfill"][0]["price_path"][1]["price"] == 1.1
