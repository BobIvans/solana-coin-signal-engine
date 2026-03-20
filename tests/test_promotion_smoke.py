import subprocess
import sys


def test_promotion_shadow_smoke():
    run_id = "runtime_smoke_test"
    cmd = [
        sys.executable,
        "scripts/run_promotion_loop.py",
        "--config",
        "config/promotion.default.yaml",
        "--mode",
        "shadow",
        "--run-id",
        run_id,
        "--max-loops",
        "1",
        "--dry-run",
    ]
    result = subprocess.run(cmd, check=False, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr

    from pathlib import Path
    run_dir = Path("runs") / run_id
    assert (run_dir / "runtime_manifest.json").exists()
    assert (run_dir / "event_log.jsonl").exists()
    assert (run_dir / "decisions.jsonl").exists()
    assert (run_dir / "positions.json").exists()
    assert (run_dir / "daily_summary.json").exists()
    assert (run_dir / "daily_summary.md").exists()
    assert (run_dir / "session_state.json").exists()
