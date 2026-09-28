"""T-20260928-07: synthetic-data unit tests for `scripts/shadow_forward.py`.

No network, no market panel -- everything here builds small hand-computed
`close`/`open_` frames the same way `tests/test_screen_lane.py` does.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import run_h20260922_05_salvage as salvage  # noqa: E402
import screen_lane as lane  # noqa: E402
import shadow_forward as sf  # noqa: E402


def _synthetic_index(periods: int) -> pd.DatetimeIndex:
    return pd.bdate_range("2020-01-01", periods=periods)


def _synthetic_panel(
    index: pd.DatetimeIndex, daily_ret: float = 0.001
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """SYM compounds at `daily_ret`/day, SHY (cash) is flat. `open[i] ==
    close[i-1]` (no overnight gap), the same convention `test_screen_lane.py`
    uses, so the whole day's move is earned by the weight effective at that
    day's open."""
    n = len(index)
    sym = 100.0 * ((1.0 + daily_ret) ** np.arange(n))
    shy = np.full(n, 100.0)
    close = pd.DataFrame({"SYM": sym, "SHY": shy}, index=index)
    open_ = close.shift(1)
    open_.iloc[0] = close.iloc[0]
    return close, open_


def _always_long_sym(close: pd.DataFrame, asof: pd.Timestamp) -> dict[str, float]:
    return {"SYM": 1.0}


def _alternate_long_sym(close: pd.DataFrame, asof: pd.Timestamp) -> dict[str, float]:
    """Long SYM on even index positions, flat (all cash) on odd ones -- gives
    genuinely different weight schedules across rebalance offsets so a
    median-across-offsets test isn't tautological."""
    pos = close.index.get_loc(asof)
    return {"SYM": 1.0} if pos % 2 == 0 else {}


# --------------------------------------------------------------------------
# (1) only post-kept_at returns are used
# --------------------------------------------------------------------------


def test_window_metrics_excludes_pre_kept_at_returns() -> None:
    index = _synthetic_index(60)
    # A synthetic return series: +50% on day 10 (well before kept_at), flat
    # 0.1%/day afterwards. If pre-kept_at data leaked in, cum_return would be
    # dominated by the day-10 jump.
    ret = pd.Series(0.001, index=index)
    ret.iloc[10] = 0.50
    turn = pd.Series(0.0, index=index)
    rf = pd.Series(0.0, index=index)
    kept_ts = index[20]  # after the jump

    mask = ret.index > kept_ts
    result = sf.window_metrics(ret, turn, rf, mask)

    expected_n = len(index) - 21  # strictly after position 20
    assert result["n"] == expected_n
    expected_cum = float((1.001**expected_n) - 1.0)
    assert result["cum_return"] == pytest.approx(expected_cum, rel=1e-9)
    # the +50% jump on day 10 must not leak into the forward slice
    assert result["cum_return"] < 1.0


def test_candidate_forward_metrics_daily_rule_only_sees_forward_dates() -> None:
    index = _synthetic_index(60)
    close, open_ = _synthetic_panel(index)
    leg_open, leg_close = salvage.legs(close, open_)
    rf = pd.Series(0.0, index=index)
    candidate = lane.ScreenCandidate(
        id="ALWAYS_LONG",
        name="always long SYM",
        source_card="test",
        universe=("SYM",),
        freq="D",
        weights_fn=_always_long_sym,
    )
    kept_ts = index[40]

    fwd, forward_index = sf.candidate_forward_metrics(
        close, leg_open, leg_close, rf, candidate, kept_ts
    )

    assert forward_index.min() > kept_ts
    assert fwd["n"] == len(index) - 41
    # full-history return for comparison: cum_return over the forward slice
    # must be strictly smaller than the full-history cumulative return.
    full_ret, _ = lane.candidate_returns_for_offset(
        close, leg_open, leg_close, candidate, 0, lane.COST_BPS_PRIMARY
    )
    full_cum = float((1.0 + full_ret).prod() - 1.0)
    assert fwd["cum_return"] < full_cum


# --------------------------------------------------------------------------
# (2) median across offsets is used for M/W rules
# --------------------------------------------------------------------------


def test_combine_offsets_takes_the_median() -> None:
    per_offset = [
        {"n": 40, "cum_return": 0.05, "sharpe": 1.0, "max_dd": -0.02},
        {"n": 40, "cum_return": 0.10, "sharpe": 2.0, "max_dd": -0.05},
        {"n": 40, "cum_return": 0.20, "sharpe": 3.0, "max_dd": -0.10},
    ]
    combined = sf.combine_offsets(per_offset)
    assert combined["n"] == 40
    assert combined["cum_return"] == pytest.approx(0.10)
    assert combined["sharpe"] == pytest.approx(2.0)
    assert combined["max_dd"] == pytest.approx(-0.05)


