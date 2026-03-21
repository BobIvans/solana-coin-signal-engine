from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from src.replay.historical_replay_harness import run_historical_replay

ROOT = Path(__file__).resolve().parents[1]


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _wallet_scored_row(*, final_score: float = 80.0) -> dict[str, object]:
    return {
        "token_address": "tok_wallet",
        "pair_address": "pair_wallet",
        "symbol": "WAL",
        "final_score": final_score,
        "entry_confidence": 0.61,
        "recommended_position_pct": 0.2,
        "wallet_registry_status": "validated",
        "smart_wallet_score_sum": 12.0,
        "smart_wallet_tier1_hits": 1,
        "smart_wallet_active_hits": 1,
        "smart_wallet_watch_hits": 0,
        "smart_wallet_early_entry_hits": 1,
        "smart_wallet_netflow_bias": 0.35,
        "smart_wallet_registry_confidence": "high",
        "rug_score": 0.08,
        "rug_verdict": "PASS",
        "buy_pressure": 0.84,
        "first30s_buy_ratio": 0.79,
        "bundle_cluster_score": 0.81,
        "volume_velocity": 5.2,
        "dev_sell_pressure_5m": 0.0,
        "x_validation_score": 58,
        "x_validation_delta": 1,
        "holder_growth_5m": 16,
        "smart_wallet_hits": 1,
        "lp_burn_confirmed": True,
        "mint_revoked": True,
        "bundle_count_first_60s": 3,
        "bundle_timing_from_liquidity_add_min": 0.18,
        "bundle_success_rate": 0.72,
        "bundle_composition_dominant": "buy-only",
        "bundle_failure_retry_pattern": 1,
        "bundle_wallet_clustering_score": 0.48,
        "cluster_concentration_ratio": 0.33,
        "num_unique_clusters_first_60s": 2,
        "creator_in_cluster_flag": False,
        "entry_price": 1.0,
        "entry_time": "2026-03-10T12:00:00Z",
        "features": {
            "age_sec": 110,
            "age_minutes": 2,
            "liquidity_usd": 32000.0,
            "buy_pressure": 0.84,
            "volume_velocity": 5.2,
            "holder_growth_5m": 16,
            "smart_wallet_hits": 1,
        },
    }


def _make_artifact_dir(base: Path) -> Path:
    _write_json(base / "entry_candidates.json", [{"token_address": "tok_wallet", "pair_address": "pair_wallet", "entry_decision": "ENTER"}])
    _write_json(
        base / "price_paths.json",
        [{
            "token_address": "tok_wallet",
            "pair_address": "pair_wallet",
            "price_path": [
                {"offset_sec": 0, "price": 1.0, "timestamp": "2026-03-10T12:00:00Z"},
                {"offset_sec": 35, "price": 1.15, "timestamp": "2026-03-10T12:00:35Z"},
                {"offset_sec": 55, "price": 1.10, "timestamp": "2026-03-10T12:00:55Z"},
            ],
        }],
    )
    return base


def _summary_for_mode(artifact_dir: Path, tmp_path: Path, mode: str) -> dict[str, object]:
    result = run_historical_replay(
        artifact_dir=artifact_dir,
        run_id=f"parity_{mode}",
        config_path=ROOT / "config" / "replay.default.yaml",
        wallet_weighting=mode,
        dry_run=True,
        output_base_dir=tmp_path,
    )
    summary = result["summary"]
    trade = result["artifacts"].trades[0]
    row = result["artifacts"].trade_feature_matrix[0]
    return {"summary": summary, "trade": trade, "row": row}


