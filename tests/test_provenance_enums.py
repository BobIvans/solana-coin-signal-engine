from __future__ import annotations

import pytest

from utils.provenance_enums import normalize_provenance_origin


@pytest.mark.parametrize(
    ("raw_value", "expected"),
    [
        ("raw_bundles", "direct_evidence"),
        ("graph_backed", "graph_evidence"),
        ("heuristic", "heuristic_evidence"),
        ("real_evidence", "direct_evidence"),
        ("heuristic_fallback", "heuristic_evidence"),
        (None, "missing"),
        ("", "missing"),
    ],
)
def test_normalize_provenance_origin_maps_legacy_aliases_and_empty_values(raw_value, expected) -> None:
    assert normalize_provenance_origin(raw_value) == expected
