# I-20260924-01: Can Alpaca's free historical options data measure the two option-implied signals that survived 2023-2026?

**Scope**: go/no-go feasibility probe only. No full ingest, no strategy test, no promotion claim. Budget ~90 minutes. Probe script: `scripts/probe_alpaca_options.py`. Raw/intermediate probe artifacts (gitignored): `data/raw/alpaca_options_probe/{iv_rows.parquet, wing_density.csv, http_evidence.json, run_log.jsonl, stats_summary.json}`.

**Question**: arXiv 2608.26115 ("Option-Implied Signals and Crash Risk ... U.S. Equity Options, 2015-2026") uses paid EOD OPRA data and finds the volatility smirk decayed to insignificance in 2023-2026, while two signals stayed significant in every regime (\|t\| > 4 for next-21-day returns): the **IV spread** (ATM call IV − ATM put IV, same strike/expiry, Cremers & Weinbaum 2010) and **risk-neutral skewness** (Bakshi-Kapadia-Madan style). Can Alpaca's free ("Indicative") historical options data — available since 2024-02 per `reports/research/intel/I-20260923-08-free-data-substitutes.md` §1 — measure either one, per stock per day?

**Method**: 20 liquid names (AAPL, MSFT, NVDA, AMZN, META, GOOGL, TSLA, AMD, JPM, XOM, NFLX, COST, AVGO, CRM, BA, DIS, PLTR, SMCI, COIN, MRNA) × 3 sample months (2024-03, 2025-04 tariff crash, 2026-06) × the first 10 US trading days of each month (600 target name-days). Credentials reused from the repo's existing `ALPACA_API_KEY_ID`/`ALPACA_API_SECRET_KEY` via `open_composer.config` (same pattern as `scripts/collect_alpaca_news_packets.py`); never printed or logged. Underlying prices time-matched from the local SIP archive via `open_composer.adapters.data.sip_parquet.load_sip_bars` (daily close for method (a), last-30-minute minute-bar VWAP for method (b)). IV solved with European Black-Scholes + Brent's method (`scipy.optimize.brentq`), q=0 fixed (no point-in-time dividend series wired up for this probe — noted, not solved), r fixed per sample month at a rough T-bill approximation (5.3% / 4.3% / 4.0%) since it is common to both legs and mostly cancels out of the spread. Full run: 283 HTTP calls, peak RSS 330 MB (soft ceiling was 500 MB), wall clock a few minutes.

---

## 1. Endpoint facts (live HTTP evidence, this session)

| Endpoint | Path | Status | Notes |
|---|---|---|---|
| Contracts (reference data) | `GET {trading_root}/v2/options/contracts` (trading_root = `alpaca_api_base_url()`, e.g. `https://paper-api.alpaca.markets/v2`) | 200 | Historical/expired contracts require `status=inactive` explicitly — the field default is `status=active` only (`AssetStatus` has exactly two values, `active`/`inactive`; there is no "as of a past date" parameter anywhere on this request). All three sample months are in the past relative to today (2026-09-24), so `status=inactive` was used throughout. |
| Bars | `GET https://data.alpaca.markets/v1beta1/options/bars` | 200 | Fields: `t,o,h,l,c,v,n,vw` (timestamp, OHLC, volume, trade count, VWAP). Confirmed working back to 2024-03-01 (earliest date tested). Paginated via `next_page_token`. |
| Trades | `GET https://data.alpaca.markets/v1beta1/options/trades` | 200 | Fields: `t,p,s,x,c` (timestamp, price, size, exchange, condition codes). Real prints, e.g. sub-second timestamps. Paginated. |
| **Quotes (historical)** | `GET https://data.alpaca.markets/v1beta1/options/quotes` | **404** `{"message":"Not Found"}` | **No historical quotes endpoint exists on this account/tier at all** — not "latest only," genuinely absent. This is the single most consequential fact in this brief: method (c) cannot run, and nothing in the free tier gives a bid/ask midpoint at a past date. Confirms and sharpens the 2026-09-23 intel brief's "quotes are indicative, not OPRA" framing into a hard capability boundary. |
| Rate limit | (response header on live calls) | — | `X-Ratelimit-Limit: 200` (per minute), confirmed via header on this account — the 2026-09-23 brief flagged this as undocumented; it is now measured. |

**Gotcha #1 — adjusted-root duplicates**: an unfiltered `underlying_symbols=AAPL` contracts query returns **two** `root_symbol` values for the same underlying (`AAPL` and `1AAPL`) covering the same strikes/expiries. Explicit `root_symbol=<SYM>` must be passed or duplicate/adjusted contracts get mixed in (verified: 73 rows unfiltered vs. the correct ~37 with `root_symbol=AAPL`).

