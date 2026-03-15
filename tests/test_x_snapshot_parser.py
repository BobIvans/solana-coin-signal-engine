import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from analytics.x_snapshot_parser import aggregate_token_snapshots, parse_query_snapshot


def test_parse_query_snapshot_handles_localized_counters():
    raw = {
        "cards": [
            {
                "author_handle": "@user",
                "text": "hello",
                "engagement": {"likes": "1.2K", "reposts": "3", "replies": "5", "views": "2M"},
            }
        ]
    }
    parsed = parse_query_snapshot(raw)
    card = parsed["cards"][0]
    assert card["engagement"]["likes"] == 1200
    assert card["engagement"]["views"] == 2_000_000


def test_aggregate_dedupes_repeated_cards_and_duplicate_ratio():
    token = {"token_address": "So11111111111111111111111111111111111111112", "symbol": "EX", "name": "Example"}
    snapshots = [
        {
            "x_status": "ok",
            "cards": [
                {"author_handle": "@a", "text": "EX to moon!!!", "engagement": {"likes": 1}},
                {"author_handle": "@a", "text": "EX to moon!!!", "engagement": {"likes": 2}},
                {"author_handle": "@b", "text": "EX to moon!", "engagement": {"likes": 3}},
            ],
        }
    ]
    agg = aggregate_token_snapshots(token, snapshots)
    assert agg["x_posts_visible"] == 2
    assert 0 <= agg["x_duplicate_text_ratio"] <= 1


def test_aggregate_handles_empty_cards():
    token = {"token_address": "So11111111111111111111111111111111111111112"}
    agg = aggregate_token_snapshots(token, [{"x_status": "empty", "cards": []}])
    assert agg["x_posts_visible"] == 0
    assert agg["x_unique_authors_visible"] == 0
