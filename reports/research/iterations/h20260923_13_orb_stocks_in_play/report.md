# H-20260923-13: Stocks-in-Play opening-range breakout -- backtest report

Iteration `h20260923_13_orb_stocks_in_play`. SIP01/SIP02 are the promotable long-only candidates; SIP03 (long-short) is a fidelity diagnostic only, never eligible for promotion. RD (random direction) and RL (random non-in-play liquid stock) controls are run for SIP01/SIP02 only, 10 seeds each, at the primary cost cell (10bp/side, same-bar-conservative stop fill).

## Window status

| window | date range | status |
|---|---|---|
| design | 2016-01-04 .. 2022-12-30 | pending |
| select | 2023-09-18 .. 2025-12-31 | complete |
| report_2026 | 2026-01-02 .. 2026-09-17 | complete |

Pending windows: design. Resume with, e.g.:

```
./scripts/run_capped.sh --mem 1.2G -- uv run python scripts/run_h20260923_13_orb_stocks_in_play.py --stage 1 --windows design
./scripts/run_capped.sh --mem 1.2G -- uv run python scripts/run_h20260923_13_orb_stocks_in_play.py --stage 2 --windows design
./scripts/run_capped.sh --mem 1.2G -- uv run python scripts/run_h20260923_13_orb_stocks_in_play.py --stage 3 --windows design
uv run python scripts/run_h20260923_13_orb_stocks_in_play.py --stage report
```

## Headline: select (primary cost 10bp/side, same-bar-conservative)

| candidate | CAGR | Sharpe | max DD | hit rate | avg R | trades | exposure | turnover(ann.) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| SIP01 | -27.1% | -8.40 | -51.3% | 8.0% | -0.29 | 4755 | 41.3% | 103.74 |
| SIP02 | -19.7% | -6.12 | -39.3% | 10.7% | -0.14 | 3763 | 32.7% | 80.46 |
| SIP03 | -82.4% | -18.90 | -98.1% | 7.9% | -0.31 | 9145 | 79.5% | 606.64 |
| bench:SPY | 22.7% | n/a | -18.8% | n/a | n/a | n/a | n/a | n/a |
| bench:BIL | 4.8% | n/a | -0.0% | n/a | n/a | n/a | n/a | n/a |
| bench:equal_weight_screen_sip01_sip03 | 74.9% | n/a | -22.1% | n/a | n/a | n/a | n/a | n/a |
| bench:equal_weight_screen_sip02 | 140.5% | n/a | -26.9% | n/a | n/a | n/a | n/a | n/a |

### Cost sensitivity (select, same-bar-conservative)

| candidate | 5bp | 10bp | 20bp | commission_only | 20bp_plus_commission |
|---|---:|---:|---:|---:|---:|
| SIP01 | -19.2% | -27.1% | -40.7% | -12.5% | -42.0% |
| SIP02 | -12.9% | -19.7% | -31.8% | -6.6% | -32.6% |
| SIP03 | -68.9% | -82.4% | -94.4% | -50.6% | -94.9% |

### Stop-fill variant (select, 10bp)

| candidate | same_bar_conservative CAGR | one_bar_late CAGR |
|---|---:|---:|
| SIP01 | -27.1% | -2.2% |
| SIP02 | -19.7% | -7.6% |
| SIP03 | -82.4% | -35.7% |

### Trade economics (select, 10bp, both stop-fill variants)

Gross R is pure price movement relative to the 10%-of-ATR14 stop distance, sized as if the trade received its full 1% risk allocation -- independent of the leverage cap and of costs. Capped gross R applies the same price movement to the position actually taken, after `leverage_cap x slot_capital` limits the notional (1.0x for SIP01/SIP02, 4.0x for SIP03) -- this is smaller in magnitude than gross R whenever the cap binds, which for a 1.0x cap against a 10%-of-ATR14 stop is most trades. Net R is capped gross R after round-trip cost, commission and (for shorts) borrow: `capped gross R - cost-in-R == net R` per trade, exactly (gross R does *not* reconcile this way -- it is a sizing-independent trade-quality figure, shown for reference). Win rate is net (`net_pnl > 0`); gross win rate (`gross R > 0`) is shown alongside it.

