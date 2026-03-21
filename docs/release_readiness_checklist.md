# Release readiness checklist

This repository treats readiness as a **formal gate**, not a vibe check.

A branch is ready for `shadow` only after the commands below are green and the repository tree is clean. A branch is ready for `constrained_paper` only after that same acceptance gate stays green and shadow-mode sanity has been confirmed on real local artifacts.

## 1. Repository hygiene

```bash
git status
grep -RIn '<<<<<<<\|=======\|>>>>>>>' . --exclude-dir=.git
find . -type f -name '*.rej'
find . -maxdepth 1 -type f \( -name '*.patch' -o -name '*git.patch' -o -name 'FETCH_HEAD' \)
```

Expected outcome:

- `git status` is clean
- no unresolved merge markers
- no `.rej`
- no patch debris / `FETCH_HEAD`

## 2. Mandatory acceptance gate

Canonical entrypoints:

```bash
make acceptance
# or
python scripts/acceptance_gate.py
```

The acceptance gate must pass all of these blocks:

- contract parity / schema / provenance
- continuation fallback semantics
- false-positive score/regime safety
- runtime real-signal integrity
- replay wallet-mode parity
- analyzer slices
- analyzer matrix truth-layer usage
- evidence-weighted sizing
- end-to-end golden smoke
- smoke scripts for contract parity, runtime, replay, and e2e golden flow

A couple of locally green tests are **not** equivalent to acceptance.

## 3. Runtime and replay posture must stay honest

Runtime default must still be real local signals:

```bash
python scripts/runtime_signal_smoke.py
```

Replay must remain historical-only:

```bash
python scripts/historical_replay_smoke.py
```

Checks:

- runtime consumes real artifact inputs by default
- replay does not fabricate a synthetic truth path when historical artifacts are present
- runtime/replay provenance remains visible in emitted artifacts

## 4. Analyzer evidence-quality review

The analyzer must keep these evidence-quality slices visible in the canonical matrix/trade truth layer:

- `partial_evidence_trades`
- `low_confidence_evidence_trades`
- `evidence_conflict_trades`
- `degraded_x_salvage_cases`
- `linkage_risk_underperformance`

Helpful commands:

```bash
pytest -q tests/test_analyzer_slices.py tests/test_analyzer_matrix.py
python scripts/e2e_golden_smoke.py
```

Review expectations:

- slices are analysis-only and sample-size-aware
- missing matrix fields do not silently masquerade as healthy evidence
- analyzer recommendations stay conservative and manual-only

## 5. Shadow promotion decision

Promotion to `shadow` is allowed only when all of the following are true:

- repo clean checks are green
- acceptance gate is green
- false-positive suites are green
- contract parity is green
- analyzer evidence-quality slices are present and sane
- evidence-weighted sizing is green
- runtime default = real signals is confirmed
- replay = historical-only is confirmed

## 6. Constrained paper promotion decision

Promotion to `constrained_paper` is allowed only after:

- the full `shadow` checklist above is already green
- shadow-mode sanity has been observed on real local artifacts
- no new acceptance regressions appear after shadow validation

## 7. Canonical operational order

1. repo clean
2. acceptance gate
3. replay/runtime verification
4. analyzer review
5. readiness decision
