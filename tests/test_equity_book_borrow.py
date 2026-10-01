from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from open_composer.research.equity_book import borrow as bw
from scripts import snapshot_alpaca_assets as snap


def test_rule_version_constant() -> None:
    assert bw.RULE_VERSION == "v1"


@pytest.mark.parametrize("k", [2, 3, 4, 5, 8, 10, 20, 25, 50])
def test_reverse_split_up_hits_each_multiple_within_tolerance(k: int) -> None:
    r = np.array([k, k * 1.029, k * 0.971, k * 1.05, k * 0.95])
    got = bw.is_reverse_split_ratio(r)
    assert got.tolist() == [True, True, True, False, False]


def test_reverse_split_direction_down_is_the_reciprocal_reading() -> None:
    r = np.array([0.5, 1 / 10, 10.0, 1.0, np.nan])
    assert bw.is_reverse_split_ratio(r, direction="down").tolist() == [
        True,
        True,
        False,
        False,
        False,
    ]
    assert bw.is_reverse_split_ratio(r, direction="up").tolist() == [
        False,
        False,
        True,
        False,
        False,
    ]
    with pytest.raises(ValueError):
        bw.is_reverse_split_ratio(r, direction="sideways")


def test_detect_reverse_splits_uses_open_over_previous_close_and_window() -> None:
    idx = pd.bdate_range("2026-01-05", periods=6)
    close = pd.DataFrame({"A": [10, 10, 10, 10, 10, 10.0], "B": [1.0, 1, 1, 1, 1, 1]}, index=idx)
    open_ = close.copy()
    open_.loc[idx[2], "B"] = 10.0  # 1-for-10 reverse split: open jumps to 10x the previous close
    open_.loc[idx[3], "A"] = 5.0  # a -50 % gap is not a reverse split in the "up" reading
    flags = bw.detect_reverse_splits(open_, close)
    assert flags["B"].tolist() == [False, False, True, False, False, False]
    assert not flags["A"].any()
    assert bw.detect_reverse_splits(open_, close, direction="down")["A"].tolist()[3] is True
    win = bw.reverse_split_in_window(flags, window=3)
    assert win["B"].tolist() == [False, False, True, True, True, False]


def test_rule_mask_logic_and_missing_values() -> None:
    adv = [100, 2000, 2001, 500, 500, 500, np.nan]
    px = [50, 10.0, 50, 9.99, 50, 50, 50]
    rs = [False, False, False, False, True, False, False]
    si = [0.1, 0.94, 0.1, 0.1, 0.1, 0.95, np.nan]
    got = bw.rule_mask(adv, px, rs, si)
    assert got.tolist() == [True, True, False, False, False, False, False]
    # missing SI: clause skipped; missing reverse-split info treated as no split
    assert bw.rule_mask([500], [50.0], [np.nan], [np.nan]).tolist() == [True]
    assert bw.rule_mask([500], [50.0], False, None).tolist() == [True]


def test_short_eligible_frame_and_wide_forms_agree() -> None:
    f = pd.DataFrame(
        {
            "adv_rank": [10, 1500, 2500, 800],
            "price": [100.0, 12.0, 30.0, 8.0],
            "reverse_split_252": [False, False, False, False],
            "si_over_shares_pct": [0.5, 0.97, 0.2, 0.1],
        },
        index=list("abcd"),
    )
    s = bw.short_eligible(f)
    assert s.dtype == bool and s.index.tolist() == list("abcd")
    assert s.tolist() == [True, False, False, False]
    wide = {
        "adv_rank": pd.DataFrame({"X": [10, 10], "Y": [3000, 10]}),
        "price": pd.DataFrame({"X": [20.0, 20.0], "Y": [20.0, 20.0]}),
        "reverse_split_252": pd.DataFrame({"X": [False, True], "Y": [False, False]}),
    }
    w = bw.short_eligible(wide)
    assert isinstance(w, pd.DataFrame)
    assert w.to_numpy().tolist() == [[True, False], [False, True]]
    with pytest.raises(ValueError):
        bw.short_eligible(f, rule="v9")


def test_si_percentile_by_group() -> None:
    s = pd.Series([1.0, 2.0, 3.0, 10.0, 20.0, np.nan])
    g = pd.Series(["d1", "d1", "d1", "d2", "d2", "d2"])
    p = bw.si_cross_sectional_pct(s, g)
    assert p.iloc[2] == 1.0 and p.iloc[3] == 0.5 and np.isnan(p.iloc[5])


class _Asset:
    def __init__(self, symbol: str, etb: bool) -> None:
        self.symbol = symbol
        self.tradable = True
        self.shortable = etb
        self.easy_to_borrow = etb
        self.marginable = True
        self.fractionable = True
        self.exchange = type("E", (), {"value": "NASDAQ"})()
        self.status = type("S", (), {"value": "active"})()
        self.asset_class = type("C", (), {"value": "us_equity"})()


def test_snapshot_frame_has_only_the_requested_columns() -> None:
    df = snap.assets_to_frame([_Asset("AAA", True), _Asset("BBB", False), _Asset("AAA", True)])
    assert df.columns.tolist() == snap.COLUMNS
    assert df["symbol"].tolist() == ["AAA", "BBB"]
    assert df["exchange"].tolist() == ["NASDAQ", "NASDAQ"]
    assert df["easy_to_borrow"].tolist() == [True, False]
