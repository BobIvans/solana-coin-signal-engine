"""Rule evaluators for deterministic exit decisions."""

from __future__ import annotations

from typing import Any


_SELL_HEAVY_COMPOSITIONS = {"sell-heavy", "sell_only", "sell-only", "distribution", "dump", "mixed_sell_bias"}


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _to_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "t", "yes", "y", "on"}:
            return True
        if normalized in {"0", "false", "f", "no", "n", "off"}:
            return False
    return bool(value)


def _text(value: Any) -> str:
    return str(value or "").strip().lower()


def _partial_taken(position_ctx: dict[str, Any], idx: int) -> bool:
    explicit = bool(position_ctx.get(f"partial_{idx}_taken"))
    partials_taken = position_ctx.get("partials_taken") or []
    if isinstance(partials_taken, list):
        if idx in partials_taken:
            return True
        if f"partial_{idx}" in partials_taken:
            return True
    return explicit


def _hold(reason: str = "hold_conditions_intact", *, warnings: list[str] | None = None) -> dict[str, Any]:
    return {
        "exit_decision": "HOLD",
        "exit_fraction": 0.0,
        "exit_reason": reason,
        "exit_flags": [],
        "exit_warnings": warnings or [],
    }


def _full(reason: str, flags: list[str], *, warnings: list[str] | None = None) -> dict[str, Any]:
    return {
        "exit_decision": "FULL_EXIT",
        "exit_fraction": 1.0,
        "exit_reason": reason,
        "exit_flags": flags,
        "exit_warnings": warnings or [],
    }


def _current_or_entry(position_ctx: dict[str, Any], current_ctx: dict[str, Any], *keys: str) -> Any:
    entry_snapshot = dict(position_ctx.get("entry_snapshot") or {})
    for key in keys:
        if key in current_ctx and current_ctx.get(key) is not None:
            return current_ctx.get(key)
    for key in keys:
        if key in entry_snapshot and entry_snapshot.get(key) is not None:
            return entry_snapshot.get(key)
    return None


def _wallet_netflow_bias(current_ctx: dict[str, Any]) -> float:
    wallet_features = current_ctx.get("wallet_features") or {}
    return _to_float(wallet_features.get("smart_wallet_netflow_bias"))


def _setting(settings: Any, name: str, default: Any) -> Any:
    return getattr(settings, name, default)


def _is_sell_heavy_composition(value: Any) -> bool:
    composition = _text(value).replace('_', '-')
    return composition in _SELL_HEAVY_COMPOSITIONS


def _continuation_warning_flags(position_ctx: dict[str, Any], current_ctx: dict[str, Any]) -> list[str]:
    warnings: list[str] = []
    net_unique_buyers = _to_float(_current_or_entry(position_ctx, current_ctx, "net_unique_buyers_60s"), default=0.0)
    if _current_or_entry(position_ctx, current_ctx, "net_unique_buyers_60s") is not None and net_unique_buyers <= 0:
        warnings.append("net_unique_buyers_stalled")

    dispersion = _to_float(
        _current_or_entry(position_ctx, current_ctx, "smart_wallet_dispersion_score"),
        default=-1.0,
    )
    if dispersion >= 0 and dispersion < 0.35:
        warnings.append("smart_wallet_dispersion_narrow")

    x_velocity = _to_float(_current_or_entry(position_ctx, current_ctx, "x_author_velocity_5m"), default=-1.0)
    if x_velocity >= 0 and x_velocity < 0.2:
        warnings.append("x_author_velocity_cooling")

    return warnings


