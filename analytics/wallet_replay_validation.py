from __future__ import annotations

import csv
import json
import math
import statistics
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from utils.io import append_jsonl, ensure_dir, read_json, write_json
from utils.provenance_enums import MISSING_PROVENANCE_ORIGIN, WALLET_FAMILY_PROVENANCE_ORIGINS, validate_provenance_origin

REPLAY_VALIDATION_CONTRACT_VERSION = "wallet_replay_validation.v1"
VALIDATED_REGISTRY_CONTRACT_VERSION = "smart_wallet_registry_validated.v1"
VALIDATED_HOT_WALLETS_CONTRACT_VERSION = "hot_wallets_validated.v1"
PROMOTION_EVENT_TYPE = "wallet_registry_replay_decision"
MAX_HOT_VALIDATED_DEFAULT = 100
MIN_SAMPLE_TIER_2_DEFAULT = 5
MIN_SAMPLE_TIER_1_DEFAULT = 10
LOW_CONFIDENCE_CAP = 0.7
MEDIUM_CONFIDENCE_CAP = 0.9
HIGH_CONFIDENCE_CAP = 1.0


@dataclass(frozen=True)
class ValidationThresholds:
    max_hot_validated: int = MAX_HOT_VALIDATED_DEFAULT
    min_sample_tier2: int = MIN_SAMPLE_TIER_2_DEFAULT
    min_sample_tier1: int = MIN_SAMPLE_TIER_1_DEFAULT


@dataclass(frozen=True)
class ReplayObservation:
    token: str
    pnl_pct: float | None
    hold_sec: int | None
    wallets: tuple[str, ...]
    source_file: str
    outcome_label: str | None = None


class ReplayInputError(ValueError):
    """Raised when local replay evidence cannot be loaded."""


KNOWN_RECORD_KEYS = (
    "records",
    "results",
    "tokens",
    "wallet_replay",
    "wallet_replay_results",
    "paper_trades",
    "trades",
    "trade_rows",
    "rows",
    "items",
    "data",
    "entries",
    "signals",
)
TOKEN_KEYS = (
    "token",
    "token_address",
    "mint",
    "mint_address",
    "base_mint",
    "address",
    "symbol_address",
    "pair_base_token",
)
PNL_KEYS = (
    "pnl_pct",
    "net_pnl_pct",
    "realized_pnl_pct",
    "avg_pnl_pct",
    "profit_pct",
    "return_pct",
)
HOLD_KEYS = ("hold_sec", "avg_hold_sec", "holding_seconds", "duration_sec")
POSITIVE_KEYS = ("was_win", "win", "positive_outcome", "profitable", "is_positive")
NEGATIVE_KEYS = ("was_loss", "loss", "negative_outcome", "is_negative")
WALLET_LIST_KEYS = (
    "wallets",
    "wallet_hits",
    "matched_wallets",
    "wallet_addresses",
    "source_wallets",
    "smart_wallets",
    "smart_wallet_hits",
    "replay_wallets",
    "wallet_hit_list",
    "wallet_matches",
)
AGGREGATE_ONLY_KEYS = (
    "smart_wallet_hit_count",
    "wallet_hit_count",
    "wallet_count",
    "matched_wallet_count",
)


def _round(value: float | None) -> float | None:
    if value is None:
        return None
    return round(float(value), 6)


def _safe_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(parsed) or math.isinf(parsed):
        return None
    return parsed


def _safe_int(value: Any) -> int | None:
    numeric = _safe_float(value)
    if numeric is None:
        return None
    return int(round(numeric))


def _as_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "y"}:
            return True
        if normalized in {"false", "0", "no", "n"}:
            return False
    if isinstance(value, (int, float)):
        return bool(value)
    return None


def _normalize_wallet(wallet: Any) -> str | None:
    if isinstance(wallet, dict):
        for key in ("wallet", "address", "wallet_address"):
            if key in wallet:
                return _normalize_wallet(wallet.get(key))
        return None
    if not isinstance(wallet, str):
        return None
    value = wallet.strip()
    return value or None


