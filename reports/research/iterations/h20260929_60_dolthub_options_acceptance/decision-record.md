# Decision Record: h20260929_60_dolthub_options_acceptance (T-20260929-60)

Data acceptance, not a strategy backtest. Criteria were written to `results.json` (`criteria`, 2026-09-29 16:31 UTC) before this task's first DoltHub data request; nothing was changed afterwards.

## P1 DoltHub post-no-preference/options as option pricing source

- Decision: **fail** under the frozen rule (T-61/62/63 stay blocked, T-64 goes to the owner). Source of every number: `results.json` (`verdict`, `tables`).
- Coverage (exact, all 1,919 US sessions 2019-02-09..2026-09-28): SPY 61.4% / 87.5%, AAPL 62.0% / 87.9%, NVDA 61.7% / 87.6%, TSLA 53.9% / 87.6% (since 2019 / since 2024; need 85% / 90%). QQQ has no rows at all. IWM, SMH and TQQQ were absent on three probe dates, MSFT/AMZN/GOOGL/META present.
- Shape of the gaps: no option data before 2019-05-10 (one day in 2019), 2020-01..2024-08 only about 58% of sessions (about 3 of 5 weekdays), 2024-09-04 onward dense (post-hoc, not a criterion: SPY 97.9%, AAPL 98.5%). NVDA gap days have larger moves (ratio 1.44) than present days.
- Spread and quotes pass for SPY, AAPL, NVDA, TSLA: ATM relative spread median 0.7% / 3.5% / 2.7% / 1.8% (limits 3% / 10%); band bad-quote share 0.04% / 0.40% / 0.02% / 0.03% (limit 2%), no stale quotes in the clean window. 130-210 contracts per symbol-day, 3-4 expiries, max about 53-56 days out.
- Snapshot time: end of day d (implied spot from put-call parity matches the SIP close of d within +0.1..0.2%, the next open only within +-1..3%). The literal parity criterion (0.10%) fails on the fixed clean window (SPY 0.15%, AAPL 0.33%, NVDA 0.39%, TSLA 0.40%, n=4-5 days) partly from carry bias of the unadjusted formula. SIP daily bars are dividend-adjusted, so parity cannot be judged against them on older dates.
- Caveats: chain-level checks are on a seeded random sample (169 days per symbol) plus the last 13 sessions, not the full chain; volatility_history is partial (2019-02..2020-08 only).
- Next: coordinator sets T-61/62/63 to blocked and T-64 to ready. If the owner wants to try anyway, a NEW preregistered contract on the dense window 2024-09-04..2026-09-28 with SPY/AAPL/NVDA/TSLA/MSFT/AMZN/GOOGL/META (about 2 years, no stress window, no QQQ/IWM/SMH/TQQQ) is the only free-data path; T-63's ETF targets and stress period are not available in free data.
