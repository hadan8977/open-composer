"""Tests for scripts/refresh_polymarket_watchlist.py (T-20261002-45) with a fake HTTP layer."""

from __future__ import annotations

import importlib.util
import sys
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
import yaml

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


refresh = _load("refresh_polymarket_watchlist")
collect = sys.modules["collect_prediction_markets"]
NOW = datetime(2026, 10, 2, 14, 0, tzinfo=UTC)


def market(mid, question, item="", *, active=True, closed=False):
    return {
        "id": str(mid),
        "question": question,
        "groupItemTitle": item,
        "active": active,
        "closed": closed,
    }


def event(slug, end, markets, *, closed=False):
    return {
        "id": slug,
        "slug": slug,
        "endDate": end,
        "active": True,
        "closed": closed,
        "markets": markets,
    }


EVENTS = {
    "Fed decision in": [
        event(
            "fed-decision-in-october-20260617",
            "2026-10-29T03:59:00Z",
            [
                market(1, "Fed decrease 25?", "25 bps decrease"),
                market(2, "Fed no change?", "No change"),
            ],
        ),
        event(
            "fed-decision-in-december-20260729",
            "2026-12-10T04:59:00Z",
            [market(3, "Fed dec no change?", "No change")],
        ),
        event(
            "fed-decision-in-january-20260729",
            "2027-01-28T04:59:00Z",
            [market(4, "Fed jan no change?", "No change")],
        ),
        event(  # resolved earlier: must be ignored
            "fed-decision-in-september-20260101",
            "2026-09-17T04:59:00Z",
            [market(5, "Fed sep?", "No change")],
        ),
    ],
    "US recession by end of 2026": [
        event(
            "us-recession-by-end-of-2026",
            "2026-12-31T00:00:00Z",
            [market(6, "US recession by end of 2026?")],
        )
    ],
    "US recession by end of 2027": [
        event(
            "us-recession-by-end-of-2027-2026080",
            "2027-12-31T23:59:00Z",
            [market(7, "US recession by end of 2027?")],
        )
    ],
    "inflation us monthly": [
        event(
            "september-inflation-us-monthly",
            "2026-10-15T03:59:00Z",
            [market(8, "CPI flat?", "≤0.0%"), market(9, "CPI 0.3?", "0.3%")],
        ),
        event(
            "october-inflation-us-monthly",
            "2026-11-12T03:59:00Z",
            [market(10, "CPI oct 0.3?", "0.3%")],
        ),
        event(
            "argentina-monthly-inflation-september-2026",
            "2026-10-13T00:00:00Z",
            [market(11, "arg")],
        ),
    ],
    "tariff rate on China": [
        event(
            "us-tariff-rate-on-china-on-december-31-2026",
            "2026-12-31T00:00:00Z",
            [market(12, "tariff <5?", "<5%"), market(13, "tariff 5-15?", "5–15%")],
        )
    ],
    "government shutdown": [
        event(
            "another-us-government-shutdown-house-winner-2026",
            "2027-02-01T04:59:00Z",
            [
                market(14, "Shutdown and Dem House?", "x"),
                market(15, "No shutdown and Dem?", "y", closed=True),
                market(16, "Other?", "z", active=False),
            ],
        )
    ],
    "which party will win the house in 2026": [
        event(
            "which-party-will-win-the-house-in-2026",
            "2026-11-04T04:59:00Z",
            [market(17, "Dem House?")],
        ),
        event(
            "which-party-will-win-the-arizona-state-house-in-2026",
            "2026-11-04T04:59:00Z",
            [market(99, "AZ")],
        ),
    ],
    "which party will win the senate in 2026": [
        event(
            "which-party-will-win-the-senate-in-2026",
            "2026-11-04T04:59:00Z",
            [market(18, "Dem Senate?"), market(19, "Party A?", active=False)],
        )
    ],
}
LOOKUP = {
    "100": market(100, "Old closed", closed=True),
    "101": market(101, "Still active, no longer discovered"),
    "103": market(103, "Inactive", active=False),
    "1": market(1, "October meeting resolved", closed=True),
}


def fake_get(url, params, timeout):
    if url.endswith("/public-search"):
        return 200, {"events": EVENTS.get(params["q"], []), "pagination": {"hasMore": False}}
    if url.endswith("/markets"):
        ids = params["id"]
        return 200, [LOOKUP[i] for i in ids if i in LOOKUP]
    raise AssertionError(url)


def make_http(get=fake_get):
    return collect.Http(get, sleep=lambda s: None, clock=lambda: 0.0)


EXISTING = [
    {"id": "2", "group": "fed_october_2026", "note": "my own note for 2"},
    {"id": "6", "group": "recession", "note": "US recession by end of 2026"},
    {"id": "100", "group": "fed_october_2026", "note": "resolved one"},
    {"id": "101", "group": "misc", "note": "manual keeper"},
    {"id": "103", "group": "misc", "note": "inactive one"},
    {"id": "104", "group": "misc", "note": "gone"},
]


def test_refresh_keeps_adds_and_drops():
    result = refresh.refresh(make_http(), EXISTING, NOW)
    by_id = {m["id"]: m for m in result["markets"]}
    assert {"2", "6", "101"} <= set(by_id)
    assert by_id["2"]["note"] == "my own note for 2"  # existing notes are stable
    assert {e["id"] for e in result["added"]} == {
        "1",
        "3",
        "7",
        "8",
        "9",
        "12",
        "13",
        "14",
        "17",
        "18",
    }
    dropped = {e["id"]: e["reason"] for e in result["dropped"]}
    assert dropped == {"100": "closed", "103": "inactive", "104": "not returned by Gamma"}
    assert result["empty_finders"] == []


