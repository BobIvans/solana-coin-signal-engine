# Wallet family metadata

`analytics/wallet_family_metadata.py` adds a conservative, deterministic family-metadata layer on top of the repo's existing wallet registry and clustering/linkage work.

## What “wallet family” means here

This repo now distinguishes between two related but different concepts:

- `wallet_family_id`: a broader, reusable grouping for wallets that share meaningful evidence such as cluster overlap, explicit registry hints, repeated launch co-appearance, shared funders, or linkage-group hints.
- `independent_family_id`: a stricter grouping that is only assigned when the evidence is materially stronger. In practice this requires multiple corroborating signals or an explicit strict hint.

Neither field claims real-world identity certainty.
They are deterministic evidence groupings, not doxxed actor labels.

## Evidence model

The module only uses additive, repo-supported evidence lanes:

- shared cluster membership (`wallet_cluster_id`, `cluster_id`, `shared_cluster_id`)
- shared funder patterns (`funder`, `funding_source`, `funded_by`, related aliases)
- repeated launch overlap (`launch_group`, `launch_id`, bundle/group aliases)
- linkage-style hints (`linkage_group`, linked-wallet peer references)
- registry hints (`wallet_family_hint`, `independent_family_hint`)
- creator/dev overlap flags (`creator_linked`, `creator_overlap`, `dev_linked`)

Evidence is intentionally conservative:

- shared funder only -> broad family can exist, but confidence stays low and `independent_family_id` stays unset
- cluster-only overlap -> broad family can exist with partial confidence
- stronger multi-signal overlap -> both `wallet_family_id` and `independent_family_id` can be assigned
- missing or malformed evidence -> fields degrade to `missing` / `failed` rather than inventing a strong family

## Additive wallet-level fields

Wallet registry and validated-registry rows can now carry:

- `wallet_family_id`
- `independent_family_id`
- `wallet_family_confidence`
- `wallet_family_origin`
- `wallet_family_reason_codes`
- `wallet_cluster_id`
- `wallet_family_member_count`
- `wallet_family_shared_funder_flag`
- `wallet_family_creator_link_flag`
- `wallet_family_status`

Allowed origins are:

- `graph_evidence`
- `linkage_evidence`
- `registry_evidence`
- `mixed_evidence`
- `heuristic_evidence`
- `missing`

Statuses are:

- `ok`
- `partial`
- `missing`
- `failed`

## Deterministic ids

Family ids are derived from the canonical sorted member set.
That keeps ids stable across reruns when family membership is unchanged.
If the member set changes, the derived id changes too, which is acceptable and explicit.

## Persistent outputs

This PR adds:

- top-level `wallet_family_summary` and `wallet_family_assignments` to the main registry outputs when registry artifacts are built
- wallet-level family fields in registry and validated-registry records
- a standalone schema at `schemas/wallet_family_metadata.schema.json`
- smoke artifacts under `data/smoke/`

## Confidence and honesty policy

This layer is evidence-aware, not identity-certain:

- missing evidence is not treated as negative proof or positive proof
- weak evidence remains low-confidence and usually `partial`
- broad family assignment is intentionally easier than strict independent-family assignment
- downstream consumers can read family metadata, but they should still consider origin, confidence, reason codes, and status together

## Smoke runner

```bash
python scripts/wallet_family_metadata_smoke.py
```

By default it writes:

- `data/smoke/wallet_family_metadata.smoke.json`
- `data/smoke/wallet_family_summary.json`

## Rollback safety

The logic is isolated in `analytics/wallet_family_metadata.py`, and integrations are additive.
Reverting the family layer should not require a registry contract migration.