| candidate | stop-fill | trades | gross R/trade | median gross R | capped gross R/trade | median capped gross R | net R/trade | median net R | win rate | gross win rate | cost-in-R mean | cost-in-R median | cost-in-R p25 | cost-in-R p75 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| SIP01 | same_bar_conservative | 4755 | -0.29 | -1.00 | -0.10 | -0.31 | -0.30 | -0.51 | 8.0% | 8.6% | 0.20 | 0.20 | 0.20 | 0.20 |
| SIP01 | one_bar_late | 4755 | 0.42 | -1.00 | 0.18 | -0.29 | -0.02 | -0.49 | 13.2% | 13.8% | 0.20 | 0.20 | 0.20 | 0.20 |
| SIP02 | same_bar_conservative | 3763 | -0.14 | -1.00 | -0.07 | -0.31 | -0.27 | -0.51 | 10.7% | 11.2% | 0.20 | 0.20 | 0.20 | 0.20 |
| SIP02 | one_bar_late | 3763 | 0.23 | -1.00 | 0.10 | -0.30 | -0.09 | -0.50 | 14.4% | 15.0% | 0.20 | 0.20 | 0.20 | 0.20 |
| SIP03 | same_bar_conservative | 9145 | -0.31 | -1.00 | -0.30 | -1.00 | -0.86 | -1.47 | 7.9% | 8.4% | 0.57 | 0.59 | 0.38 | 0.80 |
| SIP03 | one_bar_late | 9145 | 0.38 | -1.00 | 0.35 | -1.00 | -0.21 | -1.46 | 12.8% | 13.4% | 0.57 | 0.59 | 0.38 | 0.80 |

### By year (select, primary cell)

| candidate | year | CAGR | max DD | sessions |
|---|---:|---:|---:|---:|
| SIP01 | 2023 | -30.7% | -9.9% | 73 |
| SIP01 | 2024 | -27.0% | -28.3% | 252 |
| SIP01 | 2025 | -26.1% | -25.7% | 250 |
| SIP02 | 2023 | -14.5% | -4.3% | 73 |
| SIP02 | 2024 | -14.8% | -16.0% | 252 |
| SIP02 | 2025 | -25.8% | -25.6% | 250 |
| SIP03 | 2023 | -84.5% | -41.3% | 73 |
| SIP03 | 2024 | -84.7% | -84.7% | 252 |
| SIP03 | 2025 | -78.9% | -78.4% | 250 |

### RD / RL placebo controls (select, primary cell)

| candidate | control | real CAGR | median seed CAGR | seed CAGR range |
|---|---|---:|---:|---|
| SIP01 | RD | -27.1% | -42.9% | -45.7% ~ -41.8% |
| SIP01 | RL | -27.1% | -22.5% | -23.8% ~ -20.7% |
| SIP02 | RD | -19.7% | -33.0% | -34.3% ~ -31.6% |
| SIP02 | RL | -19.7% | -5.8% | -6.3% ~ -5.3% |

## Headline: report_2026 (primary cost 10bp/side, same-bar-conservative)

| candidate | CAGR | Sharpe | max DD | hit rate | avg R | trades | exposure | turnover(ann.) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| SIP01 | -18.2% | -2.96 | -13.5% | 9.6% | -0.15 | 1494 | 42.0% | 102.96 |
| SIP02 | -23.4% | -6.05 | -17.5% | 11.4% | -0.13 | 1497 | 42.1% | 103.20 |
| SIP03 | -77.2% | -13.36 | -64.7% | 9.2% | -0.26 | 2887 | 81.1% | 488.41 |
| bench:SPY | 15.7% | n/a | -8.9% | n/a | n/a | n/a | n/a | n/a |
| bench:BIL | 3.1% | n/a | -0.3% | n/a | n/a | n/a | n/a | n/a |
| bench:equal_weight_screen_sip01_sip03 | 126.5% | n/a | -8.4% | n/a | n/a | n/a | n/a | n/a |
| bench:equal_weight_screen_sip02 | 723.9% | n/a | -19.2% | n/a | n/a | n/a | n/a | n/a |

### Cost sensitivity (report_2026, same-bar-conservative)

| candidate | 5bp | 10bp | 20bp | commission_only | 20bp_plus_commission |
|---|---:|---:|---:|---:|---:|
| SIP01 | -9.3% | -18.2% | -33.4% | -2.1% | -35.1% |
| SIP02 | -15.1% | -23.4% | -37.7% | -7.5% | -38.7% |
| SIP03 | -63.0% | -77.2% | -91.3% | -45.8% | -92.2% |

### Stop-fill variant (report_2026, 10bp)

| candidate | same_bar_conservative CAGR | one_bar_late CAGR |
|---|---:|---:|
| SIP01 | -18.2% | 23.0% |
| SIP02 | -23.4% | 2.4% |
| SIP03 | -77.2% | 0.9% |

### Trade economics (report_2026, 10bp, both stop-fill variants)

Gross R is pure price movement relative to the 10%-of-ATR14 stop distance, sized as if the trade received its full 1% risk allocation -- independent of the leverage cap and of costs. Capped gross R applies the same price movement to the position actually taken, after `leverage_cap x slot_capital` limits the notional (1.0x for SIP01/SIP02, 4.0x for SIP03) -- this is smaller in magnitude than gross R whenever the cap binds, which for a 1.0x cap against a 10%-of-ATR14 stop is most trades. Net R is capped gross R after round-trip cost, commission and (for shorts) borrow: `capped gross R - cost-in-R == net R` per trade, exactly (gross R does *not* reconcile this way -- it is a sizing-independent trade-quality figure, shown for reference). Win rate is net (`net_pnl > 0`); gross win rate (`gross R > 0`) is shown alongside it.

