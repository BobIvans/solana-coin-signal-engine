import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.acceptance_gate import validate_required_operational_outputs


def test_acceptance_gate_detects_missing_runtime_outputs(tmp_path):
    missing = validate_required_operational_outputs(tmp_path, "runtime_signal_smoke")
    assert any("runtime_signal_summary.json" in item for item in missing)


def test_acceptance_gate_accepts_present_runtime_outputs(tmp_path):
    base = tmp_path / "runtime_signal"
    (base / "runs" / "runtime_signal_smoke").mkdir(parents=True, exist_ok=True)
    (base / "runtime_signal_summary.json").write_text(json.dumps({"ok": True}), encoding="utf-8")
    (base / "runs" / "runtime_signal_smoke" / "runtime_health.json").write_text(json.dumps({"ok": True}), encoding="utf-8")
    (base / "runs" / "runtime_signal_smoke" / "artifact_manifest.json").write_text(json.dumps({"ok": True}), encoding="utf-8")
    missing = validate_required_operational_outputs(tmp_path, "runtime_signal_smoke")
    assert missing == []
