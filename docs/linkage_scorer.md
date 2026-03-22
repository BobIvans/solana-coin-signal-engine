# Linkage scorer

The linkage scorer adds an explicit **creator/dev/funder evidence layer** on top of the repo's existing wallet-clustering heuristics.

## What it does

`analytics/linkage_scorer.py` evaluates whether the creator wallet, dev wallet, early buyers, and shared funders appear connected through:

- direct creator/dev-linked participant flags,
- shared funding sources,
- shared cluster ids,
- shared launch groups,
- creator/dev same-funder overlap.

It emits additive fields such as:

- `creator_dev_link_score`
- `creator_buyer_link_score`
- `dev_buyer_link_score`
- `shared_funder_link_score`
- `creator_cluster_link_score`
- `cluster_dev_link_score`
- `linkage_risk_score`
- `linkage_reason_codes`
- `linkage_confidence`
- `linkage_metric_origin`

## Honesty policy

This layer is conservative by design:

- missing evidence is not treated as negative or positive proof,
- a single weak hint should stay low-confidence,
- stronger risk requires multiple evidence types,
- `creator_in_cluster_flag` from linkage is only derived when cluster-style overlap is both present and confident,
- outputs reflect whether evidence came from graph-style overlap, heuristic hints, or both.
- emitted `linkage_metric_origin` values are canonicalized to `graph_evidence`, `heuristic_evidence`, `mixed_evidence`, or `missing`.
- legacy `heuristic` may be normalized only at ingestion boundaries; it is not allowed as fresh emitted output.

## Status fields

The scorer uses:

- `ok` when usable linkage evidence exists,
- `partial` when wallets are present but evidence is sparse,
- `missing` when the required wallet/evidence inputs are absent,
- `failed` when malformed input prevents safe scoring.

Warnings are surfaced through `linkage_warning` rather than raising hard failures.

## Downstream usage

This PR integrates linkage outputs additively into:

- wallet clustering output payloads,
- bundle enrichment payloads,
- unified scoring penalties,
- trend regime blockers and warnings,
- protective exits,
- replay feature-matrix exports.

The pre-existing cluster heuristics remain intact; linkage adds provenance-aware evidence on top.

## Funder sanitization

- common CEX / aggregator / bridge funders are sanitized before overlap counts are computed
- sanitized funders do not increase `funder_overlap_count` or shared-funder linkage flags
