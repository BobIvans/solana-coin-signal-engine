from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from collectors.solana_rpc_client import TOKEN_PROGRAM_2022, summarize_token_program_safety


def test_transfer_fee_authority_active_is_reported():
    payload = {
        "owner": TOKEN_PROGRAM_2022,
        "extensions": [{"extension": "transferFeeConfig", "transferFeeConfigAuthority": "authority_wallet"}],
    }
    out = summarize_token_program_safety(payload)
    assert out["transfer_fee_authority_active"] is True


def test_permanent_delegate_detected_is_reported():
    payload = {
        "owner": TOKEN_PROGRAM_2022,
        "extensions": [{"extension": "permanentDelegate", "delegate": "delegate_wallet"}],
    }
    out = summarize_token_program_safety(payload)
    assert out["permanent_delegate_detected"] is True


def test_default_account_state_frozen_is_reported():
    payload = {
        "owner": TOKEN_PROGRAM_2022,
        "extensions": [{"extension": "defaultAccountState", "state": "Frozen"}],
    }
    out = summarize_token_program_safety(payload)
    assert out["default_account_state_frozen"] is True


def test_dangerous_token2022_extensions_raise_hard_block_flag():
    payload = {
        "owner": TOKEN_PROGRAM_2022,
        "extensions": [
            {"extension": "permanentDelegate", "delegate": "delegate_wallet"},
            {"extension": "closeAuthority", "closeAuthority": "closer_wallet"},
        ],
    }
    out = summarize_token_program_safety(payload)
    assert out["token_sellability_hard_block_flag"] is True
    assert out["token_extension_risk_severity"] == "hard_block"
