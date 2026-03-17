import json
import subprocess
from pathlib import Path


def test_replay_runs_with_wallet_weighting_off_and_on(tmp_path: Path):
    root = Path.cwd()
    processed = root / "data" / "processed"
    processed.mkdir(parents=True, exist_ok=True)
    (processed / "entry_candidates.json").write_text(json.dumps([{"token_address": "tok1", "wallet_features": {"smart_wallet_hits": 1}}]), encoding="utf-8")
    (root / "data" / "smart_wallets.registry.json").write_text(json.dumps({"wallets": []}), encoding="utf-8")

    subprocess.check_call(["python", "scripts/replay_7d.py", "--run-id", "test_wallets_off", "--wallet-weighting", "off"])
    subprocess.check_call(["python", "scripts/replay_7d.py", "--run-id", "test_wallets_on", "--wallet-weighting", "on"])

    on_summary = json.loads((root / "runs" / "test_wallets_on" / "wallet_weighting_summary.json").read_text(encoding="utf-8"))
    assert on_summary["wallet_weighting_enabled"] is True

    signal_line = (root / "runs" / "test_wallets_on" / "signals.jsonl").read_text(encoding="utf-8").splitlines()[0]
    assert "wallet_features" in json.loads(signal_line)
