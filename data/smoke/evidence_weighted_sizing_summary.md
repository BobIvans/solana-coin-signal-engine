# Evidence-weighted sizing smoke

| case | hard_block | base_pct | effective_pct | multiplier | origin | reasons |
| --- | --- | ---: | ---: | ---: | --- | --- |
| strong_healthy_confirmation | false | 0.4200 | 0.4200 | 1.0000 | evidence_weighted | evidence_support_preserved_base_size |
| degraded_x_otherwise_decent | false | 0.2000 | 0.2000 | 1.0000 | degraded_x_policy | x_status_degraded_size_reduced |
| partial_evidence | false | 0.3500 | 0.1837 | 0.5249 | partial_evidence_reduced | partial_evidence_size_reduced, evidence_conflict_size_reduced |
| creator_linkage_risk | false | 0.4500 | 0.1733 | 0.3851 | risk_reduced | evidence_conflict_size_reduced, creator_link_risk_size_reduced |
| conflicting_evidence | false | 0.3800 | 0.1197 | 0.3150 | risk_reduced | evidence_conflict_size_reduced, creator_link_risk_moderate_size_reduced, continuation_confidence_low_size_reduced, cluster_evidence_low_confidence_size_reduced |
| hard_blocked_case | true | 0.2000 | 0.2000 | 1.0000 | evidence_weighted | evidence_support_preserved_base_size |
| missing_evidence | false | 0.2800 | 0.1092 | 0.3900 | partial_evidence_reduced | partial_evidence_size_reduced, missing_evidence_size_reduced, evidence_quality_low_size_reduced |
