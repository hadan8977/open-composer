# LLM Intraday Daily Rotation Selection: nasdaq_intraday_cycle_reversal_1m_llm

- JSON report: `/root/codex-test/open-composer/reports/research/nasdaq_intraday_cycle_reversal_1m_llm-llm-intraday-selection.json`
- Prompt artifact: `/root/codex-test/open-composer/reports/research/nasdaq_intraday_cycle_reversal_1m_llm-llm-intraday-selection-prompt.json`
- Status: `written`
- Symbols: AAPL, MSFT, NVDA, AMZN, META, GOOGL, AVGO, AMD, QCOM, AMAT, NFLX, TSLA
- Market symbol: `QQQ`
- Benchmark symbol: `TQQQ`
- Research window: `2024-05-16T13:31:00Z` -> `2026-05-15T19:59:00Z`
- Mode: `llm_training_meta_selection_daily_intraday`
- Selection objective: prefer stable annualized Alpha versus benchmark-symbol intraday exposure
- Anti-leakage: final OOS and full-window metrics are hidden until after selection.
- No LLM call is made inside the backtest loop.

## LLM Choice

- Selected: `lb10_entry5_top2_open0_mom0_rv0.8_qprior_negative_reversal_maxopen-0.2_maxmomnone`
- Confidence: `0.34`
- Rationale: Selected the top-2, 10-day lookback variant because it is the least weak option among the provided training/internal-validation evidence: it has the best meta_score, the least negative fold average alpha, the least severe fold minimum alpha, and the least negative internal validation objective alpha among the candidates. Its validation Sharpe is also highest. However, the evidence is not strong: validation alpha is still materially negative and validation traded days are sparse, so this should be treated only as a research candidate for further testing, not as evidence of live or final out-of-sample performance.
- Expected risks: All candidates have negative internal validation objective alpha, so this is only a weak research candidate rather than a supported deployment choice., Selected candidate has sparse validation trading activity with only 11 traded days, increasing estimation noise and overfitting risk., Prior validation folds are not positive for the selected candidate, with 0 of 3 positive folds, so fold consistency is poor despite being less negative than alternatives., Market gate based on prior negative QQQ conditions may create regime dependence and limited opportunity frequency., Opening-reversal behavior can be sensitive to execution assumptions, spreads, slippage, and early-session volatility.
- Rejected labels: lb10_entry5_top1_open0_mom0_rv0.8_qprior_negative_reversal_maxopen-0.2_maxmomnone, lb5_entry5_top1_open0_mom0_rv0.8_qprior_negative_reversal_maxopen-0.2_maxmomnone, lb5_entry5_top2_open0_mom0_rv0.8_qprior_negative_reversal_maxopen-0.2_maxmomnone

## LLM Contribution

- Contribution OK: `False`
- Level: `llm_assisted_selection_only`
- Label: llm_assisted_selection_only

## Pass Labels

- workflow_pass: `True`
- research_pass: `False`
- llm_contribution_pass: `False`
- paper_ready_pass: `False`
- paper_ready_blockers: `['draft/manual_signal strategy only', 'Alpaca IEX is not consolidated SIP data', 'no broker paper-readiness activation or data-source comparison', 'LLM output is advisory unless replayed from feature packets']`

## Final Validation After Selection

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
- Final OOS return: `6.16%`
- Final OOS annualized: `10.56%`
- Final OOS Alpha vs equal-weight intraday annualized: `17.62%`
- Final OOS Alpha vs TQQQ intraday annualized: `20.93%`
- Final OOS Alpha vs TQQQ buy-hold annualized: `56.51%`
- Final OOS Sharpe: `0.71`
- Final OOS max drawdown: `-8.03%`
- Final OOS traded days / round trips: `56/95`
- Final OOS win day pct: `19.33%`
- Final OOS benchmark buy-hold: `TQQQ -30.67%`
- Final OOS ex-post best buy-hold: `AMAT 97.86%`
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

## Candidates Visible To LLM

| Rank | Label | Meta Score | Train Objective Alpha | Validation Objective Alpha | Fold Avg Alpha | Fold Min Alpha | Positive Folds |
|---:|---|---:|---:|---:|---:|---:|---:|
| 1 | `lb10_entry5_top2_open0_mom0_rv0.8_qprior_negative_reversal_maxopen-0.2_maxmomnone` | -40.14 | 8.07% | -27.20% | -17.42% | -45.18% | 0/3 |
| 2 | `lb10_entry5_top1_open0_mom0_rv0.8_qprior_negative_reversal_maxopen-0.2_maxmomnone` | -55.01 | 23.65% | -34.26% | -20.42% | -54.00% | 1/3 |
| 3 | `lb5_entry5_top1_open0_mom0_rv0.8_qprior_negative_reversal_maxopen-0.2_maxmomnone` | -80.64 | 7.57% | -39.80% | -31.11% | -80.84% | 1/3 |
| 4 | `lb5_entry5_top2_open0_mom0_rv0.8_qprior_negative_reversal_maxopen-0.2_maxmomnone` | -97.61 | -3.97% | -42.90% | -40.43% | -103.60% | 1/3 |
