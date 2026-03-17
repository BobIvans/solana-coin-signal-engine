"""Minimal YAML subset loader/dumper for project configs."""

from __future__ import annotations

import json
from typing import Any


def _parse_scalar(raw: str) -> Any:
    text = raw.strip()
    if text in {"true", "True"}:
        return True
    if text in {"false", "False"}:
        return False
    if text in {"null", "None", "~", ""}:
        return None
    if text.startswith("[") and text.endswith("]"):
        inner = text[1:-1].strip()
        if not inner:
            return []
        return [_parse_scalar(part.strip()) for part in inner.split(",")]
    if (text.startswith('"') and text.endswith('"')) or (text.startswith("'") and text.endswith("'")):
        return text[1:-1]
    try:
        if "." in text:
            return float(text)
        return int(text)
    except ValueError:
        return text


def safe_load(data: str) -> Any:
    raw_lines = [line.rstrip() for line in data.splitlines() if line.strip() and not line.strip().startswith("#")]
    if not raw_lines:
        return {}
    if raw_lines[0].lstrip().startswith("{"):
        return json.loads("\n".join(raw_lines))

    root: Any = {}
    stack: list[tuple[int, Any]] = [(-1, root)]

    for idx, line in enumerate(raw_lines):
        indent = len(line) - len(line.lstrip(" "))
        content = line.strip()

        while stack and indent <= stack[-1][0]:
            stack.pop()
        parent = stack[-1][1]

        if content.startswith("- "):
            if not isinstance(parent, list):
                raise ValueError("invalid yaml structure")
            parent.append(_parse_scalar(content[2:]))
            continue

        key, _, value = content.partition(":")
        key = key.strip()
        value = value.strip()

        if value == "":
            next_indent = indent + 2
            next_is_list = False
            for look_ahead in raw_lines[idx + 1 :]:
                la_indent = len(look_ahead) - len(look_ahead.lstrip(" "))
                if la_indent < next_indent:
                    break
                if la_indent == next_indent:
                    next_is_list = look_ahead.strip().startswith("- ")
                    break
            container: Any = [] if next_is_list else {}
            parent[key] = container
            stack.append((indent, container))
        else:
            parent[key] = _parse_scalar(value)

    return root


def _dump(obj: Any, indent: int) -> list[str]:
    prefix = " " * indent
    if isinstance(obj, dict):
        lines: list[str] = []
        for key, value in obj.items():
            if isinstance(value, (dict, list)):
                lines.append(f"{prefix}{key}:")
                lines.extend(_dump(value, indent + 2))
            else:
                lines.append(f"{prefix}{key}: {json.dumps(value) if isinstance(value, str) else value}")
        return lines
    if isinstance(obj, list):
        lines = []
        for item in obj:
            lines.append(f"{prefix}- {json.dumps(item) if isinstance(item, str) else item}")
        return lines
    return [f"{prefix}{obj}"]


def safe_dump(data: Any, sort_keys: bool = False) -> str:
    if isinstance(data, dict) and sort_keys:
        data = {key: data[key] for key in sorted(data)}
    return "\n".join(_dump(data, 0)) + "\n"
