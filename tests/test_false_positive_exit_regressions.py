import sys
from pathlib import Path

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
if str(FIXTURES_DIR) not in sys.path:
    sys.path.insert(0, str(FIXTURES_DIR))

from false_positive_cases import evaluate_false_positive_exit, get_false_positive_case

_EXIT_CASES = [
    "single_cluster_fake_strength",
    "creator_linked_early_buyers",
    "retry_heavy_sniper_loop",
    "sell_heavy_bundle_distribution",
    "fake_trend_weak_continuation",
]


def test_false_positive_exit_expectations():
    for name in _EXIT_CASES:
        case = get_false_positive_case(name)
        expected = case["expected_exit_behavior"]
        exit_result = evaluate_false_positive_exit(name, forced_entry_decision=expected["position_decision"])

        assert exit_result["exit_decision"] == expected["exit_decision"], (name, exit_result)
        assert exit_result["exit_reason"] in expected.get("exit_reason_in", [exit_result["exit_reason"]]), (name, exit_result)

        flags_any = expected.get("exit_flags_any", [])
        if flags_any:
            assert any(item in exit_result.get("exit_flags", []) for item in flags_any), (name, exit_result["exit_flags"])

        warnings_any = expected.get("exit_warnings_any", [])
        if warnings_any:
            assert any(item in exit_result.get("exit_warnings", []) for item in warnings_any), (name, exit_result["exit_warnings"])
