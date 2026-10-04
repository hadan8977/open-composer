"""Fake-HTTP tests for scripts/build_pm_earnings_events.py (T-20261004-51)."""

from __future__ import annotations

import importlib.util
import json
import sys
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "build_pm_earnings_events.py"
spec = importlib.util.spec_from_file_location("build_pm_earnings_events", SCRIPT)
assert spec and spec.loader
pm = importlib.util.module_from_spec(spec)
sys.modules["build_pm_earnings_events"] = pm
spec.loader.exec_module(pm)

ET = "America/New_York"


def et_ts(text: str) -> pd.Timestamp:
    return pd.Timestamp(text).tz_localize(ET)


def gamma_event(slug: str, title: str, *, volume="9000", prices='["1", "0"]', n_markets=1):
    market = {
        "outcomes": '["Yes", "No"]',
        "outcomePrices": prices,
        "clobTokenIds": '["tokYES", "tokNO"]',
        "endDate": "2026-10-05T13:00:00Z",
        "startDate": "2026-09-28T12:00:00Z",
    }
    return {
        "id": "7",
        "slug": slug,
        "title": title,
        "volume": volume,
        "creationDate": "2026-09-28T11:00:00Z",
        "closedTime": "2026-10-05T20:00:00Z",
        "markets": [market] * n_markets,
    }


def test_parse_eps_handles_negative_and_integers() -> None:
    assert pm.parse_eps("0pt76") == 0.76
    assert pm.parse_eps("neg5pt28") == -5.28
    assert pm.parse_eps("2") == 2.0
    assert pm.parse_eps("xx") is None


def test_identity_ticker_from_title_checked_against_slug() -> None:
    ok = pm.parse_event_identity(
        "Will McCormick (MKC) beat quarterly earnings?",
        "mkc-quarterly-earnings-nongaap-eps-10-05-2026-0pt76",
    )
    assert ok["ticker"] == "MKC"
    assert ok["ticker_slug_check"] == "ok"
    assert ok["slug_date"] == date(2026, 10, 5)
    assert ok["eps_basis"] == "nongaap"
    assert ok["consensus_eps"] == 0.76

    bad = pm.parse_event_identity(
        "Will McCormick (MKC) beat quarterly earnings?",
        "xyz-quarterly-earnings-gaap-eps-10-05-2026-neg1pt5",
    )
    assert bad["ticker"] is None
    assert bad["ticker_slug_check"] == "mismatch"

    old = pm.parse_event_identity(
        "Will Dollar General (DG) beat quarterly earnings?",
        "dg-quarterly-earnings-gaap-eps-08-27-2026-2",
    )
    assert old["ticker"] == "DG"
    assert old["consensus_eps"] == 2.0

    legacy = pm.parse_event_identity(
        "Will Broadcom beat Q2 earnings forecast ($1.57 EPS)?",
        "will-broadcom-beat-q2-earnings-estimate",
    )
    assert legacy["ticker"] is None


def test_event_row_reads_yes_token_and_outcome() -> None:
    row = pm.event_row(
        gamma_event(
            "mkc-quarterly-earnings-nongaap-eps-10-05-2026-0pt76",
            "Will McCormick (MKC) beat quarterly earnings?",
        )
    )
    assert row["yes_token_id"] == "tokYES"
    assert row["beat"] == 1
    assert row["volume_usd"] == 9000.0
    miss = pm.event_row(
        gamma_event(
            "a-quarterly-earnings-gaap-eps-10-05-2026-1", "Will A (A) beat?", prices='["0", "1"]'
        )
    )
    assert miss["beat"] == 0
    assert pm.event_row(gamma_event("s", "t", n_markets=2)) is None
    unresolved = pm.event_row(gamma_event("s", "t", prices='["0.55", "0.45"]'))
    assert unresolved["beat"] is None


