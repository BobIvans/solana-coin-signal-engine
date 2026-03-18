from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
root_str = str(ROOT)
if root_str not in sys.path:
    sys.path.append(root_str)

from collectors.wallet_seed_import import import_wallet_seeds


WALLET_A = "4Nd1mYwJ8M4d4R9vYj4M5Hn5QZQqNf8QjF2bU8X2h7Ty"
WALLET_B = "9xQeWvG816bUx9EPf8x7M7fD5kX4gG9f7N1n2s3t4u5v"
WALLET_C = "7M5xJ8gH2kL9pQ3rT6vW1yZ4bN8mD2sF5hJ7kL9mN2pQ"


def _run_import(tmp_path: Path) -> tuple[dict, dict]:
    manual_dir = tmp_path / "manual"
    out = tmp_path / "normalized_wallet_candidates.json"
    event_log = tmp_path / "import_events.jsonl"
    artifact = import_wallet_seeds(manual_dir, out, event_log, generated_at="2024-01-01T00:00:00Z")
    event = json.loads(event_log.read_text(encoding="utf-8").strip().splitlines()[-1])
    return artifact, event


def test_csv_wallet_only_import(tmp_path: Path):
    manual_dir = tmp_path / "manual"
    manual_dir.mkdir(parents=True)
    (manual_dir / "manual_wallets.csv").write_text(f"wallet\n{WALLET_A}\n", encoding="utf-8")

    artifact, _ = _run_import(tmp_path)
    assert artifact["input_summary"]["valid_wallets"] == 1
    assert artifact["candidates"][0]["wallet"] == WALLET_A


def test_csv_wallet_tag_notes_import(tmp_path: Path):
    manual_dir = tmp_path / "manual"
    manual_dir.mkdir(parents=True)
    (manual_dir / "manual_wallets.csv").write_text(
        f"wallet,tag,notes\n{WALLET_A},vip,from spreadsheeet\n",
        encoding="utf-8",
    )

    artifact, _ = _run_import(tmp_path)
    candidate = artifact["candidates"][0]
    assert candidate["tags"] == ["vip"]
    assert candidate["notes"] == "from spreadsheeet"


def test_txt_import(tmp_path: Path):
    manual_dir = tmp_path / "manual"
    manual_dir.mkdir(parents=True)
    (manual_dir / "manual_wallets.txt").write_text(f"{WALLET_A}\n{WALLET_B}\n", encoding="utf-8")

    artifact, _ = _run_import(tmp_path)
    wallets = [row["wallet"] for row in artifact["candidates"]]
    assert wallets == sorted([WALLET_A, WALLET_B])


def test_json_list_str_import(tmp_path: Path):
    manual_dir = tmp_path / "manual"
    manual_dir.mkdir(parents=True)
    (manual_dir / "manual_wallets.json").write_text(json.dumps([WALLET_A, WALLET_B]), encoding="utf-8")

    artifact, _ = _run_import(tmp_path)
    assert artifact["input_summary"]["valid_wallets"] == 2


def test_json_list_object_import(tmp_path: Path):
    manual_dir = tmp_path / "manual"
    manual_dir.mkdir(parents=True)
    payload = [{"wallet": WALLET_A, "tag": "manual_bulk", "notes": "optional"}]
    (manual_dir / "manual_wallets.json").write_text(json.dumps(payload), encoding="utf-8")

    artifact, _ = _run_import(tmp_path)
    candidate = artifact["candidates"][0]
    assert candidate["tags"] == ["manual_bulk"]
    assert candidate["notes"] == "optional"


def test_duplicate_removal_across_files(tmp_path: Path):
    manual_dir = tmp_path / "manual"
    manual_dir.mkdir(parents=True)
    (manual_dir / "a.csv").write_text(f"wallet\n{WALLET_A}\n", encoding="utf-8")
    (manual_dir / "b.txt").write_text(f"{WALLET_A}\n", encoding="utf-8")

    artifact, _ = _run_import(tmp_path)
    assert artifact["input_summary"]["duplicates_removed"] == 1
    assert len(artifact["candidates"]) == 1
    assert len(artifact["candidates"][0]["source_records"]) == 2


def test_invalid_rows_and_unsupported_files_logged(tmp_path: Path):
    manual_dir = tmp_path / "manual"
    manual_dir.mkdir(parents=True)
    (manual_dir / "manual_wallets.csv").write_text("wallet\nnot_a_wallet\n", encoding="utf-8")
    (manual_dir / "notes.md").write_text("ignore", encoding="utf-8")

    artifact, event = _run_import(tmp_path)
    assert artifact["input_summary"]["invalid_rows"] == 1
    reasons = {issue["reason"] for issue in event["issues"]}
    assert "invalid_wallet" in reasons
    assert "unsupported_extension:.md" in reasons


def test_deterministic_output_ordering(tmp_path: Path):
    manual_dir = tmp_path / "manual"
    manual_dir.mkdir(parents=True)
    (manual_dir / "manual_wallets.txt").write_text(f"{WALLET_B}\n{WALLET_A}\n", encoding="utf-8")

    artifact, _ = _run_import(tmp_path)
    wallets = [row["wallet"] for row in artifact["candidates"]]
    assert wallets == [WALLET_A, WALLET_B]


def test_missing_manual_folder_does_not_crash(tmp_path: Path):
    artifact, event = _run_import(tmp_path)
    assert artifact["candidates"] == []
    assert event["status"] == "manual_dir_missing"


def test_first_tag_and_notes_preserved(tmp_path: Path):
    manual_dir = tmp_path / "manual"
    manual_dir.mkdir(parents=True)
    (manual_dir / "a.csv").write_text(f"wallet,tag,notes\n{WALLET_C},first,keep-me\n", encoding="utf-8")
    (manual_dir / "b.json").write_text(json.dumps([{"wallet": WALLET_C, "tag": "second", "notes": "replace-me"}]), encoding="utf-8")

    artifact, _ = _run_import(tmp_path)
    candidate = artifact["candidates"][0]
    assert candidate["tags"] == ["first"]
    assert candidate["notes"] == "keep-me"
