import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from src.replay.replay_input_loader import load_replay_inputs
from utils.io import append_jsonl, materialize_jsonl


def test_replay_loader_reads_segmented_signals_and_trades(tmp_path):
    artifact_dir = tmp_path / "run"
    artifact_dir.mkdir(parents=True, exist_ok=True)

    append_jsonl(artifact_dir / "signals.jsonl", {"token_address": "So111", "signal_id": "s1", "price_path": []}, segment_key="2026-03-21")
    append_jsonl(artifact_dir / "trades.jsonl", {"token_address": "So111", "position_id": "p1", "side": "buy"}, segment_key="2026-03-21")
    materialize_jsonl(artifact_dir / "signals.jsonl")
    materialize_jsonl(artifact_dir / "trades.jsonl")
    (artifact_dir / "positions.json").write_text(json.dumps([]), encoding="utf-8")

    payload = load_replay_inputs(artifact_dir=artifact_dir)
    assert str(payload["loaded_files"]["signals"]).endswith("signals.jsonl")
    assert payload["token_inputs"]["So111"]["signals"][0]["signal_id"] == "s1"
    assert payload["token_inputs"]["So111"]["trades"][0]["position_id"] == "p1"
