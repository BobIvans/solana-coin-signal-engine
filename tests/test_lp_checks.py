import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from analytics.lp_checks import check_lp_state


class DummySettings:
    RUG_LP_BURN_OWNER_ALLOWLIST = "11111111111111111111111111111111"
    RUG_LP_LOCK_PROGRAM_ALLOWLIST_PATH = "config/lock_programs.json"


def test_lp_lock_not_burn():
    result = check_lp_state(
        {
            "lp_token_balance": 10,
            "lp_owner": "owner",
            "lp_program_id": "LOCKER1",
        },
        DummySettings(),
    )
    assert result["lp_burn_confirmed"] is False
    assert result["lp_locked_flag"] is True
    assert "lock_without_burn" in result["lp_flags"]
