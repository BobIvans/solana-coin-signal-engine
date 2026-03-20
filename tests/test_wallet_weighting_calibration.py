from __future__ import annotations

import json
from pathlib import Path

import pytest

jsonschema = pytest.importorskip("jsonschema")
referencing = pytest.importorskip("referencing")
Registry = referencing.Registry
Resource = referencing.Resource

from analytics.wallet_weighting_calibration import run_wallet_weighting_calibration


def _write_json(path: Path, payload: dict | list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def _scored(tokens: list[dict], generated_at: str = "2026-03-18T10:00:00Z") -> dict:
    return {"contract_version": "unified_score_v1", "generated_at": generated_at, "tokens": tokens}


def _mode_positions(mode_dir: Path, pnls: list[float], *, gross_offset: float = 0.01) -> None:
    rows = []
    for idx, pnl in enumerate(pnls, start=1):
        rows.append(
            {
                "position_id": f"pos_{idx}",
                "token_address": f"tok_{idx}",
                "status": "closed",
                "net_pnl_pct": pnl,
                "gross_pnl_pct": pnl + gross_offset,
                "closed_at": f"2026-03-18T10:{idx:02d}:00Z",
            }
        )
    _write_json(mode_dir / "positions.json", rows)


def _base_scored_sets() -> tuple[list[dict], list[dict], list[dict]]:
    off = [
        {"token_address": "tok_a", "final_score": 70.0, "scored_at": "2026-03-18T10:00:00Z", "wallet_adjustment": {"applied_delta": 0.0, "registry_status": "ok"}},
        {"token_address": "tok_b", "final_score": 65.0, "scored_at": "2026-03-18T10:00:00Z", "wallet_adjustment": {"applied_delta": 0.0, "registry_status": "ok"}},
        {"token_address": "tok_c", "final_score": 60.0, "scored_at": "2026-03-18T10:00:00Z", "wallet_adjustment": {"applied_delta": 0.0, "registry_status": "ok"}},
    ]
    shadow = [
        {"token_address": "tok_a", "final_score": 71.0, "scored_at": "2026-03-18T10:00:00Z", "wallet_adjustment": {"applied_delta": 1.0, "registry_status": "ok"}},
        {"token_address": "tok_b", "final_score": 66.0, "scored_at": "2026-03-18T10:00:00Z", "wallet_adjustment": {"applied_delta": 1.0, "registry_status": "ok"}},
        {"token_address": "tok_c", "final_score": 59.5, "scored_at": "2026-03-18T10:00:00Z", "wallet_adjustment": {"applied_delta": -0.5, "registry_status": "ok"}},
    ]
    on = [
        {"token_address": "tok_a", "final_score": 73.0, "scored_at": "2026-03-18T10:00:00Z", "wallet_adjustment": {"applied_delta": 3.0, "registry_status": "ok"}},
        {"token_address": "tok_b", "final_score": 67.5, "scored_at": "2026-03-18T10:00:00Z", "wallet_adjustment": {"applied_delta": 2.5, "registry_status": "ok"}},
        {"token_address": "tok_c", "final_score": 58.0, "scored_at": "2026-03-18T10:00:00Z", "wallet_adjustment": {"applied_delta": -2.0, "registry_status": "ok"}},
    ]
    return off, shadow, on


def _prepare_full_fixture(tmp_path: Path) -> dict[str, Path]:
    processed_dir = tmp_path / "processed"
    off, shadow, on = _base_scored_sets()
    _write_json(processed_dir / "scored_tokens.off.json", _scored(off))
    _write_json(processed_dir / "scored_tokens.shadow.json", _scored(shadow))
    _write_json(processed_dir / "scored_tokens.on.json", _scored(on))
    _mode_positions(processed_dir / "off", [0.10] * 30 + [-0.05] * 20)
    _mode_positions(processed_dir / "shadow", [0.12] * 34 + [-0.04] * 16)
    _mode_positions(processed_dir / "on", [0.20] * 38 + [-0.03] * 12)
    return {
        "processed_dir": processed_dir,
        "out_report": processed_dir / "wallet_calibration_report.json",
        "out_md": processed_dir / "wallet_calibration_summary.md",
        "out_recommendation": processed_dir / "wallet_rollout_recommendation.json",
        "out_events": processed_dir / "wallet_calibration_events.jsonl",
    }


def _run(paths: dict[str, Path], **kwargs):
    return run_wallet_weighting_calibration(
        processed_dir=paths["processed_dir"],
        out_report=paths["out_report"],
        out_md=paths["out_md"],
        out_recommendation=paths["out_recommendation"],
        out_events=paths["out_events"],
        **kwargs,
    )


def test_complete_off_shadow_on_comparison(tmp_path: Path):
    paths = _prepare_full_fixture(tmp_path)
    report = _run(paths)
    assert report["recommendation"]["recommendation"] == "promote_to_on"
    assert report["mode_comparison"]["shadow"]["token_level"]["tokens_compared"] == 3
    assert report["mode_comparison"]["on"]["outcome_level"]["closed_trades"] == 50
    assert paths["out_md"].exists()
    assert paths["out_events"].exists()


def test_partial_inputs_handled_conservatively(tmp_path: Path):
    processed_dir = tmp_path / "processed"
    off, shadow, _ = _base_scored_sets()
    _write_json(processed_dir / "scored_tokens.off.json", _scored(off))
    _write_json(processed_dir / "scored_tokens.shadow.json", _scored(shadow))
    report = _run(
        {
            "processed_dir": processed_dir,
            "out_report": processed_dir / "wallet_calibration_report.json",
            "out_md": processed_dir / "wallet_calibration_summary.md",
            "out_recommendation": processed_dir / "wallet_rollout_recommendation.json",
            "out_events": processed_dir / "wallet_calibration_events.jsonl",
        }
    )
    assert report["recommendation"]["recommendation"] == "keep_shadow"
    assert any("Only scoring-level inputs" in note for note in report["notes"])


def test_no_usable_inputs_fails_clearly(tmp_path: Path):
    processed_dir = tmp_path / "processed"
    _write_json(processed_dir / "scored_tokens.off.json", _scored([]))
    with pytest.raises(ValueError, match="No usable off/shadow/on comparison inputs were found"):
        _run(
            {
                "processed_dir": processed_dir,
                "out_report": processed_dir / "wallet_calibration_report.json",
                "out_md": processed_dir / "wallet_calibration_summary.md",
                "out_recommendation": processed_dir / "wallet_rollout_recommendation.json",
                "out_events": processed_dir / "wallet_calibration_events.jsonl",
            }
        )


def test_keep_shadow_on_insufficient_evidence(tmp_path: Path):
    paths = _prepare_full_fixture(tmp_path)
    _mode_positions(paths["processed_dir"] / "off", [0.10, -0.20, 0.05, -0.05, 0.01])
    _mode_positions(paths["processed_dir"] / "shadow", [0.11, -0.10, 0.08, -0.02, 0.02])
    _mode_positions(paths["processed_dir"] / "on", [0.25, -0.18, 0.10, -0.12, 0.01])
    report = _run(paths)
    assert report["recommendation"]["recommendation"] == "keep_shadow"
    assert report["recommendation"]["recommendation_confidence"] == "low"


def test_rollback_to_off_on_material_negative_impact(tmp_path: Path):
    paths = _prepare_full_fixture(tmp_path)
    _mode_positions(paths["processed_dir"] / "off", [0.10] * 30 + [-0.05] * 20)
    _mode_positions(paths["processed_dir"] / "shadow", [0.11] * 30 + [-0.04] * 20)
    _mode_positions(paths["processed_dir"] / "on", [0.05] * 15 + [-0.20] * 35)
    report = _run(paths)
    assert report["recommendation"]["recommendation"] == "rollback_to_off"


def test_deterministic_output_stability(tmp_path: Path):
    paths = _prepare_full_fixture(tmp_path)
    report_one = _run(paths)
    report_two = _run(paths)
    assert report_one["generated_at"] == report_two["generated_at"]
    assert report_one["recommendation"] == report_two["recommendation"]
    assert report_one["mode_comparison"]["pairwise"] == report_two["mode_comparison"]["pairwise"]


def test_schema_validation(tmp_path: Path):
    paths = _prepare_full_fixture(tmp_path)
    _run(paths)
    report = json.loads(paths["out_report"].read_text(encoding="utf-8"))
    recommendation = json.loads(paths["out_recommendation"].read_text(encoding="utf-8"))
    schema_dir = Path(__file__).resolve().parents[1] / "schemas"
    report_schema_path = schema_dir / "wallet_calibration_report.schema.json"
    recommendation_schema_path = schema_dir / "wallet_rollout_recommendation.schema.json"
    report_schema = json.loads(report_schema_path.read_text(encoding="utf-8"))
    recommendation_schema = json.loads(recommendation_schema_path.read_text(encoding="utf-8"))
    registry = Registry().with_resources(
        [
            ("./wallet_calibration_report.schema.json", Resource.from_contents(report_schema)),
            ("./wallet_rollout_recommendation.schema.json", Resource.from_contents(recommendation_schema)),
            (report_schema_path.resolve().as_uri(), Resource.from_contents(report_schema)),
            (recommendation_schema_path.resolve().as_uri(), Resource.from_contents(recommendation_schema)),
        ]
    )
    jsonschema.Draft202012Validator(report_schema, registry=registry).validate(report)
    jsonschema.Draft202012Validator(recommendation_schema, registry=registry).validate(recommendation)
