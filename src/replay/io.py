from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from utils.io import append_jsonl, ensure_dir, write_json


def _parse_scalar(raw: str) -> Any:
    value = raw.strip()
    if value.lower() in {"true", "false"}:
        return value.lower() == "true"
    if value in {"null", "~"}:
        return None
    if value.startswith('"') and value.endswith('"'):
        return value[1:-1]
    if value.startswith("'") and value.endswith("'"):
        return value[1:-1]
    try:
        if "." in value:
            return float(value)
        return int(value)
    except ValueError:
        return value


def load_simple_yaml(path: str | Path) -> dict[str, Any]:
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    root: dict[str, Any] = {}
    stack: list[tuple[int, dict[str, Any]]] = [(-1, root)]
    for raw in lines:
        line = raw.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip(" "))
        key, _, val = line.strip().partition(":")
        while stack and indent <= stack[-1][0]:
            stack.pop()
        parent = stack[-1][1]
        if not val.strip():
            node: dict[str, Any] = {}
            parent[key] = node
            stack.append((indent, node))
        else:
            parent[key] = _parse_scalar(val)
    return root


def write_jsonl(path: str | Path, rows: list[dict[str, Any]]) -> None:
    target = Path(path)
    if target.exists():
        target.unlink()
    for row in rows:
        append_jsonl(target, row)


def write_markdown(path: str | Path, content: str) -> None:
    target = Path(path)
    ensure_dir(target.parent)
    target.write_text(content.rstrip() + "\n", encoding="utf-8")


__all__ = ["load_simple_yaml", "write_json", "write_jsonl", "write_markdown", "ensure_dir", "json"]
