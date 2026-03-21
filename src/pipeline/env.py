from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


@contextmanager
def pipeline_env(*, processed_dir: str | Path, raw_dir: str | Path | None = None, smoke_dir: str | Path | None = None) -> Iterator[None]:
    processed = Path(processed_dir)
    raw = Path(raw_dir) if raw_dir is not None else processed.parent / "raw"
    smoke = Path(smoke_dir) if smoke_dir is not None else processed.parent / "smoke"
    updates = {
        "PROCESSED_DATA_DIR": str(processed),
        "RAW_DATA_DIR": str(raw),
        "SMOKE_DIR": str(smoke),
        "SIGNALS_DIR": str(processed),
    }
    previous = {key: os.environ.get(key) for key in updates}
    try:
        for key, value in updates.items():
            os.environ[key] = value
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
