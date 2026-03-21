from __future__ import annotations

import json
from pathlib import Path

from utils.bundle_contract_fields import (
    BUNDLE_PROVENANCE_FIELDS,
    CLUSTER_PROVENANCE_FIELDS,
    LINKAGE_CONTRACT_FIELDS,
)
from utils.short_horizon_contract_fields import CONTINUATION_METADATA_FIELDS
from utils.provenance_enums import BUNDLE_PROVENANCE_ORIGINS, CLUSTER_PROVENANCE_ORIGINS, LINKAGE_PROVENANCE_ORIGINS
from utils.wallet_family_contract_fields import SMART_WALLET_FAMILY_CONTRACT_FIELDS

ROOT = Path(__file__).resolve().parents[1]


REPLAY_PARITY_FIELDS = [
    'final_score_pre_wallet',
    'wallet_weighting_requested_mode',
    'wallet_weighting_effective_mode',
    'wallet_score_component_raw',
    'wallet_score_component_applied',
    'wallet_score_component_applied_shadow',
    'replay_score_source',
    'wallet_mode_parity_status',
    'score_contract_version',
    'historical_input_hash',
]


def _schema_properties(schema_name: str) -> dict[str, object]:
    schema_path = ROOT / 'schemas' / schema_name
    return json.loads(schema_path.read_text(encoding='utf-8'))['properties']


def test_signal_event_schema_exposes_provenance_field_groups() -> None:
    properties = _schema_properties('signal_event.schema.json')

    for field in [*BUNDLE_PROVENANCE_FIELDS, *CLUSTER_PROVENANCE_FIELDS, *LINKAGE_CONTRACT_FIELDS, *CONTINUATION_METADATA_FIELDS, *SMART_WALLET_FAMILY_CONTRACT_FIELDS, *REPLAY_PARITY_FIELDS]:
        assert field in properties

    assert properties['linkage_reason_codes'] == {
        'type': ['array', 'null'],
        'items': {'type': 'string'},
    }
    assert properties['continuation_available_evidence'] == {
        'type': ['array', 'null'],
        'items': {'type': 'string'},
    }
    assert properties['continuation_inputs_status'] == {
        'type': ['object', 'string', 'null'],
    }
    assert properties['continuation_confidence'] == {
        'type': ['number', 'string', 'null'],
    }


def test_trade_event_schema_exposes_provenance_field_groups() -> None:
    properties = _schema_properties('trade_event.schema.json')

    for field in [*BUNDLE_PROVENANCE_FIELDS, *CLUSTER_PROVENANCE_FIELDS, *LINKAGE_CONTRACT_FIELDS, *CONTINUATION_METADATA_FIELDS, *SMART_WALLET_FAMILY_CONTRACT_FIELDS, *REPLAY_PARITY_FIELDS]:
        assert field in properties

    assert properties['linkage_reason_codes'] == {
        'type': ['array', 'null'],
        'items': {'type': 'string'},
    }
    assert properties['continuation_available_evidence'] == {
        'type': ['array', 'null'],
        'items': {'type': 'string'},
    }
    assert properties['continuation_inputs_status'] == {
        'type': ['object', 'string', 'null'],
    }
    assert properties['continuation_confidence'] == {
        'type': ['number', 'string', 'null'],
    }


def test_signal_event_schema_origin_enums_are_canonical() -> None:
    properties = _schema_properties('signal_event.schema.json')
    assert set(properties['bundle_metric_origin']['enum']) == set(BUNDLE_PROVENANCE_ORIGINS) | {None}
    assert set(properties['cluster_metric_origin']['enum']) == set(CLUSTER_PROVENANCE_ORIGINS) | {None}
    assert set(properties['linkage_metric_origin']['enum']) == set(LINKAGE_PROVENANCE_ORIGINS) | {None}


def test_trade_event_schema_origin_enums_are_canonical() -> None:
    properties = _schema_properties('trade_event.schema.json')
    assert set(properties['bundle_metric_origin']['enum']) == set(BUNDLE_PROVENANCE_ORIGINS) | {None}
    assert set(properties['cluster_metric_origin']['enum']) == set(CLUSTER_PROVENANCE_ORIGINS) | {None}
    assert set(properties['linkage_metric_origin']['enum']) == set(LINKAGE_PROVENANCE_ORIGINS) | {None}
