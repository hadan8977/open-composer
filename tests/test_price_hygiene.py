"""Regression tests for ``features.price_hygiene`` and its wiring into
``kernel.loop.returns_from_weight_schedule``.

Both failure modes are the real ones found by H-20260916-05 (see
``reports/research/lessons/L-20260916-05.md``), reduced to the smallest panel
that reproduces them:

* an unadjusted post-reorganization relisting (WW: 0.2496 -> 41.15 in one
  session, +16,386%), and
* a multi-session hole in the tape (AZUL: gone for months, back at 9.15,
  which ``pct_change()``'s default padding booked as +1,730% in one day).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from open_composer.research.features import price_hygiene
from open_composer.research.kernel import loop

SESSIONS = pd.bdate_range("2026-01-05", periods=24)


def _close_frame() -> pd.DataFrame:
    """Three symbols: a clean one, a reverse-split/relist one, a gap one."""
    clean = [100.0 * (1.001**i) for i in range(len(SESSIONS))]
    # SPLIT: flat at 0.25 for 12 sessions, then 40.00 onward (160x).
    split = [0.25] * 12 + [40.0 + 0.1 * i for i in range(len(SESSIONS) - 12)]
    # GAPPY: trades, disappears for 6 sessions, returns 2x higher -- a ratio
    # no jump threshold can catch, so only the gap rule sees it.
    gappy: list[float] = [10.0 + 0.05 * i for i in range(10)]
    gappy += [np.nan] * 6
    gappy += [21.0 + 0.05 * i for i in range(len(SESSIONS) - 16)]
    return pd.DataFrame(
        {"CLEAN": clean, "SPLIT": split, "GAPPY": gappy}, index=SESSIONS, dtype="float64"
    )


def test_detects_unadjusted_relisting_as_a_jump() -> None:
    breaks = price_hygiene.detect_price_breaks(_close_frame())
    jumps = [b for b in breaks if b.kind == "jump"]
    assert [b.symbol for b in jumps] == ["SPLIT"]
    jump = jumps[0]
    assert jump.price_ratio == pytest.approx(160.0)
    assert jump.gap_sessions == 1
    assert jump.last_session_before == SESSIONS[11]
    assert jump.first_session_after == SESSIONS[12]
    assert jump.as_dict()["log_return"] == pytest.approx(np.log(160.0), rel=1e-4)


def test_detects_multi_session_hole_as_a_gap_even_when_the_ratio_is_small() -> None:
    breaks = price_hygiene.detect_price_breaks(_close_frame())
    gaps = [b for b in breaks if b.kind == "gap"]
    assert [b.symbol for b in gaps] == ["GAPPY"]
    gap = gaps[0]
    # 7 sessions between the last pre-hole print and the resumption (6 missing).
    assert gap.gap_sessions == 7
    assert gap.price_ratio == pytest.approx(21.0 / 10.45)
    assert gap.price_ratio < price_hygiene.DEFAULT_MAX_ONE_DAY_PRICE_RATIO


def test_a_one_or_two_session_halt_is_left_alone() -> None:
    close = pd.DataFrame({"HALT": [10.0] * 5 + [np.nan, np.nan] + [7.0] * 5}, index=SESSIONS[:12])
    assert price_hygiene.detect_price_breaks(close) == []


def test_masking_blanks_pre_break_history_in_both_matrices_without_mutating_inputs() -> None:
    close = _close_frame()
    open_frame = close * 0.99
    close_before = close.copy()
    masked_close, masked_open, report = price_hygiene.sanitize_price_matrices(close, open_frame)

    pd.testing.assert_frame_equal(close, close_before)  # input untouched
    assert report.symbols_masked == 2
    assert report.symbols_masked_for_jump == 1
    assert report.symbols_masked_for_gap == 1
    assert report.masked_symbols == ("GAPPY", "SPLIT")

    # Everything up to and including the last break is gone; the post-break
    # security keeps its own history.
    assert masked_close.loc[: SESSIONS[11], "SPLIT"].isna().all()
    assert masked_close.loc[SESSIONS[12] :, "SPLIT"].notna().all()
    assert masked_open.loc[: SESSIONS[11], "SPLIT"].isna().all()
    assert masked_close.loc[: SESSIONS[15], "GAPPY"].isna().all()
    assert masked_close.loc[SESSIONS[16] :, "GAPPY"].notna().all()
    # An untouched symbol is byte-for-byte unchanged.
    pd.testing.assert_series_equal(masked_close["CLEAN"], close_before["CLEAN"])


def test_a_short_hole_that_reopens_near_the_same_price_is_reported_not_masked() -> None:
    """An illiquid name that goes a week without a trade is still itself.

    Dropping ghost bars is what makes these holes visible at all, so without
    this rule the source fix would have deleted the prior history of 75 extra
    symbols on the real panel for no reason.
    """
    prices = [10.0] * 8 + [np.nan] * 6 + [10.1] * (len(SESSIONS) - 14)
    close = pd.DataFrame({"ILLIQ": prices}, index=SESSIONS)
    frames, report = price_hygiene.mask_regime_breaks(close)
    assert [b.kind for b in report.breaks] == ["gap"]
    assert report.breaks[0].masked is False
    assert report.masked_symbols == ()
    pd.testing.assert_frame_equal(frames[0], close)
    # The crossing day still books nothing rather than a fabricated move.
    assert np.isnan(price_hygiene.daily_returns_no_pad(close).iloc[14, 0])


def test_a_long_hole_is_masked_even_when_the_price_step_is_small() -> None:
    """NBIS/Yandex: off the tape for 666 sessions, back 5.6% higher."""
    prices = [10.0] * 2 + [np.nan] * 21 + [10.56]
    close = pd.DataFrame({"NBIS": prices}, index=SESSIONS)
    _, report = price_hygiene.mask_regime_breaks(close)
    assert report.masked_symbols == ("NBIS",)
    assert report.symbols_masked_for_gap == 1
    assert report.breaks[0].gap_sessions == 22


def test_manifest_is_json_ready_and_says_padding_is_off() -> None:
    _, _, report = price_hygiene.sanitize_price_matrices(_close_frame())
    manifest = report.manifest()
    assert manifest["contract"] == price_hygiene.PRICE_HYGIENE_CONTRACT
    assert manifest["pad_across_gaps"] is False
    assert manifest["corporate_action_feed"] == "none_available"
    assert manifest["thresholds"]["max_gap_sessions"] == price_hygiene.DEFAULT_MAX_GAP_SESSIONS
    assert set(manifest["breaks_by_symbol"]) == {"SPLIT", "GAPPY"}
    assert manifest["breaks_by_symbol"]["SPLIT"][0]["kind"] == "jump"


def test_a_break_explained_by_a_corporate_action_feed_is_reported_but_not_masked() -> None:
    close = _close_frame()
    actions = {"SPLIT": [SESSIONS[12]]}
    breaks = price_hygiene.detect_price_breaks(close, known_corporate_actions=actions)
    explained = [b for b in breaks if b.explained_by_corporate_action]
    assert [b.symbol for b in explained] == ["SPLIT"]
    frames, report = price_hygiene.mask_regime_breaks(close, known_corporate_actions=actions)
    assert report.masked_symbols == ("GAPPY",)
    assert frames[0].loc[: SESSIONS[11], "SPLIT"].notna().all()


def test_returns_are_never_padded_across_a_hole() -> None:
    prices = pd.Series([10.0, np.nan, np.nan, 30.0], index=SESSIONS[:4])
    padded = price_hygiene.daily_returns_padding_gaps_legacy(prices)  # the defect
    assert padded.iloc[3] == pytest.approx(2.0)
    clean = price_hygiene.daily_returns_no_pad(prices)
    assert np.isnan(clean.iloc[3])


def test_ghost_bars_are_dropped_and_real_flat_sessions_are_kept() -> None:
    frame = pd.DataFrame(
        {
            "symbol": ["WW", "WW", "WW", "ILLIQ"],
            "trade_date": list(SESSIONS[:3]) + [SESSIONS[0]],
            "open": [0.2496, 0.2496, 41.15, 3.0],
            "high": [0.2496, 0.2496, 41.61, 3.0],
            "low": [0.2496, 0.2496, 36.0, 3.0],
            "close": [0.2496, 0.2496, 40.0, 3.0],
            "volume": [0.0, 0.0, 406271.0, 100.0],
            "trade_count": [0.0, 0.0, 3297.0, 1.0],
        }
    )
    kept = price_hygiene.drop_ghost_bars(frame)
    assert list(kept["symbol"]) == ["WW", "ILLIQ"]
    assert kept.loc[kept["symbol"] == "WW", "close"].tolist() == [40.0]
    assert price_hygiene.is_ghost_bar(frame).tolist() == [True, True, False, False]


def _single_name_schedule(symbol: str, date: pd.Timestamp) -> list[loop.RebalanceEvent]:
    return [
        loop.RebalanceEvent(
            date=date.isoformat(), universe_size=1, selected={symbol: 1.0}, portfolio_beta=None
        )
    ]


@pytest.mark.parametrize(
    ("symbol", "fabricated_return"),
    [("SPLIT", 159.0), ("GAPPY", 1.0095)],
)
def test_kernel_no_longer_books_a_fabricated_return_across_a_break(
    symbol: str, fabricated_return: float
) -> None:
    """Hold the broken name across its break: with hygiene off the book
    earns the fabricated move (this is the AZUL/WW defect), with hygiene on
    the position is priced as absent (the kernel's cash residual) instead.
    """
    close = _close_frame()
    spy_returns = pd.Series(0.0, index=SESSIONS)
    schedule = _single_name_schedule(symbol, SESSIONS[0])

    unhygienic = loop.returns_from_weight_schedule(
        schedule,
        close,
        spy_returns,
        cost_bps_per_side=0.0,
        include_hedge=False,
        price_hygiene_enabled=False,
    )
    assert unhygienic.max() == pytest.approx(fabricated_return, rel=0.05)
    assert not loop.LAST_PRICE_HYGIENE_MANIFEST

    hygienic = loop.returns_from_weight_schedule(
        schedule,
        close,
        spy_returns,
        cost_bps_per_side=0.0,
        include_hedge=False,
    )
    assert hygienic.abs().max() < 0.05
    assert loop.LAST_PRICE_HYGIENE_MANIFEST["symbols_masked"] == 2
    assert symbol in loop.LAST_PRICE_HYGIENE_MANIFEST["breaks_by_symbol"]


def test_kernel_prices_a_clean_name_identically_with_and_without_hygiene() -> None:
    close = _close_frame()
    spy_returns = pd.Series(0.0, index=SESSIONS)
    schedule = _single_name_schedule("CLEAN", SESSIONS[0])
    kwargs = {"cost_bps_per_side": 10.0, "include_hedge": False}
    with_hygiene = loop.returns_from_weight_schedule(schedule, close, spy_returns, **kwargs)
    without = loop.returns_from_weight_schedule(
        schedule, close, spy_returns, price_hygiene_enabled=False, **kwargs
    )
    pd.testing.assert_series_equal(with_hygiene, without)


def test_daily_feature_builder_drops_ghost_bars_at_the_source(tmp_path) -> None:
    """The source fix: ``build_daily_features`` must not read a placeholder
    session as a trading day. Without it the flat ghost segment hides the
    hole, ``vol_*`` collapses toward zero and ``dollar_adv_*`` reads 0.
    """
    from open_composer.research.features.daily_features import build_daily_features

    dates = pd.bdate_range("2020-01-01", periods=30)
    rows: list[dict[str, object]] = []
    for symbol, base in (("REAL", 100.0), ("GHOST", 20.0), ("SPY", 300.0)):
        price = base
        for index, date in enumerate(dates):
            ghosted = symbol == "GHOST" and 10 <= index < 20
            price = price if ghosted else price * 1.01
            rows.append(
                {
                    "symbol": symbol,
                    "timestamp": date,
                    "open": price,
                    "high": price,
                    "low": price,
                    "close": price,
                    "volume": 0.0 if ghosted else 1_000_000.0,
                    "trade_count": 0.0 if ghosted else 5_000.0,
                }
            )
    shard = tmp_path / "2020"
    shard.mkdir(parents=True)
    pd.DataFrame(rows).to_parquet(shard / "shard-0000.parquet", index=False)

    frame = build_daily_features(
        str(tmp_path / "*" / "*.parquet"),
        ["REAL", "GHOST"],
        return_windows=(1, 3, 5),
        vol_windows=(3,),
        beta_window=5,
        idio_vol_window=3,
        max_return_window=3,
        adv_windows=(3, 5),
        amihud_window=3,
        high_window=5,
        momentum_long_window=5,
        momentum_skip_window=3,
        memory_limit="512MB",
    )
    ghost_dates = set(dates[10:20])
    kept = frame.loc[frame["symbol"] == "GHOST", "trade_date"]
    assert not ghost_dates & set(kept)
    assert len(kept) == 20
    # The surviving REAL series is untouched: every session is still there.
    assert (frame["symbol"] == "REAL").sum() == 30
    # And no ghost-driven zero-volume liquidity row survives.
    assert (frame["dollar_adv_3"].dropna() > 0).all()
