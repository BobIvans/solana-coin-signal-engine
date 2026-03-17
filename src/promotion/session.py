from __future__ import annotations

import json
from pathlib import Path

from .types import SessionState


def load_session_state(path: str | Path) -> dict | None:
    p = Path(path)
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def write_session_state(path: str | Path, state: dict) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(state, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    tmp.replace(p)
    return p


def restore_runtime_state(session_path: str | Path, mode: str, config_hash: str, resume: bool = False) -> dict:
    if resume:
        restored = load_session_state(session_path)
        if restored:
            return restored
    return SessionState(active_mode=mode, config_hash=config_hash).as_dict()
