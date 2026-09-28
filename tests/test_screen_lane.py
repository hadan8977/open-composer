"""Screening lane: synthetic-data unit tests, no network, no market panel."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import run_h20260918_05_recent_menu as base  # noqa: E402
import screen_batch  # noqa: E402
import screen_lane as lane  # noqa: E402


def _synthetic_index(periods: int = 90) -> pd.DatetimeIndex:
    return pd.bdate_range("2020-01-01", periods=periods)


def _synthetic_panel(index: pd.DatetimeIndex) -> tuple[pd.DataFrame, pd.DataFrame]:
    """SYM grows 0.1%/day, SHY (cash) is flat. `open[i] = close[i-1]` (no
    overnight gap) so the whole day's move is earned by the weight that
    becomes effective at that day's open -- i.e. exactly the next-open-fill
    convention with zero gap risk, which keeps the expected numbers simple."""
    n = len(index)
    sym = 100.0 * (1.001 ** np.arange(n))
    shy = np.full(n, 100.0)
    close = pd.DataFrame({"SYM": sym, "SHY": shy}, index=index)
    open_ = close.shift(1)
    open_.iloc[0] = close.iloc[0]
    return close, open_


# --- rebalance dates for offsets 0 and 3 -----------------------------------


def test_signal_dates_monthly_offset_0_and_3() -> None:
    index = _synthetic_index(90)
    flags = base.rebalance_flags(index, "monthly").to_numpy()
    expected_0 = list(index[flags])
    positions_3 = np.flatnonzero(flags) + 3
    expected_3 = [index[i] for i in positions_3 if i < len(index)]

    got_0 = lane.signal_dates(index, "M", 0)
    got_3 = lane.signal_dates(index, "M", 3)

    assert got_0 == expected_0
    assert got_3 == expected_3
    # offset shifts each date 3 sessions later (dropping the trailing date if
    # it runs off the end of the index).
    assert len(got_3) <= len(got_0)
    for a, b in zip(got_0, got_3, strict=False):
        assert index.get_loc(b) == index.get_loc(a) + 3


def test_signal_dates_weekly_offset_0_and_3() -> None:
    index = _synthetic_index(90)
    flags = base.rebalance_flags(index, "weekly").to_numpy()
    expected_0 = list(index[flags])
    positions_3 = np.flatnonzero(flags) + 3
    expected_3 = [index[i] for i in positions_3 if i < len(index)]

    assert lane.signal_dates(index, "W", 0) == expected_0
    assert lane.signal_dates(index, "W", 3) == expected_3


# --- buy-and-hold reproduces the asset's return path after entry cost -----


def test_buy_and_hold_matches_asset_return_after_entry_cost() -> None:
    index = _synthetic_index(90)
    close, open_ = _synthetic_panel(index)
    leg_open, leg_close = lane.salvage.legs(close, open_)
    candidate = lane.ScreenCandidate(
        id="TEST_BH",
        name="synthetic buy and hold",
        source_card="test/synthetic",
        universe=("SYM",),
        freq="M",
        weights_fn=lambda _close, _asof: {"SYM": 1.0},
    )
    cost_bps = 10.0
    ret, turn = lane.candidate_returns_for_offset(
        close, leg_open, leg_close, candidate, 0, cost_bps
    )

    dates = lane.signal_dates(index, "M", 0)
    entry_pos = index.get_loc(dates[0]) + 1  # effective at the open after the first signal
    sym_ret = close["SYM"].pct_change().fillna(0.0)

    # day 0 is `salvage.simulate`'s own artifact (w_prev starts at all-zero,
    # so moving into 100% cash on day 0 always costs a turnover of 1.0) --
    # not specific to this candidate.
    assert turn.iloc[0] == pytest.approx(1.0)
    assert ret.iloc[0] == pytest.approx(-1.0 * cost_bps / 10_000.0)
    # before entry (after day 0): all cash, zero return
    assert (ret.iloc[1:entry_pos] == 0.0).all()
    # entry day: the asset's return minus the one-time entry turnover cost
    assert turn.iloc[entry_pos] == pytest.approx(2.0)
    expected_entry = sym_ret.iloc[entry_pos] - 2.0 * cost_bps / 10_000.0
    assert ret.iloc[entry_pos] == pytest.approx(expected_entry)
    # every day after entry: exactly the asset's return, no repeated cost
    assert (turn.iloc[entry_pos + 1 :] == 0.0).all()
    pd.testing.assert_series_equal(
        ret.iloc[entry_pos + 1 :], sym_ret.iloc[entry_pos + 1 :], check_names=False
    )


# --- leftover weight goes to SHY -------------------------------------------


def test_partial_weight_puts_remainder_in_shy() -> None:
    index = _synthetic_index(60)
    close, _open = _synthetic_panel(index)
    candidate = lane.ScreenCandidate(
        id="TEST_PARTIAL",
        name="60% SYM, 40% cash",
        source_card="test/synthetic",
        universe=("SYM",),
        freq="M",
        weights_fn=lambda _close, _asof: {"SYM": 0.6},
    )
    frame, dates = lane.weights_frame(close, candidate, 0)
    entry_pos = index.get_loc(dates[0]) + 1
    row = frame.iloc[entry_pos]
    assert row["SYM"] == pytest.approx(0.6)
    assert row["SHY"] == pytest.approx(0.4)
    assert row["SYM"] + row["SHY"] == pytest.approx(1.0)


# --- median-across-offsets bookkeeping -------------------------------------


def test_offset_summary_and_judged_offset() -> None:
    per_offset_net10 = {
        0: {"cagr": 0.10, "sharpe": 1.0, "max_dd": -0.20, "vol": 0.15},
        1: {"cagr": 0.30, "sharpe": 2.0, "max_dd": -0.05, "vol": 0.10},
        2: {"cagr": 0.20, "sharpe": 1.5, "max_dd": -0.10, "vol": 0.12},
        3: {"cagr": -0.10, "sharpe": -0.5, "max_dd": -0.40, "vol": 0.30},
        4: {"cagr": 0.05, "sharpe": 0.2, "max_dd": -0.25, "vol": 0.20},
    }
    summary = lane.offset_summary(per_offset_net10)
    assert summary["sharpe"] == {"min": -0.5, "median": 1.0, "max": 2.0}
    assert summary["cagr"]["median"] == pytest.approx(0.10)
    assert summary["max_dd"]["min"] == pytest.approx(-0.40)
    assert summary["max_dd"]["max"] == pytest.approx(-0.05)

    sharpe_by_offset = {o: v["sharpe"] for o, v in per_offset_net10.items()}
    # median sharpe (1.0) belongs to offset 0
    assert lane.judged_offset(sharpe_by_offset) == 0


# --- manifest guard refuses mismatched ids ---------------------------------


def test_manifest_guard_refuses_mismatched_ids(tmp_path: Path) -> None:
    iter_dir = tmp_path / "h_test_iter"
    iter_dir.mkdir()
    manifest = {"candidates": [{"candidate_id": "A"}, {"candidate_id": "B"}]}
    (iter_dir / "candidate-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(SystemExit):
        screen_batch.load_manifest_guard(iter_dir, ["A", "C"])

    # exact match (order-insensitive) is accepted
    result = screen_batch.load_manifest_guard(iter_dir, ["B", "A"])
    assert [c["candidate_id"] for c in result["candidates"]] == ["A", "B"]


def test_manifest_guard_missing_file(tmp_path: Path) -> None:
    with pytest.raises(SystemExit):
        screen_batch.load_manifest_guard(tmp_path / "does_not_exist", ["A"])


# --- freq="D": calendar-anchored daily rules, evaluated every session ------


def test_daily_rule_holds_only_the_day_after_each_first_of_month_signal() -> None:
    index = _synthetic_index(90)
    close, open_ = _synthetic_panel(index)
    leg_open, leg_close = lane.salvage.legs(close, open_)

    first_of_month = set(close.groupby(close.index.to_period("M")).apply(lambda g: g.index.min()))

    def weights_fn(_close: pd.DataFrame, asof: pd.Timestamp) -> dict[str, float]:
        return {"SYM": 1.0} if asof in first_of_month else {}

    candidate = lane.ScreenCandidate(
        id="D_TEST",
        name="hold SYM on the first trading day of each month",
        source_card="test/synthetic",
        universe=("SYM",),
        freq="D",
        weights_fn=weights_fn,
    )
    # cost_bps=0 isolates the holding pattern from the entry/exit turnover
    # cost artifacts covered by the buy-and-hold test above.
    ret, _turn = lane.candidate_returns_for_offset(close, leg_open, leg_close, candidate, 0, 0.0)

    sym_ret = close["SYM"].pct_change().fillna(0.0)
    nonzero_days = set(ret.index[ret.to_numpy() != 0.0])
    expected_days = {
        index[index.get_loc(d) + 1] for d in first_of_month if index.get_loc(d) + 1 < len(index)
    }
    assert nonzero_days == expected_days
    for d in expected_days:
        assert ret.loc[d] == pytest.approx(sym_ret.loc[d])


def test_daily_candidate_yields_exactly_one_version() -> None:
    candidate = lane.ScreenCandidate(
        id="D_ONE",
        name="daily rule",
        source_card="test/synthetic",
        universe=("SYM",),
        freq="D",
        weights_fn=lambda _close, _asof: {"SYM": 1.0},
    )
    offsets = lane.offsets_for_freq(candidate.freq)
    assert offsets == [0]

    # median-across-offsets collapses to the single value when n_offsets == 1
    per_offset_net10 = {0: {"cagr": 0.12, "sharpe": 0.9, "max_dd": -0.15, "vol": 0.18}}
    summary = lane.offset_summary(per_offset_net10)
    for metric, value in per_offset_net10[0].items():
        assert summary[metric] == {"min": value, "median": value, "max": value}


def test_daily_candidate_signal_dates_fn_restricts_evaluation() -> None:
    index = _synthetic_index(60)
    calls: list[pd.Timestamp] = []
    chosen = [index[5], index[20]]

    def weights_fn(_close: pd.DataFrame, asof: pd.Timestamp) -> dict[str, float]:
        calls.append(asof)
        return {"SYM": 1.0}

    candidate = lane.ScreenCandidate(
        id="D_SPARSE",
        name="evaluated on two dates only",
        source_card="test/synthetic",
        universe=("SYM",),
        freq="D",
        weights_fn=weights_fn,
        signal_dates_fn=lambda _index: chosen,
    )
    close, _open = _synthetic_panel(index)
    frame, dates = lane.weights_frame(close, candidate, 0)
    assert dates == chosen
    assert calls == chosen


def test_calendar_anchor_check_flags_month_end_rule_declared_monthly() -> None:
    import screen_batch as sb

    idx = pd.bdate_range("2020-01-01", "2021-12-31")
    close = pd.DataFrame({"SPY": np.linspace(100, 120, len(idx)), "SHY": 80.0}, index=idx)

    def month_end_only(frame: pd.DataFrame, asof: pd.Timestamp) -> dict[str, float]:
        month = frame.index[(frame.index.year == asof.year) & (frame.index.month == asof.month)]
        return {"SPY": 1.0} if month[-1] == asof else {}

    def trailing(frame: pd.DataFrame, asof: pd.Timestamp) -> dict[str, float]:
        return {"SPY": 1.0}

    bad = lane.ScreenCandidate("BAD", "bad", "x", ("SPY",), "M", month_end_only)
    good = lane.ScreenCandidate("GOOD", "good", "x", ("SPY",), "M", trailing)
    daily = lane.ScreenCandidate("DAILY", "d", "x", ("SPY",), "D", month_end_only)

    problems = sb.calendar_anchor_problems(close, [bad, good, daily])

    assert len(problems) == 1 and problems[0].startswith("BAD:")