def _extract_wallets(value: Any) -> tuple[str, ...]:
    wallets: set[str] = set()
    if isinstance(value, dict):
        for nested in value.values():
            wallets.update(_extract_wallets(nested))
    elif isinstance(value, (list, tuple, set)):
        for item in value:
            wallet = _normalize_wallet(item)
            if wallet:
                wallets.add(wallet)
    else:
        wallet = _normalize_wallet(value)
        if wallet:
            wallets.add(wallet)
    return tuple(sorted(wallets))


def _collect_candidate_records(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in KNOWN_RECORD_KEYS:
            value = payload.get(key)
            if isinstance(value, list) and value and all(isinstance(item, dict) for item in value):
                return list(value)
        if all(not isinstance(value, (list, dict)) for value in payload.values()):
            return [payload]
        rows: list[dict[str, Any]] = []
        for value in payload.values():
            if isinstance(value, list) and value and all(isinstance(item, dict) for item in value):
                rows.extend(item for item in value if isinstance(item, dict))
        return rows
    return []


def _find_nested_dict(record: dict[str, Any], keys: Iterable[str]) -> dict[str, Any] | None:
    for key in keys:
        value = record.get(key)
        if isinstance(value, dict):
            return value
    return None


def _extract_token(record: dict[str, Any]) -> str | None:
    for key in TOKEN_KEYS:
        value = record.get(key)
        if value not in (None, ""):
            return str(value)
    nested = _find_nested_dict(record, ("token", "trade", "signal", "features", "wallet_features"))
    if nested is not None:
        return _extract_token(nested)
    return None


def _extract_pnl(record: dict[str, Any]) -> float | None:
    for key in PNL_KEYS:
        value = _safe_float(record.get(key))
        if value is not None:
            return value
    for key in POSITIVE_KEYS:
        value = _as_bool(record.get(key))
        if value is not None:
            return 1.0 if value else -1.0
    for key in NEGATIVE_KEYS:
        value = _as_bool(record.get(key))
        if value is not None:
            return -1.0 if value else 1.0
    nested = _find_nested_dict(record, ("outcome", "metrics", "trade", "signal", "analysis"))
    if nested is not None:
        return _extract_pnl(nested)
    return None


def _extract_hold_sec(record: dict[str, Any]) -> int | None:
    for key in HOLD_KEYS:
        value = _safe_int(record.get(key))
        if value is not None:
            return value
    nested = _find_nested_dict(record, ("outcome", "metrics", "trade", "analysis"))
    if nested is not None:
        return _extract_hold_sec(nested)
    return None


def _extract_wallet_specific_wallets(record: dict[str, Any]) -> tuple[str, ...]:
    for key in WALLET_LIST_KEYS:
        if key in record:
            wallets = _extract_wallets(record.get(key))
            if wallets:
                return wallets
    nested = _find_nested_dict(record, ("wallet_features", "features", "enrichment", "analysis", "metadata"))
    if nested is not None:
        wallets = _extract_wallet_specific_wallets(nested)
        if wallets:
            return wallets
    return ()


def _has_aggregate_only_wallet_data(record: dict[str, Any]) -> bool:
    return any(record.get(key) not in (None, "", 0, 0.0) for key in AGGREGATE_ONLY_KEYS)


def _normalize_observation(record: dict[str, Any], source_file: str) -> ReplayObservation | None:
    token = _extract_token(record)
    if not token:
        return None
    wallets = _extract_wallet_specific_wallets(record)
    if not wallets and _has_aggregate_only_wallet_data(record):
        return None
    if not wallets:
        return None
    pnl_pct = _extract_pnl(record)
    hold_sec = _extract_hold_sec(record)
    outcome_label = record.get("outcome") if isinstance(record.get("outcome"), str) else None
    return ReplayObservation(
        token=str(token),
        pnl_pct=_round(pnl_pct),
        hold_sec=hold_sec,
        wallets=wallets,
        source_file=source_file,
        outcome_label=outcome_label,
    )


def _load_json_records(path: Path) -> list[dict[str, Any]]:
    payload = read_json(path, default=None)
    return _collect_candidate_records(payload)


def _load_jsonl_records(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            payload = json.loads(line)
            if isinstance(payload, dict):
                rows.append(payload)
    return rows


def _load_csv_records(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        return [dict(row) for row in reader]


def discover_replay_inputs(processed_dir: str | Path) -> list[Path]:
    root = Path(processed_dir)
    if not root.exists() or not root.is_dir():
        raise ReplayInputError(f"Processed directory not found: {root}")

    preferred = [
        root / "scored_tokens.json",
        root / "paper_trades.json",
        root / "paper_trades.jsonl",
        root / "post_run_analysis.json",
    ]
    discovered: list[Path] = []
    seen: set[Path] = set()

    def _add(path: Path) -> None:
        if path.exists() and path.is_file() and path not in seen:
            seen.add(path)
            discovered.append(path)

    for path in preferred:
        _add(path)
    for path in sorted(root.glob("replay_*.json")):
        _add(path)
    for pattern in ("*.json", "*.jsonl", "*.csv"):
        for path in sorted(root.glob(pattern)):
            _add(path)
    return discovered


def load_replay_observations(processed_dir: str | Path) -> tuple[list[ReplayObservation], dict[str, Any]]:
    observations: list[ReplayObservation] = []
    discovered_files = discover_replay_inputs(processed_dir)
    files_examined = 0
    files_with_records = 0
    usable_files = 0
    records_seen = 0
    skipped_no_wallet_specific = 0

    for path in discovered_files:
        loader = None
        if path.suffix == ".json":
            loader = _load_json_records
        elif path.suffix == ".jsonl":
            loader = _load_jsonl_records
        elif path.suffix == ".csv":
            loader = _load_csv_records
        if loader is None:
            continue

        files_examined += 1
        records = loader(path)
        if records:
            files_with_records += 1
        file_had_observation = False
        for record in records:
            records_seen += 1
            observation = _normalize_observation(record, path.name)
            if observation is None:
                skipped_no_wallet_specific += 1
                continue
            observations.append(observation)
            file_had_observation = True
        if file_had_observation:
            usable_files += 1

    if not observations:
        discovered_names = ", ".join(path.name for path in discovered_files) or "none"
        raise ReplayInputError(
            "No usable wallet-specific replay evidence found in local processed artifacts. "
            f"Examined {files_examined} files and {records_seen} records under {Path(processed_dir)}. "
            f"Discovered files: {discovered_names}. "
            f"Skipped {skipped_no_wallet_specific} records without wallet-specific attribution."
        )

    deduped = _dedupe_observations(observations)
    summary = {
        "processed_dir": Path(processed_dir).name,
        "discovered_files": [path.name for path in discovered_files],
        "files_examined": files_examined,
        "files_with_records": files_with_records,
        "usable_files": usable_files,
        "records_seen": records_seen,
        "wallet_specific_records": len(deduped),
        "skipped_non_wallet_specific_records": skipped_no_wallet_specific,
    }
    return deduped, summary


def _dedupe_observations(observations: list[ReplayObservation]) -> list[ReplayObservation]:
    bucket: dict[tuple[str, str], dict[str, Any]] = {}
    for observation in observations:
        for wallet in observation.wallets:
            key = (wallet, observation.token)
            state = bucket.setdefault(
                key,
                {
                    "wallet": wallet,
                    "token": observation.token,
                    "pnl_values": [],
                    "hold_values": [],
                    "sources": set(),
                    "labels": [],
                },
            )
            if observation.pnl_pct is not None:
                state["pnl_values"].append(float(observation.pnl_pct))
            if observation.hold_sec is not None:
                state["hold_values"].append(int(observation.hold_sec))
            state["sources"].add(observation.source_file)
            if observation.outcome_label:
                state["labels"].append(observation.outcome_label)

    deduped: list[ReplayObservation] = []
    for key in sorted(bucket):
        state = bucket[key]
        pnl_values = sorted(state["pnl_values"])
        hold_values = sorted(state["hold_values"])
        mean_pnl = _round(sum(pnl_values) / len(pnl_values)) if pnl_values else None
        mean_hold = int(round(sum(hold_values) / len(hold_values))) if hold_values else None
        deduped.append(
            ReplayObservation(
                token=state["token"],
                pnl_pct=mean_pnl,
                hold_sec=mean_hold,
                wallets=(state["wallet"],),
                source_file="|".join(sorted(state["sources"])),
                outcome_label=state["labels"][0] if state["labels"] else None,
            )
        )
    return deduped


def _confidence_for_sample(sample_size: int) -> str:
    if sample_size < 5:
        return "low"
    if sample_size < 15:
        return "medium"
    return "high"


def _confidence_cap(confidence: str) -> float:
    if confidence == "high":
        return HIGH_CONFIDENCE_CAP
    if confidence == "medium":
        return MEDIUM_CONFIDENCE_CAP
    return LOW_CONFIDENCE_CAP


def _normalize_bounded(value: float | None, *, lower: float, upper: float) -> float:
    if value is None:
        return 0.0
    if upper <= lower:
        return 0.0
    return round(min(1.0, max(0.0, (value - lower) / (upper - lower))), 6)


def _build_replay_evidence(wallet: str, observations: list[ReplayObservation], validated_at: str) -> dict[str, Any]:
    pnl_values = [float(item.pnl_pct) for item in observations if item.pnl_pct is not None]
    hold_values = [int(item.hold_sec) for item in observations if item.hold_sec is not None]
    replay_tokens_seen = len(observations)
    positive_hits = sum(1 for value in pnl_values if value > 0)
    negative_hits = sum(1 for value in pnl_values if value <= 0)
    winrate = (positive_hits / len(pnl_values)) if pnl_values else None
    false_positive_rate = (negative_hits / len(pnl_values)) if pnl_values else None
    mean_pnl = (sum(pnl_values) / len(pnl_values)) if pnl_values else None
    median_pnl = statistics.median(pnl_values) if pnl_values else None
    expectancy = mean_pnl
    avg_hold_sec = (sum(hold_values) / len(hold_values)) if hold_values else None
    confidence = _confidence_for_sample(replay_tokens_seen)
    score_components = {
        "normalized_expectancy": _normalize_bounded(expectancy, lower=-20.0, upper=20.0),
        "normalized_winrate": round(float(winrate or 0.0), 6),
        "normalized_median_pnl": _normalize_bounded(median_pnl, lower=-20.0, upper=20.0),
        "normalized_sample_size": _normalize_bounded(float(replay_tokens_seen), lower=0.0, upper=20.0),
        "inverse_false_positive_rate": round(1.0 - float(false_positive_rate or 0.0), 6) if false_positive_rate is not None else 0.0,
    }
    raw_score = (
        0.35 * score_components["normalized_expectancy"]
        + 0.25 * score_components["normalized_winrate"]
        + 0.20 * score_components["normalized_median_pnl"]
        + 0.10 * score_components["normalized_sample_size"]
        + 0.10 * score_components["inverse_false_positive_rate"]
    )
    evidence_score = round(raw_score * _confidence_cap(confidence), 6)
    return {
        "wallet": wallet,
        "replay_tokens_seen": replay_tokens_seen,
        "replay_hits": replay_tokens_seen,
        "positive_outcome_hits": positive_hits,
        "negative_outcome_hits": negative_hits,
        "median_pnl_pct": _round(median_pnl),
        "mean_pnl_pct": _round(mean_pnl),
        "winrate": _round(winrate),
        "false_positive_rate": _round(false_positive_rate),
        "expectancy": _round(expectancy),
        "avg_hold_sec": _round(avg_hold_sec),
        "evidence_score": evidence_score,
        "evidence_confidence": confidence,
        "promotion_decision": "hold",
        "promotion_reason": "wallet_specific_replay_evidence_computed",
        "last_validated_at": validated_at,
    }


def _is_structurally_invalid(record: dict[str, Any]) -> bool:
    if str(record.get("wallet") or "").strip() == "":
        return True
    if record.get("tier") == "rejected" or record.get("status") == "rejected":
        return True
    quality_flags = record.get("quality_flags") or {}
    return bool(quality_flags.get("invalid_format_rejected") or quality_flags.get("explicitly_unusable"))


def _decide_wallet_transition(record: dict[str, Any], evidence: dict[str, Any], thresholds: ValidationThresholds) -> tuple[str, str, str, str]:
    previous_tier = str(record.get("tier") or "tier_3")
    previous_status = str(record.get("status") or "watch")
    sample = int(evidence.get("replay_tokens_seen") or 0)
    expectancy = evidence.get("expectancy")
    evidence_score = float(evidence.get("evidence_score") or 0.0)
    false_positive_rate = evidence.get("false_positive_rate")
    confidence = evidence.get("evidence_confidence")

    if _is_structurally_invalid(record):
        return "rejected", "rejected", "reject", "wallet_record_invalid_or_unusable"

    if sample == 0:
        return previous_tier, "watch_pending_validation", "watch_pending_validation", "no_wallet_specific_replay_evidence"

    if sample < thresholds.min_sample_tier2:
        return previous_tier, "watch_pending_validation", "watch_pending_validation", "insufficient_wallet_specific_replay_sample"

    if previous_tier == "tier_2" and sample >= thresholds.min_sample_tier1 and confidence in {"medium", "high"} and (expectancy or 0.0) > 0 and (false_positive_rate if false_positive_rate is not None else 1.0) <= 0.35 and evidence_score >= 0.80:
        return "tier_1", "active", "promote", "promoted_to_tier_1_from_positive_replay_evidence"

    if previous_tier == "tier_3" and sample >= thresholds.min_sample_tier2 and (expectancy or 0.0) >= 0 and evidence_score >= 0.60:
        return "tier_2", "active", "promote", "promoted_to_tier_2_from_replay_evidence"

    if previous_tier == "tier_1" and sample >= 8 and ((expectancy is not None and expectancy <= 0) or (false_positive_rate is not None and false_positive_rate > 0.45) or evidence_score < 0.65):
        return "tier_2", "watch", "demote", "demoted_from_tier_1_due_to_negative_replay_evidence"

    if previous_tier == "tier_2" and sample >= thresholds.min_sample_tier2 and (evidence_score < 0.45 or (expectancy is not None and expectancy < 0)):
        return "tier_3", "watch", "demote", "demoted_from_tier_2_due_to_negative_replay_evidence"

    return previous_tier, ("active" if previous_status == "active" else "watch"), "hold", "replay_evidence_not_strong_enough_for_tier_change"


def _status_rank(status: str) -> int:
    ranks = {"active": 0, "watch": 1, "watch_pending_validation": 2, "rejected": 3}
    return ranks.get(status, 99)


def _tier_rank(tier: str) -> int:
    ranks = {"tier_1": 0, "tier_2": 1, "tier_3": 2, "rejected": 3}
    return ranks.get(tier, 99)


def _confidence_rank(confidence: str) -> int:
    return {"high": 0, "medium": 1, "low": 2}.get(confidence, 99)


def _registry_sort_key(record: dict[str, Any]) -> tuple[Any, ...]:
    evidence = record.get("replay_evidence") or {}
    return (
        _status_rank(str(record.get("new_status") or "watch")),
        _tier_rank(str(record.get("new_tier") or "tier_3")),
        -float(evidence.get("evidence_score") or 0.0),
        -float(record.get("registry_score") or 0.0),
        str(record.get("wallet") or ""),
    )


def _hot_sort_key(record: dict[str, Any]) -> tuple[Any, ...]:
    evidence = record.get("replay_evidence") or {}
    return (
        _tier_rank(str(record.get("new_tier") or "tier_3")),
        _confidence_rank(str(evidence.get("evidence_confidence") or "low")),
        -float(evidence.get("evidence_score") or 0.0),
        -float(record.get("registry_score") or 0.0),
        str(record.get("wallet") or ""),
    )


def _build_event(record: dict[str, Any], timestamp: str) -> dict[str, Any]:
    evidence = record.get("replay_evidence") or {}
    return {
        "event_type": PROMOTION_EVENT_TYPE,
        "wallet": record["wallet"],
        "timestamp": timestamp,
        "old_tier": record.get("previous_tier"),
        "new_tier": record.get("new_tier"),
        "old_status": record.get("previous_status"),
        "new_status": record.get("new_status"),
        "decision": record.get("promotion_decision"),
        "reason": record.get("promotion_reason"),
        "replay_tokens_seen": evidence.get("replay_tokens_seen"),
        "evidence_score": evidence.get("evidence_score"),
        "expectancy": evidence.get("expectancy"),
        "false_positive_rate": evidence.get("false_positive_rate"),
    }


def _collect_wallet_observations(observations: list[ReplayObservation]) -> dict[str, list[ReplayObservation]]:
    mapped: dict[str, list[ReplayObservation]] = defaultdict(list)
    for observation in observations:
        wallet = observation.wallets[0]
        mapped[wallet].append(observation)
    for wallet in mapped:
        mapped[wallet] = sorted(mapped[wallet], key=lambda item: (item.token, item.source_file))
    return mapped


def _build_report(
    *,
    generated_at: str,
    registry: dict[str, Any],
    validated_wallets: list[dict[str, Any]],
    input_summary: dict[str, Any],
) -> dict[str, Any]:
    evidence_wallets = [record for record in validated_wallets if int(record["replay_evidence"].get("replay_tokens_seen") or 0) > 0]
    pnl_values = [record["replay_evidence"]["expectancy"] for record in evidence_wallets if record["replay_evidence"].get("expectancy") is not None]
    winrates = [record["replay_evidence"]["winrate"] for record in evidence_wallets if record["replay_evidence"].get("winrate") is not None]
    before_tiers = defaultdict(int)
    after_tiers = defaultdict(int)
    decisions = defaultdict(int)
    for record in validated_wallets:
        before_tiers[str(record.get("previous_tier") or "rejected")] += 1
        after_tiers[str(record.get("new_tier") or "rejected")] += 1
        decisions[str(record.get("promotion_decision") or "hold")] += 1

    return {
        "contract_version": REPLAY_VALIDATION_CONTRACT_VERSION,
        "generated_at": generated_at,
        "input_summary": {
            "registry_wallets": len(registry.get("wallets") or []),
            **input_summary,
        },
        "replay_summary": {
            "total_wallets_evaluated": len(validated_wallets),
            "wallets_with_wallet_specific_evidence": len(evidence_wallets),
            "wallets_without_sufficient_evidence": sum(1 for record in validated_wallets if record["promotion_decision"] == "watch_pending_validation"),
            "wallets_promoted": decisions["promote"],
            "wallets_demoted": decisions["demote"],
            "wallets_held": decisions["hold"],
            "wallets_watch_pending_validation": decisions["watch_pending_validation"],
            "aggregate_expectancy_if_available": _round(sum(pnl_values) / len(pnl_values)) if pnl_values else None,
            "aggregate_winrate_if_available": _round(sum(winrates) / len(winrates)) if winrates else None,
        },
        "promotion_summary": {
            "promote": decisions["promote"],
            "demote": decisions["demote"],
            "hold": decisions["hold"],
            "watch_pending_validation": decisions["watch_pending_validation"],
            "reject": decisions["reject"],
        },
        "tier_change_summary": {
            "tier_1_before": before_tiers["tier_1"],
            "tier_1_after": after_tiers["tier_1"],
            "tier_2_before": before_tiers["tier_2"],
            "tier_2_after": after_tiers["tier_2"],
            "tier_3_before": before_tiers["tier_3"],
            "tier_3_after": after_tiers["tier_3"],
        },
        "notes": [
            "Replay validation uses wallet-specific local evidence only.",
            "Aggregate smart-wallet hit counts without per-wallet attribution do not trigger promotion.",
            "Sparse replay evidence results in watch_pending_validation rather than automatic rejection.",
        ],
    }


def evaluate_wallet_registry_replay(
    *,
    registry_path: str | Path,
    processed_dir: str | Path,
    out_report: str | Path,
    out_registry: str | Path,
    out_hot: str | Path,
    event_log: str | Path,
    generated_at: str | None = None,
    thresholds: ValidationThresholds | None = None,
) -> dict[str, Any]:
    thresholds = thresholds or ValidationThresholds()
    registry = read_json(registry_path, default=None)
    if not isinstance(registry, dict) or not isinstance(registry.get("wallets"), list):
        raise ReplayInputError(f"Registry file does not contain a wallet list: {registry_path}")

    timestamp = generated_at or str(registry.get("generated_at") or "") or "1970-01-01T00:00:00Z"
    observations, observation_summary = load_replay_observations(processed_dir)
    wallet_observations = _collect_wallet_observations(observations)

    validated_wallets: list[dict[str, Any]] = []
    for wallet_record in sorted(registry.get("wallets") or [], key=lambda item: str(item.get("wallet") or "")):
        wallet = str(wallet_record.get("wallet") or "")
        evidence = _build_replay_evidence(wallet, wallet_observations.get(wallet, []), timestamp)
        new_tier, new_status, decision, reason = _decide_wallet_transition(wallet_record, evidence, thresholds)
        evidence["promotion_decision"] = decision
        evidence["promotion_reason"] = reason
        validated_wallets.append(
            {
                "wallet": wallet,
                "previous_tier": wallet_record.get("tier"),
                "new_tier": new_tier,
                "previous_status": wallet_record.get("status"),
                "new_status": new_status,
                "registry_score": _round(wallet_record.get("registry_score")) or 0.0,
                "replay_evidence": evidence,
                "promotion_decision": decision,
                "promotion_reason": reason,
                "source_names": sorted(wallet_record.get("source_names") or []),
                "source_count": int(wallet_record.get("source_count") or 0),
                "tags": sorted(wallet_record.get("tags") or []),
                "notes": wallet_record.get("notes") or "",
                "wallet_family_id": wallet_record.get("wallet_family_id"),
                "independent_family_id": wallet_record.get("independent_family_id"),
                "wallet_family_confidence": _round(wallet_record.get("wallet_family_confidence")) or 0.0,
                "wallet_family_origin": validate_provenance_origin(wallet_record.get("wallet_family_origin") or MISSING_PROVENANCE_ORIGIN, allowed=WALLET_FAMILY_PROVENANCE_ORIGINS),
                "wallet_family_reason_codes": sorted(wallet_record.get("wallet_family_reason_codes") or []),
                "wallet_cluster_id": wallet_record.get("wallet_cluster_id"),
                "wallet_family_member_count": int(wallet_record.get("wallet_family_member_count") or 0),
                "wallet_family_shared_funder_flag": bool(wallet_record.get("wallet_family_shared_funder_flag", False)),
                "wallet_family_creator_link_flag": bool(wallet_record.get("wallet_family_creator_link_flag", False)),
                "wallet_family_status": str(wallet_record.get("wallet_family_status") or "missing"),
                "updated_at": timestamp,
            }
        )

    validated_wallets = sorted(validated_wallets, key=_registry_sort_key)
    report = _build_report(generated_at=timestamp, registry=registry, validated_wallets=validated_wallets, input_summary=observation_summary)
    validated_registry = {
        "contract_version": VALIDATED_REGISTRY_CONTRACT_VERSION,
        "generated_at": timestamp,
        "input_summary": report["input_summary"],
        "replay_summary": report["replay_summary"],
        "wallet_family_summary": registry.get("wallet_family_summary") or {},
        "wallet_family_assignments": registry.get("wallet_family_assignments") or [],
        "wallets": validated_wallets,
    }

    hot_wallets = [record for record in validated_wallets if record.get("new_status") == "active"]
    hot_wallets = sorted(hot_wallets, key=_hot_sort_key)[: max(0, thresholds.max_hot_validated)]
    hot_output = {
        "contract_version": VALIDATED_HOT_WALLETS_CONTRACT_VERSION,
        "generated_at": timestamp,
        "hot_summary": {
            "max_hot_wallets_size": thresholds.max_hot_validated,
            "selected_wallets": len(hot_wallets),
            "tier_1_wallets": sum(1 for record in hot_wallets if record.get("new_tier") == "tier_1"),
            "tier_2_wallets": sum(1 for record in hot_wallets if record.get("new_tier") == "tier_2"),
            "tier_3_wallets": sum(1 for record in hot_wallets if record.get("new_tier") == "tier_3"),
        },
        "wallets": hot_wallets,
    }

    write_json(out_report, report)
    write_json(out_registry, validated_registry)
    write_json(out_hot, hot_output)
    ensure_dir(Path(event_log).parent)
    for record in validated_wallets:
        append_jsonl(event_log, _build_event(record, timestamp))

    return {
        "report": report,
        "validated_registry": validated_registry,
        "validated_hot_wallets": hot_output,
        "event_log": str(Path(event_log)),
    }


__all__ = [
    "MAX_HOT_VALIDATED_DEFAULT",
    "MIN_SAMPLE_TIER_1_DEFAULT",
    "MIN_SAMPLE_TIER_2_DEFAULT",
    "ReplayInputError",
    "ValidationThresholds",
    "discover_replay_inputs",
    "evaluate_wallet_registry_replay",
    "load_replay_observations",
]
