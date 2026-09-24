"""H-20260923 (SEC XBRL fundamentals): point-in-time selection, restatement
flagging, usable-session timing, forward fill, and the derived-signal
formulas -- all on small synthetic ``companyfacts``-shaped data, no network.

Four things are pinned here, because each is a place this pipeline could
silently become a look-ahead pipeline or misread SEC's own XBRL quirks:

* :func:`select_first_filed` -- the (cik, tag, period_start, period_end) key
  must not collide a single-quarter fact with a cumulative year-to-date fact
  that happens to share the same ``end``/``fy``/``fp`` (a documented SEC XBRL
  pattern), and a genuine restatement must be flagged rather than silently
  overwriting the as-first-reported value.
* :func:`attach_usable_session` -- a same-day filing is never usable the same
  session.
* :func:`_running_latest` -- a late-filed restatement of an older,
  already-superseded period must never regress the current forward-filled
  value backward.
* :func:`sue_series` -- the Foster-Olsen-Shevlin seasonal-random-walk
  arithmetic, hand-checked against an independently computed numpy array.
"""

from __future__ import annotations

import json
from datetime import date

import numpy as np
import pandas as pd
import pytest

from open_composer.market_calendar import next_us_equity_session
from scripts.build_sec_xbrl_fundamentals import (
    _lagged_average,
    _quarterly_dict,
    _running_latest,
    apply_concept_fallback,
    attach_usable_session,
    build_facts_batch,
    classify_period,
    compute_cik_table,
    fact_rows_from_payload,
    rows_to_frame,
    select_first_filed,
    sue_series,
)

# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------


def _entry(
    end: str,
    val: float,
    accn: str,
    filed: str,
    *,
    fy: int,
    fp: str,
    form: str,
    start: str | None = None,
) -> dict:
    entry = {"end": end, "val": val, "accn": accn, "fy": fy, "fp": fp, "form": form, "filed": filed}
    if start is not None:
        entry["start"] = start
    return entry


def _payload(cik: int, facts: dict[str, dict[str, dict[str, list[dict]]]]) -> dict:
    """``facts``: ``{taxonomy: {tag: {unit: [entries]}}}``."""
    return {
        "cik": cik,
        "entityName": f"COMPANY {cik}",
        "facts": {
            taxonomy: {tag: {"units": units} for tag, units in tags.items()}
            for taxonomy, tags in facts.items()
        },
    }


def _rows_for(cik: int, payload: dict) -> pd.DataFrame:
    return rows_to_frame(fact_rows_from_payload(cik, payload, "test"))


# --------------------------------------------------------------------------
# first-filed selection / restatement flag
# --------------------------------------------------------------------------


def test_select_first_filed_flags_a_genuine_restatement() -> None:
    # The exact live case from the intel brief: Apple FY2008 Assets,
    # originally $39.572B, revised to $36.171B by a 10-K/A five months later.
    payload = _payload(
        320193,
        {
            "us-gaap": {
                "Assets": {
                    "USD": [
                        _entry(
                            "2008-09-27",
                            39572000000,
                            "0001193125-09-214859",
                            "2009-10-27",
                            fy=2009,
                            fp="FY",
                            form="10-K",
                        ),
                        _entry(
                            "2008-09-27",
                            36171000000,
                            "0001193125-10-012091",
                            "2010-01-25",
                            fy=2009,
                            fp="FY",
                            form="10-K/A",
                        ),
                    ]
                }
            }
        },
    )
    frame = select_first_filed(_rows_for(320193, payload))
    frame = frame.sort_values("filed").reset_index(drop=True)
    assert len(frame) == 2
    assert frame.loc[0, "val"] == 39572000000
    assert frame.loc[0, "restated"] is np.bool_(False) or frame.loc[0, "restated"] == False  # noqa: E712
    assert frame.loc[1, "val"] == 36171000000
    assert bool(frame.loc[1, "restated"]) is True


def test_select_first_filed_drops_a_duplicate_reaffirmation() -> None:
    # A third filing repeats the *already-restated* value as a comparative
    # figure -- this must be dropped, not counted as a second restatement.
    payload = _payload(
        1,
        {
            "us-gaap": {
                "Assets": {
                    "USD": [
                        _entry(
                            "2019-12-31", 100.0, "A", "2020-02-01", fy=2020, fp="FY", form="10-K"
                        ),
                        _entry(
                            "2019-12-31", 90.0, "B", "2020-06-01", fy=2020, fp="FY", form="10-K/A"
                        ),
                        _entry(
                            "2019-12-31", 90.0, "C", "2021-02-01", fy=2021, fp="FY", form="10-K"
                        ),
                    ]
                }
            }
        },
    )
    frame = select_first_filed(_rows_for(1, payload))
    assert len(frame) == 2
    assert sorted(frame["val"].tolist()) == [90.0, 100.0]
    assert sorted(frame["restated"].tolist()) == [False, True]


