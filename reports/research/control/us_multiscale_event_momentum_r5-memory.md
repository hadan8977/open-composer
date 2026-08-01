# Research Memory: us_multiscale_event_momentum_r5

R5 tested 15 preregistered candidates on 468 strict common sessions from 22 Alpaca Basic IEX series. Nine deterministic intraday variants and one shuffled-score placebo completed; four SEC/news candidates were dependency-skipped; the future-feature control rejected correctly. No model was trained and no LLM or event API participated in the backtest.

All deterministic candidates lost money at 5 bps one-way cost. D07 was the report-only leader at -10.94% total return, -0.59 Sharpe, and -14.05% maximum drawdown. Its average gross return was 3.21 bps per traded day versus a 10 bps modeled round trip. Every chronological slice was negative. N01 beat D08 by 0.73 Sharpe and 5.01 percentage points, so the placebo gate failed.

Do not tune or promote this exposed family. Keep `research_pass=false`, `llm_contribution_pass=false`, and `paper_ready_pass=false`. The next family should use slower residual/industry-aware momentum for selection, intraday bars for sparse timing and execution, and real PIT event packets as bounded catalyst or risk overlays. ML stays disabled until data coverage and placebo controls justify reopening it.

Data blockers remain: current-basket survivorship, IEX-only bars, no SIP parity, no event PIT history, no licensed call data, zero formal-forward observations, and no matched TCA. The GDELT live probe returned HTTP 429 with zero records; SEC and Alpha Vantage were not called because required identity/credentials were absent.
