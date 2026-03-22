import sys
from pathlib import Path

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
if str(FIXTURES_DIR) not in sys.path:
    sys.path.insert(0, str(FIXTURES_DIR))

from false_positive_cases import (
    evaluate_false_positive_entry,
    get_false_positive_case,
    list_false_positive_cases,
    score_false_positive_case,
)

_REQUIRED_CASES = {
    "single_cluster_fake_strength",
    "creator_linked_early_buyers",
    "retry_heavy_sniper_loop",
    "sell_heavy_bundle_distribution",
    "fake_trend_weak_continuation",
    "degraded_x_ambiguous_onchain",
    "partial_evidence_false_confidence",
}


def _assert_contains_all(container: list[str], expected: list[str]) -> None:
    for item in expected:
        assert item in container


def test_required_false_positive_cases_exist():
    assert _REQUIRED_CASES.issubset(set(list_false_positive_cases()))


def test_false_positive_score_expectations():
    for name in sorted(_REQUIRED_CASES):
        case = get_false_positive_case(name)
        scored = score_false_positive_case(name)
        expected = case["expected_score_signals"]

        _assert_contains_all(scored.get("score_flags", []), expected.get("flags_all", []))
        _assert_contains_all(scored.get("score_warnings", []), expected.get("warnings_all", []))

        for field, minimum in expected.get("min_fields", {}).items():
            assert float(scored.get(field) or 0.0) >= float(minimum), (name, field, scored.get(field))

        for field, maximum in expected.get("max_fields", {}).items():
            assert float(scored.get(field) or 0.0) <= float(maximum), (name, field, scored.get(field))

        if "regime_candidate" in expected:
            assert scored["regime_candidate"] == expected["regime_candidate"]


def test_partial_evidence_false_confidence_keeps_watchlist_score_but_blocks_entry():
    case = get_false_positive_case("partial_evidence_false_confidence")
    scored = score_false_positive_case("partial_evidence_false_confidence")
    entry = evaluate_false_positive_entry("partial_evidence_false_confidence", scored=scored)

    assert scored["regime_candidate"] == case["expected_score_signals"]["regime_candidate"]
    assert "watchlist_partial_evidence_review" in scored.get("score_warnings", [])
    assert entry["entry_decision"] == "IGNORE"


def test_false_positive_baseline_does_not_accidentally_pick_up_discovery_lag_penalty():
    for name in sorted(_REQUIRED_CASES):
        scored = score_false_positive_case(name)
        assert scored["discovery_lag_score_penalty"] == 0.0, (name, scored["discovery_lag_score_penalty"])
