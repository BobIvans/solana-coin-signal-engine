from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterable

_DEFAULT_POSITIVE_PNL_THRESHOLD_PCT = 0.0
_WINDOW_240S = 240
_WINDOW_15M = 15 * 60
_WINDOW_60M = 60 * 60


@dataclass(frozen=True)
class PriceObservation:
    offset_sec: float
    price: float


def _parse_ts(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _safe_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _first_present(sources: Iterable[dict[str, Any]], *fields: str) -> Any:
    for field in fields:
        for source in sources:
            if isinstance(source, dict) and field in source:
                return source.get(field)
    return None


def _normalize_observation(raw: Any, *, entry_ts: datetime | None) -> PriceObservation | None:
    if not isinstance(raw, dict):
        return None

    price = _safe_float(
        raw.get("price")
        if "price" in raw
        else raw.get("price_usd")
        if "price_usd" in raw
        else raw.get("mid_price")
        if "mid_price" in raw
        else raw.get("mark_price")
    )
    if price is None:
        return None

    offset_sec = _safe_float(
        raw.get("offset_sec")
        if "offset_sec" in raw
        else raw.get("elapsed_sec")
        if "elapsed_sec" in raw
        else raw.get("seconds_from_entry")
        if "seconds_from_entry" in raw
        else raw.get("t")
    )
    if offset_sec is None:
        point_ts = _parse_ts(raw.get("timestamp") or raw.get("ts") or raw.get("time"))
        if point_ts is None or entry_ts is None:
            return None
        offset_sec = (point_ts - entry_ts).total_seconds()

    return PriceObservation(offset_sec=float(offset_sec), price=float(price))


def extract_price_observations(*sources: dict[str, Any]) -> list[PriceObservation]:
    entry_ts = _parse_ts(_first_present(sources, "entry_time", "opened_at", "timestamp", "ts", "time"))
    raw_path = _first_present(
        sources,
        "price_path",
        "price_trajectory",
        "trajectory",
        "outcome_price_path",
        "observed_prices",
        "lifecycle_path",
    )
    if not isinstance(raw_path, list):
        return []

    observations: list[PriceObservation] = []
    for raw in raw_path:
        observation = _normalize_observation(raw, entry_ts=entry_ts)
        if observation is not None:
            observations.append(observation)

    deduped: dict[float, PriceObservation] = {}
    for observation in observations:
        deduped[observation.offset_sec] = observation
    return [deduped[key] for key in sorted(deduped)]


def compute_time_to_first_profit_sec(
    entry_price: float | None,
    observations: list[PriceObservation],
    *,
    positive_threshold_pct: float = _DEFAULT_POSITIVE_PNL_THRESHOLD_PCT,
) -> float | None:
    if entry_price is None or entry_price <= 0 or not observations:
        return None
    for observation in observations:
        pnl_pct = ((observation.price - entry_price) / entry_price) * 100.0
        if pnl_pct > positive_threshold_pct:
            return float(observation.offset_sec)
    return None


def compute_mfe_pct_240s(entry_price: float | None, observations: list[PriceObservation]) -> float | None:
    if entry_price is None or entry_price <= 0 or not observations:
        return None
    values = [((obs.price - entry_price) / entry_price) * 100.0 for obs in observations if 0 <= obs.offset_sec <= _WINDOW_240S]
    if not values:
        return None
    return max(values)


def compute_mae_pct_240s(entry_price: float | None, observations: list[PriceObservation]) -> float | None:
    if entry_price is None or entry_price <= 0 or not observations:
        return None
    values = [((obs.price - entry_price) / entry_price) * 100.0 for obs in observations if 0 <= obs.offset_sec <= _WINDOW_240S]
    if not values:
        return None
    return min(values)


def compute_trend_survival(entry_price: float | None, observations: list[PriceObservation], *, window_sec: int) -> float | None:
    if entry_price is None or entry_price <= 0 or not observations:
        return None

    window_observations = [obs for obs in observations if 0 <= obs.offset_sec <= window_sec]
    if len(window_observations) < 2:
        return None

    survived_sec = 0.0
    for index, current in enumerate(window_observations[:-1]):
        next_observation = window_observations[index + 1]
        segment_end = min(float(window_sec), next_observation.offset_sec)
        segment_duration = max(0.0, segment_end - current.offset_sec)
        if current.price >= entry_price and next_observation.price >= entry_price:
            survived_sec += segment_duration

    return survived_sec / float(window_sec)


def derive_outcome_metrics(*sources: dict[str, Any], positive_threshold_pct: float = _DEFAULT_POSITIVE_PNL_THRESHOLD_PCT) -> dict[str, float | None]:
    entry_price = _safe_float(_first_present(sources, "entry_price", "entry_price_usd", "price", "avg_entry_price", "fill_price"))
    observations = extract_price_observations(*sources)
    return {
        "time_to_first_profit_sec": compute_time_to_first_profit_sec(entry_price, observations, positive_threshold_pct=positive_threshold_pct),
        "mfe_pct_240s": compute_mfe_pct_240s(entry_price, observations),
        "mae_pct_240s": compute_mae_pct_240s(entry_price, observations),
        "trend_survival_15m": compute_trend_survival(entry_price, observations, window_sec=_WINDOW_15M),
        "trend_survival_60m": compute_trend_survival(entry_price, observations, window_sec=_WINDOW_60M),
    }