def detect_cluster_dump(position_ctx: dict[str, Any], current_ctx: dict[str, Any], settings: Any) -> dict[str, Any]:
    sell_concentration = _to_float(_current_or_entry(position_ctx, current_ctx, "cluster_sell_concentration_120s"), default=-1.0)
    concentration_ratio = _to_float(
        _current_or_entry(position_ctx, current_ctx, "cluster_concentration_ratio_now", "cluster_concentration_ratio")
    )
    buy_pressure = _to_float(current_ctx.get("buy_pressure_now", current_ctx.get("buy_pressure")), default=1.0)
    dominant_composition = _current_or_entry(position_ctx, current_ctx, "bundle_composition_dominant_now", "bundle_composition_dominant")
    netflow_bias = _wallet_netflow_bias(current_ctx)

    if sell_concentration < 0:
        return {"severity": "none", "flags": [], "warnings": []}

    warn_threshold = float(settings.EXIT_CLUSTER_CONCENTRATION_SELL_THRESHOLD)
    hard_threshold = float(settings.EXIT_CLUSTER_DUMP_HARD)
    suspicious_distribution = _is_sell_heavy_composition(dominant_composition)
    concentrated_cluster = concentration_ratio >= warn_threshold
    momentum_breakdown = buy_pressure < float(settings.EXIT_TREND_BUY_PRESSURE_FLOOR)
    negative_netflow = netflow_bias < 0

    if sell_concentration >= hard_threshold and (concentrated_cluster or suspicious_distribution or negative_netflow or momentum_breakdown):
        return {
            "severity": "hard",
            "flags": ["cluster_dump_detected", "cluster_sell_concentration_spike"],
            "warnings": [],
        }

    if sell_concentration >= warn_threshold and concentrated_cluster and (suspicious_distribution or negative_netflow or momentum_breakdown):
        return {
            "severity": "exit",
            "flags": ["cluster_dump_detected"],
            "warnings": [],
        }

    if sell_concentration >= warn_threshold and (concentrated_cluster or suspicious_distribution):
        return {
            "severity": "warn",
            "flags": [],
            "warnings": ["cluster_dump_detected"],
        }

    return {"severity": "none", "flags": [], "warnings": []}


def detect_cluster_distribution_exit(position_ctx: dict[str, Any], current_ctx: dict[str, Any], settings: Any) -> dict[str, Any]:
    sell_concentration = _to_float(
        _current_or_entry(position_ctx, current_ctx, "cluster_sell_concentration_120s"),
        default=-1.0,
    )
    if sell_concentration < 0:
        return {"severity": "none", "flags": [], "warnings": []}

    warn_threshold = float(
        _setting(settings, "EXIT_CLUSTER_SELL_CONCENTRATION_WARN", getattr(settings, "EXIT_CLUSTER_CONCENTRATION_SELL_THRESHOLD", 0.65))
    )
    hard_threshold = float(
        _setting(settings, "EXIT_CLUSTER_SELL_CONCENTRATION_HARD", getattr(settings, "EXIT_CLUSTER_DUMP_HARD", 0.82))
    )
    liquidity_refill = _to_float(_current_or_entry(position_ctx, current_ctx, "liquidity_refill_ratio_120s"), default=-1.0)
    shock_recovery_sec = _to_float(_current_or_entry(position_ctx, current_ctx, "liquidity_shock_recovery_sec"), default=-1.0)
    concentration_ratio = _to_float(
        _current_or_entry(position_ctx, current_ctx, "cluster_concentration_ratio_now", "cluster_concentration_ratio")
    )
    buy_pressure = _to_float(current_ctx.get("buy_pressure_now", current_ctx.get("buy_pressure")), default=1.0)
    suspicious_distribution = _is_sell_heavy_composition(
        _current_or_entry(position_ctx, current_ctx, "bundle_composition_dominant_now", "bundle_composition_dominant")
    )
    confirmations = 0
    if concentration_ratio >= warn_threshold:
        confirmations += 1
    if liquidity_refill >= 0 and liquidity_refill < float(_setting(settings, "EXIT_LIQUIDITY_REFILL_FAIL_MIN", 0.85)):
        confirmations += 1
    if shock_recovery_sec >= float(_setting(settings, "EXIT_SHOCK_RECOVERY_TOO_SLOW_SEC", 180)):
        confirmations += 1
    if suspicious_distribution:
        confirmations += 1
    if buy_pressure < float(settings.EXIT_TREND_BUY_PRESSURE_FLOOR):
        confirmations += 1
    if _wallet_netflow_bias(current_ctx) < 0:
        confirmations += 1

    secondary_warnings = _continuation_warning_flags(position_ctx, current_ctx)
    if sell_concentration >= hard_threshold and confirmations >= 1:
        return {
            "severity": "exit",
            "flags": ["cluster_distribution_detected", "cluster_sell_concentration_spike"],
            "warnings": secondary_warnings,
        }

    if sell_concentration >= warn_threshold and confirmations >= 1:
        return {
            "severity": "warn",
            "flags": [],
            "warnings": ["cluster_distribution_detected", *secondary_warnings],
        }

    return {"severity": "none", "flags": [], "warnings": []}


