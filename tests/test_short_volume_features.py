"""H-20260916-07 follow-up: point-in-time FINRA short-volume-ratio features.

Every test here uses a small synthetic ``parsed.parquet`` fixture built in
this file -- never the real FINRA archive (that would make the test suite
depend on network access and on a multi-GB local download). The fixture is
redirected into ``scripts.build_short_volume_features`` by monkeypatching
its module-level ``PARSED_PATH``/``DUCKDB_TMP`` constants, since
:func:`build_year` reads them as globals at call time.

What is pinned, and why (mirrors the task's own list of required cases):

* the ratio maths (``short_volume / total_volume``, null when the
  denominator is not positive);
* the trailing rolling mean/z-score over exactly N *calendar* sessions,
  including the case where one of those sessions is a gap;
* the publication-lag shift (a feature row must use the *previous* session's
  FINRA file, never its own session's);
* missing-day handling (a gap must be NULL, never the last good value carried
  forward); and
* universe restriction (a symbol outside ``universe_symbols`` never appears
  in the output, even when the raw archive has full data for it).
"""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

import scripts.build_short_volume_features as bsvf
from open_composer.market_calendar import next_us_equity_session, us_equity_session_dates

YEAR = 2024
#: Ten consecutive real US equity sessions starting 2024-01-02, computed from
#: the shared calendar rather than hand-typed, so the fixture can never drift
#: out of sync with what ``next_us_equity_session`` itself would say.
SESSIONS = us_equity_session_dates(date(2024, 1, 1), date(2024, 3, 31))[:10]
S0, S1, S2, S3, S4, S5, S6, S7, S8, S9 = SESSIONS

#: AAA has real FINRA rows on every session except S4, a deliberate gap.
#: Ratios: 0.10, 0.20, 0.15, 0.30, <gap>, 0.25, 0.05, 0.40, 0.10, 0.20
AAA_ROWS = [
    (S0, 100.0, 1000.0),
    (S1, 200.0, 1000.0),
    (S2, 150.0, 1000.0),
    (S3, 300.0, 1000.0),
    # S4 intentionally omitted: the gap under test.
    (S5, 250.0, 1000.0),
    (S6, 50.0, 1000.0),
    (S7, 400.0, 1000.0),
    (S8, 100.0, 1000.0),
    (S9, 200.0, 1000.0),
]
#: A zero-total-volume day: the ratio must be null, not a divide-by-zero.
AAA_ZERO_VOLUME_DAY = (S6, 0.0, 0.0)

#: BBB has full coverage in the raw archive but is never in the universe --
#: it must not appear in the output at all.
BBB_ROWS = [(day, 10.0, 100.0) for day in SESSIONS]


def _write_parsed_fixture(path, rows: dict[str, list[tuple]]) -> None:
    records = []
    for symbol, symbol_rows in rows.items():
        for trade_date, short_volume, total_volume in symbol_rows:
            records.append(
                {
                    "trade_date": pd.Timestamp(trade_date),
                    "publication_date": pd.Timestamp(trade_date),
                    "visible_date": pd.Timestamp(next_us_equity_session(trade_date)),
                    "symbol": symbol,
                    "short_volume": short_volume,
                    "short_exempt_volume": 0.0,
                    "total_volume": total_volume,
                    "market_facilities": "Q",
                    "source": "test_fixture",
                    "fetched_at": pd.Timestamp.now(tz="UTC"),
                    "input_hash": "0" * 64,
                }
            )
    frame = pd.DataFrame.from_records(records)
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(path, index=False)


@pytest.fixture
def parsed_archive(tmp_path, monkeypatch):
    """Redirect the builder at a small synthetic archive with a known gap."""
    parsed_path = tmp_path / "parsed.parquet"
    _write_parsed_fixture(parsed_path, {"AAA": AAA_ROWS, "BBB": BBB_ROWS})
    monkeypatch.setattr(bsvf, "PARSED_PATH", parsed_path)
    monkeypatch.setattr(bsvf, "DUCKDB_TMP", tmp_path / "duckdb_tmp")
    # Bound the scan to the target year alone: the fixture's sessions all
    # fall in YEAR's first quarter, so a same-year window is enough lookback
    # for every window under test here and keeps the grid tiny.
    monkeypatch.setattr(bsvf, "LOOKBACK_YEARS", 0)
    return parsed_path