def test_select_first_filed_does_not_collide_quarterly_and_ytd_facts() -> None:
    # Same (end, fy, fp): a 3-month Q3 fact and a 9-month YTD Q3 fact, the
    # exact SEC XBRL duplicate-context pattern the module docstring warns
    # about. Different `start`, so they must survive as two distinct facts,
    # neither flagged as a restatement of the other.
    payload = _payload(
        2,
        {
            "us-gaap": {
                "EarningsPerShareDiluted": {
                    "USD/shares": [
                        _entry(
                            "2026-06-27",
                            2.02,
                            "A",
                            "2026-07-31",
                            fy=2026,
                            fp="Q3",
                            form="10-Q",
                            start="2026-03-29",
                        ),
                        _entry(
                            "2026-06-27",
                            6.88,
                            "A",
                            "2026-07-31",
                            fy=2026,
                            fp="Q3",
                            form="10-Q",
                            start="2025-09-28",
                        ),
                    ]
                }
            }
        },
    )
    frame = select_first_filed(_rows_for(2, payload))
    assert len(frame) == 2
    assert not frame["restated"].any()
    assert sorted(frame["val"].tolist()) == [2.02, 6.88]


# --------------------------------------------------------------------------
# concept fallback
# --------------------------------------------------------------------------


def test_apply_concept_fallback_prefers_the_higher_priority_tag() -> None:
    payload = _payload(
        3,
        {
            "us-gaap": {
                "Revenues": {
                    "USD": [
                        _entry(
                            "2020-12-31",
                            1000.0,
                            "A",
                            "2021-02-01",
                            fy=2020,
                            fp="FY",
                            form="10-K",
                            start="2020-01-01",
                        )
                    ]
                },
                "SalesRevenueNet": {
                    "USD": [
                        # Same period as above (should lose to Revenues).
                        _entry(
                            "2020-12-31",
                            999.0,
                            "Z",
                            "2021-02-01",
                            fy=2020,
                            fp="FY",
                            form="10-K",
                            start="2020-01-01",
                        ),
                        # A period only SalesRevenueNet covers (should survive).
                        _entry(
                            "2019-12-31",
                            800.0,
                            "Y",
                            "2020-02-01",
                            fy=2019,
                            fp="FY",
                            form="10-K",
                            start="2019-01-01",
                        ),
                    ]
                },
            }
        },
    )
    frame = select_first_filed(_rows_for(3, payload))
    frame = apply_concept_fallback(frame)
    revenue = frame.loc[frame["concept"] == "revenue"].sort_values("period_end")
    assert revenue["val"].tolist() == [800.0, 1000.0]
    assert revenue["tag"].tolist() == ["SalesRevenueNet", "Revenues"]


def test_apply_concept_fallback_keeps_instant_concepts() -> None:
    # Regression: instant concepts (total_assets, stockholders_equity,
    # shares_outstanding) have period_start = NaT on every row. pandas
    # groupby's default dropna=True excludes NaN/NaT group keys entirely,
    # which silently deleted every instant-concept row here until fixed.
    payload = _payload(
        8,
        {
            "us-gaap": {
                "Assets": {
                    "USD": [
                        _entry(
                            "2020-12-31", 500.0, "A", "2021-02-01", fy=2020, fp="FY", form="10-K"
                        )
                    ]
                }
            }
        },
    )
    frame = select_first_filed(_rows_for(8, payload))
    frame = apply_concept_fallback(frame)
    assets = frame.loc[frame["concept"] == "total_assets"]
    assert len(assets) == 1
    assert assets["val"].iloc[0] == 500.0


# --------------------------------------------------------------------------
# period classification
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("start", "end", "expected"),
    [
        (None, "2020-12-31", "instant"),
        ("2020-01-01", "2020-03-31", "Q"),  # 90 days
        ("2020-01-01", "2020-12-31", "FY"),  # 365 days
        ("2020-01-01", "2020-06-30", "YTD_other"),  # ~181 days, half-year
        ("2020-01-01", "2020-09-30", "YTD_other"),  # ~274 days, 9-month
    ],
)
def test_classify_period_bands(start: str | None, end: str, expected: str) -> None:
    starts = pd.Series([pd.Timestamp(start) if start else pd.NaT])
    ends = pd.Series([pd.Timestamp(end)])
    assert classify_period(starts, ends).iloc[0] == expected


