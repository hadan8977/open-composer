"""Panel readers and the industry lookup of the panel builder (synthetic files, no market data)."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from open_composer.research.equity_book.panel import PanelAttributes, PricePanel

ROOT = Path(__file__).resolve().parents[1]


def _write_prices(base: Path) -> None:
    (base / "prices").mkdir(parents=True)
    d = pd.bdate_range("2023-12-28", periods=6)
    rows = []
    for k, dt in enumerate(d):
        for sym, px in (("AAA", 10.0), ("BBB", 20.0)):
            if sym == "BBB" and k >= 4:
                continue  # BBB delists
            rows.append((dt, sym, px + k, px + k + 0.5))
    df = pd.DataFrame(rows, columns=["trade_date", "symbol", "open", "close"])
    df[df.trade_date.dt.year == 2023].to_parquet(base / "prices/2023.parquet")
    df[df.trade_date.dt.year == 2024].to_parquet(base / "prices/2024.parquet")
    etf = pd.DataFrame(
        {
            "trade_date": list(d)
            + [pd.Timestamp("2024-01-08")],  # a date outside the stock calendar
            "symbol": ["SPY"] * 7,
            "open": np.arange(7) + 400.0,
            "close": np.arange(7) + 401.0,
            "volume": 1.0,
        }
    )
    etf.to_parquet(base / "etf_daily.parquet")


def test_price_panel_from_dir_reads_years_etfs_and_respects_the_stock_calendar(
    tmp_path: Path,
) -> None:
    _write_prices(tmp_path)
    p = PricePanel.from_dir(tmp_path)
    assert len(p.dates) == 6  # ETF-only date 2024-01-08 is not a session of the panel
    assert set(p.symbols) == {"AAA", "BBB", "SPY"}
    assert p.close[0, p.col("AAA")] == 10.5 and np.isnan(p.close[5, p.col("BBB")])
    assert p.close[5, p.col("SPY")] == 406.0
    sub = PricePanel.from_dir(tmp_path, symbols=["AAA"], start="2024-01-01")
    assert list(sub.symbols) == ["AAA", "SPY"] and sub.dates[0] == pd.Timestamp("2024-01-01")
    no_open = PricePanel.from_dir(tmp_path, load_open=False)
    assert np.isnan(no_open.open).all() and no_open.close.shape == p.close.shape
    only_stocks = PricePanel.from_dir(tmp_path, include_etfs=False)
    assert "SPY" not in set(only_stocks.symbols)


def test_panel_attributes_cross_section_and_trade_attrs(tmp_path: Path) -> None:
    (tmp_path / "panel").mkdir()
    d = pd.Timestamp("2024-01-02")
    df = pd.DataFrame(
        {
            "trade_date": [d, d, d + pd.Timedelta(days=1)],
            "symbol": ["AAA", "BBB", "AAA"],
            "close": [10.0, 20.0, 11.0],
            "dollar_adv_21": [1e6, 2e6, 1.1e6],
            "vol_21": [0.02, 0.03, 0.02],
            "adv_rank": [5, 1, 5],
        }
    )
    df.to_parquet(tmp_path / "panel/2024.parquet")
    pa = PanelAttributes(tmp_path)
    cs = pa.at(d)
    assert list(cs.index) == ["AAA", "BBB"]
    ta = pa.trade_attrs(d, ["BBB", "ZZZ"])
    assert ta.loc["BBB", "dollar_adv_21"] == 2e6 and np.isnan(ta.loc["ZZZ", "dollar_adv_21"])
    assert "prior_close" in ta.columns


def test_ff48_lookup_uses_verified_link_else_nearest_unverified(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sys.path.insert(0, str(ROOT / "scripts"))
    import build_equity_book_panel as bp  # noqa: PLC0415

    sic = pd.DataFrame(
        {
            "symbol": ["AAA", "AAA", "BBB", "CCC"],
            "cik": [1, 2, 3, 4],
            "link_first_date": pd.to_datetime(["2016-01-01", "2020-01-01", "2018-06-01", None]),
            "link_last_date": pd.to_datetime(["2019-12-31", None, "2021-01-01", None]),
            "sic": [2000.0, 3570.0, 6021.0, np.nan],
            "ff48": [2, 35, 44, np.nan],
            "ff12": [1, 6, 11, np.nan],
        }
    )
    path = tmp_path / "sic_map.parquet"
    sic.to_parquet(path)
    monkeypatch.setattr(bp, "SIC_PATH", path)
    months = pd.DataFrame(
        {
            "symbol": ["AAA", "AAA", "BBB", "BBB", "CCC", "ZZZ"],
            "month_end": pd.to_datetime(
                ["2018-01-31", "2022-01-31", "2015-01-30", "2019-01-31", "2019-01-31", "2019-01-31"]
            ),
        }
    )
    out = bp.ff48_by_month_end(months).set_index(["symbol", "month_end"])
    r = out.loc[("AAA", pd.Timestamp("2018-01-31"))]
    assert r["ff48"] == 2 and r["ff48_verified"]
    r = out.loc[("AAA", pd.Timestamp("2022-01-31"))]
    assert r["ff48"] == 35 and r["ff48_verified"]  # open-ended link covers the date
    r = out.loc[("BBB", pd.Timestamp("2015-01-30"))]
    assert r["ff48"] == 44 and not r["ff48_verified"]  # nearest link, flagged
    assert out.loc[("BBB", pd.Timestamp("2019-01-31"))]["ff48_verified"]
    assert pd.isna(out.loc[("CCC", pd.Timestamp("2019-01-31"))]["ff48"])  # no SIC at all
    assert pd.isna(out.loc[("ZZZ", pd.Timestamp("2019-01-31"))]["ff48"])
