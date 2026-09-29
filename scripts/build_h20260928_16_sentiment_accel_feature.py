"""T-20260928-16: build the sent_accel feature from DeepSeek item scores,
compute daily cross-sectional rank IC vs forward 5-day returns, and the
shuffled-news-within-date placebo.

Card: reports/research/iterations/h20260928_16_8k_sentiment_accel/{direction-
review,candidate-manifest}.json. Construction: github.com/quangkhaidataka/
LLM_Alpha (see direction-review.json source llm_alpha_repo_construction_and_
results).

Point-in-time rule
-------------------
An item (8-K or news) is attributed to the first trading day D such that its
`visible_at` timestamp (already including the assumed scoring latency, see
scripts/score_h20260928_16_sentiment_accel.py) falls at or before D's session
close (16:00 America/New_York); items visible after that cutoff, or on a
non-trading day, are attributed to the NEXT trading day. The feature value
computed "as of the close of day t" therefore only ever uses items whose
visible_at is <= day t's 16:00 ET cutoff -- an item visible strictly after
that cutoff cannot appear in day t's feature. See
tests/test_h20260928_16_sentiment_accel.py for the point-in-time join test.

Usage
-----
    uv run python scripts/build_h20260928_16_sentiment_accel_feature.py
"""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

_sip = importlib.import_module("scripts._sip_daily_lookup")

ITEMS_PATH = ROOT / "data/features/h20260928_16_sentiment_accel_scores/items.parquet"
OUT_DIR = ROOT / "reports/research/iterations/h20260928_16_8k_sentiment_accel"

SHORT_WINDOW = 5
LONG_WINDOW = 20
HORIZON = 5
PLACEBO_SEED = 20260928

UNIVERSE_TICKERS = [
    "AAON",
    "AAPL",
    "ADBE",
    "ALIT",
    "ALT",
    "AMC",
    "ARCB",
    "ATR",
    "BTU",
    "BYD",
    "CADL",
    "CZR",
    "DELL",
    "DLTR",
    "DVLT",
    "EHC",
    "ERIE",
    "EVRG",
    "FANG",
    "FLNA",
    "FNB",
    "FRMI",
    "FRSH",
    "GENB",
    "GPCR",
    "HAL",
    "HONA",
    "HWM",
    "L",
    "LIVN",
    "LOAR",
    "LSCC",
    "NAVN",
    "OGN",
    "PCAR",
    "PODD",
    "QS",
    "RRC",
    "RXT",
    "SIRI",
    "STLD",
    "SUI",
    "TER",
    "TOL",
    "TXG",
    "UAA",
    "WAB",
    "WAL",
    "WEX",
    "YUM",
]

SESSION_CLOSE_HOUR_ET = 16


def _naive_days(trading_days: pd.DatetimeIndex) -> pd.DatetimeIndex:
    """Normalise any trading-day index (tz-aware or not) to tz-naive
    calendar-date midnights, the single internal representation every grid
    in this module is indexed by."""
    idx = pd.DatetimeIndex(trading_days)
    if idx.tz is not None:
        idx = idx.tz_convert("UTC").tz_localize(None)
    return idx.normalize()


def attribute_trading_day(visible_at: pd.Series, trading_days: pd.DatetimeIndex) -> pd.Series:
    """Map each UTC `visible_at` timestamp to the first trading day (a
    tz-naive date, from `trading_days`) whose 16:00 America/New_York close is
    >= that timestamp. Vectorised, used by both the real build and the unit
    test so the two can never silently diverge."""
    naive_days = _naive_days(trading_days)
    closes_et = naive_days.tz_localize("America/New_York") + pd.Timedelta(
        hours=SESSION_CLOSE_HOUR_ET
    )
    order = np.argsort(closes_et.values)
    closes_utc_naive_sorted = closes_et.tz_convert("UTC").tz_localize(None).values[order]
    day_labels_sorted = naive_days.values[order]

    visible_utc_naive = visible_at.dt.tz_convert("UTC").dt.tz_localize(None).to_numpy()
    positions = np.searchsorted(closes_utc_naive_sorted, visible_utc_naive, side="left")
    positions = np.clip(positions, 0, len(day_labels_sorted) - 1)
    attributed = pd.Series(day_labels_sorted[positions], index=visible_at.index)
    return attributed