def detect_failed_liquidity_refill(position_ctx: dict[str, Any], current_ctx: dict[str, Any], settings: Any) -> dict[str, Any]:
    refill_ratio = _to_float(_current_or_entry(position_ctx, current_ctx, "liquidity_refill_ratio_120s"), default=-1.0)
    if refill_ratio < 0:
        return {"severity": "none", "flags": [], "warnings": []}

    fail_min = float(_setting(settings, "EXIT_LIQUIDITY_REFILL_FAIL_MIN", 0.85))
    severe_min = fail_min * 0.75
    shock_recovery_sec = _to_float(_current_or_entry(position_ctx, current_ctx, "liquidity_shock_recovery_sec"), default=-1.0)
    seller_reentry = _to_float(_current_or_entry(position_ctx, current_ctx, "seller_reentry_ratio"), default=-1.0)
    buy_pressure = _to_float(current_ctx.get("buy_pressure_now", current_ctx.get("buy_pressure")), default=1.0)

    confirmations = 0
    if shock_recovery_sec >= float(_setting(settings, "EXIT_SHOCK_RECOVERY_TOO_SLOW_SEC", 180)):
        confirmations += 1
    if seller_reentry >= 0 and seller_reentry <= float(_setting(settings, "EXIT_SELLER_REENTRY_WEAK_MAX", 0.2)):
        confirmations += 1
    if buy_pressure < float(settings.EXIT_TREND_BUY_PRESSURE_FLOOR):
        confirmations += 1

    secondary_warnings = _continuation_warning_flags(position_ctx, current_ctx)
    if refill_ratio <= severe_min and confirmations >= 1:
        return {
            "severity": "exit",
            "flags": ["failed_liquidity_refill_detected"],
            "warnings": secondary_warnings,
        }

    if refill_ratio < fail_min:
        return {
            "severity": "warn",
            "flags": [],
            "warnings": ["failed_liquidity_refill_detected", *secondary_warnings],
        }

    return {"severity": "none", "flags": [], "warnings": []}


def detect_weak_reentry_exit(position_ctx: dict[str, Any], current_ctx: dict[str, Any], settings: Any) -> dict[str, Any]:
    reentry_ratio = _to_float(_current_or_entry(position_ctx, current_ctx, "seller_reentry_ratio"), default=-1.0)
    if reentry_ratio < 0:
        return {"severity": "none", "flags": [], "warnings": []}

    weak_max = float(_setting(settings, "EXIT_SELLER_REENTRY_WEAK_MAX", 0.2))
    severe_max = weak_max * 0.5
    refill_ratio = _to_float(_current_or_entry(position_ctx, current_ctx, "liquidity_refill_ratio_120s"), default=-1.0)
    shock_recovery_sec = _to_float(_current_or_entry(position_ctx, current_ctx, "liquidity_shock_recovery_sec"), default=-1.0)
    secondary_warnings = _continuation_warning_flags(position_ctx, current_ctx)

    paired_weakness = 0
    if refill_ratio >= 0 and refill_ratio < float(_setting(settings, "EXIT_LIQUIDITY_REFILL_FAIL_MIN", 0.85)):
        paired_weakness += 1
    if shock_recovery_sec >= float(_setting(settings, "EXIT_SHOCK_RECOVERY_TOO_SLOW_SEC", 180)):
        paired_weakness += 1
    if _to_float(
        _current_or_entry(position_ctx, current_ctx, "cluster_sell_concentration_120s"),
        default=0.0,
    ) >= float(_setting(settings, "EXIT_CLUSTER_SELL_CONCENTRATION_WARN", getattr(settings, "EXIT_CLUSTER_CONCENTRATION_SELL_THRESHOLD", 0.65))):
        paired_weakness += 1

    if reentry_ratio <= severe_max and paired_weakness >= 1:
        return {
            "severity": "exit",
            "flags": ["weak_reentry_detected"],
            "warnings": secondary_warnings,
        }

    if reentry_ratio <= weak_max:
        return {
            "severity": "warn",
            "flags": [],
            "warnings": ["weak_reentry_detected", *secondary_warnings],
        }

    return {"severity": "none", "flags": [], "warnings": []}


