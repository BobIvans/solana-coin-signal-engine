"""Contract parity helpers for artifact, contract, and docs consistency checks."""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from utils.bundle_contract_fields import (
        BUNDLE_CONTRACT_FIELDS,
        BUNDLE_PROVENANCE_FIELDS,
        CLUSTER_PROVENANCE_FIELDS,
        LINKAGE_CONTRACT_FIELDS,
    )
except Exception:  # pragma: no cover - fallback for partial environments
    BUNDLE_CONTRACT_FIELDS = [
        "bundle_count_first_60s",
        "bundle_size_value",
        "unique_wallets_per_bundle_avg",
        "bundle_timing_from_liquidity_add_min",
        "bundle_success_rate",
        "bundle_composition_dominant",
        "bundle_tip_efficiency",
        "bundle_failure_retry_pattern",
        "cross_block_bundle_correlation",
        "bundle_wallet_clustering_score",
        "cluster_concentration_ratio",
        "num_unique_clusters_first_60s",
        "creator_in_cluster_flag",
    ]
    BUNDLE_PROVENANCE_FIELDS = [
        "bundle_evidence_status",
        "bundle_evidence_source",
        "bundle_evidence_confidence",
        "bundle_evidence_warning",
        "bundle_metric_origin",
    ]
    CLUSTER_PROVENANCE_FIELDS = [
        "cluster_evidence_status",
        "cluster_evidence_source",
        "cluster_evidence_confidence",
        "cluster_metric_origin",
        "graph_cluster_id_count",
        "graph_cluster_coverage_ratio",
        "creator_cluster_id",
        "dominant_cluster_id",
    ]
    LINKAGE_CONTRACT_FIELDS = [
        "creator_dev_link_score",
        "creator_buyer_link_score",
        "dev_buyer_link_score",
        "shared_funder_link_score",
        "creator_cluster_link_score",
        "cluster_dev_link_score",
        "linkage_risk_score",
        "creator_funder_overlap_count",
        "buyer_funder_overlap_count",
        "funder_overlap_count",
        "linkage_reason_codes",
        "linkage_confidence",
        "linkage_metric_origin",
        "linkage_status",
        "linkage_warning",
    ]

try:
    from utils.short_horizon_contract_fields import SHORT_HORIZON_SIGNAL_FIELDS, CONTINUATION_METADATA_FIELDS
except Exception:  # pragma: no cover - fallback for partial environments
    SHORT_HORIZON_SIGNAL_FIELDS = [
        "net_unique_buyers_60s",
        "liquidity_refill_ratio_120s",
        "cluster_sell_concentration_120s",
        "smart_wallet_dispersion_score",
        "x_author_velocity_5m",
        "seller_reentry_ratio",
        "liquidity_shock_recovery_sec",
    ]
    CONTINUATION_METADATA_FIELDS = [
        "continuation_status",
        "continuation_warning",
        "continuation_confidence",
        "continuation_metric_origin",
        "continuation_coverage_ratio",
        "continuation_inputs_status",
        "continuation_warnings",
        "continuation_available_evidence",
        "continuation_missing_evidence",
    ]

try:
    from analytics.analyzer_matrix import _MATRIX_NUMERIC_FIELDS, _MATRIX_CATEGORICAL_FIELDS
except Exception:  # pragma: no cover - fallback for partial environments
    _MATRIX_NUMERIC_FIELDS = [
        "regime_confidence",
        "final_score",
        "bundle_count_first_60s",
        "bundle_size_value",
        "unique_wallets_per_bundle_avg",
        "bundle_timing_from_liquidity_add_min",
        "bundle_success_rate",
        "bundle_tip_efficiency",
        "cross_block_bundle_correlation",
        "bundle_wallet_clustering_score",
        "cluster_concentration_ratio",
        "num_unique_clusters_first_60s",
        "hold_sec",
        "gross_pnl_pct",
        "net_pnl_pct",
        "x_validation_score_entry",
        "x_validation_delta_entry",
        "net_unique_buyers_60s",
        "liquidity_refill_ratio_120s",
        "cluster_sell_concentration_120s",
        "smart_wallet_dispersion_score",
        "x_author_velocity_5m",
        "seller_reentry_ratio",
        "liquidity_shock_recovery_sec",
    ]
    _MATRIX_CATEGORICAL_FIELDS = [
        "regime_decision",
        "expected_hold_class",
        "bundle_composition_dominant",
        "bundle_failure_retry_pattern",
        "creator_in_cluster_flag",
        "x_status",
        "exit_reason_final",
    ]


