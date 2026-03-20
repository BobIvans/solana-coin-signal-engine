from __future__ import annotations

from scripts.evidence_weighted_sizing_smoke import OUTPUT_JSON, OUTPUT_MD, run_smoke


def test_evidence_weighted_sizing_smoke_writes_outputs():
    payload = run_smoke()

    assert payload["case_count"] == 7
    assert OUTPUT_JSON.exists()
    assert OUTPUT_MD.exists()

    cases = {case["name"]: case for case in payload["cases"]}
    assert cases["strong_healthy_confirmation"]["sizing"]["effective_position_pct"] == cases["strong_healthy_confirmation"]["sizing"]["base_position_pct"]
    assert cases["degraded_x_otherwise_decent"]["sizing"]["sizing_origin"] == "degraded_x_policy"
    assert cases["hard_blocked_case"]["hard_block"] is True
    assert cases["hard_blocked_case"]["would_open_position"] is False
    assert cases["missing_evidence"]["sizing"]["partial_evidence_flag"] is True
