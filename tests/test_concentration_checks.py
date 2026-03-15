import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from analytics.concentration_checks import check_concentration


class DummySettings:
    RUG_TOP1_HOLDER_HARD_MAX = 0.2
    RUG_TOP20_HOLDER_HARD_MAX = 0.65


def test_concentration_top1_hard_penalty():
    result = check_concentration({"top1_holder_share": 0.31, "top20_holder_share": 0.4}, DummySettings())
    assert result["concentration_penalty"] >= 0.5
    assert "top1_high" in result["concentration_flags"]