@pytest.mark.parametrize(
    ("stamp", "s", "r", "kind"),
    [
        ("2026-10-07 07:30", date(2026, 10, 6), date(2026, 10, 7), "pre_market"),
        ("2026-10-07 09:29", date(2026, 10, 6), date(2026, 10, 7), "pre_market"),
        ("2026-10-07 09:30", date(2026, 10, 6), date(2026, 10, 7), "intraday"),
        ("2026-10-07 15:59", date(2026, 10, 6), date(2026, 10, 7), "intraday"),
        ("2026-10-07 16:00", date(2026, 10, 7), date(2026, 10, 8), "after_close"),
        ("2026-10-09 17:00", date(2026, 10, 9), date(2026, 10, 12), "after_close"),  # Friday
        ("2026-10-10 11:00", date(2026, 10, 9), date(2026, 10, 12), "non_session_day"),  # Sat
        ("2026-10-12 08:00", date(2026, 10, 9), date(2026, 10, 12), "pre_market"),
    ],
)
def test_signal_and_reaction_days(stamp: str, s: date, r: date, kind: str) -> None:
    assert pm.reaction_and_signal_day(et_ts(stamp)) == (s, r, kind)


def test_acceptance_is_read_as_eastern_wall_clock() -> None:
    out = pm.eastern_wall_clock(pd.Series(["2026-10-07T20:05:00Z"]))
    assert out.iloc[0] == et_ts("2026-10-07 20:05")
    summer = pm.eastern_wall_clock(pd.Series(["2026-07-01T07:00:00Z"]))
    assert summer.iloc[0].utcoffset() == pd.Timedelta(hours=-4)


def test_match_picks_nearest_item_202_within_two_days() -> None:
    events = pd.DataFrame(
        {
            "ticker": ["AAA", "AAA", "BBB", None],
            "slug_date": [
                date(2026, 10, 7),
                date(2026, 12, 1),
                date(2026, 10, 7),
                date(2026, 10, 7),
            ],
        }
    )
    earnings = pd.DataFrame(
        {
            "ticker": ["AAA", "AAA", "AAA", "BBB"],
            "accession": ["far", "near", "other_item", "bbb"],
            "acceptance_utc": [
                "2026-10-10T12:00:00Z",
                "2026-10-06T20:05:00Z",
                "2026-10-07T12:00:00Z",
                "2026-10-04T12:00:00Z",
            ],
            "items": ["2.02,9.01", "2.02,9.01", "5.02", "2.02"],
        }
    )
    out = pm.match_announcements(events, earnings)
    assert out.loc[0, "accession"] == "near"
    assert out.loc[0, "timing_source"] == "8k_2.02"
    assert pd.isna(out.loc[1, "accession"])  # slug date beyond 2 days of any 8-K
    assert pd.isna(out.loc[2, "accession"])  # 3 days away
    assert out.loc[3, "timing_source"] == "none"  # no ticker


class FakeHttp:
    def __init__(self, pages: list[list[dict]], history: dict[tuple[str, int], list[dict]]) -> None:
        self.pages = pages
        self.history = history
        self.calls: list[tuple[str, dict]] = []

    def get(self, url: str, params: dict | None = None, *, allow_404: bool = False):
        params = params or {}
        self.calls.append((url, params))
        if url.endswith("/events"):
            idx = params["offset"] // pm.PAGE
            return self.pages[idx] if idx < len(self.pages) else []
        return {"history": self.history.get((params["market"], params["fidelity"]), [])}


def test_fetch_events_paginates_until_short_page(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pm, "PAGE", 2)
    http = FakeHttp([[{"id": 1}, {"id": 2}], [{"id": 3}]], {})
    assert [e["id"] for e in pm.fetch_events(http)] == [1, 2, 3]
    assert len(http.calls) == 2


def test_cut_ts_is_1500_eastern_across_dst() -> None:
    summer = pd.Timestamp(pm.cut_ts(date(2026, 7, 1)), unit="s", tz="UTC")
    winter = pd.Timestamp(pm.cut_ts(date(2026, 12, 1)), unit="s", tz="UTC")
    assert summer.hour == 19
    assert winter.hour == 20
    week = pd.Timestamp(pm.cut_ts(date(2026, 7, 1), 7), unit="s", tz="UTC")
    assert week == summer - pd.Timedelta(days=7)


