from __future__ import annotations

import threading
from pathlib import Path

from utils.io import append_jsonl, read_jsonl


def test_append_jsonl_is_safe_under_multithreaded_writes(tmp_path: Path):
    path = tmp_path / "events.jsonl"
    total_threads = 8
    writes_per_thread = 50

    def worker(tid: int) -> None:
        for i in range(writes_per_thread):
            append_jsonl(path, {"thread": tid, "i": i})

    threads = [threading.Thread(target=worker, args=(idx,)) for idx in range(total_threads)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    rows = read_jsonl(path)
    assert len(rows) == total_threads * writes_per_thread


def test_append_jsonl_segmented_mode_is_safe_under_multithreaded_writes(tmp_path: Path):
    path = tmp_path / "segmented.jsonl"
    total_threads = 6
    writes_per_thread = 40

    def worker(tid: int) -> None:
        for i in range(writes_per_thread):
            append_jsonl(
                path,
                {"thread": tid, "i": i, "ts": "2026-03-22T00:00:00+00:00"},
                segment_key="2026-03-22",
            )

    threads = [threading.Thread(target=worker, args=(idx,)) for idx in range(total_threads)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    rows = read_jsonl(path)
    assert len(rows) == total_threads * writes_per_thread