# --------------------------------------------------------------------------
# malformed source dates (real SEC XBRL data quality, observed live)
# --------------------------------------------------------------------------


def test_rows_to_frame_survives_a_garbage_start_date() -> None:
    # Observed live in this build: a filer's `start` was "0202-02-01"
    # (evidently a typo for "2002-..."), a year pandas cannot represent as a
    # nanosecond timestamp -- this used to raise OutOfBoundsDatetime and
    # crash the whole batch. It must instead survive as an excluded row, not
    # be misclassified as an instant fact.
    payload = _payload(
        9,
        {
            "us-gaap": {
                "Revenues": {
                    "USD": [
                        _entry(
                            "2002-03-31",
                            100.0,
                            "A",
                            "2002-05-01",
                            fy=2002,
                            fp="Q1",
                            form="10-Q",
                            start="0202-02-01",
                        )
                    ]
                }
            }
        },
    )
    frame = rows_to_frame(fact_rows_from_payload(9, payload, "test"))
    assert len(frame) == 1
    assert frame.loc[0, "period_kind"] == "YTD_other"
    assert pd.isna(frame.loc[0, "period_start"])


def test_rows_to_frame_drops_a_fact_with_an_unparseable_end_or_filed_date() -> None:
    payload = _payload(
        10,
        {
            "us-gaap": {
                "Assets": {
                    "USD": [
                        _entry("0202-12-31", 1.0, "A", "2020-02-01", fy=2020, fp="FY", form="10-K"),
                        _entry("2020-12-31", 2.0, "B", "0202-02-01", fy=2020, fp="FY", form="10-K"),
                    ]
                }
            }
        },
    )
    frame = rows_to_frame(fact_rows_from_payload(10, payload, "test"))
    assert frame.empty


def test_rows_to_frame_drops_a_period_end_after_its_own_filed_date() -> None:
    # Observed live in this build: 422 of 2.2M rows (concentrated in the
    # manually-entered cover-page shares-outstanding date) had a period_end
    # years after the filing date -- a logical impossibility (you cannot
    # file a report before the period it covers has ended) that would
    # otherwise get "stuck" as _running_latest's forever-most-recent value.
    payload = _payload(
        11,
        {
            "dei": {
                "EntityCommonStockSharesOutstanding": {
                    "shares": [
                        _entry(
                            "2034-03-05", 999.0, "A", "2020-02-01", fy=2020, fp="FY", form="10-K"
                        ),
                        _entry(
                            "2019-12-31", 500.0, "B", "2020-02-01", fy=2020, fp="FY", form="10-K"
                        ),
                    ]
                }
            }
        },
    )
    frame = rows_to_frame(fact_rows_from_payload(11, payload, "test"))
    assert len(frame) == 1
    assert frame.loc[0, "val"] == 500.0


# --------------------------------------------------------------------------
# usable-session timing
# --------------------------------------------------------------------------


def test_attach_usable_session_is_never_the_filing_session() -> None:
    payload = _payload(
        4,
        {
            "us-gaap": {
                "Assets": {
                    "USD": [
                        _entry("2020-12-31", 1.0, "A", "2021-02-02", fy=2020, fp="FY", form="10-K"),
                        # A Friday filing must roll to the next session, not
                        # the weekend and not Friday itself.
                        _entry("2020-06-30", 1.0, "B", "2021-01-08", fy=2020, fp="Q2", form="10-Q"),
                    ]
                }
            }
        },
    )
    frame = attach_usable_session(_rows_for(4, payload))
    for _, row in frame.iterrows():
        filed_date = row["filed"].date()
        expected = next_us_equity_session(filed_date)
        assert row["usable_session"] == pd.Timestamp(expected)
        assert row["usable_session"].date() != filed_date


# --------------------------------------------------------------------------
# Q4 derivation
# --------------------------------------------------------------------------


