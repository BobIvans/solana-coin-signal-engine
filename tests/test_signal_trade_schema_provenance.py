from __future__ import annotations

import json
from pathlib import Path

from utils.bundle_contract_fields import (
    BUNDLE_PROVENANCE_FIELDS,
    CLUSTER_PROVENANCE_FIELDS,
    LINKAGE_CONTRACT_FIELDS,
)
from utils.short_horizon_contract_fields import CONTINUATION_METADATA_FIELDS

ROOT = Path(__file__).resolve().parents[1]


def _schema_properties(schema_name: str) -> dict[str, object]:
    schema_path = ROOT / 'schemas' / schema_name
    return json.loads(schema_path.read_text(encoding='utf-8'))['properties']


def test_signal_event_schema_exposes_provenance_field_groups() -> None:
    properties = _schema_properties('signal_event.schema.json')

    for field in [*BUNDLE_PROVENANCE_FIELDS, *CLUSTER_PROVENANCE_FIELDS, *LINKAGE_CONTRACT_FIELDS, *CONTINUATION_METADATA_FIELDS]:
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

    for field in [*BUNDLE_PROVENANCE_FIELDS, *CLUSTER_PROVENANCE_FIELDS, *LINKAGE_CONTRACT_FIELDS, *CONTINUATION_METADATA_FIELDS]:
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