| candidate | stop-fill | trades | gross R/trade | median gross R | capped gross R/trade | median capped gross R | net R/trade | median net R | win rate | gross win rate | cost-in-R mean | cost-in-R median | cost-in-R p25 | cost-in-R p75 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| SIP01 | same_bar_conservative | 1494 | -0.15 | -1.00 | 0.01 | -0.40 | -0.19 | -0.60 | 9.6% | 10.0% | 0.19 | 0.20 | 0.20 | 0.20 |
| SIP01 | one_bar_late | 1494 | 0.60 | -1.00 | 0.39 | -0.38 | 0.20 | -0.58 | 15.1% | 15.7% | 0.19 | 0.20 | 0.20 | 0.20 |
| SIP02 | same_bar_conservative | 1497 | -0.13 | -1.00 | -0.06 | -0.41 | -0.25 | -0.61 | 11.4% | 11.8% | 0.19 | 0.20 | 0.20 | 0.20 |
| SIP02 | one_bar_late | 1497 | 0.46 | -1.00 | 0.22 | -0.38 | 0.02 | -0.58 | 16.4% | 16.9% | 0.19 | 0.20 | 0.20 | 0.20 |
| SIP03 | same_bar_conservative | 2887 | -0.26 | -1.00 | -0.25 | -1.00 | -0.72 | -1.40 | 9.2% | 9.6% | 0.47 | 0.44 | 0.30 | 0.66 |
| SIP03 | one_bar_late | 2887 | 0.48 | -1.00 | 0.48 | -1.00 | 0.01 | -1.38 | 15.0% | 15.4% | 0.47 | 0.44 | 0.30 | 0.66 |

### By year (report_2026, primary cell)

| candidate | year | CAGR | max DD | sessions |
|---|---:|---:|---:|---:|
| SIP01 | 2026 | -18.2% | -13.5% | 178 |
| SIP02 | 2026 | -23.4% | -17.5% | 178 |
| SIP03 | 2026 | -77.2% | -64.7% | 178 |

### RD / RL placebo controls (report_2026, primary cell)

| candidate | control | real CAGR | median seed CAGR | seed CAGR range |
|---|---|---:|---:|---|
| SIP01 | RD | -18.2% | -38.7% | -41.3% ~ -33.7% |
| SIP01 | RL | -18.2% | -22.8% | -26.2% ~ -16.9% |
| SIP02 | RD | -23.4% | -38.1% | -41.3% ~ -36.2% |
| SIP02 | RL | -23.4% | -7.2% | -11.0% ~ -5.2% |

## Adoption-rule gates (evaluated exactly as preregistered in the hypothesis card)

| candidate | gate | value | threshold | direction | pass |
|---|---|---:|---:|:-:|:-:|
| SIP01 | design_beats_equal_weight_eligible_universe | n/a | 0.0000 | > | n/a |
| SIP01 | design_beats_rd_placebo_median | n/a | 0.0000 | > | n/a |
| SIP01 | design_beats_rl_placebo_median | n/a | 0.0000 | > | n/a |
| SIP01 | design_positive_net_of_20bp_plus_commission | n/a | 0.0000 | > | n/a |
| SIP01 | select_window_cagr_10bp | -0.2710 | 0.5000 | >= | FAIL |
| SIP01 | select_window_max_drawdown_10bp | -0.5128 | -0.3500 | >= | FAIL |
| SIP01 | select_window_placebo_beat_rate | 0.5000 | 0.9000 | >= | FAIL |
| SIP02 | design_beats_equal_weight_eligible_universe | n/a | 0.0000 | > | n/a |
| SIP02 | design_beats_rd_placebo_median | n/a | 0.0000 | > | n/a |
| SIP02 | design_beats_rl_placebo_median | n/a | 0.0000 | > | n/a |
| SIP02 | design_positive_net_of_20bp_plus_commission | n/a | 0.0000 | > | n/a |
| SIP02 | select_window_cagr_10bp | -0.1974 | 0.5000 | >= | FAIL |
| SIP02 | select_window_max_drawdown_10bp | -0.3935 | -0.3500 | >= | FAIL |
| SIP02 | select_window_placebo_beat_rate | 0.5000 | 0.9000 | >= | FAIL |

- SIP01: all gates evaluated = False, adoption_pass = False
- SIP02: all gates evaluated = False, adoption_pass = False

**Overall verdict: `pending`**

## Published numbers (reference only, long+short combined -- see caveat)

