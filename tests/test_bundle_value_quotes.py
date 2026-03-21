import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import collectors.bundle_detector as bundle_detector


class DummySettings:
    BUNDLE_QUOTE_SYMBOL_ALLOWLIST = "USDC,USDT,WSOL"
    BUNDLE_QUOTE_MINT_ALLOWLIST = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v,Es9vMFrzaCERmJfrF4H2FYD1mA4P5uQWGWpZJYG1qhZY,So11111111111111111111111111111111111111112"


def test_usdc_quote_transfer_produces_bundle_value():
    value, origin = bundle_detector._extract_value({"tokenTransfers": [{"tokenSymbol": "USDC", "tokenAmount": 150.0}]}, DummySettings())
    assert value == 150.0
    assert origin == "quote_transfer"


def test_usdt_quote_transfer_produces_bundle_value():
    value, origin = bundle_detector._extract_value({"tokenTransfers": [{"tokenSymbol": "USDT", "tokenAmount": 220.0}]}, DummySettings())
    assert value == 220.0
    assert origin == "quote_transfer"


def test_quote_transfer_origin_is_marked_as_quote_transfer():
    value, origin = bundle_detector._extract_value({"tokenTransfers": [{"tokenSymbol": "WSOL", "tokenAmount": 3.5}]}, DummySettings())
    assert value == 3.5
    assert origin == "quote_transfer"
