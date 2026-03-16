# post_run_analyzer (PR-10)

`post_run_analyzer` читает артефакты paper-trading прогона и строит честный пост-фактум отчёт.

## Inputs

Обязательные файлы:

- `trades.jsonl`
- `signals.jsonl`
- `positions.json`
- `portfolio_state.json`

## Reconstruction logic

Реконструкция выполняется по `position_id`:

1. Находит entry trade (`side=buy|entry`).
2. Находит все exit trades (`side=sell|exit`).
3. Считает partial exits как `len(exits)-1`.
4. Финальный lifecycle получает `exit_reason_final` из последнего exit.
5. PnL агрегируется суммой exit legs (`gross_pnl_sol`, `net_pnl_sol`, fees/slippage).

Если trade-логов недостаточно, используется fallback из `positions.json` только для `status=closed`.

## Metrics

### Portfolio/regime/exit/friction

- Portfolio: winrate, profit factor, average/median trade PnL, max drawdown, realized/unrealized split.
- Regime: winrate/profit-factor/hold-time/failed-fill/partial-exit usage by `SCALP|TREND`.
- Exit reason: distribution + pnl/winrate/hold-time by reason.
- Friction: slippage, priority fee, failed fill rate, partial fill rate, net-vs-gross gap.

### Correlations

Корреляции считаются для обязательных метрик относительно `net_pnl_pct`:

- `bundle_cluster_score`
- `first30s_buy_ratio`
- `priority_fee_avg_first_min`
- `first50_holder_conc_est`
- `holder_entropy_est`
- `dev_sell_pressure_5m`
- `pumpfun_to_raydium_sec`
- `x_validation_score`

Метод: `pearson + spearman` с optional outlier clipping (`POST_RUN_OUTLIER_CLIP_PCT`).

Если sample `< POST_RUN_MIN_TRADES_FOR_CORRELATION`, метрика помечается `insufficient_sample`.

## Recommendation policy

Рекомендации выдаются в консервативном стиле:

- `weight_adjustment`
- `threshold_adjustment`
- `degrade_policy_adjustment`
- `friction_model_adjustment`
- `sample_size_warning`

Сильные рекомендации блокируются при малом sample size.

## Caveat policy

Отчёт всегда включает честные предупреждения:

- `small_sample_warning`
- `high_outlier_sensitivity`
- `too_many_partial_fills`
- `degraded_x_dominates_sample`
- `open_positions_bias`
- `correlation_not_causation`

## Outputs

- `post_run_summary.json`
- `post_run_recommendations.json`
- `post_run_report.md`
- optional append-only `analyzer_events.jsonl`