ENTRY_REQUIRED_FIELDS = {
    "token_address",
    "entry_decision",
    "entry_confidence",
    "recommended_position_pct",
    "entry_reason",
    "regime_confidence",
    "regime_reason_flags",
    "regime_blockers",
    "expected_hold_class",
    "entry_snapshot",
}

SCORED_REQUIRED_FIELDS = {
    "token_address",
    "onchain_core",
    "early_signal_bonus",
    "x_validation_bonus",
    "rug_penalty",
    "spam_penalty",
    "confidence_adjustment",
    "final_score",
    "regime_candidate",
}

REPLAY_REQUIRED_FIELDS = {
    "position_id",
    "regime_decision",
    "expected_hold_class",
    "x_status",
    "exit_reason_final",
    "hold_sec",
    "net_pnl_pct",
    "bundle_count_first_60s",
    "bundle_size_value",
    "net_unique_buyers_60s",
    "liquidity_refill_ratio_120s",
    "cluster_sell_concentration_120s",
    "smart_wallet_dispersion_score",
    "x_author_velocity_5m",
    "seller_reentry_ratio",
    "liquidity_shock_recovery_sec",
}

STATUS_SEVERITY = {
    "ok": 0,
    "warning": 1,
    "empty": 2,
    "mismatch": 3,
    "missing": 4,
    "malformed": 5,
}


@dataclass(frozen=True)
class ArtifactContract:
    contract_group: str
    artifact_name: str
    artifact_path: str
    required_fields: tuple[str, ...]
    optional_fields: tuple[str, ...] = ()
    selector: str | None = None
    description: str = ""


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _as_sorted_strings(values: Iterable[str]) -> list[str]:
    return sorted({str(value) for value in values if str(value)})


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        raw = line.strip()
        if not raw:
            continue
        row = json.loads(raw)
        if isinstance(row, dict):
            rows.append(row)
    return rows


def _resolve_nested(payload: Any, selector: str) -> Any:
    current = payload
    for part in selector.split("."):
        if part == "tokens" and isinstance(current, dict):
            current = current.get("tokens", [])
            continue
        if isinstance(current, dict):
            current = current.get(part)
        else:
            return None
    return current


def _extract_rows(payload: Any, selector: str | None) -> list[dict[str, Any]]:
    target = payload if selector is None else _resolve_nested(payload, selector)
    if target is None:
        return []
    if isinstance(target, list):
        return [row for row in target if isinstance(row, dict)]
    if isinstance(target, dict):
        if selector is None and isinstance(target.get("tokens"), list):
            return [row for row in target.get("tokens", []) if isinstance(row, dict)]
        return [target]
    return []


