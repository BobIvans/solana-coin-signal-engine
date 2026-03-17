from src.wallets.normalize import normalize_status, normalize_tier, normalize_wallet_record, validate_wallet_address


def test_invalid_addresses_rejected():
    assert validate_wallet_address("bad-address") is False
    item = normalize_wallet_record({"wallet_address": "bad-address"})
    assert item["_invalid_reason"] == "invalid_wallet_address"


def test_missing_optional_fields_filled():
    item = normalize_wallet_record({"wallet_address": "4Nd1mYwJ8M4d4R9vYj4M5Hn5QZQqNf8QjF2bU8X2h7Ty"})
    assert item["source"] == "unknown"
    assert item["status"] == "active"
    assert item["tier"] == "tier_3"


def test_status_tier_normalization():
    assert normalize_tier("T1") == "tier_1"
    assert normalize_status("INACTIVE") == "inactive"