def build_daily_raw_pol(
    items: pd.DataFrame, trading_days: pd.DatetimeIndex, tickers: list[str]
) -> pd.DataFrame:
    """Return a (trading_day x ticker) DataFrame of mean raw_pol, 0.0 where
    no item was attributed to that (ticker, day)."""
    items = items.copy()
    items["raw_pol"] = items["polarity"] * items["magnitude"]
    items["day"] = attribute_trading_day(items["visible_at"], trading_days)
    grouped = items.groupby(["day", "ticker"])["raw_pol"].mean().unstack("ticker")
    grid = pd.DataFrame(0.0, index=_naive_days(trading_days), columns=tickers)
    grid.update(grouped.reindex(columns=tickers))
    return grid.fillna(0.0)


def build_coverage_mask(
    items: pd.DataFrame, trading_days: pd.DatetimeIndex, tickers: list[str]
) -> pd.DataFrame:
    """True where a ticker has >=1 attributed item within the trailing
    LONG_WINDOW trading days (used to exclude all-zero tickers from ranking,
    which would otherwise tie-rank on pure absence of information)."""
    items = items.copy()
    items["day"] = attribute_trading_day(items["visible_at"], trading_days)
    has_item = items.groupby(["day", "ticker"]).size().unstack("ticker")
    grid = pd.DataFrame(False, index=_naive_days(trading_days), columns=tickers)
    grid.update((has_item.reindex(columns=tickers) > 0).astype(bool))
    coverage = grid.rolling(LONG_WINDOW, min_periods=1).max().astype(bool)
    return coverage


def compute_accel_and_score(daily_raw_pol: pd.DataFrame, coverage: pd.DataFrame) -> dict:
    short_ma = daily_raw_pol.rolling(SHORT_WINDOW, min_periods=1).mean()
    long_ma = daily_raw_pol.rolling(LONG_WINDOW, min_periods=1).mean()
    accel = short_ma - long_ma
    accel_masked = accel.where(coverage)

    def cs_rank_score(row: pd.Series) -> pd.Series:
        valid = row.dropna()
        if len(valid) < 5:
            return pd.Series(np.nan, index=row.index)
        ranks = valid.rank(pct=True) - 0.5
        return ranks.reindex(row.index)

    rank_centered = accel_masked.apply(cs_rank_score, axis=1)
    sent_accel = -1.0 * rank_centered
    return {"accel": accel, "accel_masked": accel_masked, "sent_accel": sent_accel}


def compute_forward_returns(prices: pd.DataFrame, trading_days: pd.DatetimeIndex) -> pd.DataFrame:
    """forward_return[t, ticker] = close[t+HORIZON] / open[t+1] - 1, i.e. the
    frozen project convention: close signal at t -> next session's open fill,
    held HORIZON sessions."""
    pivot_open = prices.pivot_table(index="timestamp", columns="symbol", values="open")
    pivot_close = prices.pivot_table(index="timestamp", columns="symbol", values="close")
    pivot_open.index = pivot_open.index.tz_convert("UTC").normalize().tz_localize(None)
    pivot_close.index = pivot_close.index.tz_convert("UTC").normalize().tz_localize(None)
    idx = _naive_days(trading_days)
    pivot_open = pivot_open.reindex(idx)
    pivot_close = pivot_close.reindex(idx)
    entry_open = pivot_open.shift(-1)
    exit_close = pivot_close.shift(-HORIZON)
    fwd = exit_close / entry_open - 1.0
    return fwd


def daily_rank_ic(score: pd.DataFrame, fwd_return: pd.DataFrame) -> pd.Series:
    ics = {}
    for day in score.index:
        s = score.loc[day].dropna()
        r = fwd_return.loc[day].reindex(s.index).dropna()
        common = s.index.intersection(r.index)
        if len(common) < 5:
            continue
        rho, _ = stats.spearmanr(s.loc[common], r.loc[common])
        if rho == rho:  # not NaN
            ics[day] = rho
    return pd.Series(ics).sort_index()


