import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from utils.cache import cache_get, cache_set
from utils.rate_limit import acquire
from utils.retry import with_retry


def test_cache_set_get():
    cache_set("dex", "k", {"v": 1})
    assert cache_get("dex", "k") == {"v": 1}


def test_rate_limit_acquire():
    assert acquire("dex") is True


def test_with_retry_wraps_function():
    def _ok(value: int) -> int:
        return value + 1

    assert with_retry(_ok, 1) == 2
