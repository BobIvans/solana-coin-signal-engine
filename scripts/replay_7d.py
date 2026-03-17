from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from replay.chain_backfill import build_chain_context
from replay.deterministic import make_run_paths, seed_everything, stable_sort_records
from replay.feature_builder import build_features_for_step, inject_degraded_x_fields
from replay.io import load_simple_yaml, write_json, write_jsonl
from replay.manifest import build_manifest, write_manifest
from replay.report import build_summary, write_summary_json, write_summary_md
from replay.simulator import simulate_signals
from replay.universe import build_replay_universe


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Deterministic 7-day replay runner")
    parser.add_argument("--config", required=True)
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--max-open-positions", type=int, default=None)
    parser.add_argument("--max-trades-per-day", type=int, default=None)
    parser.add_argument("--wallet-weighting", choices=["on", "off"], default="on")
    parser.add_argument("--start-ts", default=None)
    parser.add_argument("--end-ts", default=None)
    return parser.parse_args()


def _window(days: int, start_ts: str | None, end_ts: str | None) -> tuple[str, str]:
    if end_ts:
        end = datetime.fromisoformat(end_ts.replace("Z", "+00:00"))
    else:
        end = datetime.now(tz=timezone.utc).replace(microsecond=0)
    if start_ts:
        start = datetime.fromisoformat(start_ts.replace("Z", "+00:00"))
    else:
        start = end - timedelta(days=days)
    return start.isoformat().replace("+00:00", "Z"), end.isoformat().replace("+00:00", "Z")


def main() -> int:
    args = _parse_args()
    config = load_simple_yaml(args.config)
    args.start_ts, args.end_ts = _window(args.days, args.start_ts, args.end_ts)
    if args.max_open_positions is not None:
        config.setdefault("simulation", {})["max_open_positions"] = args.max_open_positions
    if args.max_trades_per_day is not None:
        config.setdefault("simulation", {})["max_trades_per_day"] = args.max_trades_per_day

    seed_everything(args.seed)
    paths = make_run_paths(args.run_id, str(config.get("output", {}).get("base_dir", "runs")))

    print(f"[replay] run_id={args.run_id}")
    manifest = build_manifest(config, args)
    write_manifest(paths.manifest_path, manifest)
    print(f"[replay] manifest_written path={paths.manifest_path}")

    candidates, shortlist = build_replay_universe(config=config, start_ts=args.start_ts, end_ts=args.end_ts, dry_run=args.dry_run)
    write_jsonl(paths.universe_path, candidates)
    print(f"[replay] universe_built candidates={len(candidates)} shortlist={len(shortlist)}")

    backfill_rows = build_chain_context(shortlist, config, dry_run=args.dry_run)
    write_jsonl(paths.backfill_path, backfill_rows)
    print(f"[replay] backfill_complete tokens={len(backfill_rows)}")

    backfill_map = {r["token_address"]: r for r in backfill_rows}
    signals = []
    for cand in shortlist:
        features = build_features_for_step(cand, backfill_map.get(cand["token_address"], {}), config, wallet_weighting=args.wallet_weighting == "on")
        score = round(55.0 + 60.0 * (0.35 * features["buy_pressure"] + 0.25 * min(1.0, features["volume_velocity"] / 6.0) + 0.2 * (1 - features["rug_score_light"]) + 0.2 * min(1.0, features["smart_wallet_hits"] / 3.0)), 4)
        signal = {
            "run_id": args.run_id,
            "ts": cand["discovered_at"],
            "token_address": cand["token_address"],
            "pair_address": cand["pair_address"],
            "regime_candidate": "SCALP" if score >= 75 else "IGNORE",
            "final_score": score,
            "features": features,
        }
        inject_degraded_x_fields(signal, config)
        signals.append(signal)

    signals = stable_sort_records(signals, ("ts", "token_address", "pair_address"))
    simulated_signals, trades, positions = simulate_signals(signals, config)
    write_jsonl(paths.signals_path, simulated_signals)
    print(f"[replay] signals_built count={len(simulated_signals)}")

    write_jsonl(paths.trades_path, trades)
    write_json(paths.positions_path, positions)
    print(f"[replay] trades_simulated count={len(trades)}")

    summary = build_summary(simulated_signals, trades, wallet_weighting_mode=args.wallet_weighting, x_mode=config.get("x_mode", {}).get("status", "degraded"))
    write_summary_json(str(paths.summary_json_path), summary)
    write_summary_md(str(paths.summary_md_path), summary)
    print(f"[replay] summary_written path={paths.summary_json_path}")
    print("[replay] done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
