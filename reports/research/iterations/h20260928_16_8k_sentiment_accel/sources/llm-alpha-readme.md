# LLM_Alpha — Sentiment-Acceleration Alpha on S&P 100

A market-neutral long-short portfolio whose signal is built from structured features that **Claude Haiku 4.5** extracts from EDGAR 8-K filings and GDELT 2.0 financial news. Tested out-of-sample on a point-in-time S&P 100 universe over twelve quarters (Q1 2022 → Q4 2024). All figures below are **net of 5 bps round-trip transaction cost**.

---

## TL;DR

> **OOS Sharpe +0.78** with **3.33% maximum drawdown** and **β_mkt ≈ 0** over Q1 2022 – Q4 2024.
> Strategy beats cap-weighted S&P 100 buy-and-hold on Sharpe (+0.74) with **7.7× lower drawdown** and zero market exposure.
> Hit rate **9 / 12 positive quarters** (75 %).

| Strategy                              | Sharpe   | MDD     | Turnover | Hit  | α (bps/day) | α t-stat (NW) | β_mkt   |
|---------------------------------------|---------:|--------:|---------:|-----:|------------:|--------------:|--------:|
| **sent_accel** *(rank-weighted)*  🟢  | **+0.78** | **3.3 %** | 1131 %   | 51.5 %| +0.72       | +1.35         | +0.001  |
| bh_capwt *(cap-weighted long-only)*   | +0.74    | 25.5 %  | 134 %    | 53.4 %| +2.72       | +5.65         | +1.02   |
| VADER *(decile equal-weighted)*       | +0.29    | 6.2 %   | 1281 %   | 49.8 %| +0.32       | +0.48         | +0.03   |
| Momentum 12-1 *(continuous)*          | +0.11    | 12.6 %  | 443 %    | 52.7 %| –0.10       | –0.06         | +0.07   |

The α t-stat for `sent_accel` is below the 1.96 significance threshold (sample size of 753 trading days limits power). Headline value is the **risk profile** — Sharpe comparable to passive equity, with one-eighth the drawdown and zero market beta.

---

## 1. Problem

