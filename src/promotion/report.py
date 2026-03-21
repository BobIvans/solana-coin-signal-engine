from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _write_json(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return path


def write_daily_summary_json(path: str | Path, summary: dict) -> Path:
    return _write_json(Path(path), summary)


def write_runtime_health_json(path: str | Path, summary: dict) -> Path:
    return _write_json(Path(path), summary)


def write_artifact_manifest_json(path: str | Path, summary: dict) -> Path:
    return _write_json(Path(path), summary)


def write_daily_summary_md(path: str | Path, summary: dict) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    ops = summary.get("ops") or {}
    artifact_paths = summary.get("artifact_paths") or {}
    warnings = summary.get("warnings") or []
    lines = [
        f"# Daily Summary ({summary.get('run_id', '-')})",
        "",
        f"- Mode: `{summary.get('mode')}`",
        f"- Trades today: `{summary.get('trades_today')}`",
        f"- Open positions: `{summary.get('open_positions')}`",
        f"- PnL % today: `{summary.get('pnl_pct_today')}`",
        f"- Realized PnL today (SOL): `{summary.get('realized_pnl_sol_today')}`",
        f"- Daily loss %: `{summary.get('daily_loss_pct')}`",
        f"- Consecutive losses: `{summary.get('consecutive_losses')}`",
        "",
        "## Operational quality",
        f"- Runtime live current-state count: `{ops.get('runtime_current_state_live_count', summary.get('runtime_current_state_live_count', 0))}`",
        f"- Runtime fallback current-state count: `{ops.get('runtime_current_state_fallback_count', summary.get('runtime_current_state_fallback_count', 0))}`",
        f"- Runtime stale current-state count: `{ops.get('runtime_current_state_stale_count', summary.get('runtime_current_state_stale_count', 0))}`",
        f"- Degraded-X entries attempted/opened/blocked: `{ops.get('degraded_x_entries_attempted', summary.get('degraded_x_entries_attempted', 0))}` / `{ops.get('degraded_x_entries_opened', summary.get('degraded_x_entries_opened', 0))}` / `{ops.get('degraded_x_entries_blocked', summary.get('degraded_x_entries_blocked', 0))}`",
        f"- Partial evidence entries: `{ops.get('partial_evidence_entry_count', summary.get('partial_evidence_entry_count', 0))}`",
        f"- Fallback refresh failures: `{ops.get('fallback_refresh_failure_count', summary.get('fallback_refresh_failure_count', 0))}`",
        "",
        "## Artifact pointers",
    ]
    for key in sorted(artifact_paths):
        lines.append(f"- {key}: `{artifact_paths[key]}`")
    if warnings:
        lines.extend(["", "## Warnings", *[f"- {warning}" for warning in warnings]])
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return target


def write_runtime_health_md(path: str | Path, summary: dict) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f"# Runtime Health ({summary.get('run_id', '-')})",
        "",
        f"- Mode: `{summary.get('mode')}`",
        f"- Current-state live/fallback/stale: `{summary.get('runtime_current_state_live_count', 0)}` / `{summary.get('runtime_current_state_fallback_count', 0)}` / `{summary.get('runtime_current_state_stale_count', 0)}`",
        f"- Current-state stale rate: `{summary.get('runtime_current_state_stale_rate', 0.0)}`",
        f"- Degraded-X attempted/opened/blocked: `{summary.get('degraded_x_entries_attempted', 0)}` / `{summary.get('degraded_x_entries_opened', 0)}` / `{summary.get('degraded_x_entries_blocked', 0)}`",
        f"- Tx window partial/truncated: `{summary.get('tx_window_partial_count', 0)}` / `{summary.get('tx_window_truncated_count', 0)}`",
        f"- Partial evidence entries: `{summary.get('partial_evidence_entry_count', 0)}`",
        f"- Unresolved replay rows: `{summary.get('unresolved_replay_row_count', 0)}`",
    ]
    warnings = summary.get("warnings") or []
    if warnings:
        lines.extend(["", "## Warnings", *[f"- {warning}" for warning in warnings]])
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return target
