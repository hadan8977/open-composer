# Decision Record: h20260929_11_multiq_sue

## P1

- Path: multiq_sue_screen (8 batch candidates: ENET_TOP50, ENET_TOP20, ENET_MOM_TOP50, SUE1_TOP50, MOM12_1_TOP50, EW_POOL, RAND_TOP50, ENET_SHUF_TOP50; ENET_LS information only)
- Decision: stop. No keep-eligible candidate clears K1, K2 or watch_recent; the increment criterion fails for ENET_TOP50, ENET_TOP20 and ENET_MOM_TOP50. Source: `reports/research/screens/h20260929_11_multiq_sue/leaderboard.json` via `results.json`.
- Evidence: ENET_TOP50 anchor median Sharpe 0.60 (bar 1.1882), stress 0.38 (bar 0.6447), K2 edge -0.11 / -0.29, DSR 0.32; SUE1_TOP50 0.88, MOM12_1_TOP50 1.10, ENET_SHUF_TOP50 0.68, RAND_TOP50 0.51. ENET RankIC 2019-2023 24 months, mean -0.0055, t -0.21; 2024+ 24 months, mean -0.0089, t -0.33; 4 of 8 yearly models were all-zero.
- Reason: the cross-validated elastic net finds essentially no SUE-history signal in the S&P 500 pool on our filing-visible SEC XBRL data; the long-only top-50 book earns less than plain single-quarter SUE and 12-1 momentum and is indistinguishable from the label-shuffle placebo. Consistent with the earlier single-quarter refutation (dir:pead_xbrl_sue_filing_date) and with the PEAD-decay literature in the brief.
- Rejected variants: ENET_TOP20 (anchor 0.37), ENET_MOM_TOP50 (anchor 0.83, worse than MOM12_1_TOP50 alone), ENET_LS (information only, anchor net Sharpe -0.46).
- Next iteration suggestion: none for this route. Reopen only with announcement-date (press-release timestamped) earnings surprises, analyst-estimate SUE, or a longer SUE history than 2016 onward, and a model trained on more than about 7 years.
- ML contribution: ml_contribution_pass false (model did not beat baselines or the label-shuffle placebo). workflow_pass true, research_pass false, llm_contribution_pass false, paper_ready_pass false.