def test_replay_cli_preserves_shadow_mode(tmp_path: Path):
    artifact_dir = _make_artifact_dir(tmp_path / "cli_shadow")
    _write_json(artifact_dir / "scored_tokens.shadow.json", {"tokens": [_wallet_scored_row()]})

    run_id = "shadow_cli_mode"
    subprocess.run(
        [
            sys.executable,
            "scripts/replay_7d.py",
            "--artifact-dir",
            str(artifact_dir),
            "--config",
            "config/replay.default.yaml",
            "--run-id",
            run_id,
            "--wallet-weighting",
            "shadow",
            "--dry-run",
        ],
        check=True,
        cwd=ROOT,
    )
    summary = json.loads((ROOT / "runs" / run_id / "replay_summary.json").read_text(encoding="utf-8"))
    matrix_row = json.loads((ROOT / "runs" / run_id / "trade_feature_matrix.jsonl").read_text(encoding="utf-8").splitlines()[0])
    assert summary["wallet_weighting_requested_mode"] == "shadow"
    assert summary["wallet_weighting_effective_modes"] == ["shadow"]
    assert summary["replay_score_source"] == "mode_specific_scored_artifact"
    assert matrix_row["wallet_weighting_requested_mode"] == "shadow"
    assert matrix_row["wallet_weighting_effective_mode"] == "shadow"


def test_generic_scored_artifact_gets_rescored_across_modes(tmp_path: Path):
    artifact_dir = _make_artifact_dir(tmp_path / "generic_rescore")
    _write_json(artifact_dir / "scored_tokens.json", {"tokens": [_wallet_scored_row(final_score=80.0)]})

    off = _summary_for_mode(artifact_dir, tmp_path, "off")
    shadow = _summary_for_mode(artifact_dir, tmp_path, "shadow")
    on = _summary_for_mode(artifact_dir, tmp_path, "on")

    assert off["summary"]["historical_input_hash"] == shadow["summary"]["historical_input_hash"] == on["summary"]["historical_input_hash"]
    assert off["summary"]["replay_score_source"] == shadow["summary"]["replay_score_source"] == on["summary"]["replay_score_source"] == "generic_scored_artifact_rescored"
    assert off["row"]["final_score_pre_wallet"] == shadow["row"]["final_score_pre_wallet"] == on["row"]["final_score_pre_wallet"] == 80.0
    assert off["row"]["wallet_score_component_applied"] == 0.0
    assert shadow["row"]["wallet_score_component_applied"] == 0.0
    assert on["row"]["wallet_score_component_applied"] > 0.0
    assert shadow["row"]["wallet_score_component_applied_shadow"] > 0.0
    assert on["row"]["wallet_score_component_applied_shadow"] > 0.0
    assert off["row"]["wallet_weighting_effective_mode"] == "off"
    assert shadow["row"]["wallet_weighting_effective_mode"] == "shadow"
    assert on["row"]["wallet_weighting_effective_mode"] == "on"
    assert off["trade"]["token_address"] == shadow["trade"]["token_address"] == on["trade"]["token_address"] == "tok_wallet"
    assert off["trade"]["replay_resolution_status"] == shadow["trade"]["replay_resolution_status"] == on["trade"]["replay_resolution_status"]


def test_mode_specific_scored_artifact_takes_precedence(tmp_path: Path):
    artifact_dir = _make_artifact_dir(tmp_path / "mode_specific")
    _write_json(artifact_dir / "scored_tokens.json", {"tokens": [_wallet_scored_row(final_score=60.0)]})
    _write_json(artifact_dir / "scored_tokens.shadow.json", {"tokens": [_wallet_scored_row(final_score=71.0)]})

    result = run_historical_replay(
        artifact_dir=artifact_dir,
        run_id="shadow_mode_specific",
        config_path=ROOT / "config" / "replay.default.yaml",
        wallet_weighting="shadow",
        dry_run=True,
        output_base_dir=tmp_path,
    )
    summary = result["summary"]
    row = result["artifacts"].trade_feature_matrix[0]
    assert str(summary["scored_input_file"]).endswith("scored_tokens.shadow.json")
    assert summary["replay_score_source"] == "mode_specific_scored_artifact"
    assert row["final_score_pre_wallet"] == 71.0
