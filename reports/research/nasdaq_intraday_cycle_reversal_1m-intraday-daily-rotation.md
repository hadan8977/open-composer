# Intraday Daily Rotation Research: nasdaq_intraday_cycle_reversal_1m

- JSON report: `/root/codex-test/open-composer/reports/research/nasdaq_intraday_cycle_reversal_1m-intraday-daily-rotation.json`
- Symbols: AAPL, MSFT, NVDA, AMZN, META, GOOGL, AVGO, AMD, QCOM, AMAT, NFLX, TSLA
- Timeframe: `1m`
- Research window: `2024-05-16T13:31:00Z` -> `2026-05-15T19:59:00Z`
- Market gate symbol: `QQQ`
- Benchmark symbol: `TQQQ`
- Data as-of: `2026-05-15T19:59:00+00:00`
- Data source/feed: `alpaca` / `iex`
- Data source mode: `cache`
- Point-in-time: selection uses previous closes plus confirmed opening bars only.
- Execution: enter next bar after opening window, exit same day on last regular bar.
- Selection objective: prefer stable annualized Alpha versus equal-weight universe intraday exposure

## Assumptions

- Selection uses only previous regular-session closes plus confirmed same-day opening bars.
- Entry occurs at the next bar open after the opening window.
- All positions are exited at the same day's final regular-session close.
- No overnight positions, leverage, shorts, or real broker orders are used.
- Commission is 0.005% per fill.
- Slippage is 2 bps per fill.
- TQQQ buy-and-hold is reported as a stress benchmark, not as the primary intraday acceptance gate.
- Alpaca IEX data is not consolidated full-market SIP data when feed=iex.

## Research Cost

- Candidates evaluated: `4`
- Walk-forward candidates: `4`
- Walk-forward top-K filter: `4`
- Estimated backtest passes: `30`
- Runtime total seconds: `38.93`

## Acceptance Gate

- passed: `False`
- objective: `equal_weight_alpha`
- oos_objective_alpha_annualized_pct: `30.524930291455476`
- oos_sharpe_ratio: `1.0920418948309079`
- oos_traded_days: `56`
- oos_alpha_vs_tqqq_buy_hold_annualized_pct: `69.42112146771451`
- walk_forward_positive_alpha_folds: `1`
- walk_forward_fold_count: `3`
- quality_flags: `['does_not_beat_ex_post_best_symbol']`

## Pass Labels

- workflow_pass: `True`
- research_pass: `True`
- llm_contribution_pass: `False`
- paper_ready_pass: `False`
- paper_ready_blockers: `['draft/manual_signal strategy only', 'Alpaca IEX is not consolidated SIP data', 'no broker paper-readiness activation or data-source comparison', 'LLM output is advisory unless replayed from feature packets']`

## Top Candidates

### Rank 1: lb10_entry5_top1_open0_mom0_rv0.8_qprior_negative_reversal_maxopen-0.2_maxmomnone

- Score: `17.83`
- Quality flags: `does_not_beat_ex_post_best_symbol`
- Train return: `12.20%`
- Train annualized: `8.91%`
- Train Alpha vs equal-weight intraday annualized: `15.32%`
- Train Alpha vs TQQQ intraday annualized: `8.47%`
- Train Alpha vs TQQQ buy-hold annualized: `-41.38%`
- Train Sharpe: `0.49`
- Train max drawdown: `-15.39%`
- Train traded days / round trips: `100/100`
- Train win day pct: `17.94%`
- Train benchmark buy-hold: `TQQQ 73.27%`
- Train ex-post best buy-hold: `TSLA 143.98%`
- Out of sample return: `13.37%`
- Out of sample annualized: `23.47%`
- Out of sample Alpha vs equal-weight intraday annualized: `30.52%`
- Out of sample Alpha vs TQQQ intraday annualized: `33.83%`
- Out of sample Alpha vs TQQQ buy-hold annualized: `69.42%`
- Out of sample Sharpe: `1.09`
- Out of sample max drawdown: `-9.43%`
- Out of sample traded days / round trips: `56/56`
- Out of sample win day pct: `20.00%`
- Out of sample benchmark buy-hold: `TQQQ -30.67%`
- Out of sample ex-post best buy-hold: `AMAT 97.86%`
- Full window return: `27.21%`
- Full window annualized: `13.17%`
- Full window Alpha vs equal-weight intraday annualized: `19.78%`
- Full window Alpha vs TQQQ intraday annualized: `16.17%`
- Full window Alpha vs TQQQ buy-hold annualized: `3.18%`
- Full window Sharpe: `0.66`
- Full window max drawdown: `-15.39%`
- Full window traded days / round trips: `156/156`
- Full window win day pct: `18.57%`
- Full window benchmark buy-hold: `TQQQ 20.35%`
- Full window ex-post best buy-hold: `AMD 153.82%`

