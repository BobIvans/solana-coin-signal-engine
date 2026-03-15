"""Holder concentration metrics derived from top20 largest token accounts."""

from __future__ import annotations

import math
from typing import Any


def _to_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _safe_ratio(num: float, den: float) -> float:
    if den <= 0:
        return 0.0
    return max(0.0, min(1.0, num / den))


def compute_holder_metrics(mint: str, token_supply: dict, largest_accounts: dict) -> dict[str, Any]:
    del mint
    supply_value = token_supply.get("value", {}) if isinstance(token_supply, dict) else {}
    total_supply = _to_float(supply_value.get("uiAmount") or 0)
    raw_amount = str(supply_value.get("amount") or "0")
    decimals = int(supply_value.get("decimals") or 0)

    top_accounts = largest_accounts.get("value", []) if isinstance(largest_accounts, dict) else []
    balances = [_to_float(item.get("uiAmount") or 0) for item in top_accounts if isinstance(item, dict)]
    balances = [bal for bal in balances if bal > 0]

    top1 = balances[0] if balances else 0.0
    top20_sum = sum(balances[:20])

    tail_est = 0.0
    if len(balances) >= 2:
        slope = balances[-1] / max(balances[0], 1e-9)
        avg_tail = balances[-1] * (0.8 + 0.4 * slope)
        tail_est = max(0.0, avg_tail * 30)

    first50_est = _safe_ratio(top20_sum + tail_est, total_supply)

    p = [b / max(top20_sum + tail_est, 1e-9) for b in balances[:20] if b > 0]
    tail_prob = max(0.0, 1.0 - sum(p))
    entropy = -sum(pi * math.log(pi, 2) for pi in p if pi > 0)
    if tail_prob > 0:
        entropy += -tail_prob * math.log(tail_prob, 2)

    return {
        "decimals": decimals,
        "token_supply_raw": raw_amount,
        "token_supply_ui": total_supply,
        "top1_holder_share": round(_safe_ratio(top1, total_supply), 6),
        "top20_holder_share": round(_safe_ratio(top20_sum, total_supply), 6),
        "first50_holder_conc_est": round(first50_est, 6),
        "holder_entropy_est": round(entropy, 6),
        "holder_metrics_warnings": [
            "first50_holder_conc_est is heuristic",
            "holder_entropy_est is heuristic",
        ],
    }