def test_derive_q4_backs_out_the_fourth_quarter() -> None:
    payload = _payload(
        5,
        {
            "us-gaap": {
                "Revenues": {
                    "USD": [
                        _entry(
                            "2020-03-31",
                            100.0,
                            "A",
                            "2020-05-01",
                            fy=2020,
                            fp="Q1",
                            form="10-Q",
                            start="2020-01-01",
                        ),
                        _entry(
                            "2020-06-30",
                            110.0,
                            "B",
                            "2020-08-01",
                            fy=2020,
                            fp="Q2",
                            form="10-Q",
                            start="2020-04-01",
                        ),
                        _entry(
                            "2020-09-30",
                            120.0,
                            "C",
                            "2020-11-01",
                            fy=2020,
                            fp="Q3",
                            form="10-Q",
                            start="2020-07-01",
                        ),
                        _entry(
                            "2020-12-31",
                            450.0,
                            "D",
                            "2021-02-01",
                            fy=2020,
                            fp="FY",
                            form="10-K",
                            start="2020-01-01",
                        ),
                    ]
                }
            }
        },
    )
    cleaned = build_facts_batch(fact_rows_from_payload(5, payload, "test"))
    q4 = cleaned.loc[(cleaned["concept"] == "revenue") & (cleaned["fp"] == "Q4")]
    assert len(q4) == 1
    row = q4.iloc[0]
    assert row["val"] == pytest.approx(450.0 - 100.0 - 110.0 - 120.0)
    assert bool(row["derived_q4"]) is True
    assert row["filed"] == pd.Timestamp("2021-02-01")


def test_derive_q4_skips_when_a_quarter_is_missing() -> None:
    payload = _payload(
        6,
        {
            "us-gaap": {
                "Revenues": {
                    "USD": [
                        _entry(
                            "2020-03-31",
                            100.0,
                            "A",
                            "2020-05-01",
                            fy=2020,
                            fp="Q1",
                            form="10-Q",
                            start="2020-01-01",
                        ),
                        # Q2 missing.
                        _entry(
                            "2020-09-30",
                            120.0,
                            "C",
                            "2020-11-01",
                            fy=2020,
                            fp="Q3",
                            form="10-Q",
                            start="2020-07-01",
                        ),
                        _entry(
                            "2020-12-31",
                            450.0,
                            "D",
                            "2021-02-01",
                            fy=2020,
                            fp="FY",
                            form="10-K",
                            start="2020-01-01",
                        ),
                    ]
                }
            }
        },
    )
    cleaned = build_facts_batch(fact_rows_from_payload(6, payload, "test"))
    assert not ((cleaned["concept"] == "revenue") & (cleaned["fp"] == "Q4")).any()


# --------------------------------------------------------------------------
# running-latest: forward fill never regresses on a stale restatement
# --------------------------------------------------------------------------


def test_running_latest_forward_fills_and_never_goes_backward() -> None:
    p0, p1 = pd.Timestamp("2020-03-31"), pd.Timestamp("2020-06-30")
    s1, s2, s3 = pd.Timestamp("2020-05-01"), pd.Timestamp("2020-08-01"), pd.Timestamp("2020-11-01")
    events = [
        (s1, p0, 100.0),  # Q1, first known
        (s2, p1, 110.0),  # Q2, supersedes Q1
    ]
    result = _running_latest(events)
    assert result == [(s1, 100.0), (s2, 110.0)]

    # A restatement of the *older* Q1 period arrives after Q2 is already
    # known. It must not regress the running value back to a Q1 number.
    late_restatement_of_q1 = (pd.Timestamp("2020-09-01"), p0, 95.0)
    result_with_stale_restatement = _running_latest([*events, late_restatement_of_q1])
    assert result_with_stale_restatement == [(s1, 100.0), (s2, 110.0)]

    # A restatement of the *current* (most recent) period does update it.
    restatement_of_q2 = (s3, p1, 111.0)
    result_with_current_restatement = _running_latest([*events, restatement_of_q2])
    assert result_with_current_restatement == [(s1, 100.0), (s2, 110.0), (s3, 111.0)]


# --------------------------------------------------------------------------
# SUE arithmetic
# --------------------------------------------------------------------------


def test_sue_series_matches_hand_computed_foster_olsen_shevlin() -> None:
    eps = [1.00, 1.10, 1.05, 1.20, 1.05, 1.18, 1.12, 1.30, 1.10, 1.25, 1.20, 1.40, 1.15]
    base = pd.Timestamp("2016-01-01")
    quarterly = {
        qidx: (base + pd.Timedelta(days=90 * qidx + 45), base + pd.Timedelta(days=90 * qidx), val)
        for qidx, val in enumerate(eps)
    }
    result = dict(sue_series(quarterly))
    t = 12
    diffs = np.array([eps[k] - eps[k - 4] for k in range(t - 8, t)])
    expected = (eps[t] - eps[t - 4]) / diffs.std(ddof=1)
    assert quarterly[t][0] in result
    assert result[quarterly[t][0]] == pytest.approx(expected)
    # Only one quarter (t=12) has the full 12-quarter history this data provides.
    assert len(result) == 1