def detect_shock_not_recovered_exit(position_ctx: dict[str, Any], current_ctx: dict[str, Any], settings: Any) -> dict[str, Any]:
    recovery_sec = _to_float(_current_or_entry(position_ctx, current_ctx, "liquidity_shock_recovery_sec"), default=-1.0)
    if recovery_sec < 0:
        return {"severity": "none", "flags": [], "warnings": []}

    too_slow_sec = float(_setting(settings, "EXIT_SHOCK_RECOVERY_TOO_SLOW_SEC", 180))
    severe_sec = too_slow_sec * 1.5
    refill_ratio = _to_float(_current_or_entry(position_ctx, current_ctx, "liquidity_refill_ratio_120s"), default=-1.0)
    sell_concentration = _to_float(_current_or_entry(position_ctx, current_ctx, "cluster_sell_concentration_120s"), default=-1.0)
    secondary_warnings = _continuation_warning_flags(position_ctx, current_ctx)

    confirmations = 0
    if refill_ratio >= 0 and refill_ratio < float(_setting(settings, "EXIT_LIQUIDITY_REFILL_FAIL_MIN", 0.85)):
        confirmations += 1
    if sell_concentration >= float(_setting(settings, "EXIT_CLUSTER_SELL_CONCENTRATION_WARN", getattr(settings, "EXIT_CLUSTER_CONCENTRATION_SELL_THRESHOLD", 0.65))):
        confirmations += 1

    if recovery_sec >= severe_sec and confirmations >= 1:
        return {
            "severity": "exit",
            "flags": ["shock_not_recovered_detected"],
            "warnings": secondary_warnings,
        }

    if recovery_sec >= too_slow_sec:
        return {
            "severity": "warn",
            "flags": [],
            "warnings": ["shock_not_recovered_detected", *secondary_warnings],
        }

    return {"severity": "none", "flags": [], "warnings": []}


def detect_bundle_failure_spike(position_ctx: dict[str, Any], current_ctx: dict[str, Any], settings: Any) -> dict[str, Any]:
    pattern_now = _to_float(
        _current_or_entry(position_ctx, current_ctx, "bundle_failure_retry_pattern_now", "bundle_failure_retry_pattern"),
        default=-1.0,
    )
    retry_delta = _to_float(current_ctx.get("bundle_failure_retry_delta"), default=0.0)
    correlation = _to_float(
        _current_or_entry(position_ctx, current_ctx, "cross_block_bundle_correlation_now", "cross_block_bundle_correlation")
    )
    dominant_composition = _current_or_entry(position_ctx, current_ctx, "bundle_composition_dominant_now", "bundle_composition_dominant")

    if pattern_now < 0 and "bundle_failure_retry_delta" not in current_ctx:
        return {"severity": "none", "flags": [], "warnings": []}

    threshold = float(settings.EXIT_BUNDLE_FAILURE_SPIKE_THRESHOLD)
    severe_pattern = pattern_now >= threshold * 2 if pattern_now >= 0 else False
    severe_delta = retry_delta >= threshold * 2
    suspicious_distribution = _is_sell_heavy_composition(dominant_composition)
    synchronized_failures = correlation >= 0.7

    if severe_delta or (severe_pattern and (synchronized_failures or suspicious_distribution)):
        return {
            "severity": "exit",
            "flags": ["bundle_failure_spike"],
            "warnings": [],
        }

    if retry_delta >= threshold or pattern_now >= threshold:
        return {
            "severity": "warn",
            "flags": [],
            "warnings": ["bundle_failure_spike"],
        }

    return {"severity": "none", "flags": [], "warnings": []}


