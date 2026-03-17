import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from replay.deterministic import hash_config, make_run_paths


def test_same_config_same_hash():
    cfg = {"a": 1, "b": {"c": True}}
    assert hash_config(cfg) == hash_config({"b": {"c": True}, "a": 1})


def test_make_run_paths_has_expected_files():
    paths = make_run_paths("unit_manifest")
    assert paths.manifest_path.name == "manifest.json"
    assert paths.summary_json_path.name == "replay_summary.json"