def test_sue_series_requires_no_gaps_in_the_lookback() -> None:
    quarterly = {
        i: (pd.Timestamp("2020-01-01") + pd.Timedelta(days=i), pd.NaT, 1.0 + 0.01 * i)
        for i in range(12)
    }
    del quarterly[5]  # a gap inside the 8-quarter lookback window for t=11
    result = sue_series(quarterly)
    assert result == []


def test_quarterly_dict_keeps_first_filed_only() -> None:
    payload = _payload(
        7,
        {
            "us-gaap": {
                "EarningsPerShareDiluted": {
                    "USD/shares": [
                        _entry(
                            "2020-03-31",
                            1.0,
                            "A",
                            "2020-05-01",
                            fy=2020,
                            fp="Q1",
                            form="10-Q",
                            start="2020-01-01",
                        ),
                    ]
                }
            }
        },
    )
    cleaned = build_facts_batch(fact_rows_from_payload(7, payload, "test"))
    quarterly = _quarterly_dict(cleaned, "eps_diluted")
    assert quarterly[2020 * 4 + 0][2] == 1.0


# --------------------------------------------------------------------------
# ratio formulas + forward fill, end to end on one synthetic issuer
# --------------------------------------------------------------------------


def _annual_row(
    cik: int,
    concept: str,
    tag: str,
    taxonomy: str,
    unit: str,
    *,
    fy: int,
    val: float,
    filed: str,
    kind: str,
    start: str | None,
) -> dict:
    return {
        "cik": cik,
        "concept": concept,
        "taxonomy": taxonomy,
        "tag": tag,
        "unit": unit,
        "period_start": pd.Timestamp(start) if start else pd.NaT,
        "period_end": pd.Timestamp(f"{fy}-12-31"),
        "fy": fy,
        "fp": "FY",
        "val": val,
        "accn": f"{cik}-{fy}-{concept}",
        "form": "10-K",
        "filed": pd.Timestamp(filed),
        "period_kind": kind,
        "restated": False,
        "usable_session": pd.Timestamp(next_us_equity_session(date.fromisoformat(filed))),
        "derived_q4": False,
    }


def _synthetic_issuer_frame(cik: int) -> pd.DataFrame:
    rows = []
    specs = [
        ("total_assets", "Assets", "us-gaap", "USD", "instant", 2020, 1000.0, "2021-02-02"),
        ("total_assets", "Assets", "us-gaap", "USD", "instant", 2021, 1200.0, "2022-02-02"),
        (
            "stockholders_equity",
            "StockholdersEquity",
            "us-gaap",
            "USD",
            "instant",
            2020,
            600.0,
            "2021-02-02",
        ),
        (
            "stockholders_equity",
            "StockholdersEquity",
            "us-gaap",
            "USD",
            "instant",
            2021,
            700.0,
            "2022-02-02",
        ),
        ("net_income", "NetIncomeLoss", "us-gaap", "USD", "FY", 2020, 150.0, "2021-02-02"),
        ("net_income", "NetIncomeLoss", "us-gaap", "USD", "FY", 2021, 180.0, "2022-02-02"),
        ("gross_profit", "GrossProfit", "us-gaap", "USD", "FY", 2020, 400.0, "2021-02-02"),
        ("gross_profit", "GrossProfit", "us-gaap", "USD", "FY", 2021, 480.0, "2022-02-02"),
        (
            "operating_cash_flow",
            "NetCashProvidedByUsedInOperatingActivities",
            "us-gaap",
            "USD",
            "FY",
            2020,
            170.0,
            "2021-02-02",
        ),
        (
            "operating_cash_flow",
            "NetCashProvidedByUsedInOperatingActivities",
            "us-gaap",
            "USD",
            "FY",
            2021,
            190.0,
            "2022-02-02",
        ),
    ]
    for concept, tag, taxonomy, unit, kind, fy, val, filed in specs:
        start = f"{fy}-01-01" if kind == "FY" else None
        rows.append(
            _annual_row(
                cik,
                concept,
                tag,
                taxonomy,
                unit,
                fy=fy,
                val=val,
                filed=filed,
                kind=kind,
                start=start,
            )
        )
    return pd.DataFrame(rows)