def _build(universe_symbols: list[str] = ("AAA", "BBB")) -> pd.DataFrame:
    return bsvf.build_year(
        YEAR,
        universe_symbols=list(universe_symbols),
        as_of=date(YEAR, 12, 31),
        memory_limit="512MB",
    )


def _row(frame: pd.DataFrame, symbol: str, trade_date: date) -> pd.Series:
    match = frame.loc[
        (frame["symbol"] == symbol) & (frame["trade_date"] == pd.Timestamp(trade_date))
    ]
    assert len(match) == 1, f"expected exactly one row for {symbol}/{trade_date}, got {len(match)}"
    return match.iloc[0]


# --------------------------------------------------------------------------
# ratio maths
# --------------------------------------------------------------------------


def test_ratio_is_short_volume_over_total_volume(parsed_archive) -> None:
    frame = _build()
    row = _row(frame, "AAA", next_us_equity_session(S1))
    assert row["observation_date"] == pd.Timestamp(S1)
    assert row["short_volume_ratio"] == pytest.approx(200.0 / 1000.0)


def test_ratio_is_null_when_total_volume_not_positive(tmp_path, monkeypatch) -> None:
    parsed_path = tmp_path / "parsed.parquet"
    rows = list(AAA_ROWS)
    rows[5] = AAA_ZERO_VOLUME_DAY  # replace the S6 row with a zero-volume day
    _write_parsed_fixture(parsed_path, {"AAA": rows})
    monkeypatch.setattr(bsvf, "PARSED_PATH", parsed_path)
    monkeypatch.setattr(bsvf, "DUCKDB_TMP", tmp_path / "duckdb_tmp")
    monkeypatch.setattr(bsvf, "LOOKBACK_YEARS", 0)

    frame = _build(["AAA"])
    row = _row(frame, "AAA", next_us_equity_session(S6))
    assert row["observation_date"] == pd.Timestamp(S6)
    assert row["total_volume"] == 0.0
    assert pd.isna(row["short_volume_ratio"])


# --------------------------------------------------------------------------
# publication-lag shift
# --------------------------------------------------------------------------


def test_no_row_ever_uses_its_own_sessions_file(parsed_archive) -> None:
    """Global invariant: every row's ``observation_date`` (the FINRA file it
    is built from) must be strictly earlier than its own ``trade_date`` (the
    session it is attached to and usable on). A same-day match here would be
    the exact look-ahead the module docstring's publication rule forbids.
    """
    frame = _build()
    with_record = frame.loc[frame["observation_date"].notna()]
    assert (with_record["observation_date"] < with_record["trade_date"]).all()


def test_feature_row_uses_the_immediately_preceding_session_only(parsed_archive) -> None:
    frame = _build()
    row = _row(frame, "AAA", next_us_equity_session(S2))
    assert row["observation_date"] == pd.Timestamp(S2)
    assert row["short_volume_ratio"] == pytest.approx(150.0 / 1000.0)

    # The session S2 itself must reflect S1's file, not S2's own same-day one.
    row_s2 = _row(frame, "AAA", S2)
    assert row_s2["observation_date"] == pd.Timestamp(S1)
    assert row_s2["short_volume_ratio"] == pytest.approx(200.0 / 1000.0)


# --------------------------------------------------------------------------
# missing-day handling
# --------------------------------------------------------------------------


def test_gap_day_produces_null_not_a_forward_filled_value(parsed_archive) -> None:
    """S4 has no raw row at all. The feature row attached to the session
    after S4 must be null, and specifically must NOT silently carry forward
    S3's ratio (0.30) -- that would turn an honest gap into a fabricated
    signal, which is the exact failure mode the task calls out.
    """
    feature_date = next_us_equity_session(S4)
    frame = _build(["AAA"])
    row = _row(frame, "AAA", feature_date)
    assert row["observation_date"] == pd.Timestamp(S4)
    assert pd.isna(row["short_volume_ratio"])
    assert not row["record_present"]
    prior_ratio = 300.0 / 1000.0
    assert row["short_volume_ratio"] != pytest.approx(prior_ratio)


def test_record_present_flag_distinguishes_gap_from_real_zero(parsed_archive) -> None:
    frame = _build(["AAA"])
    present = _row(frame, "AAA", next_us_equity_session(S0))
    gap = _row(frame, "AAA", next_us_equity_session(S4))
    assert bool(present["record_present"]) is True
    assert bool(gap["record_present"]) is False


# --------------------------------------------------------------------------
# trailing rolling mean / z-score
# --------------------------------------------------------------------------


