import sys
from pathlib import Path

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
if str(FIXTURES_DIR) not in sys.path:
    sys.path.insert(0, str(FIXTURES_DIR))

from false_positive_cases import get_false_positive_case, replay_false_positive_case

_REPLAY_CASES = [
    "single_cluster_fake_strength",
    "creator_linked_early_buyers",
    "retry_heavy_sniper_loop",
    "sell_heavy_bundle_distribution",
    "fake_trend_weak_continuation",
    "degraded_x_ambiguous_onchain",
    "partial_evidence_false_confidence",
]


def test_false_positive_replay_expectations():
    for name in _REPLAY_CASES:
        case = get_false_positive_case(name)
        replay = replay_false_positive_case(name)
        expected = case["expected_replay_behavior"]

        assert replay["replay_label"] == expected["replay_label"], (name, replay)
        assert replay["entry"]["entry_decision"] != "TREND", (name, replay["entry"])
        assert replay["replay_label"] != "trend_survived", (name, replay)
