import sys
from pathlib import Path

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
if str(FIXTURES_DIR) not in sys.path:
    sys.path.insert(0, str(FIXTURES_DIR))

from false_positive_cases import (
    evaluate_false_positive_entry,
    get_false_positive_case,
    list_false_positive_cases,
)

_REQUIRED_CASES = [
    "single_cluster_fake_strength",
    "creator_linked_early_buyers",
    "retry_heavy_sniper_loop",
    "sell_heavy_bundle_distribution",
    "fake_trend_weak_continuation",
    "degraded_x_ambiguous_onchain",
    "partial_evidence_false_confidence",
]


def test_false_positive_regime_expectations():
    for name in _REQUIRED_CASES:
        case = get_false_positive_case(name)
        entry = evaluate_false_positive_entry(name)
        expected = case["expected_regime_behavior"]

        if "entry_decision" in expected:
            assert entry["entry_decision"] == expected["entry_decision"], (name, entry)
        for disallowed in expected.get("entry_decision_not", []):
            assert entry["entry_decision"] != disallowed, (name, entry)

        blockers_any = expected.get("blockers_any", [])
        if blockers_any:
            assert any(item in entry.get("regime_blockers", []) for item in blockers_any), (name, entry["regime_blockers"])

        warnings_any = expected.get("warnings_any", [])
        if warnings_any:
            assert any(item in entry.get("entry_warnings", []) for item in warnings_any), (name, entry["entry_warnings"])


def test_false_positive_baseline_does_not_trigger_discovery_lag_trend_block():
    for name in _REQUIRED_CASES:
        entry = evaluate_false_positive_entry(name)
        assert entry.get("discovery_lag_blocked_trend") is False, (name, entry)