def test_price_history_falls_back_to_finer_fidelity_only_when_empty() -> None:
    http = FakeHttp([], {("tok", 10): [{"t": 5, "p": 0.4}], ("tok", 1): [{"t": 6, "p": 0.5}]})
    points, fid = pm.price_history(http, "tok", 0, 10)
    assert (points, fid) == ([(5, 0.4)], 10)
    http = FakeHttp([], {("tok", 60): [{"t": 9, "p": 0.7}]})
    assert pm.price_history(http, "tok", 0, 10) == ([(9, 0.7)], 60)
    assert pm.price_history(FakeHttp([], {}), "tok", 0, 10) == ([], None)


def test_last_at_or_before_never_looks_ahead() -> None:
    pts = [(10, 0.2), (20, 0.5), (30, 0.9)]
    assert pm.last_at_or_before(pts, 25) == (0.5, 20)
    assert pm.last_at_or_before(pts, 20) == (0.5, 20)
    assert pm.last_at_or_before(pts, 5) == (None, None)


def test_attach_prices_stale_flags_and_p7() -> None:
    s = pd.Timestamp("2026-10-07")
    cut = pm.cut_ts(s.date())
    cut7 = pm.cut_ts(s.date(), 7)
    history = {
        ("fresh", 60): [
            {"t": cut7 - 3600, "p": 0.40},
            {"t": cut - 7200, "p": 0.62},
            {"t": cut + 3600, "p": 0.99},  # after the cut: must not be used
        ],
        ("stale", 60): [{"t": cut - 30 * 3600, "p": 0.55}],
    }
    events = pd.DataFrame(
        {
            "yes_token_id": ["fresh", "stale", "none"],
            "S": [s, s, pd.NaT],
        }
    )
    out = pm.attach_prices(events, FakeHttp([], history), log=lambda *_: None)
    assert out.loc[0, "P"] == 0.62
    assert not out.loc[0, "P_stale"]
    assert out.loc[0, "P7"] == 0.40
    assert out.loc[1, "P_stale"]
    assert out.loc[1, "P_age_h"] == pytest.approx(30.0)
    assert out.loc[2, "price_error"] == "no_timing"
    assert pd.isna(out.loc[2, "P"])


def test_coverage_funnel_counts_each_step() -> None:
    r = pd.Timestamp("2026-10-07")
    df = pd.DataFrame(
        {
            "ticker": ["A", "B", "C", "D", "E", None],
            "beat": [1, 0, 1, 1, 0, 1],
            "sip_bars_ok": [True, True, True, True, False, True],
            "R": [r, r, r, pd.NaT, r, r],
            "P": [0.5, 0.6, None, 0.5, 0.5, 0.5],
            "P_stale": [False, True, True, False, False, False],
            "volume_usd": [9000, 9000, 9000, 9000, 9000, 9000],
        }
    )
    cov = pm.coverage_funnel(df)
    assert cov["funnel"] == {
        "all_events": 6,
        "ticker_parsed_and_resolved": 5,
        "sip_bars": 4,
        "timing_matched_8k": 3,
        "p_valid": 2,
        "not_stale": 1,
        "volume_ge_5k": 1,
    }
    assert cov["primary_events"] == 1
    assert cov["weeks_with_ge_6_events"] == 0


def test_merge_feasibility_keeps_existing_keys(tmp_path: Path) -> None:
    path = tmp_path / "f.json"
    path.write_text(json.dumps({"keep": 1}))
    pm.merge_feasibility(path, {"funnel": {"all_events": 3}}, {"x": 2})
    doc = json.loads(path.read_text())
    assert doc["keep"] == 1
    assert doc["data_build"]["funnel"] == {"all_events": 3}
    assert "polymarket_data_terms" in doc["data_build"]
