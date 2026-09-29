"""T-20260928-17: build the risk_score feature from DeepSeek 8-K item scores,
compute per-quarter cross-sectional rank IC vs forward 20-day returns, and
the mismatched-filings-within-quarter placebo.

Card: reports/research/iterations/h20260928_17_filing_risk_labels/{direction-
review,candidate-manifest}.json.

Reduction rule: a (ticker, quarter) cell with more than one fetchable 8-K
uses the chronologically LAST filing's score (most information-rich, still
PIT-safe since its own visible_at still gates the entry date).

Point-in-time rule
-------------------
Reuses scripts/build_h20260928_16_sentiment_accel_feature.py's
`attribute_trading_day` (a filing's `visible_at` maps to the first trading
day whose 16:00 America/New_York close is >= visible_at); the entry fill is
the NEXT trading day's open after that attributed day, so a filing's own
score can never affect a return dated before the filing was visible. See
tests/test_h20260928_17_filing_risk_labels.py.

Usage
-----
    uv run python scripts/build_h20260928_17_filing_risk_labels_feature.py
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
_t16 = importlib.import_module("scripts.build_h20260928_16_sentiment_accel_feature")

ITEMS_PATH = ROOT / "data/features/h20260928_17_filing_risk_labels_scores/items.parquet"
OUT_DIR = ROOT / "reports/research/iterations/h20260928_17_filing_risk_labels"

HORIZON = 20
PLACEBO_SEED = 20260928

UNIVERSE_TICKERS = [
    "AAON",
    "ABBV",
    "ADMA",
    "AGX",
    "ALSN",
    "AMD",
    "AMR",
    "ASTC",
    "BA",
    "CB",
    "CCK",
    "CF",
    "CGON",
    "EHC",
    "ELS",
    "ENSG",
    "ES",
    "EXR",
    "FICO",
    "FSLR",
    "GDDY",
    "GOOG",
    "HEI",
    "HOOD",
    "HSIC",
    "HUBB",
    "IEX",
    "IR",
    "JPM",
    "KRC",
    "LHX",
    "MOH",
    "MTSI",
    "NOW",
    "NTRS",
    "NWSA",
    "OLED",
    "PSX",
    "RKLB",
    "RNR",
    "RPM",
    "SG",
    "SSNC",
    "TEL",
    "TFX",
    "ULS",
    "UWMC",
    "VVV",
    "WVE",
    "XYL",
]
QUARTERS = ["2024Q3", "2024Q4", "2025Q1", "2025Q2", "2025Q3", "2025Q4", "2026Q1", "2026Q2"]


def reduce_to_one_per_ticker_quarter(items: pd.DataFrame) -> pd.DataFrame:
    items = items.sort_values("acceptance_utc")
    return items.groupby(["ticker", "quarter"], as_index=False).last()


def attach_forward_return(
    panel: pd.DataFrame, prices: pd.DataFrame, trading_days_by_ticker: dict[str, pd.DatetimeIndex]
) -> pd.DataFrame:
    """For each (ticker, quarter) row, attribute the filing's visible_at to a
    trading day, enter at the NEXT trading day's open, exit HORIZON trading
    days later at close."""
    out_rows = []
    pivot_open = prices.pivot_table(index="timestamp", columns="symbol", values="open")
    pivot_close = prices.pivot_table(index="timestamp", columns="symbol", values="close")
    pivot_open.index = pivot_open.index.tz_convert("UTC").normalize().tz_localize(None)
    pivot_close.index = pivot_close.index.tz_convert("UTC").normalize().tz_localize(None)

    for row in panel.itertuples(index=False):
        ticker = row.ticker
        cal = trading_days_by_ticker.get(ticker)
        if cal is None or len(cal) == 0:
            continue
        visible_at = pd.Series([pd.Timestamp(row.visible_at)])
        attributed_day = _t16.attribute_trading_day(visible_at, cal).iloc[0]
        cal_sorted = _t16._naive_days(cal).sort_values()
        pos = cal_sorted.searchsorted(attributed_day, side="right")  # strictly AFTER attribution
        if pos >= len(cal_sorted):
            continue
        entry_day = cal_sorted[pos]
        exit_pos = pos + HORIZON - 1
        if exit_pos >= len(cal_sorted):
            continue
        exit_day = cal_sorted[exit_pos]
        try:
            entry_open = pivot_open.loc[entry_day, ticker]
            exit_close = pivot_close.loc[exit_day, ticker]
        except KeyError:
            continue
        if pd.isna(entry_open) or pd.isna(exit_close) or entry_open == 0:
            continue
        out_rows.append(
            {
                "ticker": ticker,
                "quarter": row.quarter,
                "risk_score": row.risk_score,
                "attributed_day": attributed_day,
                "entry_day": entry_day,
                "exit_day": exit_day,
                "fwd_return": exit_close / entry_open - 1.0,
            }
        )
    return pd.DataFrame(out_rows)


def per_quarter_rank_ic(panel: pd.DataFrame) -> pd.Series:
    ics = {}
    for quarter, group in panel.groupby("quarter"):
        if len(group) < 5:
            continue
        rho, _ = stats.spearmanr(group["risk_score"], group["fwd_return"])
        if rho == rho:
            ics[quarter] = rho
    return pd.Series(ics).reindex(QUARTERS).dropna()


def summarize_ic(ic_series: pd.Series) -> dict:
    if len(ic_series) == 0:
        return {"n_quarters": 0, "mean_ic": None, "t_stat": None, "positive_share": None}
    n = len(ic_series)
    mean_ic = float(ic_series.mean())
    std_ic = float(ic_series.std(ddof=1)) if n > 1 else 0.0
    t_stat = mean_ic / (std_ic / np.sqrt(n)) if std_ic > 0 else None
    positive_share = float((ic_series > 0).mean())
    return {
        "n_quarters": n,
        "mean_ic": mean_ic,
        "std_ic": std_ic,
        "t_stat": t_stat,
        "positive_share": positive_share,
        "per_quarter": {str(k): float(v) for k, v in ic_series.items()},
    }


def shuffled_panel(panel: pd.DataFrame, seed: int) -> pd.DataFrame:
    """Placebo: within each quarter, permute risk_score across tickers
    (mismatched-filings-across-tickers-within-quarter)."""
    rng = np.random.default_rng(seed)
    panel = panel.copy()
    for _quarter, group in panel.groupby("quarter"):
        idx = group.index.to_numpy()
        perm = rng.permutation(idx)
        panel.loc[idx, "risk_score"] = panel.loc[perm, "risk_score"].to_numpy()
    return panel


def main() -> int:
    items = pd.read_parquet(ITEMS_PATH)
    items = items[items["status"] == "ok"].copy()
    items["acceptance_utc"] = pd.to_datetime(items["acceptance_utc"], utc=True)
    items["visible_at"] = pd.to_datetime(items["visible_at"], utc=True)
    items["risk_score"] = items["risk_score"].astype(float)
    print(f"loaded {len(items)} ok-status items")

    panel = reduce_to_one_per_ticker_quarter(items)
    print(f"reduced to {len(panel)} (ticker, quarter) rows (target 400)")

    prices = _sip.load_daily_ohlc(UNIVERSE_TICKERS, years=[2024, 2025, 2026])
    trading_days_by_ticker = {
        t: pd.DatetimeIndex(
            sorted(
                prices[prices["symbol"] == t]["timestamp"]
                .dt.tz_convert("UTC")
                .dt.normalize()
                .unique()
            )
        )
        for t in UNIVERSE_TICKERS
    }

    fwd_panel = attach_forward_return(panel, prices, trading_days_by_ticker)
    print(f"{len(fwd_panel)} rows with a computable forward-20d return")

    real_ic = per_quarter_rank_ic(fwd_panel)
    placebo_ic = per_quarter_rank_ic(shuffled_panel(fwd_panel, PLACEBO_SEED))

    summary = {
        "real": summarize_ic(real_ic),
        "placebo": summarize_ic(placebo_ic),
        "n_ticker_quarters_scored": int(len(panel)),
        "n_ticker_quarters_with_return": int(len(fwd_panel)),
    }
    print(json.dumps(summary, indent=2))

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "ic-summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    fwd_panel.to_csv(OUT_DIR / "panel-with-forward-returns.csv", index=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
