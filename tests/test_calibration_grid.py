from src.calibration.grid import build_candidate_grid


def test_grid_is_deterministic_and_unique():
    config = {
        "baseline": {"a": 1, "b": 2},
        "grid": {"a": [1, 2], "b": [2, 3]},
    }

    first = build_candidate_grid(config)
    second = build_candidate_grid(config)

    assert first == second
    keys = [tuple(sorted(candidate["params"].items())) for candidate in first]
    assert len(keys) == len(set(keys))
    assert first[0]["candidate_id"] == "baseline"