def collect_contract_definitions() -> list[ArtifactContract]:
    replay_optional = tuple(_as_sorted_strings((set(_MATRIX_NUMERIC_FIELDS) | set(_MATRIX_CATEGORICAL_FIELDS)) - REPLAY_REQUIRED_FIELDS))
    return [
        ArtifactContract(
            contract_group="core_shortlist",
            artifact_name="shortlist",
            artifact_path="data/processed/shortlist.json",
            required_fields=("token_address",),
            optional_fields=("symbol", "name", "pair_address", "age_sec", "liquidity_usd", "txns_m5"),
            description="Minimal discovery shortlist contract.",
        ),
        ArtifactContract(
            contract_group="core_x_validation",
            artifact_name="x_validated",
            artifact_path="data/processed/x_validated.json",
            required_fields=("token_address",),
            optional_fields=("x_status", "x_validation_score", "x_validation_confidence", "x_validation_reason", "x_mentions_count"),
            description="Minimal X-validation contract.",
        ),
        ArtifactContract(
            contract_group="core_enriched",
            artifact_name="enriched_tokens",
            artifact_path="data/processed/enriched_tokens.json",
            required_fields=("token_address", "enrichment_status", "contract_version", "enriched_at"),
            optional_fields=("top20_holder_share", "first50_holder_conc_est", "holder_entropy_est", "smart_wallet_hits", "dev_sell_pressure_5m"),
            description="Core on-chain enrichment contract.",
        ),
        ArtifactContract(
            contract_group="bundle_cluster",
            artifact_name="enriched_tokens",
            artifact_path="data/processed/enriched_tokens.json",
            required_fields=tuple(BUNDLE_CONTRACT_FIELDS),
            optional_fields=(),
            description="Raw bundle and cluster metric fields carried on enriched-token rows.",
        ),
        ArtifactContract(
            contract_group="bundle_provenance",
            artifact_name="enriched_tokens",
            artifact_path="data/processed/enriched_tokens.json",
            required_fields=tuple(BUNDLE_PROVENANCE_FIELDS),
            optional_fields=(),
            description="Bundle evidence provenance/status/confidence fields.",
        ),
        ArtifactContract(
            contract_group="cluster_provenance",
            artifact_name="enriched_tokens",
            artifact_path="data/processed/enriched_tokens.json",
            required_fields=tuple(CLUSTER_PROVENANCE_FIELDS),
            optional_fields=(),
            description="Graph-backed cluster evidence provenance and coverage fields.",
        ),
        ArtifactContract(
            contract_group="linkage_evidence",
            artifact_name="enriched_tokens",
            artifact_path="data/processed/enriched_tokens.json",
            required_fields=tuple(LINKAGE_CONTRACT_FIELDS),
            optional_fields=(),
            description="Creator/dev/funder linkage evidence fields.",
        ),
        ArtifactContract(
            contract_group="continuation",
            artifact_name="enriched_tokens",
            artifact_path="data/processed/enriched_tokens.json",
            required_fields=tuple(SHORT_HORIZON_SIGNAL_FIELDS + CONTINUATION_METADATA_FIELDS),
            optional_fields=("wallet_registry_status",),
            description="Short-horizon and continuation provenance fields.",
        ),
        ArtifactContract(
            contract_group="core_rug_assessed",
            artifact_name="rug_assessed_tokens",
            artifact_path="data/processed/rug_assessed_tokens.json",
            required_fields=("token_address", "rug_score", "rug_status"),
            optional_fields=("rug_flags", "rug_warnings", "lp_burn_confirmed", "lp_locked_flag"),
            description="Rug engine output contract.",
        ),
        ArtifactContract(
            contract_group="core_scored",
            artifact_name="scored_tokens",
            artifact_path="data/processed/scored_tokens.json",
            required_fields=tuple(sorted(SCORED_REQUIRED_FIELDS)),
            optional_fields=("score_flags", "score_warnings"),
            description="Unified scoring output contract.",
        ),
        ArtifactContract(
            contract_group="core_entry_candidates",
            artifact_name="entry_candidates",
            artifact_path="data/processed/entry_candidates.json",
            required_fields=tuple(sorted(ENTRY_REQUIRED_FIELDS)),
            optional_fields=("entry_flags",),
            description="Entry selector output contract.",
        ),
        ArtifactContract(
            contract_group="replay_feature_matrix",
            artifact_name="trade_feature_matrix",
            artifact_path="trade_feature_matrix.jsonl",
            required_fields=tuple(sorted(REPLAY_REQUIRED_FIELDS)),
            optional_fields=replay_optional,
            description="Optional replay/analyzer feature matrix contract.",
        ),
        ArtifactContract(
            contract_group="post_run_summary",
            artifact_name="post_run_summary",
            artifact_path="data/processed/post_run_summary.json",
            required_fields=("as_of", "contract_version", "warnings"),
            optional_fields=("matrix_analysis_available", "matrix_row_count", "trade_feature_matrix_path", "friction_summary"),
            selector=None,
            description="Analyzer summary artifact contract.",
        ),
        ArtifactContract(
            contract_group="post_run_recommendations",
            artifact_name="post_run_recommendations",
            artifact_path="data/processed/post_run_recommendations.json",
            required_fields=("contract_version", "recommendations"),
            optional_fields=(),
            selector=None,
            description="Analyzer recommendation artifact contract.",
        ),
    ]