### Rank 2: lb10_entry5_top2_open0_mom0_rv0.8_qprior_negative_reversal_maxopen-0.2_maxmomnone

- Score: `4.74`
- Quality flags: `does_not_beat_ex_post_best_symbol`
- Train return: `-0.04%`
- Train annualized: `-0.03%`
- Train Alpha vs equal-weight intraday annualized: `6.38%`
- Train Alpha vs TQQQ intraday annualized: `-0.47%`
- Train Alpha vs TQQQ buy-hold annualized: `-50.32%`
- Train Sharpe: `0.11`
- Train max drawdown: `-18.53%`
- Train traded days / round trips: `100/178`
- Train win day pct: `17.06%`
- Train benchmark buy-hold: `TQQQ 73.27%`
- Train ex-post best buy-hold: `TSLA 143.98%`
- Out of sample return: `6.16%`
- Out of sample annualized: `10.56%`
- Out of sample Alpha vs equal-weight intraday annualized: `17.62%`
- Out of sample Alpha vs TQQQ intraday annualized: `20.93%`
- Out of sample Alpha vs TQQQ buy-hold annualized: `56.51%`
- Out of sample Sharpe: `0.71`
- Out of sample max drawdown: `-8.03%`
- Out of sample traded days / round trips: `56/95`
- Out of sample win day pct: `19.33%`
- Out of sample benchmark buy-hold: `TQQQ -30.67%`
- Out of sample ex-post best buy-hold: `AMAT 97.86%`
- Full window return: `6.11%`
- Full window annualized: `3.10%`
- Full window Alpha vs equal-weight intraday annualized: `9.71%`
- Full window Alpha vs TQQQ intraday annualized: `6.10%`
- Full window Alpha vs TQQQ buy-hold annualized: `-6.90%`
- Full window Sharpe: `0.25`
- Full window max drawdown: `-18.53%`
- Full window traded days / round trips: `156/273`
- Full window win day pct: `17.76%`
- Full window benchmark buy-hold: `TQQQ 20.35%`
- Full window ex-post best buy-hold: `AMD 153.82%`

### Rank 3: lb5_entry5_top1_open0_mom0_rv0.8_qprior_negative_reversal_maxopen-0.2_maxmomnone