def test_compute_cik_table_ratio_formulas_and_forward_fill() -> None:
    frame = _synthetic_issuer_frame(42)
    table = compute_cik_table(42, frame)
    table = table.set_index("usable_session").sort_index()

    s1 = pd.Timestamp(next_us_equity_session(date(2021, 2, 2)))
    s2 = pd.Timestamp(next_us_equity_session(date(2022, 2, 2)))
    assert list(table.index) == [s1, s2]

    # Forward fill: total_assets is known and holds at 1000 at s1, still
    # visible (not reset to NaN) at s2 alongside the update... it should
    # actually be *replaced* by the new value at s2 since s2 is itself an
    # update session; the point is no NaN gap appears anywhere.
    assert not table["total_assets"].isna().any()
    assert table.loc[s1, "total_assets"] == 1000.0
    assert table.loc[s2, "total_assets"] == 1200.0

    # gross_profitability = trailing annual gross profit / total assets.
    assert table.loc[s1, "gross_profitability"] == pytest.approx(400.0 / 1000.0)
    assert table.loc[s2, "gross_profitability"] == pytest.approx(480.0 / 1200.0)

    # roe = trailing annual net income / stockholders' equity.
    assert table.loc[s1, "roe"] == pytest.approx(150.0 / 600.0)
    assert table.loc[s2, "roe"] == pytest.approx(180.0 / 700.0)

    # asset_growth: no fy-1 (2019) at s1 -> NaN; (1200-1000)/1000 at s2.
    assert pd.isna(table.loc[s1, "asset_growth"])
    assert table.loc[s2, "asset_growth"] == pytest.approx(0.2)

    # accruals: no data ~1y before s1 -> NaN; a real lagged point at s2.
    assert pd.isna(table.loc[s1, "accruals"])
    expected_avg = _lagged_average(
        np.array([s1.to_datetime64(), s2.to_datetime64()]), np.array([1000.0, 1200.0])
    )[1]
    assert table.loc[s2, "accruals"] == pytest.approx((180.0 - 190.0) / expected_avg)


def test_lagged_average_uses_nearest_prior_point_within_tolerance() -> None:
    dates = np.array(
        [np.datetime64("2020-01-01"), np.datetime64("2021-01-01"), np.datetime64("2025-01-01")]
    )
    values = np.array([100.0, 150.0, 999.0])
    result = _lagged_average(dates, values)
    # index 1 (2021-01-01): ~365 days before is 2020-01-01 (exact match).
    assert result[1] == pytest.approx((150.0 + 100.0) / 2.0)
    # index 2 (2025-01-01): nearest prior point is 4 years away, no match
    # within the 60-day tolerance -> NaN, not a degenerate one-point average.
    assert np.isnan(result[2])


# --------------------------------------------------------------------------
# ticker mapping
# --------------------------------------------------------------------------


def test_build_cik_symbol_map_restricts_to_the_universe(tmp_path, monkeypatch) -> None:
    import scripts.build_sec_xbrl_fundamentals as builder

    tickers_path = tmp_path / "company_tickers.json"
    tickers_path.write_text(
        json.dumps(
            {
                "0": {"cik_str": 1, "ticker": "AAA", "title": "Company AAA"},
                "1": {"cik_str": 2, "ticker": "BBB", "title": "Company BBB"},
                "2": {"cik_str": 3, "ticker": "CCC", "title": "Company CCC"},
            }
        )
    )
    universe_dir = tmp_path / "universe_broad"
    universe_dir.mkdir()
    pd.DataFrame(
        {
            "month_end": [pd.Timestamp("2020-01-31")] * 2,
            "symbol": ["AAA", "CCC"],
            "adv_rank": [1, 2],
            "dollar_adv": [1.0, 2.0],
            "close": [10.0, 20.0],
        }
    ).to_parquet(universe_dir / "2020.parquet")

    monkeypatch.setattr(builder, "TICKERS_PATH", tickers_path)
    monkeypatch.setattr(builder, "UNIVERSE_BROAD_ROOT", universe_dir)

    mapped = builder.build_cik_symbol_map(None)
    # BBB is in company_tickers.json but not the universe -> excluded.
    # DDD (hypothetically in the universe) would be excluded too: a symbol
    # with no CIK match is simply absent, never guessed.
    assert sorted(mapped["symbol"]) == ["AAA", "CCC"]
    assert set(mapped["cik"]) == {1, 3}