def collect_artifact_field_presence(
    repo_root: Path | str,
    artifact_path: str,
    *,
    selector: str | None = None,
) -> dict[str, Any]:
    root = Path(repo_root).expanduser().resolve()
    target = (root / artifact_path).resolve()
    try:
        relative_path = target.relative_to(root)
    except ValueError:
        relative_path = target

    result: dict[str, Any] = {
        "artifact_path": str(relative_path),
        "exists": target.exists(),
        "status": "ok",
        "structure": "unknown",
        "row_count": 0,
        "present_fields": [],
        "present_any_fields": [],
        "parse_error": "",
        "rows": [],
    }
    if not target.exists():
        result["status"] = "missing"
        result["structure"] = "missing"
        return result

    try:
        if target.suffix == ".jsonl":
            payload = _load_jsonl(target)
            result["structure"] = "jsonl"
        else:
            payload = _load_json(target)
            result["structure"] = "json"
    except Exception as exc:  # pragma: no cover - exercised via tests
        result["status"] = "malformed"
        result["structure"] = "malformed"
        result["parse_error"] = f"{type(exc).__name__}: {exc}"
        return result

    rows = _extract_rows(payload, selector)
    result["rows"] = rows
    result["row_count"] = len(rows)
    if not rows:
        result["status"] = "empty"
        return result

    key_sets = [set(row.keys()) for row in rows]
    present_all = set.intersection(*key_sets) if key_sets else set()
    present_any = set.union(*key_sets) if key_sets else set()
    result["present_fields"] = _as_sorted_strings(present_all)
    result["present_any_fields"] = _as_sorted_strings(present_any)
    return result


def _apply_docs_sync_notes(
    entry: dict[str, Any],
    docs_sync: dict[str, Any] | None,
) -> None:
    if not docs_sync:
        entry["docs_sync_notes"] = []
        return

    notes: list[str] = []
    basename = Path(entry["artifact_path"]).name
    if basename in docs_sync.get("missing_artifacts_in_readme", []):
        notes.append(f"README is missing artifact reference: {basename}")
    if basename in docs_sync.get("missing_artifacts_in_contracts_doc", []):
        notes.append(f"docs/contracts.md is missing artifact reference: {basename}")
    entry["docs_sync_notes"] = notes