def detect_retry_manipulation(position_ctx: dict[str, Any], current_ctx: dict[str, Any], settings: Any) -> dict[str, Any]:
    pattern_now = _to_float(
        _current_or_entry(position_ctx, current_ctx, "bundle_failure_retry_pattern_now", "bundle_failure_retry_pattern"),
        default=-1.0,
    )
    retry_delta = _to_float(current_ctx.get("bundle_failure_retry_delta"), default=0.0)
    correlation = _to_float(
        _current_or_entry(position_ctx, current_ctx, "cross_block_bundle_correlation_now", "cross_block_bundle_correlation")
    )
    dominant_composition = _current_or_entry(position_ctx, current_ctx, "bundle_composition_dominant_now", "bundle_composition_dominant")
    buy_pressure = _to_float(current_ctx.get("buy_pressure_now", current_ctx.get("buy_pressure")), default=1.0)
    netflow_bias = _wallet_netflow_bias(current_ctx)

    if pattern_now < 0:
        return {"severity": "none", "flags": [], "warnings": []}

    threshold = float(settings.EXIT_RETRY_MANIPULATION_HARD)
    suspicious_distribution = _is_sell_heavy_composition(dominant_composition)
    negative_netflow = netflow_bias < 0
    weak_buy_pressure = buy_pressure < float(settings.EXIT_SCALP_BUY_PRESSURE_FLOOR)
    synchronized_retries = correlation >= 0.8

    if pattern_now >= threshold and (retry_delta >= float(settings.EXIT_BUNDLE_FAILURE_SPIKE_THRESHOLD) or synchronized_retries) and (suspicious_distribution or negative_netflow or weak_buy_pressure):
        return {
            "severity": "hard",
            "flags": ["retry_manipulation_flag", "retry_manipulation_detected"],
            "warnings": [],
        }

    if pattern_now >= threshold * 0.75 and (retry_delta > 0 or synchronized_retries):
        return {
            "severity": "warn",
            "flags": [],
            "warnings": ["retry_manipulation_flag"],
        }

    return {"severity": "none", "flags": [], "warnings": []}


def detect_creator_cluster_exit_risk(position_ctx: dict[str, Any], current_ctx: dict[str, Any], settings: Any) -> dict[str, Any]:
    creator_flag = _to_bool(
        _current_or_entry(position_ctx, current_ctx, "creator_in_cluster_flag_now", "creator_in_cluster_flag"),
        default=False,
    )
    creator_activity = _to_float(current_ctx.get("creator_cluster_activity_now"), default=-1.0)
    concentration_ratio = _to_float(
        _current_or_entry(position_ctx, current_ctx, "cluster_concentration_ratio_now", "cluster_concentration_ratio")
    )
    correlation = _to_float(
        _current_or_entry(position_ctx, current_ctx, "cross_block_bundle_correlation_now", "cross_block_bundle_correlation")
    )
    dominant_composition = _current_or_entry(position_ctx, current_ctx, "bundle_composition_dominant_now", "bundle_composition_dominant")
    netflow_bias = _wallet_netflow_bias(current_ctx)

    if not creator_flag or creator_activity < 0:
        return {"severity": "none", "flags": [], "warnings": []}

    threshold = float(settings.EXIT_CREATOR_CLUSTER_RISK_HARD)
    suspicious_distribution = _is_sell_heavy_composition(dominant_composition)
    concentrated_cluster = concentration_ratio >= float(settings.EXIT_CLUSTER_CONCENTRATION_SELL_THRESHOLD)
    negative_netflow = netflow_bias < 0

    if creator_activity >= threshold and (concentrated_cluster or correlation >= 0.7 or suspicious_distribution) and negative_netflow:
        return {
            "severity": "hard",
            "flags": ["creator_cluster_exit_risk", "creator_cluster_activity_elevated"],
            "warnings": [],
        }

    if creator_activity >= threshold and (concentrated_cluster or correlation >= 0.7 or suspicious_distribution):
        return {
            "severity": "exit",
            "flags": ["creator_cluster_exit_risk"],
            "warnings": [],
        }

    if creator_activity >= threshold * 0.75 and (concentrated_cluster or correlation >= 0.5):
        return {
            "severity": "warn",
            "flags": [],
            "warnings": ["creator_cluster_exit_risk"],
        }

    return {"severity": "none", "flags": [], "warnings": []}