def test_rolling_mean_5_skips_the_gap_rather_than_shrinking_the_window(parsed_archive) -> None:
    """The 5-calendar-session window ending at S4 (a gap) spans S0..S4. Only
    four of those five sessions have a real ratio; the mean must be the
    average of exactly those four (SQL's null-skipping AVG), not an average
    computed by reaching back to a 5th *available* observation (S5), which
    would silently redefine "5-session" to mean "5 non-null observations".
    """
    frame = _build(["AAA"])
    row = _row(frame, "AAA", next_us_equity_session(S4))
    expected_mean = pd.Series([0.10, 0.20, 0.15, 0.30]).mean()
    expected_std = pd.Series([0.10, 0.20, 0.15, 0.30]).std(ddof=1)
    assert row["short_volume_ratio_mean_5"] == pytest.approx(expected_mean)
    assert row["short_volume_ratio_std_5"] == pytest.approx(expected_std)
    # The current session's own ratio is null (it's the gap), so the z-score
    # must be null even though mean/std were both computable from history.
    assert pd.isna(row["short_volume_ratio_zscore_5"])


def test_zscore_5_matches_hand_computation_on_a_real_day(parsed_archive) -> None:
    frame = _build(["AAA"])
    row = _row(frame, "AAA", next_us_equity_session(S5))
    window = pd.Series([0.20, 0.15, 0.30, float("nan"), 0.25])  # S1..S5, S4 is the gap
    expected_mean = window.mean()  # pandas .mean() already skips NaN
    expected_std = window.std(ddof=1)
    expected_z = (0.25 - expected_mean) / expected_std
    assert row["short_volume_ratio_mean_5"] == pytest.approx(expected_mean)
    assert row["short_volume_ratio_zscore_5"] == pytest.approx(expected_z)


def test_warmup_guard_nulls_windows_before_enough_sessions_have_passed(parsed_archive) -> None:
    """At S3 (the 4th calendar session), a 5-session window has not yet been
    seen at all -- it must be null, matching pandas' ``min_periods=window``
    rolling default, not an average over whatever 4 rows happen to exist.
    """
    frame = _build(["AAA"])
    row = _row(frame, "AAA", next_us_equity_session(S3))
    assert row["observation_date"] == pd.Timestamp(S3)
    assert pd.isna(row["short_volume_ratio_mean_5"])
    assert pd.isna(row["short_volume_ratio_zscore_5"])
    assert pd.isna(row["short_volume_ratio_mean_21"])
    assert pd.isna(row["short_volume_ratio_mean_60"])


# --------------------------------------------------------------------------
# universe restriction
# --------------------------------------------------------------------------


def test_symbols_outside_the_universe_are_dropped_even_with_full_raw_coverage(
    parsed_archive,
) -> None:
    frame = _build(["AAA"])  # BBB has full raw coverage but is excluded here
    assert set(frame["symbol"]) == {"AAA"}


def test_universe_symbol_with_no_raw_coverage_gets_all_null_rows_not_dropped(
    tmp_path, monkeypatch
) -> None:
    parsed_path = tmp_path / "parsed.parquet"
    _write_parsed_fixture(parsed_path, {"AAA": AAA_ROWS})  # CCC has no raw rows at all
    monkeypatch.setattr(bsvf, "PARSED_PATH", parsed_path)
    monkeypatch.setattr(bsvf, "DUCKDB_TMP", tmp_path / "duckdb_tmp")
    monkeypatch.setattr(bsvf, "LOOKBACK_YEARS", 0)

    frame = bsvf.build_year(
        YEAR, universe_symbols=["AAA", "CCC"], as_of=date(YEAR, 12, 31), memory_limit="512MB"
    )
    ccc = frame.loc[frame["symbol"] == "CCC"]
    assert len(ccc) > 0
    assert ccc["record_present"].eq(False).all()
    assert ccc["short_volume_ratio"].isna().all()


# --------------------------------------------------------------------------
# schema sanity
# --------------------------------------------------------------------------


def test_feature_and_metadata_columns_do_not_overlap() -> None:
    assert set(bsvf.FEATURE_COLUMNS).isdisjoint(bsvf.METADATA_COLUMNS)


def test_output_columns_match_the_declared_contract(parsed_archive) -> None:
    frame = _build()
    expected = ["symbol", "trade_date", *bsvf.FEATURE_COLUMNS, *bsvf.METADATA_COLUMNS]
    assert list(frame.columns) == expected