def compute_contract_parity_report(
    repo_root: Path | str,
    *,
    contract_definitions: list[ArtifactContract] | None = None,
    include_docs_sync: bool = False,
) -> dict[str, Any]:
    repo_root = Path(repo_root).expanduser().resolve()
    definitions = contract_definitions or collect_contract_definitions()
    events: list[dict[str, Any]] = [{
        "event": "contract_parity_started",
        "ts": _utc_now_iso(),
        "repo_root": str(repo_root),
        "contract_groups": len(definitions),
    }]

    docs_sync: dict[str, Any] | None = None
    if include_docs_sync:
        from tools.docs_sync_audit import audit_docs_sync

        docs_sync = audit_docs_sync(repo_root, contract_definitions=definitions)
        events.append(
            {
                "event": "docs_sync_checked",
                "ts": _utc_now_iso(),
                "status": docs_sync.get("status", "unknown"),
                "missing_in_readme": len(docs_sync.get("missing_artifacts_in_readme", [])),
                "missing_in_contracts_doc": len(docs_sync.get("missing_artifacts_in_contracts_doc", [])),
            }
        )

    allowed_fields_by_artifact: dict[str, set[str]] = {}
    for definition in definitions:
        allowed_fields_by_artifact.setdefault(definition.artifact_path, set()).update(definition.required_fields)
        allowed_fields_by_artifact.setdefault(definition.artifact_path, set()).update(definition.optional_fields)

    contract_groups: list[dict[str, Any]] = []
    for definition in definitions:
        presence = collect_artifact_field_presence(repo_root, definition.artifact_path, selector=definition.selector)
        present_all = set(presence.get("present_fields", []))
        present_any = set(presence.get("present_any_fields", []))
        required = set(definition.required_fields)
        optional = set(definition.optional_fields)
        allowed_for_artifact = allowed_fields_by_artifact.get(definition.artifact_path, required | optional)
        missing_required = _as_sorted_strings(required - present_all)
        missing_optional = _as_sorted_strings(optional - present_any)
        extras = _as_sorted_strings(present_any - allowed_for_artifact)

        if presence["status"] in {"missing", "malformed", "empty"}:
            status = presence["status"]
        elif missing_required:
            status = "mismatch"
        elif extras:
            status = "warning"
        else:
            status = "ok"

        warnings: list[str] = []
        if presence["status"] == "missing":
            warnings.append("artifact_missing")
            events.append(
                {
                    "event": "artifact_missing",
                    "ts": _utc_now_iso(),
                    "contract_group": definition.contract_group,
                    "artifact_name": definition.artifact_name,
                    "artifact_path": definition.artifact_path,
                }
            )
        if presence["status"] == "malformed":
            warnings.append("artifact_malformed")
            events.append(
                {
                    "event": "artifact_malformed",
                    "ts": _utc_now_iso(),
                    "contract_group": definition.contract_group,
                    "artifact_name": definition.artifact_name,
                    "artifact_path": definition.artifact_path,
                    "parse_error": presence.get("parse_error", ""),
                }
            )
        if missing_required:
            warnings.append("required_fields_missing")
            events.append(
                {
                    "event": "required_fields_missing",
                    "ts": _utc_now_iso(),
                    "contract_group": definition.contract_group,
                    "artifact_name": definition.artifact_name,
                    "missing_field_count": len(missing_required),
                    "missing_fields": missing_required,
                }
            )
        if extras:
            warnings.append("extra_fields_detected")
            events.append(
                {
                    "event": "extra_fields_detected",
                    "ts": _utc_now_iso(),
                    "contract_group": definition.contract_group,
                    "artifact_name": definition.artifact_name,
                    "extra_field_count": len(extras),
                    "extra_fields": extras,
                }
            )

        entry = {
            "contract_group": definition.contract_group,
            "artifact_name": definition.artifact_name,
            "artifact_path": definition.artifact_path,
            "description": definition.description,
            "required_fields": _as_sorted_strings(definition.required_fields),
            "optional_fields": _as_sorted_strings(definition.optional_fields),
            "present_fields": _as_sorted_strings(present_all),
            "present_any_fields": _as_sorted_strings(present_any),
            "missing_required_fields": missing_required,
            "missing_optional_fields": missing_optional,
            "extra_fields": extras,
            "row_count": presence.get("row_count", 0),
            "status": status,
            "warnings": _as_sorted_strings(warnings),
        }
        _apply_docs_sync_notes(entry, docs_sync)
        contract_groups.append(entry)
        events.append(
            {
                "event": "contract_group_checked",
                "ts": _utc_now_iso(),
                "contract_group": definition.contract_group,
                "artifact_name": definition.artifact_name,
                "status": status,
                "required_field_count": len(definition.required_fields),
                "missing_required_field_count": len(missing_required),
                "extra_field_count": len(extras),
            }
        )

    overall_status = "ok"
    for entry in contract_groups:
        if STATUS_SEVERITY[entry["status"]] > STATUS_SEVERITY[overall_status]:
            overall_status = entry["status"]

    summary = {
        "overall_status": overall_status,
        "contract_groups_checked": len(contract_groups),
        "artifacts_checked": len(contract_groups),
        "ok_count": len([entry for entry in contract_groups if entry["status"] == "ok"]),
        "warning_count": len([entry for entry in contract_groups if entry["status"] == "warning"]),
        "mismatch_count": len([entry for entry in contract_groups if entry["status"] == "mismatch"]),
        "missing_count": len([entry for entry in contract_groups if entry["status"] == "missing"]),
        "malformed_count": len([entry for entry in contract_groups if entry["status"] == "malformed"]),
        "empty_count": len([entry for entry in contract_groups if entry["status"] == "empty"]),
        "events_emitted": len(events),
    }
    events.append(
        {
            "event": "contract_parity_completed",
            "ts": _utc_now_iso(),
            "overall_status": overall_status,
            "mismatch_count": summary["mismatch_count"],
            "missing_count": summary["missing_count"],
            "malformed_count": summary["malformed_count"],
        }
    )

    return {
        "metadata": {
            "tool_version": "contract_parity_v1",
            "generated_at": _utc_now_iso(),
            "repo_root": str(repo_root),
        },
        "summary": summary,
        "contract_groups": contract_groups,
        "docs_sync": docs_sync or {},
        "events": events,
    }


def validate_required_contracts(report: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    for entry in report.get("contract_groups", []):
        if entry.get("status") in {"mismatch", "missing", "malformed", "empty"}:
            failures.append(
                f"{entry.get('contract_group')}:{entry.get('artifact_name')}={entry.get('status')}"
            )
    return failures