def evaluate_hard_exit(position_ctx: dict, current_ctx: dict, settings: Any) -> dict:
    dev_sell = _to_float(current_ctx.get("dev_sell_pressure_now", current_ctx.get("dev_sell_pressure_5m")))
    if bool(settings.EXIT_DEV_SELL_HARD) and dev_sell > 0:
        return _full("dev_sell_detected", ["dev_sell_detected"])

    if bool(settings.EXIT_RUG_FLAG_HARD) and bool(current_ctx.get("rug_flag_now")):
        return _full("rug_flag_triggered", ["rug_flag_detected"])

    cluster_dump = detect_cluster_dump(position_ctx, current_ctx, settings)
    if cluster_dump["severity"] == "hard":
        return _full("cluster_dump_detected", cluster_dump["flags"])

    retry_manipulation = detect_retry_manipulation(position_ctx, current_ctx, settings)
    if retry_manipulation["severity"] == "hard":
        return _full("retry_manipulation_detected", retry_manipulation["flags"])

    creator_risk = detect_creator_cluster_exit_risk(position_ctx, current_ctx, settings)
    if creator_risk["severity"] == "hard":
        return _full("creator_cluster_exit_risk", creator_risk["flags"])

    return _hold()


def evaluate_scalp_exit(position_ctx: dict, current_ctx: dict, settings: Any) -> dict:
    hold_sec = int(current_ctx.get("hold_sec", 0))
    pnl_pct = _to_float(current_ctx.get("pnl_pct"))
    liquidity_drop_pct = _to_float(current_ctx.get("liquidity_drop_pct"))
    cluster_dump = detect_cluster_dump(position_ctx, current_ctx, settings)
    cluster_distribution = detect_cluster_distribution_exit(position_ctx, current_ctx, settings)
    failed_refill = detect_failed_liquidity_refill(position_ctx, current_ctx, settings)
    weak_reentry = detect_weak_reentry_exit(position_ctx, current_ctx, settings)
    shock_recovery = detect_shock_not_recovered_exit(position_ctx, current_ctx, settings)
    bundle_failure = detect_bundle_failure_spike(position_ctx, current_ctx, settings)
    retry_manipulation = detect_retry_manipulation(position_ctx, current_ctx, settings)
    creator_risk = detect_creator_cluster_exit_risk(position_ctx, current_ctx, settings)
    warnings = [
        *cluster_dump["warnings"],
        *cluster_distribution["warnings"],
        *failed_refill["warnings"],
        *weak_reentry["warnings"],
        *shock_recovery["warnings"],
        *bundle_failure["warnings"],
        *retry_manipulation["warnings"],
        *creator_risk["warnings"],
    ]

    if cluster_dump["severity"] in {"hard", "exit"}:
        return _full("cluster_dump_detected", ["cluster_dump_detected", *cluster_dump["flags"]], warnings=warnings)

    if cluster_distribution["severity"] == "exit" and failed_refill["severity"] == "exit":
        return _full(
            "cluster_distribution_exit",
            ["cluster_distribution_detected", *cluster_distribution["flags"], *failed_refill["flags"]],
            warnings=warnings,
        )

    if shock_recovery["severity"] == "exit" and failed_refill["severity"] == "exit":
        return _full(
            "shock_not_recovered_exit",
            ["shock_not_recovered_detected", *shock_recovery["flags"], *failed_refill["flags"]],
            warnings=warnings,
        )

    if retry_manipulation["severity"] == "hard":
        return _full("retry_manipulation_detected", retry_manipulation["flags"], warnings=warnings)

    if creator_risk["severity"] == "exit":
        return _full("creator_cluster_exit_risk", creator_risk["flags"], warnings=warnings)

    if bundle_failure["severity"] == "exit" and (pnl_pct <= 0 or hold_sec >= int(settings.EXIT_SCALP_RECHECK_SEC)):
        return _full("bundle_failure_spike", bundle_failure["flags"], warnings=warnings)

    if pnl_pct <= float(settings.EXIT_SCALP_STOP_LOSS_PCT):
        return _full("scalp_stop_loss", ["stop_loss_triggered"], warnings=warnings)

    if liquidity_drop_pct >= float(settings.EXIT_SCALP_LIQUIDITY_DROP_PCT):
        return _full("trend_liquidity_breakdown", ["liquidity_breakdown_triggered"], warnings=warnings)

    if hold_sec >= int(settings.EXIT_SCALP_MAX_HOLD_SEC):
        return _full("scalp_max_hold_timeout", ["max_hold_timeout"], warnings=warnings)

    if hold_sec >= int(settings.EXIT_SCALP_RECHECK_SEC) and pnl_pct > 0:
        flags: list[str] = []
        entry_snapshot = dict(position_ctx.get("entry_snapshot") or {})

        entry_volume = _to_float(entry_snapshot.get("volume_velocity"))
        now_volume = _to_float(current_ctx.get("volume_velocity_now", current_ctx.get("volume_velocity")))
        if entry_volume > 0 and now_volume < entry_volume * float(settings.EXIT_SCALP_VOLUME_VELOCITY_DECAY):
            flags.append("volume_velocity_decay")

        entry_x_score = _to_float(entry_snapshot.get("x_validation_score"))
        now_x_score = _to_float(current_ctx.get("x_validation_score_now", current_ctx.get("x_validation_score")))
        if entry_x_score > 0 and now_x_score < entry_x_score * float(settings.EXIT_SCALP_X_SCORE_DECAY):
            flags.append("x_score_decay")

        now_buy_pressure = _to_float(current_ctx.get("buy_pressure_now", current_ctx.get("buy_pressure")))
        if now_buy_pressure < float(settings.EXIT_SCALP_BUY_PRESSURE_FLOOR):
            flags.append("buy_pressure_below_floor")

        bundle_delta = _to_float(current_ctx.get("bundle_cluster_delta"))
        if bundle_delta < 0:
            flags.append("bundle_cluster_negative_delta")

        if bundle_failure["severity"] == "exit":
            flags.extend(bundle_failure["flags"])
        if retry_manipulation["severity"] == "warn" and flags:
            flags.append("retry_manipulation_flag")

        if flags:
            if "cluster_dump_detected" in flags:
                reason = "cluster_dump_detected"
            elif "bundle_failure_spike" in flags:
                reason = "bundle_failure_spike"
            elif "volume_velocity_decay" in flags:
                reason = "scalp_momentum_decay_after_recheck"
            elif "x_score_decay" in flags:
                reason = "scalp_x_validation_collapse"
            elif "buy_pressure_below_floor" in flags:
                reason = "scalp_buy_pressure_breakdown"
            else:
                reason = "scalp_momentum_decay_after_recheck"
            return _full(reason, flags, warnings=warnings)

    return _hold(warnings=warnings)


