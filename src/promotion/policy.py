from __future__ import annotations


def validate_runtime_config(config: dict) -> None:
    mode = config.get("runtime", {}).get("mode")
    modes = config.get("modes", {})
    if mode not in modes:
        raise ValueError(f"runtime.mode={mode} is not declared in modes")
    for key in ("constrained_paper", "expanded_paper"):
        m = modes.get(key, {})
        if m.get("open_positions") and int(m.get("max_open_positions", 0)) <= 0:
            raise ValueError(f"{key}.max_open_positions must be > 0")
        if m.get("open_positions") and int(m.get("max_trades_per_day", 0)) <= 0:
            raise ValueError(f"{key}.max_trades_per_day must be > 0")


def config_hash(config: dict) -> str:
    import hashlib
    import json

    payload = json.dumps(config, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()
