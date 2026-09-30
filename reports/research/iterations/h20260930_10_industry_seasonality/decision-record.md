# Decision Record: h20260930_10_industry_seasonality

## P1

- Path: industry_seasonality_screen (6 cells, top_n 2/3/5 x avg_years 1/5, 23 industry ETFs, front-running shift 1)
- Decision: stop. Plan A1 is refuted at stage 1: 0/6 cells satisfy anchor 10bp Sharpe >= 1.19, 20bp anchor CAGR > 0 and placebo beat fraction <= 10% together. Stage 2 (C2 combination) is not triggered.
- Reason: anchor 10bp Sharpe is 0.52-1.12 to 2026-09-29 (best I_K2_Y5 1.118; 1.184 on the lane window to 2026-09-17), below 1.19 for every cell; placebo beat fraction <= 10% only for I_K2_Y5 and I_K3_Y5 (0.05 each; others 0.20-0.45); 20bp anchor CAGR > 0 for all six. Stress-window Sharpe -0.07 to 0.35; informational C2 combination increments are negative for all six in both windows; daily-return correlation with S0 is 0.65-0.75. Source: results.json, leaderboard.json.
- Next iteration suggestion: do not reopen the industry-ETF extension with a new grid or universe. The seasonal leg of C2 stays S0 (9 sector SPDRs). Reopen only with 20 or more years of industry index history (the original 20-year averaging cannot be replicated on ETF data from 2016). No ML or AI-information entry condition is met by this result.