SIP01/SIP02 above are long-only; the paper's own headline (Sharpe 2.81, 41.6% annualized, 1,637% total, -12% max drawdown) is a combined long+short number with no long-only split ever published, so it is **not** a same-basis comparison for SIP01/SIP02. SIP03 (long-short, this report's diagnostic row, never promotable) is the only candidate meant to be read against it, as an implementation-fidelity check.

- `paper_headline_long_short`: {"total_return": 16.37, "annualized_return": 0.416, "sharpe": 2.81, "max_drawdown": -0.12} -- Zarattini/Barbon/Aziz SSRN 4729284, 2016-2023, long+short combined, no long-only split ever published, zero-slippage MATLAB backtest, $0.0035/share commission only (no bps).
- `paper_base_no_relvol_filter`: {"total_return": 0.29, "sharpe": 0.48} -- same paper, same window, relative-volume filter removed.
- `spy_buy_and_hold_paper_window`: {"total_return": 1.98, "sharpe": 0.78} -- same paper, same 2016-2023 window.
- `quantconnect_replication_2016_only`: {"sharpe": 2.396, "spy_sharpe": 0.836} -- independent QuantConnect replication, 2016 only, top-1000-liquid universe.
- `etf_orb_known_negative_oos`: {} -- dir:orb_etf_opening_range_breakout OOS 2024-01-02..2026-09-17: QQQ -3.0%, SPY -6.0% annualized; random-direction placebo captured 92.7-92.9% of real return. Reused as a reference floor, not re-simulated here.

### SIP03 fidelity vs. the published paper

Paper (2016-2023, long+short, commission-only cost model, zero slippage): total return 16.37x, annualized 41.6%, Sharpe 2.81, max DD -12.0%.

SIP03 below is shown at `commission_only` cost (matching the paper's own cost model exactly, isolating period from cost-methodology) and `same_bar_conservative`, for every window this run has actually completed. **None of the windows below overlap the paper's 2016-2023 study period** -- design (2016-2022) is the only window that would overlap it, and design has not been run in this pass (see Window status above; resumable command included). Until design exists, a poor number here cannot yet distinguish 'replication is unfaithful' from 'edge decayed post-publication' -- it can only be read as this candidate's performance in a period the paper never claimed to cover. The design-window run is the direct fidelity test.

| window | total return | annualized | Sharpe | max DD | trades |
|---|---:|---:|---:|---:|---:|
| select | -0.80x | -50.6% | -7.71 | -80.1% | 9145 |
| report_2026 | -0.35x | -45.8% | -5.62 | -35.4% | 2887 |

## Data-quality diligence (Stage 0)

```json
{
  "sip_minute_years": [
    2023,
    2024,
    2025,
    2026
  ],
  "sip_hist_minute_years": [
    2016,
    2017,
    2018,
    2019,
    2020,
    2021,
    2022
  ],
  "sip_daily_years": [
    2016,
    2017,
    2018,
    2019,
    2020,
    2021,
    2022,
    2023,
    2024,
    2025,
    2026
  ],
  "premarket_probe_symbol": "AAPL",
  "premarket_probe_date": "2024-01-03",
  "premarket_probe_total_rows": 750,
  "premarket_probe_rows_before_0930_et": 198,
  "premarket_probe_earliest_et_time": "04:00:00",
  "generated_at": "2026-09-23T08:56:19.620984-04:00"
}
```

## Methodology notes and disclosed deviations

- Doji = `candle_open == candle_close` exactly (the paper's own rule; a disclosed correction of `scripts/run_h20260918_02_orb_etf.py`'s 5%-of-range approximation).
- No hand-built symbol-to-shard index was written (a disclosed implementation-strategy departure from `engine-design.md`'s sketch, not from any preregistered rule/parameter/window/candidate/gate); see the script's module docstring for the reasoning.
- RD's random direction draw (±1) is unconstrained by a candidate's own `allow_short` even for long-only SIP01/SIP02, matching `search-space.json`'s literal control description and this project's existing ETF-ORB placebo convention. This makes RD a strictly more permissive control than the candidate itself for long-only candidates, which is conservative for adoption-rule gate (b).
- RL uses the candidate's own long/short mechanics (`allow_long`/`allow_short`) on a different, randomly-drawn set of eligible-but-not-top-20 symbols -- "same mechanics, different selection", per `search-space.json`.
- The equal-weight-eligible-universe benchmark uses each eligible symbol's own prior-close-to-close daily return (from the same `data/sip/daily` eligibility table), not a same-day open-to-close or full-path return, since Stage 3 deliberately does not fetch full-day paths for the whole eligible universe (only the ~20-150 selected/drawn names per day) -- a disclosed, conservative proxy.
- Position sizing follows `candidate-manifest.json` exactly per candidate (`leverage_cap` 1.0x for SIP01/SIP02, the paper's own 4.0x for SIP03), not a single house-wide constant.