- Score: `-1.14`
- Quality flags: `oos_no_annualized_alpha_vs_equal_weight_intraday, oos_no_annualized_alpha_vs_benchmark_intraday, oos_low_sharpe, does_not_beat_ex_post_best_symbol`
- Train return: `-8.31%`
- Train annualized: `-6.14%`
- Train Alpha vs equal-weight intraday annualized: `0.95%`
- Train Alpha vs TQQQ intraday annualized: `-3.91%`
- Train Alpha vs TQQQ buy-hold annualized: `-49.09%`
- Train Sharpe: `-0.23`
- Train max drawdown: `-12.22%`
- Train traded days / round trips: `113/113`
- Train win day pct: `18.84%`
- Train benchmark buy-hold: `TQQQ 63.11%`
- Train ex-post best buy-hold: `TSLA 139.84%`
- Out of sample return: `-16.55%`
- Out of sample annualized: `-26.21%`
- Out of sample Alpha vs equal-weight intraday annualized: `-19.16%`
- Out of sample Alpha vs TQQQ intraday annualized: `-15.85%`
- Out of sample Alpha vs TQQQ buy-hold annualized: `19.74%`
- Out of sample Sharpe: `-1.45`
- Out of sample max drawdown: `-23.39%`
- Out of sample traded days / round trips: `54/54`
- Out of sample win day pct: `16.67%`
- Out of sample benchmark buy-hold: `TQQQ -30.67%`
- Out of sample ex-post best buy-hold: `AMAT 97.86%`
- Full window return: `-23.48%`
- Full window annualized: `-12.74%`
- Full window Alpha vs equal-weight intraday annualized: `-5.66%`
- Full window Alpha vs TQQQ intraday annualized: `-7.97%`
- Full window Alpha vs TQQQ buy-hold annualized: `-19.30%`
- Full window Sharpe: `-0.60`
- Full window max drawdown: `-25.07%`
- Full window traded days / round trips: `167/167`
- Full window win day pct: `18.18%`
- Full window benchmark buy-hold: `TQQQ 13.29%`
- Full window ex-post best buy-hold: `AMD 148.68%`

### Rank 4: lb5_entry5_top2_open0_mom0_rv0.8_qprior_negative_reversal_maxopen-0.2_maxmomnone

- Score: `-19.47`
- Quality flags: `oos_no_annualized_alpha_vs_equal_weight_intraday, oos_no_annualized_alpha_vs_benchmark_intraday, oos_low_sharpe, does_not_beat_ex_post_best_symbol`
- Train return: `-20.47%`
- Train annualized: `-15.41%`
- Train Alpha vs equal-weight intraday annualized: `-8.32%`
- Train Alpha vs TQQQ intraday annualized: `-13.18%`
- Train Alpha vs TQQQ buy-hold annualized: `-58.36%`
- Train Sharpe: `-0.82`
- Train max drawdown: `-24.49%`
- Train traded days / round trips: `113/207`
- Train win day pct: `17.68%`
- Train benchmark buy-hold: `TQQQ 63.11%`
- Train ex-post best buy-hold: `TSLA 139.84%`
- Out of sample return: `-18.53%`
- Out of sample annualized: `-29.13%`
- Out of sample Alpha vs equal-weight intraday annualized: `-22.08%`
- Out of sample Alpha vs TQQQ intraday annualized: `-18.77%`
- Out of sample Alpha vs TQQQ buy-hold annualized: `16.82%`
- Out of sample Sharpe: `-2.24`
- Out of sample max drawdown: `-23.56%`
- Out of sample traded days / round trips: `54/99`
- Out of sample win day pct: `14.67%`
- Out of sample benchmark buy-hold: `TQQQ -30.67%`
- Out of sample ex-post best buy-hold: `AMAT 97.86%`
- Full window return: `-35.21%`
- Full window annualized: `-19.83%`
- Full window Alpha vs equal-weight intraday annualized: `-12.75%`
- Full window Alpha vs TQQQ intraday annualized: `-15.06%`
- Full window Alpha vs TQQQ buy-hold annualized: `-26.39%`
- Full window Sharpe: `-1.19`
- Full window max drawdown: `-38.81%`
- Full window traded days / round trips: `167/306`
- Full window win day pct: `16.77%`
- Full window benchmark buy-hold: `TQQQ 13.29%`
- Full window ex-post best buy-hold: `AMD 148.68%`

## Walk Forward

### Fold 1: lb10_entry5_top1_open0_mom0_rv0.8_qprior_negative_reversal_maxopen-0.2_maxmomnone