def test_combine_offsets_skips_none_values() -> None:
    per_offset = [
        {"n": 10, "cum_return": 0.01, "sharpe": None, "max_dd": None},
        {"n": 10, "cum_return": 0.02, "sharpe": None, "max_dd": None},
    ]
    combined = sf.combine_offsets(per_offset)
    assert combined["sharpe"] is None
    assert combined["max_dd"] is None
    assert combined["cum_return"] == pytest.approx(0.015)


def test_weekly_rule_forward_metric_is_the_median_across_offsets() -> None:
    index = _synthetic_index(260)
    close, open_ = _synthetic_panel(index, daily_ret=0.002)
    leg_open, leg_close = salvage.legs(close, open_)
    rf = pd.Series(0.0, index=index)
    candidate = lane.ScreenCandidate(
        id="ALTERNATING",
        name="alternating SYM/cash",
        source_card="test",
        universe=("SYM",),
        freq="W",
        weights_fn=_alternate_long_sym,
    )
    kept_ts = index[60]

    fwd, _ = sf.candidate_forward_metrics(close, leg_open, leg_close, rf, candidate, kept_ts)

    # recompute independently at every weekly offset and take the median by
    # hand, the same way `screen_lane.offset_summary` judges the frozen
    # backtest -- confirms the pipeline doesn't just report a single offset.
    per_offset = []
    for o in lane.WEEKLY_OFFSETS:
        ret, turn = lane.candidate_returns_for_offset(
            close, leg_open, leg_close, candidate, o, lane.COST_BPS_PRIMARY
        )
        mask = ret.index > kept_ts
        per_offset.append(sf.window_metrics(ret, turn, rf, mask))
    expected_sharpe = float(np.median([d["sharpe"] for d in per_offset if d["sharpe"] is not None]))

    assert fwd["sharpe"] == pytest.approx(expected_sharpe)
    # the offsets must actually differ, otherwise this isn't testing the
    # median mechanism at all.
    sharpes = {d["sharpe"] for d in per_offset if d["sharpe"] is not None}
    assert len(sharpes) > 1


# --------------------------------------------------------------------------
# (3) a changed module hash is flagged
# --------------------------------------------------------------------------


def test_integrity_status_ok_when_commits_match() -> None:
    assert sf.integrity_status("abc123", "abc123") == "ok"


def test_integrity_status_flags_changed_commit() -> None:
    assert sf.integrity_status("abc123", "def456") == "rule changed after freeze"


def test_integrity_status_flags_missing_commit_either_side() -> None:
    assert sf.integrity_status(None, "def456") == "rule changed after freeze"
    assert sf.integrity_status("abc123", None) == "rule changed after freeze"


def test_process_excludes_candidate_with_changed_module(monkeypatch: pytest.MonkeyPatch) -> None:
    index = _synthetic_index(60)
    close, open_ = _synthetic_panel(index)
    leg_open, leg_close = salvage.legs(close, open_)
    candidate = lane.ScreenCandidate(
        id="C1",
        name="c1",
        source_card="test",
        universe=("SYM",),
        freq="D",
        weights_fn=_always_long_sym,
    )

    class _FakeModule:
        CANDIDATES = [candidate]

    kept_lines = [
        {
            "id": "kept:iter:C1",
            "iteration": "iter",
            "kept_at": str(index[10].date()) + "T00:00:00+00:00",
            "commit": "recorded_sha",
            "module": "scripts/screen_batches/does_not_matter.py",
            "candidate_id": "C1",
            "tier": "watch_recent",
        }
    ]

    monkeypatch.setattr(sf, "load_candidate_module", lambda path: _FakeModule())
    monkeypatch.setattr(sf, "git_file_commit_now", lambda path: "different_sha")
    # process() also builds S3/SPY; stub those out too since this candidate
    # panel doesn't have the full S3 universe.
    monkeypatch.setattr(salvage, "legs", lambda c, o: (leg_open, leg_close))
    monkeypatch.setattr(
        lane,
        "s3_incumbent",
        lambda close, lo, lc, cost: (
            pd.Series(0.0, index=close.index),
            pd.Series(0.0, index=close.index),
        ),
    )
    close_with_spy = close.copy()
    close_with_spy["SPY"] = 100.0
    close_with_spy[lane.RF] = 100.0  # "BIL": needed by process()'s rf series
    monkeypatch.setattr(sf, "load_forward_panel", lambda symbols: (close_with_spy, open_))

    rows, dropped = sf.process(kept_lines)

    assert dropped == []
    assert len(rows) == 1
    assert rows[0]["integrity"] == "rule changed after freeze"
    assert rows[0]["excluded_from_verdict"] is True
    assert rows[0]["forward"]["cum_return"] is None


