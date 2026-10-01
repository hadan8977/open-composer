# ruff: noqa: E501
"""Return convention (design section 3): legs, holes, delisting, label/return parity."""

from __future__ import annotations

import numpy as np
import pandas as pd

from open_composer.research.equity_book.panel import PricePanel
from open_composer.research.equity_book.returns import (
    build_legs,
    compound_legs,
    forward_open_to_open,
    holding_period_return,
)

NAN = np.nan


def test_legs_split_close_to_close_exactly() -> None:
    o = np.array([[10.0], [10.5], [10.2], [11.0]])
    c = np.array([[10.2], [10.4], [10.8], [10.9]])
    legs = build_legs(o, c)
    # overnight * intraday == close-to-close, session by session after the first
    for i in range(1, 4):
        assert abs((1 + legs.ov[i, 0]) * (1 + legs.intra[i, 0]) - c[i, 0] / c[i - 1, 0]) < 1e-15
    assert legs.ov[0, 0] == 0.0  # no previous close
    assert abs(legs.intra[0, 0] - (10.2 / 10.0 - 1)) < 1e-15
    assert legs.delist_pos[0] == -1


def test_hole_stale_open_and_delisting() -> None:
    # symbol 0: hole on session 2, back on 3.  symbol 1: open missing on 2.  symbol 2: delists after 1.
    o = np.array([[10, 20, 30], [11, 21, 31], [NAN, NAN, NAN], [12, 22, NAN], [13, 23, NAN]], float)
    c = np.array([[10, 20, 30], [11, 21, 31], [NAN, 22, NAN], [12, 23, NAN], [13, 24, NAN]], float)
    legs = build_legs(o, c)
    assert legs.priced[2].tolist() == [False, True, False]
    # hole: zero legs, then the whole move from the last valid close
    assert legs.ov[2, 0] == 0 and legs.intra[2, 0] == 0
    assert abs(legs.ov[3, 0] - (12 / 11 - 1)) < 1e-15
    # stale open: overnight 0, intraday = whole close-to-close move
    assert legs.ov[2, 1] == 0 and abs(legs.intra[2, 1] - (22 / 21 - 1)) < 1e-15
    # delisting: last valid close at session 1, first session without a price is 2
    assert legs.delist_pos.tolist() == [-1, -1, 2]


def test_forward_label_equals_compounded_legs() -> None:
    rng = np.random.default_rng(1)
    t_n, n = 40, 12
    close = 50 * np.exp(np.cumsum(rng.normal(0, 0.02, (t_n, n)), axis=0))
    open_ = close * np.exp(rng.normal(0, 0.01, (t_n, n)))
    close[10, 3] = NAN  # hole inside the span
    open_[10, 3] = NAN
    open_[22, 5] = NAN  # missing exit open (stale)
    close[15:, 7] = NAN  # delists inside the span
    open_[15:, 7] = NAN
    close[3:, 9] = NAN  # gone before the entry
    open_[3:, 9] = NAN
    legs = build_legs(open_, close)
    for t in (4, 8, 12):
        entry, exit_ = t + 1, t + 1 + 21
        lab = forward_open_to_open(open_, close, entry, exit_)
        comp = compound_legs(legs, entry, exit_)
        both = np.isfinite(lab) & np.isfinite(comp)
        assert both.sum() >= 8
        np.testing.assert_allclose(lab[both], comp[both], rtol=0, atol=1e-12)
        # a name that cannot be entered has no label and no compounded return
        assert not np.isfinite(lab[9]) and not np.isfinite(comp[9])


def test_forward_label_fallback_to_last_valid_close() -> None:
    o = np.array([[10.0], [10.0], [12.0], [NAN]])
    c = np.array([[10.0], [11.0], [13.0], [NAN]])
    lab = forward_open_to_open(o, c, 1, 3)
    assert abs(lab[0] - (13.0 / 10.0 - 1)) < 1e-15


def test_holding_period_return_compounds() -> None:
    assert abs(holding_period_return(np.array([0.1, -0.1])) - (1.1 * 0.9 - 1)) < 1e-15


def test_price_panel_from_long_roundtrip() -> None:
    df = pd.DataFrame(
        {
            "trade_date": pd.to_datetime(["2024-01-02", "2024-01-02", "2024-01-03"]),
            "symbol": ["A", "B", "A"],
            "open": [1.0, 2.0, 1.1],
            "close": [1.05, 2.1, 1.2],
        }
    )
    p = PricePanel.from_long(df)
    assert p.open.shape == (2, 2)
    assert np.isnan(p.close[1, p.col("B")])