**Gotcha #2 — open interest is a frozen last-known value, not a daily series**: contract rows carry `open_interest`, `close_price`, and `close_price_date`, and these ARE populated for expired contracts (e.g. `AAPL240419C00172500`: `open_interest=36296`, `close_price=0.01`, `close_price_date=2024-04-19`) — but `close_price_date` always equals the contract's *last trading day* (here, its expiration date). This is a single static snapshot frozen at last update, not a historical daily OI time series. It refines the 2026-09-23 brief's "one day lagged" framing: for a live/current contract it is "yesterday's OI"; for an expired contract it is "OI as of whenever it stopped updating," which cannot be used to reconstruct what OI was on an arbitrary earlier historical date. This does not block IV spread or skewness (neither needs OI) but rules out any OI-based signal from this endpoint.

**Gotcha #3 — nearest-30-DTE must mean *monthly*, not literally-nearest**: an early design check queried a weekly expiring 2024-04-05 for bars/trades starting 2024-03-01 (~35 DTE) and got back **zero bars, zero trades** — not a data-access problem but because that specific weekly likely wasn't listed yet that far out. The same strike/window against the 2024-04-19 **monthly** (3rd Friday) returned a full month of daily bars starting 2024-03-01. The probe therefore always resolves the nearest **monthly** expiry to (window midpoint + 30 calendar days), not the literal nearest listed expiry — using the naive nearest-any-expiry approach would conflate "not tradable yet" with "no free-tier data" and understate coverage.

**Gotcha #4 — split-adjusted local prices break the strike-band search**: `AVGO` (10-for-1 split effective 2024-07-15) and `SMCI` (10-for-1 split effective 2024-09-30) both returned **zero contracts** for 2024-03, because the local SIP daily archive's `data_source_adjustment="all"` reports split-adjusted (post-split-scale) closes for pre-split dates, while the real contracts listed in March 2024 were quoted at the pre-split nominal strikes (~10x higher). The strike-band search (spot ±15%) computed from adjusted prices found nothing. Both names work fine in 2025-04 and 2026-06 (after their splits). **A full ingest must compute the contracts strike-band filter from unadjusted/nominal historical prices** (or a corporate-action-aware band), even though adjusted prices are correctly used everywhere else in this repo. [Verified via web search: [Broadcom 10-for-1 split completed 2024-07-15](https://www.sec.gov/Archives/edgar/data/1730168/000173016824000077/avgo-05052024x8kxex99.htm); [Super Micro 10-for-1 split effective 2024-09-30](https://www.miaxglobal.com/sites/default/files/alert-files/SMCI_Split_55298.pdf).]

**Side finding, out of this probe's scope but worth a ticket**: `NFLX`/2025-04 also returned zero contracts, for an unrelated reason — the local SIP daily archive prices NFLX at roughly **1/10th** its real level that month (e.g., close of `$91.83` on 2025-04-11 in `data/sip/daily/`, vs. a confirmed real closing price of **$918.29** on 2025-04-11 [Robinhood/market data via WebSearch]). NFLX has not split since 2015 (7-for-1), so this looks like a genuine local SIP data-quality bug, not a corporate action — separate from Alpaca options entirely. Flagging for a follow-up SIP daily audit ticket; not investigated further here (out of budget).

> **Main-session correction (2026-09-24):** the NFLX/2025-04 case is not a data defect. Netflix split 10-for-1 in November 2025, and our local daily archive is split-adjusted, so $91.83 is the adjusted form of $918.29. It is the same cause as gotcha #4 (AVGO, SMCI): the probe needs unadjusted underlying prices to match option strikes. There is no separate NFLX price bug to ticket.


---

## 2. Coverage / noise table per method

600 target name-days; 570 attempted after excluding the 3 zero-contract name-months above (AVGO/2024-03, SMCI/2024-03, NFLX/2025-04 — all explained, all fixable). "Usable" = both call and put legs solved to a finite Black-Scholes IV (no-arbitrage price checks, `brentq` convergence).

| Method | Coverage (usable/attempted) | Mean | SD | p10 | p50 | p90 | mean lag-1 autocorr | time-gap R² vs \|spread\| |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| (a) daily bar close | 38.9% | +4.35% | 9.37% | −0.78% | +1.11% | +11.39% | **−0.15** | 0.029 |
| (b) VWAP of last 30 min of trades | 30.5% | +3.81% | 7.62% | −0.47% | +1.09% | +10.05% | **−0.24** | 0.008 |
| (c) historical quotes | not runnable — endpoint returns HTTP 404 on this account | | | | | | | |

Literature scale for comparison (arXiv 2608.26115, OPRA EOD, 2015-2026): mean IV spread near **−1%**, SD "a few %." Both free-tier methods land with the **wrong sign** (positive, not negative) at the mean and median, and with **2-3x the dispersion** the literature reports, in the pooled 3-month sample.

