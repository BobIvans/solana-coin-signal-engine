#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from analytics.analyzer import run_post_run_analysis
from config.settings import load_settings
from src.promotion.runtime_signal_loader import load_latest_runtime_signal_batch
from src.replay.historical_replay_harness import run_historical_replay
from utils.io import ensure_dir, read_json, write_json

FIXTURES = REPO_ROOT / "tests" / "fixtures" / "historical_replay"
RUNTIME_JSONL_PRECEDENCE = [
    {
        "origin": "historical_replay_jsonl",
        "path": "trade_feature_matrix.jsonl",
        "kind": "jsonl",
        "required_fields": ("token_address",),
    }
]


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        raw = raw.strip()
        if raw:
            rows.append(json.loads(raw))
    return rows


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text("\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n", encoding="utf-8")


def _read_jsonl_file(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return _read_jsonl(path)


@contextmanager
def _scoped_env(updates: dict[str, str]):
    previous = {key: os.environ.get(key) for key in updates}
    try:
        os.environ.update(updates)
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _load_fixture_set(name: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    root = FIXTURES / name
    return (
        _read_json(root / "entry_candidates.json"),
        _read_jsonl(root / "scored_tokens.jsonl"),
        _read_json(root / "price_paths.json"),
    )


def _scenario_inputs(name: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    if name == "healthy":
        return _load_fixture_set("full_win")

    if name == "partial":
        entries, scored, price_paths = _load_fixture_set("partial_missing_exit")
        row = dict(scored[0])
        row["partial_evidence_flag"] = True
        row["recommended_position_pct"] = 0.18
        row["effective_position_pct"] = 0.18
        row["sizing_multiplier"] = 0.58
        row["sizing_reason_codes"] = ["partial_evidence"]
        row["sizing_warning"] = "partial_evidence"
        row["continuation_status"] = "partial"
        row["continuation_warning"] = "partial_evidence"
        row["continuation_warnings"] = ["partial_evidence"]
        row["linkage_status"] = "partial"
        row["linkage_warning"] = "partial_evidence"
        return entries, [row], price_paths

    if name == "stale":
        entries, scored, price_paths = _load_fixture_set("full_win")
        row = dict(scored[0])
        row["recommended_position_pct"] = 0.16
        row["effective_position_pct"] = 0.16
        row["sizing_multiplier"] = 0.48
        row["sizing_reason_codes"] = ["stale_evidence"]
        row["sizing_warning"] = "stale_evidence"
        row["partial_evidence_flag"] = True
        row["continuation_status"] = "partial"
        row["continuation_warning"] = "stale_cache_allowed"
        row["continuation_warnings"] = ["stale_cache_allowed", "upstream_failed_use_stale"]
        row["continuation_inputs_status"] = "stale"
        row["continuation_metric_origin"] = "stale_cache_fixture"
        row["linkage_status"] = "partial"
        row["linkage_warning"] = "stale_cache_allowed"
        row["regime_decision"] = "SCALP"
        row["regime_blockers"] = ["stale_evidence_caution"]
        return entries, [row], price_paths

    if name == "degraded_x":
        entries, scored, price_paths = _load_fixture_set("full_win")
        row = dict(scored[0])
        row["symbol"] = "DGX"
        row["x_status"] = "degraded"
        row["x_validation_score"] = 45
        row["x_validation_delta"] = 0
        row["recommended_position_pct"] = 0.12
        row["effective_position_pct"] = 0.12
        row["sizing_multiplier"] = 0.35
        row["sizing_reason_codes"] = ["x_degraded_size_reduced"]
        row["sizing_warning"] = "x_degraded_size_reduced"
        row["entry_flags"] = ["x_degraded_size_reduced"]
        row["regime_decision"] = "SCALP"
        row["regime_blockers"] = ["x_degraded"]
        return entries, [row], price_paths

    raise KeyError(f"Unknown scenario: {name}")


def _write_scenario_inputs(base_dir: Path, name: str) -> Path:
    inputs_dir = ensure_dir(base_dir / name / "inputs")
    entries, scored, price_paths = _scenario_inputs(name)
    write_json(inputs_dir / "entry_candidates.json", entries)
    _write_jsonl(inputs_dir / "scored_tokens.jsonl", scored)
    write_json(inputs_dir / "price_paths.json", price_paths)
    return inputs_dir


def _prepare_portfolio_state(target_dir: Path, result: dict[str, Any]) -> None:
    trades = result["artifacts"].trades
    positions = result["artifacts"].positions
    net_pnl_pct = 0.0
    if trades:
        try:
            net_pnl_pct = float(trades[0].get("net_pnl_pct") or 0.0)
        except (TypeError, ValueError):
            net_pnl_pct = 0.0
    payload = {
        "starting_equity_sol": 1.0,
        "equity_sol": 1.0 + (net_pnl_pct / 100.0),
        "unrealized_pnl_sol": 0.0,
        "total_signals": len(result["artifacts"].signals),
        "total_entries_attempted": len(trades),
        "total_fills_successful": len(trades),
        "total_positions_open": sum(1 for row in positions if str(row.get("status", "")).lower() == "open"),
    }
    write_json(target_dir / "portfolio_state.json", payload)


def _prepare_analyzer_inputs(run_dir: Path, result: dict[str, Any]) -> Path:
    analyzer_dir = ensure_dir(run_dir.parent / "analyzer_input")
    shutil.copyfile(run_dir / "trades.jsonl", analyzer_dir / "trades.jsonl")
    shutil.copyfile(run_dir / "signals.jsonl", analyzer_dir / "signals.jsonl")
    shutil.copyfile(run_dir / "trade_feature_matrix.jsonl", analyzer_dir / "trade_feature_matrix.jsonl")
    write_json(analyzer_dir / "positions.json", result["artifacts"].positions)
    _prepare_portfolio_state(analyzer_dir, result)
    return analyzer_dir


def _run_analyzer(analyzer_dir: Path) -> dict[str, Any]:
    env = {
        "TRADES_DIR": str(analyzer_dir),
        "SIGNALS_DIR": str(analyzer_dir),
        "POSITIONS_DIR": str(analyzer_dir),
        "PROCESSED_DATA_DIR": str(analyzer_dir),
        "POST_RUN_ANALYZER_ENABLED": "1",
        "POST_RUN_ANALYZER_FAILCLOSED": "1",
    }
    with _scoped_env(env):
        return run_post_run_analysis(load_settings())


def _scenario_summary(name: str, result: dict[str, Any], run_dir: Path, analyzer_result: dict[str, Any]) -> dict[str, Any]:
    trade = result["artifacts"].trades[0]
    row = result["artifacts"].trade_feature_matrix[0]
    runtime_batch = load_latest_runtime_signal_batch(
        run_dir,
        stale_after_sec=None,
        precedence=RUNTIME_JSONL_PRECEDENCE,
    )

    analyzer_events = _read_jsonl_file(Path(analyzer_result.get("summary_path", "")).parent / "analyzer_events.jsonl") if analyzer_result.get("summary_path") else []
    matrix_loaded = next((event for event in analyzer_events if event.get("event") == "trade_feature_matrix_loaded"), {})

    summary: dict[str, Any] = {
        "ok": True,
        "run_id": result["summary"]["run_id"],
        "replay_mode": result["summary"]["replay_mode"],
        "runtime_signal_origin": runtime_batch["selected_origin"],
        "runtime_signal_status": runtime_batch["batch_status"],
        "runtime_signal_count": len(runtime_batch["signals"]),
        "runtime_selected_artifact": runtime_batch["selected_artifact"],
        "replay_data_status": row.get("replay_data_status"),
        "replay_resolution_status": row.get("replay_resolution_status"),
        "regime": row.get("regime_decision"),
        "recommended_position_pct": row.get("recommended_position_pct"),
        "sizing_multiplier": row.get("sizing_multiplier"),
        "sizing_warning": row.get("sizing_warning"),
        "partial_evidence_flag": bool(row.get("partial_evidence_flag")),
        "continuation_status": row.get("continuation_status"),
        "continuation_warning": row.get("continuation_warning"),
        "linkage_status": row.get("linkage_status"),
        "linkage_warning": row.get("linkage_warning"),
        "x_status": row.get("x_status"),
        "x_validation_score": row.get("x_validation_score_entry"),
        "x_validation_delta": row.get("x_validation_delta_entry"),
        "selected_exit_reason": trade.get("exit_reason_final"),
        "trade_feature_matrix_path": str(run_dir / "trade_feature_matrix.jsonl"),
        "analyzer_summary_path": analyzer_result.get("summary_path"),
        "analyzer_report_path": analyzer_result.get("report_path"),
        "analyzer_matrix_path": matrix_loaded.get("path"),
        "summary_path": str(run_dir / "replay_summary.json"),
        "manifest_path": str(run_dir / "manifest.json"),
        "signals_path": str(run_dir / "signals.jsonl"),
        "trades_path": str(run_dir / "trades.jsonl"),
        "positions_path": str(run_dir / "positions.json"),
    }

    required = [
        run_dir / "signals.jsonl",
        run_dir / "trades.jsonl",
        run_dir / "positions.json",
        run_dir / "trade_feature_matrix.jsonl",
        run_dir / "replay_summary.json",
        run_dir / "manifest.json",
    ]
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise AssertionError(f"{name}: missing required artifacts: {missing}")

    if runtime_batch["selected_origin"] != "historical_replay_jsonl":
        raise AssertionError(f"{name}: runtime loader did not select replay jsonl artifact")
    if not runtime_batch["signals"]:
        raise AssertionError(f"{name}: runtime loader returned no rows")
    if not str(summary.get("analyzer_matrix_path") or "").endswith("trade_feature_matrix.jsonl"):
        raise AssertionError(f"{name}: analyzer did not consume replay trade_feature_matrix.jsonl")

    if name == "healthy":
        if summary["partial_evidence_flag"]:
            raise AssertionError("healthy: partial_evidence_flag should be false")
        if summary["x_status"] == "degraded":
            raise AssertionError("healthy: x_status unexpectedly degraded")
        if summary["recommended_position_pct"] is not None and float(summary["recommended_position_pct"]) < 0.30:
            raise AssertionError("healthy: position unexpectedly too small")
        if summary["replay_data_status"] != "historical":
            raise AssertionError("healthy: replay_data_status should stay historical")

    elif name == "partial":
        if summary["replay_data_status"] != "historical_partial":
            raise AssertionError("partial: replay_data_status should be historical_partial")
        if not summary["partial_evidence_flag"]:
            raise AssertionError("partial: partial_evidence_flag should be true")
        if summary["recommended_position_pct"] is not None and float(summary["recommended_position_pct"]) >= 0.30:
            raise AssertionError("partial: expected reduced size")
        if summary["replay_resolution_status"] not in {"partial", "unresolved"}:
            raise AssertionError("partial: expected partial or unresolved replay resolution")

    elif name == "stale":
        stale_visible = any(
            marker in str(value)
            for marker in ("stale_cache_allowed", "upstream_failed_use_stale")
            for value in (summary["continuation_warning"], summary["linkage_warning"], summary["sizing_warning"])
        )
        summary["stale_provenance_visible"] = stale_visible
        if not stale_visible:
            raise AssertionError("stale: stale provenance is not visible downstream")
        if summary["recommended_position_pct"] is not None and float(summary["recommended_position_pct"]) >= 0.30:
            raise AssertionError("stale: expected cautious reduced size")
        if summary["replay_data_status"] != "historical":
            raise AssertionError("stale: replay should remain historical while stale provenance stays visible")

    elif name == "degraded_x":
        if summary["x_status"] != "degraded":
            raise AssertionError("degraded_x: x_status must be degraded")
        if summary["x_validation_score"] != 45:
            raise AssertionError("degraded_x: x_validation_score must be 45")
        if summary["x_validation_delta"] != 0:
            raise AssertionError("degraded_x: x_validation_delta must be 0")
        if summary["recommended_position_pct"] is not None and float(summary["recommended_position_pct"]) >= 0.20:
            raise AssertionError("degraded_x: expected cautious reduced size")

    return summary


def run_e2e_golden_smoke(base_dir: Path) -> dict[str, Any]:
    base_dir = ensure_dir(base_dir)
    scenario_names = ["healthy", "partial", "stale", "degraded_x"]
    final_summary: dict[str, Any] = {}

    for name in scenario_names:
        scenario_root = base_dir / name
        if scenario_root.exists():
            shutil.rmtree(scenario_root)
        ensure_dir(scenario_root)
        inputs_dir = _write_scenario_inputs(base_dir, name)
        run_id = f"e2e_golden_{name}"
        result = run_historical_replay(
            artifact_dir=inputs_dir,
            run_id=run_id,
            config_path=REPO_ROOT / "config" / "replay.default.yaml",
            wallet_weighting="off",
            dry_run=True,
            output_base_dir=scenario_root,
            allow_synthetic_smoke=False,
        )
        run_dir = Path(result["outputs"]["run_dir"])
        analyzer_dir = _prepare_analyzer_inputs(run_dir, result)
        analyzer_result = _run_analyzer(analyzer_dir)
        final_summary[name] = _scenario_summary(name, result, run_dir, analyzer_result)

    summary_path = base_dir / "e2e_golden_summary.json"
    write_json(summary_path, final_summary)
    return {"summary_path": str(summary_path), "scenarios": final_summary}


def main() -> int:
    parser = argparse.ArgumentParser(description="Deterministic end-to-end golden smoke chain")
    parser.add_argument("--base-dir", default=str(REPO_ROOT / "data" / "smoke" / "e2e_golden"), help="Base output directory")
    args = parser.parse_args()

    result = run_e2e_golden_smoke(Path(args.base_dir).expanduser().resolve())
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