def test_next_two_fed_meetings_and_groups():
    result = refresh.refresh(make_http(), [], NOW)
    groups = {m["id"]: m["group"] for m in result["markets"]}
    assert groups["1"] == groups["2"] == "fed_october_2026"
    assert groups["3"] == "fed_december_2026"
    assert "4" not in groups and "5" not in groups  # third meeting and a resolved one
    assert groups["8"] == "cpi_us_monthly_sep_2026" and "10" not in groups  # the next CPI only
    assert groups["6"] == groups["7"] == "recession"
    assert groups["12"] == "tariff_china_rate_end_2026"
    assert groups["17"] == groups["18"] == "midterms_2026"
    assert "99" not in groups and "15" not in groups and "16" not in groups and "19" not in groups
    notes = {m["id"]: m["note"] for m in result["markets"]}
    assert notes["1"] == "Fed 25 bps decrease after the October 2026 meeting"
    assert notes["2"] == "Fed no change after the October 2026 meeting"
    assert notes["8"] == "September US CPI MoM ≤0.0%"


def test_after_the_october_meeting_the_next_two_roll_forward():
    later = datetime(2026, 10, 30, 14, 0, tzinfo=UTC)
    result = refresh.refresh(
        make_http(), [{"id": "1", "group": "fed_october_2026", "note": "n"}], later
    )
    groups = {m["id"]: m["group"] for m in result["markets"]}
    assert groups["3"] == "fed_december_2026" and groups["4"] == "fed_january_2027"
    assert "1" in {e["id"] for e in result["dropped"]}  # the expired event no longer lists it


def test_a_group_that_vanishes_is_reported_and_existing_ids_are_checked_not_wiped():
    def get(url, params, timeout):
        if url.endswith("/public-search") and params["q"] == "government shutdown":
            return 200, {"events": []}
        return fake_get(url, params, timeout)

    existing = [{"id": "14", "group": "government_shutdown", "note": "n"}]
    LOOKUP["14"] = market(14, "still open")
    try:
        result = refresh.refresh(make_http(get), existing, NOW)
    finally:
        del LOOKUP["14"]
    assert "shutdown" in result["empty_finders"]
    assert "14" in {m["id"] for m in result["markets"]}  # kept because it is still active


def test_refuses_to_wipe_when_gamma_returns_no_existing_ids():
    def get(url, params, timeout):
        if url.endswith("/markets"):
            return 200, []
        return fake_get(url, params, timeout)

    with pytest.raises(RuntimeError, match="refusing to wipe"):
        refresh.refresh(make_http(get), [{"id": "104", "group": "g", "note": "n"}], NOW)


def test_midterm_year():
    assert refresh.midterm_year(date(2026, 10, 2)) == 2026
    assert refresh.midterm_year(date(2026, 11, 20)) == 2028
    assert refresh.midterm_year(date(2027, 3, 1)) == 2028


def test_rendered_yaml_round_trips_through_the_collector_loader(tmp_path):
    result = refresh.refresh(make_http(), EXISTING, NOW)
    path = tmp_path / "wl.yaml"
    path.write_text(refresh.render(result["markets"], "2026-10-02T14:00:00Z"), encoding="utf-8")
    payload = yaml.safe_load(path.read_text())
    assert payload["looked_up_at"] == "2026-10-02T14:00:00Z" and payload["version"] == 1
    loaded = collect.load_watchlist(path)
    assert [m["id"] for m in loaded] == [m["id"] for m in result["markets"]]
    assert loaded[0]["note"]


def test_main_dry_run_writes_nothing_and_real_run_writes(tmp_path, monkeypatch, capsys):
    path = tmp_path / "wl.yaml"
    path.write_text(refresh.render(EXISTING, "2026-10-01T00:00:00Z"), encoding="utf-8")
    before = path.read_text()
    http = make_http()
    monkeypatch.setattr(collect, "Http", lambda: http)
    assert (
        refresh.main(["--watchlist", str(path), "--dry-run", "--now", "2026-10-02T14:00:00Z"]) == 0
    )
    out = capsys.readouterr().out
    assert "dry run: nothing written" in out and "+ 1 [fed_october_2026]" in out
    assert "- 100 [fed_october_2026]" in out and path.read_text() == before
    assert refresh.main(["--watchlist", str(path), "--now", "2026-10-02T14:00:00Z"]) == 0
    assert path.read_text() != before
    assert yaml.safe_load(path.read_text())["looked_up_at"] == "2026-10-02T14:00:00Z"


def test_missing_live_file_is_seeded_from_the_tracked_config(tmp_path, monkeypatch):
    seed = tmp_path / "config.yaml"
    seed.write_text(refresh.render(EXISTING, "2026-10-01T00:00:00Z"), encoding="utf-8")
    before = seed.read_text()
    live = tmp_path / "live" / "watchlist.live.yaml"
    http = make_http()
    monkeypatch.setattr(collect, "Http", lambda: http)
    monkeypatch.setattr(refresh, "WATCHLIST", seed)
    assert refresh.main(["--watchlist", str(live), "--now", "2026-10-02T14:00:00Z"]) == 0
    assert seed.read_text() == before  # the tracked file is never edited
    assert yaml.safe_load(live.read_text())["looked_up_at"] == "2026-10-02T14:00:00Z"


def test_collector_prefers_the_live_watchlist(tmp_path, monkeypatch):
    live = tmp_path / "watchlist.live.yaml"
    monkeypatch.setattr(collect, "LIVE_WATCHLIST", live)
    assert collect.active_watchlist_path() == collect.WATCHLIST
    live.write_text(refresh.render(EXISTING, "2026-10-02T14:00:00Z"), encoding="utf-8")
    assert collect.active_watchlist_path() == live