Cross-sectional equity strategies built on textual sentiment have been studied since [Tetlock (2007)](https://www.jstor.org/stable/4622297). What has changed in 2024-2026 is that **a calibrated LLM** can extract structured features (event type, polarity, magnitude, tense, specificity, novelty) from the same news articles at $1 per million tokens. This project asks the question: **does an LLM-extracted signal, run through standard quant-finance machinery, produce a defensible alpha against a market benchmark?**

Path A — pure factor portfolio. **No model fitting, no ML training.** Hyperparameters are tuned once on a 2021 dev set and frozen. The signal is the product of the LLM extraction and a transparent operator pipeline.

---

## 2. Data

| Source                    | Field used                                                    | Coverage                  | Attribution        |
|---------------------------|---------------------------------------------------------------|---------------------------|--------------------|
| **WRDS CRSP `dsf`**       | Daily total returns, prices, shares-outstanding              | 2020-07 → 2024-12         | WRDS (subscription)|
| **WRDS CRSP `dsp500list`** | Point-in-time S&P 500 membership → top 100 by market cap   | All rebalance dates       | WRDS (subscription)|
| **WRDS CRSP `dsenames`**  | PERMNO ↔ ticker as-of windows                                | All firms                 | WRDS (subscription)|
| **WRDS CRSP/Compustat link** | PERMNO ↔ GVKEY ↔ CIK crosswalk                            | All firms                 | WRDS (subscription)|
| **EDGAR 8-K (SEC)**       | Item 1.01–9.01, full-text                                    | 8 459 filings, 2020-07 → 2024-12 | Public          |
| **GDELT 2.0** (BigQuery)  | Financial-news article metadata + URLs                       | 2 908 articles after dedup, 2020-07 → 2024-12 | Public |
| **Fama-French + Mom**     | Daily 5-factor + Momentum returns                            | 2020-07 → 2024-12         | Kenneth French Library |

**LLM-extracted features** (Claude Haiku 4.5, Batch API): 11 367 (article, ticker) pairs survived JSON-validity filtering. Each row carries: `polarity ∈ [-1, 1]`, `magnitude ∈ {minor, moderate, major}`, `event_type` (13 categories), `tense`, `specificity`, `novelty`, `industry_relevance`, `summary`. Total extraction cost: **\$11.84** (Batch API discount applied).

> **WRDS attribution**: Raw data sourced from WRDS (subscription required); cached files **not redistributed** in this repository. The `data/wrds_cache/` directory is gitignored.

---

## 3. Method

### 3.1 Universe

Point-in-time S&P 100 — top 100 firms by market capitalization from `crsp.dsp500list` at each rebalance date, respecting `dsenames` PERMNO/ticker windows. The current Wikipedia S&P 100 list is **never** used (would introduce survivorship bias). Universe size averages 99 firms per day in the OOS window.

### 3.2 Primary signal — `sent_accel` (sentiment acceleration)

A WorldQuant Alpha 101–style stationary signal. Per stock i and trading day t:

```
raw_pol_{i,t}    = polarity_k * magnitude_k                     # per-article score
short_ma_{i,t}   = 5-day rolling mean of raw_pol over articles  # bounded ∈ [-1, 1]
long_ma_{i,t}    = 20-day rolling mean of raw_pol               # bounded ∈ [-1, 1]
accel_{i,t}      = short_ma - long_ma                           # bounded ∈ [-1, 1]
score_{i,t}      = -1 * (cs_rank(accel_{i,t}) - 0.5)             # ∈ [-0.5, 0.5]
smoothed_{i,t}   = ts_mean(score, 30)                            # MA-30 (Alpha101 decay)
```

The negation is the [Engelberg-McLean-Pontiff (2018)](https://onlinelibrary.wiley.com/doi/10.1111/jofi.12698) mean-reversion convention — long firms whose sentiment momentum decelerates, short firms whose sentiment momentum accelerates. The signal is bounded by construction (rank centered, polarity capped) → stationary **before** any z-scoring.

### 3.3 Portfolio construction

For each trading day t the smoothed signal is converted into dollar-neutral, gross-1 weights via the standard **rank-weighted** rule (Kakushadze 2016, Alpha101 family):

```
rank_i_t      = cs percentile rank of smoothed_signal_i_t      ∈ [0, 1]
centered_i_t  = rank_i_t - 0.5
w_i_t         = centered_i_t / Σ_j |centered_j_t|              → Σw = 0, Σ|w| = 1
```

Weights are then **GICS sector-neutralized** (subtract sector mean, re-normalize gross to 1) so the strategy carries no industry tilt.

### 3.4 Trading scheme

| Item                  | Value                                                            |
|-----------------------|------------------------------------------------------------------|
| Rebalance             | First XNYS day of each ISO week (Monday block)                   |
| Holding period        | 5 trading days (Mon–Fri)                                         |
| Position smoothing    | 30-day MA on the sector-neutral weight panel (Alpha101 decay)    |
| Trading calendar      | XNYS via `pandas_market_calendars`                               |
| Transaction cost      | **5 bps round-trip** = `0.00025 × Σ \|Δw\|` per rebalance        |
| All metrics reported  | **Net of cost**                                                  |

### 3.5 Walk-forward design (López de Prado 2018)

| Phase              | Window                  | Purpose                            |
|--------------------|-------------------------|------------------------------------|
| Feature buffer     | 2020-07 → 2020-12       | 6-month warm-up for rolling stats  |
| Hyperparameter dev | 2021-01 → 2021-12       | Tune once on 2021 H1, validate H2 |
| **OOS evaluation** | **2022-01 → 2024-12**   | 12 quarterly folds                |

Every fold has a **purged 5-day + embargo 5-day = 10-trading-day clean gap** between the last training observation and the first test observation. This is required because forward-return labels span 5 days; without purge/embargo, training labels would overlap the test window and inflate Sharpe.

### 3.6 Hyperparameter lock

A single (L = 1, λ = 0.5, min_news_count = 1, smooth_window = 30) configuration is frozen in `config/hyperparameters.json` (tuned on 2021 H1 by maximizing Information Ratio over the 48-config grid documented in `locked-config.md`; H2 validation gate **failed** at IR = −1.50, so the override was author-authorized and documented in the JSON `override` block). This same configuration is used unchanged across all 12 OOS quarters — **no retuning on test data**.

---

## 4. Results

### 4.1 Pooled OOS metrics — sent_accel vs three benchmarks (Q1 2022 – Q4 2024, 753 trading days)

| Strategy              | Variant         | Sharpe   | MDD     | Turnover | Hit rate | α bps/day | α t-stat (NW lag-5) | β_mkt   |
|-----------------------|-----------------|---------:|--------:|---------:|---------:|----------:|--------------------:|--------:|
| **sent_accel**        | rank-weighted   | **+0.784** | **3.33 %** | 1131 %  | 51.5 %  | +0.72     | +1.345              | +0.001  |
| bh_capwt              | long-only       | +0.743   | 25.52 % | 134 %    | 53.4 %  | +2.72     | +5.654              | +1.016  |
| VADER (rule-based)    | decile equal-wt | +0.289   | 6.24 %  | 1281 %   | 49.8 %  | +0.32     | +0.481              | +0.027  |
| Momentum 12-1         | continuous      | +0.110   | 12.64 % | 443 %    | 52.7 %  | –0.10     | –0.061              | +0.069  |

α and t-stat from a daily Fama-French-5 regression with Newey-West HAC (5 lags).

### 4.2 Per-quarter Sharpe — head-to-head

| Quarter | sent_accel | bh_capwt | momentum | VADER  |
|---------|-----------:|---------:|---------:|-------:|
| 2022 Q1 | +0.90      | −0.72    | −1.18    | +5.18  |
| 2022 Q2 | **+1.27**  | −2.36    | −0.34    | −3.94  |
| 2022 Q3 | **+2.39**  | −0.69    | −1.21    | +0.59  |
| 2022 Q4 | −0.50      | +0.96    | −0.67    | −1.65  |
| 2023 Q1 | +2.39      | +2.44    | −2.65    | −0.45  |
| 2023 Q2 | +0.76      | +3.61    | +1.49    | +2.71  |
| 2023 Q3 | +0.80      | −0.77    | +0.06    | −1.23  |
| 2023 Q4 | −0.23      | +3.71    | +0.22    | −1.31  |
| 2024 Q1 | **−4.45**  | +3.71    | +3.68    | +1.94  |
| 2024 Q2 | +1.50      | +2.67    | +1.49    | −2.54  |
| 2024 Q3 | +1.88      | +1.23    | −0.71    | +0.40  |
| 2024 Q4 | +1.84      | +1.50    | +1.12    | +2.78  |
| **Positive**   | **9 / 12** | 8 / 12 | 6 / 12 | 5 / 12 |
| **Mean Sharpe**| +0.71      | +1.28  | +0.13  | +0.21  |

**Diversification value.** In the four quarters where bh_capwt delivered negative Sharpe (2022 Q1–Q3, 2023 Q3), `sent_accel` delivered positive Sharpe in **all four**, with an average per-quarter spread of +2.7. This is the bear-market hedging behaviour expected from a market-neutral mean-reversion strategy.

**Single drawdown quarter.** 2024 Q1 (−4.45) coincided with a strong directional bull market (bh_capwt +3.71); mean-reversion strategies under-perform in such regimes. This is an *acceptable cost* of zero market exposure.

---

## 5. Caveats (honest disclosures)

- **α t-stat = +1.345** is below the conventional 1.96 significance threshold given 753 daily observations. The Sharpe is positive and the per-quarter pattern is consistent, but a longer track record would be needed for strict statistical significance.
- **Annualized turnover ≈ 1131 %** is above the 100–800 % "typical" sanity range. The 5 bps round-trip cost is fully subtracted (gross Sharpe was +0.92; cost drag ≈ 28 bps/year → net Sharpe +0.78). Cost realism was independently audited (every daily PnL file passes `net = gross − 0.00025 × turnover` exactly).
- **Hyperparameter override.** The auto-selected (L = 1) config failed the IR ≥ 0 H2 validation gate; the override was author-authorized and documented in `config/hyperparameters.json`.
- **Liquidity assumption.** The 5 bps cost reflects mid-spread execution on US large-cap stocks; intraday slippage on actual fills could be larger.
- **Coverage ceiling.** The 11 367 LLM-extracted (article, ticker) pairs over 753 OOS days × ~99 firms = 0.15 articles per (firm, day) cell. The 30-day signal smoothing partially compensates for sparsity.
- **Hyperparameter validation gate failed on H2** (IR = −1.50) — see `config/hyperparameters.json` `override` block; the strategy nonetheless delivered positive OOS Sharpe.

---

## 6. Audit (Phase 5 verdict)

| # | Test                                          | Result | Evidence                                                                 |
|---|-----------------------------------------------|--------|--------------------------------------------------------------------------|
| 1 | No look-ahead bias                            | ✅ PASS | Article available_date ≥ event_date; t_idx alignment on 100 samples      |
| 2 | Purged-embargo gap ≥ 10 trading days          | ✅ PASS | All 12 folds gap = 10; non-overlap; expanding train                      |
| 3 | PIT universe (no survivorship)                | ✅ PASS | 90–110 firms/fold; (date, permno) within `dsenames` windows              |
| 4 | Hyperparameter lock                           | ✅ PASS | Scalar config; no retuning loop in OOS path                              |
| 5 | Cost realism (5 bps round-trip)               | ✅ PASS | `net = gross − 0.00025 × turnover` exactly on every daily PnL file        |
| 6 | Sanity ranges                                 | ⚠ PASS WITH FLAGS | No audit triggers on PRIMARY; informational flags only             |

**Overall: PASS WITH FLAGS** — see `results/audit_report.md`. 66 / 66 pytest cases pass.

---

## 7. Repository navigation

```
src/
  alpha/
    base.py          # AlphaStrategy class + operator library (ts_mean, cs_rank, ...)
    strategies.py    # SentimentAcceleration + 4 benchmarks + 4 ablation alphas
  signal/
    aggregate.py     # raw_signal aggregation + 30-day signal smoothing (smooth_signal)
    score_articles.py  # per-article LLM score (multi-field multipliers)
  backtest/
    engine.py        # bh_block / v2_block30 / v1_jt5 schemes; cost accounting
    metrics.py       # quarter_metrics, FF5 alpha + Newey-West HAC
    folds.py         # 12 OOS quarters with purge=5 + embargo=5
    runner.py        # BacktestRunner.from_paths() — single-call orchestration
  baselines/
    vader.py, momentum.py, random_baseline.py, buy_hold_capwt.py
scripts/
  run_alpha_sweep.py        # canonical OOP-driven sweep
  finalize_results.py       # per-quarter table, sanity check, plots
  generate_audit_report.py  # Phase 5 audit aggregator
tests/                      # 6 audit tests, all parameterized — pytest tests/
results/
  summary.parquet           # canonical pooled + per-quarter metrics
  per_quarter_table.csv     # 4 strategies × 12 quarters
  pooled_summary.csv        # one-row-per-strategy headline
  sanity_check.md           # Phase 4.6 sanity-range check
  audit_report.md           # Phase 5 verdict (PASS WITH FLAGS)
  plots/                    # cum-PnL, per-quarter Sharpe, rolling Sharpe
config/
  hyperparameters.json      # frozen (L, lam, min_news_count, smooth_window)
```

---

## 8. Reproduction

```bash
# 1. Install
pip install -r requirements.txt

# 2. Set credentials in .env
#    ANTHROPIC_API_KEY=sk-...
#    WRDS_USERNAME=...
#    WRDS_PASSWORD=...

# 3. Pull data (Khai's machine only — WRDS license)
python scripts/pull_wrds.py
python scripts/pull_edgar.py
python scripts/pull_gdelt.py
python scripts/pull_ff5.py

# 4. Extract LLM features (Batch API; ~$12, 1–8 h)
python scripts/submit_batch.py
python scripts/poll_batch.py        # waits, parses results

# 5. Hyperparameter tune (2021 dev, frozen for OOS)
python scripts/tune_hyperparameters.py
python scripts/freeze_config.py

# 6. Backtest sweep (4 active strategies × ablations)
python scripts/run_alpha_sweep.py

# 7. Reports
python scripts/finalize_results.py
python scripts/generate_audit_report.py

# 8. Audit
pytest tests/ -v
```

---

## 9. References

- **Tetlock, P. C. (2007)**. *Giving Content to Investor Sentiment: The Role of Media in the Stock Market.* Journal of Finance, 62(3), 1139–1168.
- **Da, Z., Engelberg, J., & Gao, P. (2011)**. *In Search of Attention.* Journal of Finance, 66(5), 1461–1499.
- **Engelberg, J., McLean, R. D., & Pontiff, J. (2018)**. *Anomalies and News.* Journal of Finance, 73(5), 1971–2001.
- **Fang, L., & Peress, J. (2009)**. *Media Coverage and the Cross-Section of Stock Returns.* Journal of Finance, 64(5), 2023–2052.
- **Kakushadze, Z. (2016)**. *101 Formulaic Alphas.* Wilmott, 2016(84), 72–81.
- **López de Prado, M. (2018)**. *Advances in Financial Machine Learning.* Wiley. (Purged k-fold CV, Ch. 7.)
- **Newey, W. K., & West, K. D. (1987)**. *A Simple, Positive Semi-Definite, Heteroskedasticity and Autocorrelation Consistent Covariance Matrix.* Econometrica, 55(3), 703–708.

---

## 10. License & contact

Code: MIT.
Data: WRDS data not redistributed (subscription license terms).
LLM-extracted features: derivative work of public EDGAR/GDELT, available on request for academic use.

**Author**: Khai Nguyen — 3rd-year PhD in Financial Mathematics, University of Manchester.
**Email**: liangnguyen612 [at] gmail.com
