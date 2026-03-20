from __future__ import annotations

from pathlib import Path

import src.replay as replay_pkg

ROOT = Path(__file__).resolve().parents[1]
REMOVED_SIMULATOR = ROOT / "src" / "replay" / "simulator.py"
SCAN_DIRS = (ROOT / "src", ROOT / "scripts", ROOT / "tests")


def _python_files() -> list[Path]:
    files: list[Path] = []
    for base in SCAN_DIRS:
        files.extend(sorted(path for path in base.rglob("*.py") if path.is_file()))
    return files


def test_stale_replay_simulator_file_is_removed() -> None:
    assert not REMOVED_SIMULATOR.exists(), "src/replay/simulator.py must stay removed"



def test_no_code_imports_removed_replay_simulator() -> None:
    module_ref = ".".join(["src", "replay", "simulator"])
    forbidden = [f"from {module_ref}", f"import {module_ref}"]
    offenders: list[str] = []

    for path in _python_files():
        content = path.read_text(encoding="utf-8")
        for needle in forbidden:
            if needle in content:
                offenders.append(f"{path.relative_to(ROOT)}: contains {needle!r}")

    assert not offenders, "\n".join(offenders)



def test_replay_package_surface_does_not_expose_removed_simulator() -> None:
    exported = getattr(replay_pkg, "__all__", [])

    assert all("simulator" not in name for name in exported)
    assert "simulate_signals" not in exported
    assert "simulate_trade_exit" not in exported
    assert not hasattr(replay_pkg, "simulate_signals")
    assert not hasattr(replay_pkg, "simulate_trade_exit")
