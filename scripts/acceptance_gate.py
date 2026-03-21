#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class GateBlock:
    name: str
    kind: str
    command: tuple[str, ...]
    description: str


def _pytest_block(name: str, description: str, *tests: str) -> GateBlock:
    return GateBlock(name=name, kind='pytest', command=('pytest', '-q', *tests), description=description)


def _python_block(name: str, description: str, *args: str) -> GateBlock:
    return GateBlock(name=name, kind='python', command=(sys.executable, *args), description=description)


PYTEST_BLOCKS: tuple[GateBlock, ...] = (
    _pytest_block(
        'contract_schema_provenance',
        'Contract parity, schema, and provenance truth-layer checks.',
        'tests/test_contract_parity.py',
        'tests/test_signal_trade_schema_provenance.py',
        'tests/test_trade_feature_matrix_schema.py',
    ),
    _pytest_block(
        'continuation_false_positive_safety',
        'Continuation fallback semantics plus false-positive score/regime safety.',
        'tests/test_continuation_enricher_fallback.py',
        'tests/test_false_positive_score_regressions.py',
        'tests/test_false_positive_regime_regressions.py',
    ),
    _pytest_block(
        'runtime_replay_integrity',
        'Runtime real-signal and replay wallet-mode parity integrity.',
        'tests/test_runtime_real_signal_loop.py',
        'tests/test_replay_wallet_weighting_parity.py',
    ),
    _pytest_block(
        'analyzer_sizing_e2e',
        'Analyzer slices, matrix truth-layer, evidence-weighted sizing, and end-to-end golden smoke test coverage.',
        'tests/test_analyzer_slices.py',
        'tests/test_analyzer_matrix.py',
        'tests/test_evidence_weighted_sizing.py',
        'tests/test_e2e_golden_smoke.py',
    ),
)


def _smoke_blocks(base_dir: Path) -> tuple[GateBlock, ...]:
    return (
        _python_block(
            'contract_parity_smoke',
            'Deterministic contract parity smoke using isolated acceptance artifacts.',
            'scripts/contract_parity_smoke.py',
            '--base-dir',
            str(base_dir / 'contract_parity'),
        ),
        _python_block(
            'runtime_signal_smoke',
            'Deterministic runtime real-signal smoke using isolated acceptance artifacts.',
            'scripts/runtime_signal_smoke.py',
            '--base-dir',
            str(base_dir / 'runtime_signal'),
        ),
        _python_block(
            'historical_replay_smoke',
            'Deterministic historical-only replay smoke using isolated acceptance artifacts.',
            'scripts/historical_replay_smoke.py',
            '--output-base-dir',
            str(base_dir / 'historical_replay'),
        ),
        _python_block(
            'e2e_golden_smoke',
            'Deterministic end-to-end golden smoke chain with analyzer verification.',
            'scripts/e2e_golden_smoke.py',
            '--base-dir',
            str(base_dir / 'e2e_golden'),
        ),
    )


def _git_status() -> dict[str, object]:
    git_dir = REPO_ROOT / '.git'
    if not git_dir.exists():
        return {'available': False, 'clean': None, 'porcelain': []}
    completed = subprocess.run(
        ['git', 'status', '--porcelain'],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    lines = [line for line in completed.stdout.splitlines() if line.strip()]
    return {
        'available': True,
        'clean': completed.returncode == 0 and not lines,
        'porcelain': lines,
    }


def _run_block(block: GateBlock) -> dict[str, object]:
    completed = subprocess.run(
        list(block.command),
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    stdout_lines = completed.stdout.strip().splitlines() if completed.stdout.strip() else []
    stderr_lines = completed.stderr.strip().splitlines() if completed.stderr.strip() else []
    return {
        'name': block.name,
        'kind': block.kind,
        'description': block.description,
        'command': list(block.command),
        'returncode': completed.returncode,
        'ok': completed.returncode == 0,
        'stdout_tail': stdout_lines[-20:],
        'stderr_tail': stderr_lines[-20:],
    }


def build_blocks(base_dir: Path, *, skip_smokes: bool = False) -> tuple[GateBlock, ...]:
    blocks = list(PYTEST_BLOCKS)
    if not skip_smokes:
        blocks.extend(_smoke_blocks(base_dir))
    return tuple(blocks)


def main() -> int:
    parser = argparse.ArgumentParser(description='Operational acceptance gate for branch readiness.')
    parser.add_argument('--base-dir', default=None, help='Optional directory for isolated smoke outputs. Defaults to a temporary directory outside the repo.')
    parser.add_argument('--skip-smokes', action='store_true', help='Run only the pytest acceptance blocks.')
    parser.add_argument('--list', action='store_true', help='List acceptance blocks and exit.')
    args = parser.parse_args()

    temp_dir: str | None = None
    if args.base_dir:
        base_dir = Path(args.base_dir).expanduser().resolve()
        base_dir.mkdir(parents=True, exist_ok=True)
    else:
        temp_dir = tempfile.mkdtemp(prefix='solana_acceptance_gate_')
        base_dir = Path(temp_dir)

    blocks = build_blocks(base_dir, skip_smokes=args.skip_smokes)
    if args.list:
        payload = {
            'base_dir': str(base_dir),
            'skip_smokes': bool(args.skip_smokes),
            'blocks': [
                {
                    'name': block.name,
                    'kind': block.kind,
                    'description': block.description,
                    'command': list(block.command),
                }
                for block in blocks
            ],
        }
        print(json.dumps(payload, sort_keys=True))
        if temp_dir:
            shutil.rmtree(temp_dir, ignore_errors=True)
        return 0

    repo_clean_before = _git_status()
    results: list[dict[str, object]] = []
    failed_block: str | None = None
    for block in blocks:
        result = _run_block(block)
        results.append(result)
        if not result['ok']:
            failed_block = block.name
            break

    repo_clean_after = _git_status()
    ok = failed_block is None
    payload = {
        'ok': ok,
        'failed_block': failed_block,
        'base_dir': str(base_dir),
        'repo_clean_before': repo_clean_before,
        'repo_clean_after': repo_clean_after,
        'blocks': results,
        'required_gate': [block.name for block in blocks],
    }
    print(json.dumps(payload, sort_keys=True))

    if temp_dir and ok:
        shutil.rmtree(temp_dir, ignore_errors=True)
    return 0 if ok else 1


if __name__ == '__main__':
    raise SystemExit(main())
