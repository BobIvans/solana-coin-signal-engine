import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from analytics.authority_checks import check_authorities


def test_authority_flags_for_active_mint():
    result = check_authorities({"mint_authority": "Creator", "freeze_authority": None})
    assert result["mint_revoked"] is False
    assert result["freeze_revoked"] is True
    assert "mint_active" in result["authority_flags"]


def test_authority_flags_for_active_freeze():
    result = check_authorities({"mint_authority": None, "freeze_authority": "Creator"})
    assert result["mint_revoked"] is True
    assert result["freeze_revoked"] is False
    assert "freeze_active" in result["authority_flags"]


def test_authority_hard_block_flags_include_freeze_active():
    result = check_authorities({"mint_authority": None, "freeze_authority": "Creator"})
    assert "freeze_active" in result["authority_hard_block_flags"]
