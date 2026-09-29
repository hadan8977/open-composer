# External Brief: h20260929_12_hedged_factor_ensemble

Full structured entries (url, date, type, credibility, core claim, Open
Composer applicability, reflection) are in `external-brief.json`. Summary:

1. **AlphaAgent (arXiv:2502.16789, KDD'25)** -- LLM-driven factor loop's S&P
   500 test-window IC is ~0.0056, a quarter of its own China CSI 500 IC.
   Already verified under T-15; re-cited to set a realistic IC ceiling for
   this task's ensembles.
2. **R&D-Agent(Q) (arXiv:2505.15155, NeurIPS'25 poster)** -- combined/curated
   factor loop beats classical factor libraries by ~3.5-4x IC on NASDAQ100
   post-2023, but absolute IC (0.0162) stays small. Supports testing
   ensembles over single factors; already verified under T-15.
3. **Azevedo & Hoegner 2023 (RQFA)** -- 299-anomaly x 30-ML-approach study,
   OOS Sharpe up to 1.39 long-short, 1979-2019. This project's own local
   replication of the same mechanism (screen + rank) already lost to a
   momentum baseline on 2018-2026 data -- the paper's Sharpe did not survive
   this project's implementation, which is why this task changes the
   construction (hedge for decorrelation) rather than re-running the
   refuted mechanism.
4. **Step 13 report** (dir:ml_ranking_liquid500_recent_vs_momentum_rule) --
   required prior art: screened factor ensembles reached 17.5-19.4%
   annualized long-only, half the momentum rule's 33.7%.
5. **Step 11 report** (dir:baseline_chain_b0_b1_b2_market_neutral_vs_long) --
   required prior art: SPY-beta-neutral hedge was a systematic drag, not a
   risk reducer, at weekly rebalance.
6. **directions.jsonl K2 rows** (equity_momentum_concentrated_pwb,
   factor_style_etf_momentum_rotation) -- long-only sleeves at 0.66-0.72
   correlation with S3 still fail the diversifier-edge test; motivates a
   tight < 0.3 correlation bar for this task's hedged forms.
7. **ProShares inverse-ETF hedging guidance** (new source, fetched and
   snapshotted 2026-09-29) -- SH/PSQ have a one-day investment objective and
   real compounding decay; issuer's own guidance is tactical use, not a
   static multi-year hedge. Grounds the choice to use actual SH/PSQ prices.
8. **T-15 select-results.json** -- the exact, already-computed select-window
   ICIR/sign scan (268 candidates with valid ICIR) this task's ensembles are
   built from; no new IC computation.

See `candidate-matrix-revisions` in external-brief.json for the three design
decisions this evidence drove (dropping nested composite cards, the capped
partial-beta hedge construction, and the tightened <0.3 correlation bar).