# --------------------------------------------------------------------------
# (4) watch_recent exit rule: fires at the thresholds, not before 63 sessions
# --------------------------------------------------------------------------


def test_watch_exit_not_applicable_outside_watch_recent_tier() -> None:
    result = sf.watch_exit_status("kept", n=200, sharpe=0.1, max_dd=-0.5, anchor_dd=-0.05)
    assert result == {"applicable": False}


def test_watch_exit_too_early_before_63_sessions() -> None:
    result = sf.watch_exit_status(
        "watch_recent", n=sf.WATCH_EXIT_MIN_SESSIONS - 1, sharpe=0.1, max_dd=-0.5, anchor_dd=-0.05
    )
    assert result["status"] == "too early"


def test_watch_exit_fires_on_low_sharpe_at_threshold_sessions() -> None:
    result = sf.watch_exit_status(
        "watch_recent",
        n=sf.WATCH_EXIT_MIN_SESSIONS,
        sharpe=0.49,
        max_dd=-0.01,
        anchor_dd=-0.05,
    )
    assert result["status"] == "exit"
    assert any("sharpe" in r for r in result["reasons"])


def test_watch_exit_does_not_fire_at_exactly_0_5_sharpe() -> None:
    # threshold is "< 0.5", not "<= 0.5"
    result = sf.watch_exit_status(
        "watch_recent", n=sf.WATCH_EXIT_MIN_SESSIONS, sharpe=0.5, max_dd=-0.01, anchor_dd=-0.05
    )
    assert result["status"] == "hold"


def test_watch_exit_fires_on_dd_exceeding_1_5x_anchor() -> None:
    anchor_dd = -0.05
    result = sf.watch_exit_status(
        "watch_recent",
        n=sf.WATCH_EXIT_MIN_SESSIONS,
        sharpe=1.0,
        max_dd=-0.076,  # more negative than 1.5 * -0.05 = -0.075
        anchor_dd=anchor_dd,
    )
    assert result["status"] == "exit"
    assert any("max DD" in r for r in result["reasons"])


def test_watch_exit_does_not_fire_at_exactly_1_5x_dd() -> None:
    anchor_dd = -0.05
    result = sf.watch_exit_status(
        "watch_recent",
        n=sf.WATCH_EXIT_MIN_SESSIONS,
        sharpe=1.0,
        max_dd=-0.075,  # exactly 1.5x, not beyond
        anchor_dd=anchor_dd,
    )
    assert result["status"] == "hold"


def test_watch_exit_holds_when_within_both_thresholds() -> None:
    result = sf.watch_exit_status("watch_recent", n=200, sharpe=1.2, max_dd=-0.03, anchor_dd=-0.05)
    assert result["status"] == "hold"
    assert result["reasons"] == []


# --------------------------------------------------------------------------
# dropped-tier filtering and replaces-relation labeling
# --------------------------------------------------------------------------


def test_process_treats_dropped_tier_as_untracked() -> None:
    kept_lines = [
        {
            "id": "kept:iter:D1",
            "candidate_id": "D1",
            "iteration": "iter",
            "tier": "dropped_by_owner",
            "dropped_note": "owner dropped it",
        }
    ]
    rows, dropped = sf.process(kept_lines)
    assert rows == []
    assert len(dropped) == 1
    assert dropped[0]["tier"] == "dropped"
    assert dropped[0]["status"] == "dropped, not tracked"


def test_build_relations_labels_base_and_replacement() -> None:
    lines = [
        {"id": "kept:iter:A", "candidate_id": "A", "tier": "watch_recent"},
        {
            "id": "kept:iter:A2",
            "candidate_id": "A2",
            "tier": "watch_recent",
            "replaces": "kept:iter:A",
        },
    ]
    relations = sf.build_relations(lines)
    assert relations["kept:iter:A"] == "base, replaced by kept:iter:A2"
    assert relations["kept:iter:A2"] == "replacement, replaces kept:iter:A"


def test_kept_at_to_ts_normalizes_and_strips_tz() -> None:
    ts_z = sf.kept_at_to_ts("2026-09-28T06:10:45.010708Z")
    ts_offset = sf.kept_at_to_ts("2026-09-28T03:40:43.742482+00:00")
    assert ts_z == pd.Timestamp("2026-09-28")
    assert ts_offset == pd.Timestamp("2026-09-28")
    assert ts_z.tzinfo is None
