"""H-20260916-07 step 0: the FINRA short-interest schedule parser and its
point-in-time visibility rule.

Three things are pinned here, because all three are places where a
short-interest pipeline silently becomes a look-ahead pipeline:

* :func:`collect_finra_short_interest.parse_official_schedule` -- FINRA's own
  settlement / due / **publication** table, whose month-day cells carry no
  year. The December-settlement / January-publication row is the one where a
  naive parser puts visibility a full year early, so it is tested explicitly.
* :func:`collect_finra_short_interest.publication_date_from_rule` -- the
  7-US-session lag the official table implies, checked against hand-computed
  dates including a market-only holiday (Good Friday) and a federal one.
* The capability fixture ``data/fixtures/capabilities/finra_short_interest.jsonl``
  is checked row by row: its ``visible_at`` must be the session after its
  ``published_at``, and its ``published_at`` must be 7 sessions after its
  settlement date, so a fixture that quietly claims earlier visibility fails
  the suite.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from open_composer.market_calendar import next_us_equity_session
from scripts.collect_finra_short_interest import (
    FIELD_RENAME,
    PARSED_COLUMNS,
    PUBLICATION_LAG_SESSIONS,
    parse_official_schedule,
    publication_date_from_rule,
    validate_rule_against_official,
)

ROOT = Path(__file__).resolve().parents[1]
CAPABILITY_FIXTURE = ROOT / "data" / "fixtures" / "capabilities" / "finra_short_interest.jsonl"

SCHEDULE_HTML = """
<div>
<h3>2025 Short Interest Reporting Dates</h3>
<table><tbody>
<tr><th>Settlement Date</th><th>Due Date 1</th><th>Publication Date</th></tr>
<tr><td>December 15 (Monday)</td><td>December 17 &ndash; 6:00 p.m. (Wednesday)</td>
<td>December 24 (Wednesday)</td></tr>
<tr><td>December 31 (Wednesday)</td><td>January 5 &ndash; 6:00 p.m. (Monday)</td>
<td>January 12 (Monday)</td></tr>
</tbody></table>
<h3>2026 Short Interest Reporting Dates</h3>
<table><tbody>
<tr><th>Settlement Date</th><th>Due Date1</th><th>Publication Date</th></tr>
<tr><td>March 31(Tuesday)</td><td>April 2 &ndash; 6:00 p.m.(Thursday)</td>
<td>April 10(Friday)</td></tr>
<tr><td>June 15(Monday)</td><td>June 17 &ndash; 6:00 p.m.(Wednesday)</td>
<td>June 25(Thursday)</td></tr>
</tbody></table>
</div>
"""


def test_schedule_parses_year_from_the_heading() -> None:
    frame = parse_official_schedule(SCHEDULE_HTML)
    assert list(frame["settlement_date"]) == [
        date(2025, 12, 15),
        date(2025, 12, 31),
        date(2026, 3, 31),
        date(2026, 6, 15),
    ]


def test_december_settlement_publishes_in_the_following_january() -> None:
    frame = parse_official_schedule(SCHEDULE_HTML)
    row = frame.loc[frame["settlement_date"] == date(2025, 12, 31)].iloc[0]
    assert row["publication_date"] == date(2026, 1, 12)
    assert row["due_date"] == date(2026, 1, 5)


def test_seven_session_rule_reproduces_the_official_rows() -> None:
    frame = parse_official_schedule(SCHEDULE_HTML)
    validation = validate_rule_against_official(frame)
    assert validation["agrees"], validation["mismatches"]
    assert validation["lag_sessions"] == PUBLICATION_LAG_SESSIONS


def test_rule_skips_good_friday_a_market_only_holiday() -> None:
    """2026-03-31 + 7 sessions = 2026-04-10 only if Good Friday (2026-04-03) is
    not a session. A banking calendar would land a day early."""
    assert publication_date_from_rule(date(2026, 3, 31)) == date(2026, 4, 10)


def test_rule_skips_juneteenth() -> None:
    assert publication_date_from_rule(date(2026, 6, 15)) == date(2026, 6, 25)


def test_rule_lag_is_configurable_and_monotone() -> None:
    settlement = date(2026, 6, 15)
    shorter = publication_date_from_rule(settlement, lag_sessions=1)
    longer = publication_date_from_rule(settlement, lag_sessions=10)
    assert settlement < shorter < longer


def test_field_rename_covers_the_parsed_schema() -> None:
    """Every normalized column either comes from a FINRA field or is derived
    here; a new PARSED_COLUMNS entry with neither is a silently empty column."""
    derived = {
        "publication_date",
        "visible_date",
        "publication_date_source",
        "source",
        "fetched_at",
        "input_hash",
    }
    assert set(PARSED_COLUMNS) == set(FIELD_RENAME.values()) | derived


@pytest.mark.parametrize("line", CAPABILITY_FIXTURE.read_text(encoding="utf-8").splitlines())
def test_capability_fixture_visibility_is_the_session_after_publication(line: str) -> None:
    if not line.strip():
        pytest.skip("blank line")
    record = json.loads(line)
    published = pd.Timestamp(record["published_at"]).tz_convert("America/New_York").date()
    visible = pd.Timestamp(record["visible_at"]).tz_convert("America/New_York").date()
    assert visible == next_us_equity_session(published), record["id"]


@pytest.mark.parametrize("line", CAPABILITY_FIXTURE.read_text(encoding="utf-8").splitlines())
def test_capability_fixture_publication_matches_the_seven_session_rule(line: str) -> None:
    if not line.strip():
        pytest.skip("blank line")
    record = json.loads(line)
    settlement = date.fromisoformat(record["raw"]["settlement_date"])
    published = pd.Timestamp(record["published_at"]).tz_convert("America/New_York").date()
    assert published == publication_date_from_rule(settlement), record["id"]