**Failure-mode breakdown (method a, 570 attempted × 2 legs = 1,140 leg-solves)**: 694 legs (61%) failed with `no_price` — the specific ATM contract simply had **zero bars/trades that day** — vs. only 1 leg rejected for violating a no-arbitrage price bound. So the coverage bottleneck is **liquidity/presence**, not bad quote quality: when a print exists, it almost always solves to a sane IV. This matters for the verdict below — it means the noise problem is structural (no quote midpoint, so a raw last trade is the only price available) rather than a data-cleaning problem.

**Regime breakdown (method a) — the reason this is not a flat no-go**:

| Sample month | Coverage | Mean | SD | Median |
|---|---:|---:|---:|---:|
| 2024-03 | 28.3% | +10.2% | 14.9% | +6.7% |
| 2025-04 (tariff crash) | 37.9% | +5.0% | 7.9% | +2.5% |
| 2026-06 | **49.5%** | **+0.83%** | **2.96%** | **+0.55%** |

There is a clean, monotonic improvement from the earliest sample month to the most recent one on every axis: coverage roughly doubles (28%→50%), SD falls by 5x (14.9%→2.96%, finally landing in the literature's "a few %" range), and the median converges toward (though never crosses the sign of) the paper's scale. This reads as the free tier's practical usability improving as the feed/market matures since its Feb-2024 launch — directly relevant given this project's own "recent regime, not 10-year durability" mandate (`docs/research-mission.zh.md`).

**Day-to-day autocorrelation**: negative for both methods (−0.15, −0.24), averaged across 30/25 symbol-month series with enough points to measure. The task's own framing applies directly here: "a real signal is persistent; timing noise is not." A persistent, slowly-varying risk-premium-like construct (which is what the paper claims to have found and what would make this worth building) should show non-negative day-to-day autocorrelation. Negative autocorrelation of this magnitude is the textbook signature of alternating measurement noise (bid/ask bounce: today's last print near the ask, tomorrow's near the bid), not a persistent signal.

**Call/put trade-time mismatch**: contributes very little to the variance (R² = 0.008–0.029 of \|spread\| against the seconds-gap between the call's and put's last trade). This rules out simple timing asynchrony as the dominant noise source (a hypothesis that looked plausible from a single-symbol spot check during design, before the full run). The more likely explanation, consistent with the endpoint facts above, is **bid/ask-side bias in last-trade prices** (no historical quote midpoint is available at all — confirmed 404 — so every price here is a raw trade print, which options-market literature on retail order-flow imbalance would expect to sit non-randomly on the ask for calls and the bid for puts).

---

## 3. Is risk-neutral skewness computable at all?

Checked separately: on each name-month's last window day, pulled bars for **every** strike in the fetched chain (not just ATM) and counted valid (non-null, `close>0`, `high≥low`) daily bars, bucketed by moneyness.

- Per-strike valid-bar coverage ranged **36%–59%** across 5 moneyness buckets (deep OTM put wing, OTM put wing, near-ATM, OTM call wing, deep OTM call wing) × both rights — no strong asymmetry between the put wing and call wing.
- Usable **OTM strikes per side** (moneyness >5% from spot) per name-month: median **12**, IQR 7–17, min 1, max 35 (n=111 symbol-month-right cells).
- A BKM-style numerical integration typically wants on the order of a handful to a couple dozen valid OTM strikes per side; a median of 12 is workable, but the 25th-percentile of 7 (and occasional single-digit-or-1 cells) means a real implementation needs an explicit minimum-strike-count quality gate rather than assuming every name-day is estimable.

**Verdict on this sub-question**: skewness is computable, mechanically, more often than not — but it inherits the exact same last-trade/no-quotes limitation as the IV spread (no bid/ask midpoint anywhere in the free tier), so its noise/persistence properties are unverified by this probe and should not be assumed to be better just because more strikes are available. That is a separate, cheap follow-up test, not yet run.

---

## 4. Rate limits and full-ingest extrapolation (500 names, 2024-02 to 2026-09)

Measured: 283 HTTP calls covered 60 name-months (≈4.7 calls/name-month) at the batched design this probe used — one contracts call, one batched bars call, 1-2 paginated trades calls, and one wing-bars call **per (name, month)**, each spanning the full date window rather than per-day calls. This batching (not per-day requests) is the reason the probe stayed cheap; it is the recommended design for a full ingest too.

Extrapolating to daily (not 10-day-sampled) coverage for the full job requires slightly more pagination per name-month (full-month trade volume, full-month wing chain instead of one representative day) — estimated **~7 calls/name-month** (documented assumption, not measured at full scale):

- Universe/period: 500 names × ~32 months (2024-02 → 2026-09) = 16,000 name-months.
- Calls: 16,000 × 7 ≈ **112,000 HTTP calls**.
- Time: at the measured `X-Ratelimit-Limit: 200`/min, paced conservatively at ~150/min to leave 429 headroom → ≈747 minutes of API time ≈ **~12-13 hours**, realistically **~13-16 hours wall-clock** with processing/IV-solving overhead, which the probe showed is small relative to API time.
- Storage (derived features only, not raw ticks):
  - IV-spread rows: 500 × 32 × ~21 trading days × 2 methods ≈ 672,000 rows × ~150 bytes (parquet) ≈ **~100 MB**.
  - Full daily wing bars for skewness: 500 × 32 × 21 × ~34 valid strikes/name-month (this probe's measured mean) ≈ 11.4M rows × ~120 bytes ≈ **~1.4 GB**.
  - Contracts reference table: well under 50 MB.
  - **Total ≈ 1.5-2 GB parquet** — trivial against the box's ~27 GB free disk. Do **not** persist raw trade-level ticks long-term (that would run tens of GB); derive VWAP at ingest time and keep only a small audit sample.

This extrapolation is analytical (scaled from the measured 60-name-month rate), not a second live run — consistent with the probe budget.

---

## 5. Verdict: GO-with-caveats (narrow), NO-GO (as literally specified)

**As a direct reproduction of arXiv 2608.26115's IV-spread construct: NO-GO.** Three independent lines of evidence point the same way: (1) historical quotes are confirmed unavailable (HTTP 404) so every price is a raw last trade, not the bid/ask midpoint the literature construct assumes; (2) the resulting spread has the **wrong sign** and 2-5x the literature's dispersion in every one of the 3 sample months; (3) day-to-day autocorrelation is **negative**, the opposite signature of the persistent signal the paper reports. Recommending a full 500-name/32-month backfill (~13-16 hours of API budget, per §4) on top of this would be spending real compute on a construct that, on the evidence gathered here, is not measuring the same object the paper found predictive.

**As a narrower, honestly-scoped exploration: GO-with-caveats**, specifically:
1. Do not assume the paper's coefficients or significance transfer — the free-tier construct is a **different, noisier proxy** (last-trade-based, not quote-midpoint-based) and must be re-tested for its own predictive value from scratch, matched against a quant-only baseline, before any promotion-track claim.
2. Restrict any pilot to the **most recent regime** (2025-2026H1-ish, where this probe found coverage ~50% and SD already in the literature's "a few %" range) rather than backfilling 2024, which this probe found to be dominated by noise (SD 14.9%, coverage 28%).
3. Any use requires an explicit **liquidity/coverage quality gate** per name-day (e.g., require the trade to fall inside a defined pre-close window and reject `no_price` legs) — 61% of leg-failures in this probe were simply "contract didn't trade that day," which a downstream model must not silently impute.
4. Risk-neutral skewness has a workable strike count (median 12 OTM strikes/side) but shares the same no-quotes limitation and has **not** been checked for autocorrelation/predictive signature — that is the next cheap test, not yet run, before any ingest decision on skewness specifically.
5. Before any backfill spend, fix the one identified engineering issue (split-adjusted local prices used for the strike-band search; NFLX/2025-04 is the same cause, see the correction above) — both are cheap, both artificially depress measured coverage today, and neither is a free-tier data limitation.

**Recommended next step, if pursued**: a small pilot (e.g., 50-100 liquid names, 2025-06 onward only, with the quality gate from caveat 3) to test whether the recent-regime, quality-gated version of either signal actually has predictive power and non-negative persistence — a cheap decisive test — **before** committing to the full 500-name/2024-02 backfill costed in §4.

---

## Appendix: files

- Probe script: `scripts/probe_alpaca_options.py` (`--quick` for a 1-symbol/1-month smoke test; no args for the full 20×3 probe).
- `data/raw/alpaca_options_probe/iv_rows.parquet` — 1,140 rows, per (symbol, month, day, method) IV spread and inputs.
- `data/raw/alpaca_options_probe/wing_density.csv` — 4,600 rows, per (symbol, month, strike, right) wing coverage.
- `data/raw/alpaca_options_probe/http_evidence.json`, `run_log.jsonl` — endpoint status codes and per-call log, no secrets.
- `data/raw/alpaca_options_probe/stats_summary.json` — the aggregate numbers this brief quotes.
- `capabilities/registry.yaml`'s `options.trial_chain` (provider: `unconfigured`) is the natural place to record `provider: alpaca` plus these caveats **if** a follow-up decides to move forward on the narrow GO-with-caveats path above; not changed by this probe per its own scope limits.