def evaluate_trend_exit(position_ctx: dict, current_ctx: dict, settings: Any) -> dict:
    pnl_pct = _to_float(current_ctx.get("pnl_pct"))
    buy_pressure = _to_float(current_ctx.get("buy_pressure_now", current_ctx.get("buy_pressure")))
    liquidity_drop_pct = _to_float(current_ctx.get("liquidity_drop_pct"))
    x_delta = _to_float(current_ctx.get("x_validation_score_delta"))
    cluster_dump = detect_cluster_dump(position_ctx, current_ctx, settings)
    cluster_distribution = detect_cluster_distribution_exit(position_ctx, current_ctx, settings)
    failed_refill = detect_failed_liquidity_refill(position_ctx, current_ctx, settings)
    weak_reentry = detect_weak_reentry_exit(position_ctx, current_ctx, settings)
    shock_recovery = detect_shock_not_recovered_exit(position_ctx, current_ctx, settings)
    bundle_failure = detect_bundle_failure_spike(position_ctx, current_ctx, settings)
    retry_manipulation = detect_retry_manipulation(position_ctx, current_ctx, settings)
    creator_risk = detect_creator_cluster_exit_risk(position_ctx, current_ctx, settings)
    warnings = [
        *cluster_dump["warnings"],
        *cluster_distribution["warnings"],
        *failed_refill["warnings"],
        *weak_reentry["warnings"],
        *shock_recovery["warnings"],
        *bundle_failure["warnings"],
        *retry_manipulation["warnings"],
        *creator_risk["warnings"],
    ]

    if cluster_dump["severity"] in {"hard", "exit"}:
        return _full("cluster_dump_detected", ["cluster_dump_detected", *cluster_dump["flags"]], warnings=warnings)

    if cluster_distribution["severity"] == "exit":
        return _full("cluster_distribution_exit", cluster_distribution["flags"], warnings=warnings)

    if failed_refill["severity"] == "exit" and shock_recovery["severity"] in {"exit", "warn"}:
        return _full(
            "failed_liquidity_refill_exit",
            [*failed_refill["flags"], "shock_not_recovered_detected"],
            warnings=warnings,
        )

    if shock_recovery["severity"] == "exit" and failed_refill["severity"] in {"exit", "warn"}:
        return _full(
            "shock_not_recovered_exit",
            [*shock_recovery["flags"], "failed_liquidity_refill_detected"],
            warnings=warnings,
        )

    if weak_reentry["severity"] == "exit" and (
        failed_refill["severity"] in {"exit", "warn"} or cluster_distribution["severity"] in {"exit", "warn"}
    ):
        return _full(
            "weak_reentry_exit",
            [*weak_reentry["flags"], "continuation_failure_confirmed"],
            warnings=warnings,
        )

    if creator_risk["severity"] in {"hard", "exit"}:
        return _full("creator_cluster_exit_risk", creator_risk["flags"], warnings=warnings)

    if retry_manipulation["severity"] == "hard":
        return _full("retry_manipulation_detected", retry_manipulation["flags"], warnings=warnings)

    if bundle_failure["severity"] == "exit" and (retry_manipulation["severity"] == "warn" or buy_pressure < float(settings.EXIT_TREND_BUY_PRESSURE_FLOOR) + 0.05):
        return _full("bundle_failure_spike", bundle_failure["flags"], warnings=warnings)

    if pnl_pct <= float(settings.EXIT_TREND_HARD_STOP_PCT):
        return _full("trend_hard_stop", ["stop_loss_triggered"], warnings=warnings)

    if buy_pressure < float(settings.EXIT_TREND_BUY_PRESSURE_FLOOR):
        return _full("scalp_buy_pressure_breakdown", ["buy_pressure_below_floor"], warnings=warnings)

    if liquidity_drop_pct >= float(settings.EXIT_TREND_LIQUIDITY_DROP_PCT):
        return _full("trend_liquidity_breakdown", ["liquidity_breakdown_triggered"], warnings=warnings)

    if x_delta < 0:
        entry_snapshot = dict(position_ctx.get("entry_snapshot") or {})
        entry_x = _to_float(entry_snapshot.get("x_validation_score"))
        now_x = _to_float(current_ctx.get("x_validation_score_now", current_ctx.get("x_validation_score")))
        if entry_x > 0 and now_x < entry_x * float(settings.EXIT_SCALP_X_SCORE_DECAY):
            return _full("trend_social_confirmation_collapse", ["x_score_decay"], warnings=warnings)

    if "holder_growth_now" in current_ctx and _to_float(current_ctx.get("holder_growth_now")) <= 0 and bool(current_ctx.get("holder_growth_negative_persistent")):
        return _full("trend_social_confirmation_collapse", ["holder_growth_collapse"], warnings=warnings)

    partial_1_taken = _partial_taken(position_ctx, 1)
    partial_2_taken = _partial_taken(position_ctx, 2)

    if not partial_1_taken and pnl_pct >= float(settings.EXIT_TREND_PARTIAL1_PCT):
        return {
            "exit_decision": "PARTIAL_EXIT",
            "exit_fraction": 0.33,
            "exit_reason": "trend_partial_take_profit_1",
            "exit_flags": ["partial_take_profit_1"],
            "exit_warnings": warnings,
        }

    if partial_1_taken and not partial_2_taken and pnl_pct >= float(settings.EXIT_TREND_PARTIAL2_PCT):
        return {
            "exit_decision": "PARTIAL_EXIT",
            "exit_fraction": 0.50,
            "exit_reason": "trend_partial_take_profit_2",
            "exit_flags": ["partial_take_profit_2"],
            "exit_warnings": warnings,
        }

    return _hold(warnings=warnings)
