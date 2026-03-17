from __future__ import annotations

from pathlib import Path
from typing import Any

from utils.io import write_json


def write_wallet_feature_stats(path: str | Path, **stats: Any) -> Path:
    return write_json(path, dict(stats))


def write_wallet_weighting_summary(path: str | Path, **summary: Any) -> Path:
    return write_json(path, dict(summary))
