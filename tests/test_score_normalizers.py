import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from analytics.score_normalizers import normalize_capped, normalize_inverse, normalize_log_scaled, normalize_unit_interval


def test_normalize_unit_interval():
    assert normalize_unit_interval(None) == 0.0
    assert normalize_unit_interval(-1) == 0.0
    assert normalize_unit_interval(0.4) == 0.4
    assert normalize_unit_interval(3) == 1.0


def test_normalize_capped():
    assert normalize_capped(None, 0, 100) == 0.0
    assert normalize_capped(50, 0, 100) == 0.5
    assert normalize_capped(-1, 0, 100) == 0.0
    assert normalize_capped(999, 0, 100) == 1.0
    assert normalize_capped(10, 5, 5) == 0.0


def test_normalize_inverse():
    assert normalize_inverse(None, 0.1, 0.9) == 0.0
    assert math.isclose(normalize_inverse(0.1, 0.1, 0.9), 1.0)
    assert math.isclose(normalize_inverse(0.9, 0.1, 0.9), 0.0)
    assert 0.0 <= normalize_inverse(0.5, 0.1, 0.9) <= 1.0


def test_normalize_log_scaled():
    assert normalize_log_scaled(None, 1, 100) == 0.0
    assert normalize_log_scaled(1, 1, 100) == 0.0
    assert normalize_log_scaled(100, 1, 100) == 1.0
    mid = normalize_log_scaled(10, 1, 100)
    assert 0.0 < mid < 1.0
    assert normalize_log_scaled(5, 0, 100) == 0.0