def summarize_ic(ic_series: pd.Series) -> dict:
    if len(ic_series) == 0:
        return {"n_days": 0, "mean_ic": None, "t_stat": None, "positive_share": None}
    n = len(ic_series)
    mean_ic = float(ic_series.mean())
    std_ic = float(ic_series.std(ddof=1)) if n > 1 else 0.0
    t_stat = mean_ic / (std_ic / np.sqrt(n)) if std_ic > 0 else None
    positive_share = float((ic_series > 0).mean())
    return {
        "n_days": n,
        "mean_ic": mean_ic,
        "std_ic": std_ic,
        "t_stat": t_stat,
        "positive_share": positive_share,
    }


def shuffled_items(items: pd.DataFrame, seed: int) -> pd.DataFrame:
    """Placebo: shuffle each item's ticker among the tickers that had >=1
    item on the same calendar (visible_at UTC) date -- keeps the daily item
    volume identical, breaks the true item-to-ticker correspondence."""
    rng = np.random.default_rng(seed)
    items = items.copy()
    items["cal_date"] = items["visible_at"].dt.date
    shuffled_ticker = items["ticker"].copy()
    for _, group in items.groupby("cal_date"):
        idx = group.index
        perm = rng.permutation(idx.to_numpy())
        shuffled_ticker.loc[idx] = items.loc[perm, "ticker"].to_numpy()
    items["ticker"] = shuffled_ticker
    return items


def main() -> int:
    items = pd.read_parquet(ITEMS_PATH)
    items = items[items["status"] == "ok"].copy()
    items["visible_at"] = pd.to_datetime(items["visible_at"], utc=True)
    items["polarity"] = items["polarity"].astype(float)
    items["magnitude"] = items["magnitude"].astype(float)
    print(f"loaded {len(items)} ok-status items")

    prices = _sip.load_daily_ohlc(UNIVERSE_TICKERS, years=[2026])
    trading_days = pd.DatetimeIndex(
        sorted(prices["timestamp"].dt.tz_convert("UTC").dt.normalize().unique())
    )
    trading_days = trading_days[
        (trading_days >= pd.Timestamp("2026-04-01", tz="UTC"))
        & (trading_days <= pd.Timestamp("2026-07-11", tz="UTC"))
    ]
    print(f"{len(trading_days)} trading days in evaluation window")

    fwd_return = compute_forward_returns(prices, trading_days)

    def run_pipeline(items_df: pd.DataFrame) -> dict:
        daily = build_daily_raw_pol(items_df, trading_days, UNIVERSE_TICKERS)
        coverage = build_coverage_mask(items_df, trading_days, UNIVERSE_TICKERS)
        result = compute_accel_and_score(daily, coverage)
        ic_sent_accel = daily_rank_ic(result["sent_accel"], fwd_return)
        ic_accel = daily_rank_ic(result["accel_masked"], fwd_return)
        return {
            "ic_sent_accel": ic_sent_accel,
            "ic_accel": ic_accel,
        }

    real = run_pipeline(items)
    placebo = run_pipeline(shuffled_items(items, PLACEBO_SEED))

    summary = {
        "real": {
            "sent_accel_negated": summarize_ic(real["ic_sent_accel"]),
            "accel_unnegated": summarize_ic(real["ic_accel"]),
        },
        "placebo": {
            "sent_accel_negated": summarize_ic(placebo["ic_sent_accel"]),
            "accel_unnegated": summarize_ic(placebo["ic_accel"]),
        },
    }
    print(json.dumps(summary, indent=2))

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "ic-summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    real["ic_sent_accel"].rename("ic").to_frame().assign(kind="real_sent_accel").to_csv(
        OUT_DIR / "daily-ic-real-sent-accel.csv"
    )
    placebo["ic_sent_accel"].rename("ic").to_frame().assign(kind="placebo_sent_accel").to_csv(
        OUT_DIR / "daily-ic-placebo-sent-accel.csv"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
