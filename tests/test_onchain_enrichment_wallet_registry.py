from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
root_str = str(ROOT)
if root_str not in sys.path:
    sys.path.append(root_str)

import scripts.onchain_enrichment_smoke as smoke

try:
    from jsonschema import Draft7Validator
except ImportError:  # pragma: no cover - optional dependency
    Draft7Validator = None


class DummyRpc:
    def get_token_largest_accounts(self, token_address):
        return {"value": [{"amount": "500", "address": "acct1"}]}

    def get_token_supply(self, token_address):
        return {"value": {"amount": "1000", "decimals": 6, "uiAmount": 1000.0}}

    def get_signatures_for_address(self, source_addr, limit):
        return []

    def get_token_accounts_by_owner(self, owner, mint):
        return {"value": []}


class DummyHelius:
    def get_asset(self, token_address):
        return {"decimals": 6, "token_info": {"decimals": 6}}

    def get_transactions_by_address(self, address, limit):
        return []

    def get_transactions_by_signatures(self, signatures):
        return []


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _patch_dependencies(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(
        smoke,
        "load_settings",
        lambda: SimpleNamespace(
            PROCESSED_DATA_DIR=tmp_path / "processed",
            ONCHAIN_ENRICHMENT_MAX_TOKENS=5,
            SOLANA_RPC_URL="https://example.invalid",
            SOLANA_RPC_COMMITMENT="confirmed",
            HELIUS_API_KEY="dummy",
            SMART_WALLET_SEED_PATH=tmp_path / "seeds" / "smart_wallets.json",
            SMART_WALLET_HIT_WINDOW_SEC=300,
            HELIUS_TX_ADDR_LIMIT=40,
            HELIUS_TX_SIG_BATCH=25,
            ALLOW_LAUNCH_PATH_HEURISTICS_ONLY=True,
        ),
    )
    monkeypatch.setattr(smoke, "SolanaRpcClient", lambda *args, **kwargs: DummyRpc())
    monkeypatch.setattr(smoke, "HeliusClient", lambda *args, **kwargs: DummyHelius())
    monkeypatch.setattr(smoke, "compute_holder_metrics", lambda *args, **kwargs: {
        "top1_holder_share": 0.1,
        "top20_holder_share": 0.2,
        "first50_holder_conc_est": 0.3,
        "holder_entropy_est": 0.4,
        "unique_buyers_5m": 5,
        "holder_growth_5m": 2,
        "holder_metrics_warnings": [],
        "decimals": 6,
        "token_supply_raw": "1000",
        "token_supply_ui": 1000.0,
    })
    monkeypatch.setattr(smoke, "infer_dev_wallet", lambda *args, **kwargs: {"dev_wallet_est": "dev1", "dev_wallet_confidence_score": 0.5})
    monkeypatch.setattr(smoke, "compute_dev_sell_pressure_5m", lambda *args, **kwargs: {"dev_sell_pressure_5m": 0.0})
    monkeypatch.setattr(smoke, "estimate_launch_path", lambda *args, **kwargs: {
        "launch_path_label": "pumpfun_to_raydium",
        "pumpfun_to_raydium_sec": 42,
        "launch_path_confidence_score": 0.8,
    })
    monkeypatch.setattr(smoke, "compute_smart_wallet_hits", lambda *args, **kwargs: {
        "smart_wallet_hits": 2,
        "smart_wallet_hit_wallets": ["hot1", "watch1"],
    })
    monkeypatch.setattr(smoke, "utc_now_iso", lambda: "2026-03-18T12:00:00Z")
    _write_json(tmp_path / "seeds" / "smart_wallets.json", ["hot1", "watch1"])


def test_onchain_enrichment_smoke_with_validated_registry(monkeypatch, tmp_path: Path):
    shortlist = tmp_path / "shortlist.json"
    x_validated = tmp_path / "x_validated.json"
    validated_registry = tmp_path / "smart_wallets.validated.json"
    hot_registry = tmp_path / "hot_wallets.validated.json"

    _write_json(shortlist, {"shortlist": [{"token_address": "mint1", "pair_created_at": "2026-03-18T11:59:00Z", "pair_address": "pair1", "symbol": "ABC", "name": "Alpha"}]})
    _write_json(x_validated, {"tokens": [{"token_address": "mint1"}]})
    _write_json(validated_registry, {
        "contract_version": "smart_wallet_registry_validated.v1",
        "wallets": [
            {"wallet": "hot1", "new_tier": "tier_1", "new_status": "active", "registry_score": 0.9},
            {"wallet": "watch1", "new_tier": "tier_3", "new_status": "watch_pending_validation", "registry_score": 0.4},
        ],
    })
    _write_json(hot_registry, {
        "contract_version": "hot_wallets_validated.v1",
        "wallets": [{"wallet": "hot1", "new_tier": "tier_1", "new_status": "active"}],
    })

    _patch_dependencies(monkeypatch, tmp_path)
    payload = smoke.run(shortlist, x_validated, validated_registry_path=validated_registry, hot_registry_path=hot_registry)
    token = payload["tokens"][0]

    assert token["wallet_registry_status"] == "validated"
    assert token["smart_wallet_hits"] == 2
    assert token["smart_wallet_hit_wallets"] == ["hot1", "watch1"]
    assert token["smart_wallet_score_sum"] == 1.1
    assert token["smart_wallet_tier1_hits"] == 1
    assert token["smart_wallet_watch_hits"] == 1
    assert token["smart_wallet_registry_confidence"] == "medium"

    event_lines = (tmp_path / "processed" / "onchain_enrichment_events.jsonl").read_text(encoding="utf-8").splitlines()
    assert any('"event": "wallet_registry_loaded"' in line for line in event_lines)
    assert any('"event": "token_wallet_hits_computed"' in line for line in event_lines)


def test_onchain_enrichment_smoke_degrades_when_registry_missing(monkeypatch, tmp_path: Path):
    shortlist = tmp_path / "shortlist.json"
    x_validated = tmp_path / "x_validated.json"
    _write_json(shortlist, {"shortlist": [{"token_address": "mint1", "pair_created_at": "2026-03-18T11:59:00Z", "pair_address": "pair1"}]})
    _write_json(x_validated, {"tokens": [{"token_address": "mint1"}]})
    _patch_dependencies(monkeypatch, tmp_path)

    payload = smoke.run(
        shortlist,
        x_validated,
        validated_registry_path=tmp_path / "missing.validated.json",
        hot_registry_path=tmp_path / "missing.hot.json",
    )
    token = payload["tokens"][0]
    assert token["wallet_registry_status"] == "degraded_missing_registry"
    assert token["smart_wallet_score_sum"] == 0.0
    assert token["smart_wallet_tier1_hits"] == 0
    assert token["smart_wallet_registry_confidence"] == "low"
    assert token["smart_wallet_hit_wallets"] == ["hot1", "watch1"]


def test_enriched_schema_declares_wallet_registry_fields_and_accepts_smoke_record(monkeypatch, tmp_path: Path):
    shortlist = tmp_path / "shortlist.json"
    x_validated = tmp_path / "x_validated.json"
    validated_registry = tmp_path / "smart_wallets.validated.json"
    hot_registry = tmp_path / "hot_wallets.validated.json"

    _write_json(shortlist, {"shortlist": [{"token_address": "mint1", "pair_created_at": "2026-03-18T11:59:00Z", "pair_address": "pair1"}]})
    _write_json(x_validated, {"tokens": [{"token_address": "mint1"}]})
    _write_json(validated_registry, {"contract_version": "smart_wallet_registry_validated.v1", "wallets": [{"wallet": "hot1", "new_tier": "tier_1", "new_status": "active", "registry_score": 0.9}]})
    _write_json(hot_registry, {"contract_version": "hot_wallets_validated.v1", "wallets": [{"wallet": "hot1", "new_tier": "tier_1", "new_status": "active"}]})
    _patch_dependencies(monkeypatch, tmp_path)

    payload = smoke.run(shortlist, x_validated, validated_registry_path=validated_registry, hot_registry_path=hot_registry)
    token = payload["tokens"][0]

    schema_path = ROOT / "schemas" / "enriched_token.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    token_schema = schema["properties"]["tokens"]["items"]
    required = set(token_schema["required"])
    assert {"wallet_registry_status", "smart_wallet_score_sum", "smart_wallet_registry_confidence"}.issubset(required)

    if Draft7Validator is not None:
        Draft7Validator(schema).validate(payload)
    else:
        assert required.issubset(token.keys())
