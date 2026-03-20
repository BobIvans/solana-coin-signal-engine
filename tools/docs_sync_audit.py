"""Lightweight repo-aware docs synchronization audit helpers."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

_ARTIFACT_RE = re.compile(r"[A-Za-z0-9_./-]+\.(?:jsonl|json|md|py)")
_CONFLICT_MARKERS = ("<<<<<<<", "=======", ">>>>>>>")
_REQUIRED_TOOL_REFERENCES = (
    "tools/contract_parity.py",
    "tools/docs_sync_audit.py",
    "scripts/contract_parity_smoke.py",
    "docs/contracts.md",
)


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def _extract_paths(text: str) -> set[str]:
    return {match.group(0) for match in _ARTIFACT_RE.finditer(text)}


def _expected_contract_group_names(contract_definitions: list[Any]) -> list[str]:
    return sorted({str(definition.contract_group) for definition in contract_definitions})


def audit_docs_sync(
    repo_root: Path | str,
    *,
    contract_definitions: list[Any],
    readme_relpath: str = "README.md",
    contracts_relpath: str = "docs/contracts.md",
) -> dict[str, Any]:
    root = Path(repo_root).expanduser().resolve()
    readme_path = root / readme_relpath
    contracts_path = root / contracts_relpath

    readme_text = _read_text(readme_path)
    contracts_text = _read_text(contracts_path)
    combined_text = "\n".join([readme_text, contracts_text])

    expected_artifacts = sorted({Path(definition.artifact_path).name for definition in contract_definitions})
    readme_paths = _extract_paths(readme_text)
    contracts_paths = _extract_paths(contracts_text)
    combined_paths = _extract_paths(combined_text)

    missing_in_readme = [name for name in expected_artifacts if name not in readme_paths]
    missing_in_contracts = [name for name in expected_artifacts if name not in contracts_paths]
    extra_documented_artifacts = sorted(
        {
            path
            for path in combined_paths
            if Path(path).name.endswith((".json", ".jsonl"))
            and Path(path).name not in expected_artifacts
        }
    )

    stale_references: list[str] = []
    for marker in _CONFLICT_MARKERS:
        if marker in readme_text:
            stale_references.append(f"README contains merge conflict marker: {marker}")
        if marker in contracts_text:
            stale_references.append(f"docs/contracts.md contains merge conflict marker: {marker}")

    expected_groups = _expected_contract_group_names(contract_definitions)
    missing_group_headings = [
        group for group in expected_groups if group not in contracts_text
    ]
    missing_tool_references = [
        ref for ref in _REQUIRED_TOOL_REFERENCES if ref not in combined_text
    ]

    warnings = []
    if missing_in_readme:
        warnings.append("readme_missing_artifacts")
    if missing_in_contracts:
        warnings.append("contracts_doc_missing_artifacts")
    if extra_documented_artifacts:
        warnings.append("extra_documented_artifacts")
    if stale_references:
        warnings.append("stale_doc_references")
    if missing_group_headings:
        warnings.append("missing_contract_group_headings")
    if missing_tool_references:
        warnings.append("missing_tool_references")

    status = "ok" if not warnings else "mismatch"
    return {
        "status": status,
        "readme_path": readme_relpath,
        "contracts_doc_path": contracts_relpath,
        "expected_artifacts": expected_artifacts,
        "documented_artifacts_readme": sorted(readme_paths),
        "documented_artifacts_contracts_doc": sorted(contracts_paths),
        "missing_artifacts_in_readme": missing_in_readme,
        "missing_artifacts_in_contracts_doc": missing_in_contracts,
        "extra_documented_artifacts": extra_documented_artifacts,
        "stale_references": stale_references,
        "missing_contract_group_headings": missing_group_headings,
        "missing_tool_references": missing_tool_references,
        "warnings": warnings,
    }