- Train selected return: `7.18%`
- Train selected annualized: `15.39%`
- Train selected Alpha vs equal-weight intraday annualized: `39.66%`
- Train selected Alpha vs TQQQ intraday annualized: `42.34%`
- Train selected Alpha vs TQQQ buy-hold annualized: `-42.14%`
- Train selected Sharpe: `0.99`
- Train selected max drawdown: `-9.70%`
- Train selected traded days / round trips: `41/41`
- Train selected win day pct: `22.95%`
- Train selected benchmark buy-hold: `TQQQ 24.61%`
- Train selected ex-post best buy-hold: `TSLA 90.37%`
- Test return: `1.60%`
- Test annualized: `3.33%`
- Test Alpha vs equal-weight intraday annualized: `-0.97%`
- Test Alpha vs TQQQ intraday annualized: `-15.36%`
- Test Alpha vs TQQQ buy-hold annualized: `26.85%`
- Test Sharpe: `0.26`
- Test max drawdown: `-15.39%`
- Test traded days / round trips: `48/48`
- Test win day pct: `20.49%`
- Test benchmark buy-hold: `TQQQ -12.17%`
- Test ex-post best buy-hold: `AVGO 40.80%`

### Fold 2: lb10_entry5_top1_open0_mom0_rv0.8_qprior_negative_reversal_maxopen-0.2_maxmomnone

- Train selected return: `8.89%`
- Train selected annualized: `9.20%`
- Train selected Alpha vs equal-weight intraday annualized: `20.32%`
- Train selected Alpha vs TQQQ intraday annualized: `16.08%`
- Train selected Alpha vs TQQQ buy-hold annualized: `-0.06%`
- Train selected Sharpe: `0.46`
- Train selected max drawdown: `-15.39%`
- Train selected traded days / round trips: `89/89`
- Train selected win day pct: `21.72%`
- Train selected benchmark buy-hold: `TQQQ 8.95%`
- Train selected ex-post best buy-hold: `TSLA 90.98%`
- Test return: `19.80%`
- Test annualized: `45.24%`
- Test Alpha vs equal-weight intraday annualized: `46.48%`
- Test Alpha vs TQQQ intraday annualized: `48.18%`
- Test Alpha vs TQQQ buy-hold annualized: `-121.41%`
- Test Sharpe: `2.57`
- Test max drawdown: `-2.19%`
- Test traded days / round trips: `22/22`
- Test win day pct: `11.48%`
- Test benchmark buy-hold: `TQQQ 60.77%`
- Test ex-post best buy-hold: `AMD 128.41%`

### Fold 3: lb10_entry5_top1_open0_mom0_rv0.8_qprior_negative_reversal_maxopen-0.2_maxmomnone

- Train selected return: `30.45%`
- Train selected annualized: `20.09%`
- Train selected Alpha vs equal-weight intraday annualized: `28.03%`
- Train selected Alpha vs TQQQ intraday annualized: `25.67%`
- Train selected Alpha vs TQQQ buy-hold annualized: `-22.42%`
- Train selected Sharpe: `0.90`
- Train selected max drawdown: `-15.39%`
- Train selected traded days / round trips: `111/111`
- Train selected win day pct: `18.31%`
- Train selected benchmark buy-hold: `TQQQ 67.27%`
- Train selected ex-post best buy-hold: `TSLA 126.59%`
- Test return: `-2.49%`
- Test annualized: `-5.07%`
- Test Alpha vs equal-weight intraday annualized: `-2.26%`
- Test Alpha vs TQQQ intraday annualized: `-7.90%`
- Test Alpha vs TQQQ buy-hold annualized: `40.11%`
- Test Sharpe: `-0.18`
- Test max drawdown: `-9.43%`
- Test traded days / round trips: `45/45`
- Test win day pct: `19.67%`
- Test benchmark buy-hold: `TQQQ -25.25%`
- Test ex-post best buy-hold: `AMAT 94.79%`

## Overfit And Benchmark Notes

- Best parameters are selected on the training window; OOS is scored after selection.
- Walk-forward folds reselect parameters only from prior days.
- `TQQQ` buy-and-hold is a leveraged overnight benchmark and is shown as a stress comparison, not the primary intraday acceptance gate.
- The comparable intraday benchmarks are equal-weight universe intraday and `TQQQ` intraday-only over the same entry/exit bars.
