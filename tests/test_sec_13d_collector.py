"""H-20260916-05 step 0: the Schedule 13D/13G parser and its visibility rule.

Three things are pinned here, because each is a place where a 13D event
table silently becomes a look-ahead table:

* :func:`collect_sec_13d_filings.parse_header_fields` -- the issuer must come
  from the header's ``SUBJECT COMPANY:`` block. EDGAR usually serializes the
  *filer* (the activist) first, so a parser that takes the first ``CIK:`` it
  sees attributes every event to the wrong company.
* :func:`build_sec_13d_features.visible_session` -- a filing accepted after
  the closing bell is not tradable until the next session, and the card's
  entry is the session *after* that.
* The capability fixture ``data/fixtures/capabilities/sec_13d_13g.jsonl`` is
  re-derived row by row from its own acceptance timestamps, so a fixture that
  quietly claims earlier visibility fails the suite.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from open_composer.market_calendar import next_us_equity_session
from scripts.build_sec_13d_features import entry_session, visible_session
from scripts.collect_sec_13d_filings import (
    parse_form_index,
    parse_item4_length,
    parse_percent_of_class,
    parse_submission,
    strip_markup,
)

ROOT = Path(__file__).resolve().parents[1]
CAPABILITY_FIXTURE = ROOT / "data" / "fixtures" / "capabilities" / "sec_13d_13g.jsonl"


def _idx_line(form: str, company: str, cik: str, date_filed: str, path: str) -> str:
    """One space-padded ``form.idx`` row.

    Built rather than pasted so the fixture stays inside the line-length
    limit while keeping what the parser actually depends on: at least two
    spaces between every field, and a company name that may itself contain
    single *and* double spaces.
    """
    return f"{form.ljust(17)}{company.ljust(62)}{cik.ljust(12)}{date_filed}  {path}"


FORM_IDX = "\n".join(
    [
        "Description:           Master Index of EDGAR Dissemination Feed by Form Type",
        "Last Data Received:    March 31, 2024",
        "",
        "Form Type   Company Name       CIK         Date Filed  File Name",
        "-" * 100,
        _idx_line("10-K", "SOME OTHER CO", "111111", "2024-01-02", "edgar/data/111111/a.txt"),
        _idx_line(
            "SC 13D",
            "EXAMPLE TARGET CORP",
            "320193",
            "2024-01-03",
            "edgar/data/320193/0001111111-24-000002.txt",
        ),
        _idx_line(
            "SC 13D",
            "ACTIVIST PARTNERS LP",
            "555555",
            "2024-01-03",
            "edgar/data/555555/0001111111-24-000002.txt",
        ),
        _idx_line(
            "SC 13D/A",
            "EXAMPLE TARGET CORP  /DE/",
            "320193",
            "2024-02-14",
            "edgar/data/320193/0001111111-24-000003.txt",
        ),
        _idx_line(
            "SC 13G",
            "BIG INDEX FUND TARGET INC",
            "789019",
            "2024-02-14",
            "edgar/data/789019/0002222222-24-000004.txt",
        ),
        _idx_line(
            "SC 13E3",
            "GOING PRIVATE CO",
            "999999",
            "2024-03-01",
            "edgar/data/999999/0003333333-24-000005.txt",
        ),
        # the 2024-12-18 rename: a 17-character form type and a company name
        # whose first token is a number
        _idx_line(
            "SCHEDULE 13D/A",
            "RENAMED AFTER 2024 DEC CORP",
            "777777",
            "2025-04-11",
            "edgar/data/777777/0004444444-25-000006.txt",
        ),
        _idx_line(
            "SCHEDULE 13G",
            "1 800 FLOWERS COM INC",
            "1084869",
            "2025-04-09",
            "edgar/data/1084869/0005555555-25-000007.txt",
        ),
    ]
).encode("latin-1")

SUBMISSION = b"""<SEC-DOCUMENT>0001111111-24-000002.txt : 20240103
<SEC-HEADER>0001111111-24-000002.hdr.sgml : 20240103
<ACCEPTANCE-DATETIME>20240103163012
ACCESSION NUMBER:\t\t0001111111-24-000002
CONFORMED SUBMISSION TYPE:\tSC 13D
PUBLIC DOCUMENT COUNT:\t\t2
FILED AS OF DATE:\t\t20240103
DATE AS OF CHANGE:\t\t20240103

SUBJECT COMPANY:\t

\tCOMPANY DATA:\t
\t\tCOMPANY CONFORMED NAME:\t\t\tEXAMPLE TARGET CORP
\t\tCENTRAL INDEX KEY:\t\t\t0000320193
\t\tCIK:\t\t\t0000320193
\t\tSTANDARD INDUSTRIAL CLASSIFICATION:\tSERVICES [7372]

FILED BY:\t

\tCOMPANY DATA:\t
\t\tCOMPANY CONFORMED NAME:\t\t\tACTIVIST PARTNERS LP
\t\tCIK:\t\t\t0000555555
</SEC-HEADER>
<DOCUMENT>
<TYPE>SC 13D
<SEQUENCE>1
<TEXT>
<html><body>
<table><tr><td>13</td><td>PERCENT OF CLASS REPRESENTED BY AMOUNT
IN ROW (11)</td><td>7.4%</td></tr></table>
<p>Item 4. Purpose of Transaction</p>
<p>The Reporting Persons intend to engage with the board regarding a sale of
the Company and intend to nominate directors at the next annual meeting.</p>
<p>Item 5. Interest in Securities of the Issuer</p>
<p>Not applicable.</p>
</body></html>
</TEXT>
</DOCUMENT>
"""


def test_parse_form_index_keeps_only_schedule_13_rows() -> None:
    frame = parse_form_index(FORM_IDX)
    assert sorted(frame["form_type"].unique()) == ["SC 13D", "SC 13D/A", "SC 13G"]
    assert "SC 13E3" not in set(frame["form_type"])
    assert "SC 13E3" not in set(frame["form_type_raw"])
    # the same accession appears once per associated CIK (issuer and filer)
    duplicated = frame.loc[frame["accession"] == "0001111111-24-000002"]
    assert sorted(duplicated["cik"].tolist()) == [320193, 555555]
    # company names containing spaces and a /DE/ suffix survive the split
    amended = frame.loc[frame["form_type"] == "SC 13D/A"].iloc[0]
    assert amended["company_name"] == "EXAMPLE TARGET CORP  /DE/"
    assert amended["cik"] == 320193
    assert amended["date_filed"] == pd.Timestamp("2024-02-14")


def test_parse_form_index_normalizes_the_2024_12_form_type_rename() -> None:
    """``SCHEDULE 13D/A`` must not be truncated to a *new* ``SC 13D``.

    The rename came with the 2024-12-18 structured-XML mandate. Slicing the
    old 12-character form-type column dropped the ``/A`` and turned every
    2025+ amendment into a new filing -- which for this card would have
    multiplied the primary (new-13D-only) sample by roughly five.
    """
    frame = parse_form_index(FORM_IDX)
    renamed = frame.loc[frame["form_type_raw"] == "SCHEDULE 13D/A"]
    assert len(renamed) == 1
    assert renamed.iloc[0]["form_type"] == "SC 13D/A"
    assert renamed.iloc[0]["company_name"] == "RENAMED AFTER 2024 DEC CORP"
    assert renamed.iloc[0]["cik"] == 777777
    # a company name whose own first token is a number survives the split
    flowers = frame.loc[frame["form_type_raw"] == "SCHEDULE 13G"].iloc[0]
    assert flowers["company_name"] == "1 800 FLOWERS COM INC"
    assert flowers["form_type"] == "SC 13G"


def test_parse_submission_takes_the_issuer_from_the_subject_company_block() -> None:
    row = parse_submission(
        SUBMISSION,
        accession="0001111111-24-000002",
        index_form_type="SC 13D",
        index_date_filed="2024-01-03",
        max_bytes=320_000,
    )
    # the filer (ACTIVIST PARTNERS LP, CIK 555555) must not become the issuer
    assert row["issuer_cik"] == 320193
    assert row["issuer_name"] == "EXAMPLE TARGET CORP"
    assert row["filer_names"] == "ACTIVIST PARTNERS LP"
    assert row["filer_ciks"] == "555555"
    assert row["acceptance_datetime_et"] == "20240103163012"
    assert row["form_type"] == "SC 13D"
    assert row["percent_of_class"] == pytest.approx(7.4)
    assert row["percent_parse_confidence"] == "high"
    assert row["item4_present"] is True
    assert row["item4_chars"] > 80
    assert row["truncated"] is False


def test_percent_of_class_prefers_the_structured_xml_value() -> None:
    body = "<percentOfClass>5.2</percentOfClass> PERCENT OF CLASS ... 99.9%"
    value, confidence, source = parse_percent_of_class(strip_markup(body), body)
    assert (value, confidence, source) == (pytest.approx(5.2), "high", "xml")


def test_percent_of_class_reports_none_rather_than_guessing() -> None:
    value, confidence, source = parse_percent_of_class("no cover page reached", "")
    assert value is None
    assert confidence == "none"
    assert source == "not_found"


def test_item4_length_uses_the_last_heading_not_the_table_of_contents() -> None:
    body_text = (
        "Table of contents: Item 4. Purpose of Transaction .... 5 "
        "Item 4. Purpose of Transaction The reporting person will seek board seats. "
        "Item 5. Interest in Securities of the Issuer"
    )
    chars, present = parse_item4_length(body_text)
    assert present is True
    assert chars == len("The reporting person will seek board seats.")


def test_item4_absent_is_reported_as_zero_not_missing() -> None:
    assert parse_item4_length("Item 1. Security and Issuer") == (0, False)


def test_visible_session_intraday_filing_is_visible_same_session() -> None:
    # 2024-01-03 16:30:12 ET is *after* the 16:00 close -> next session
    assert visible_session(pd.Timestamp("2024-01-03 16:30:12")) == date(2024, 1, 4)
    # 09:45 ET the same day is inside the session
    assert visible_session(pd.Timestamp("2024-01-03 09:45:00")) == date(2024, 1, 3)


def test_visible_session_rolls_over_weekends_and_holidays() -> None:
    # Friday 2024-11-29 is a 13:00 early close: 14:00 ET is already after it
    assert visible_session(pd.Timestamp("2024-11-29 14:00:00")) == date(2024, 12, 2)
    # Saturday acceptance is never a session
    assert visible_session(pd.Timestamp("2024-11-30 10:00:00")) == date(2024, 12, 2)
    # Friday before Labor Day 2026 (Monday 2026-09-07 is a holiday)
    assert visible_session(pd.Timestamp("2026-09-04 18:00:00")) == date(2026, 9, 8)


def test_entry_session_is_the_session_after_visibility() -> None:
    assert entry_session(date(2024, 1, 3)) == date(2024, 1, 4)
    assert entry_session(date(2024, 11, 29)) == date(2024, 12, 2)


def test_capability_fixture_visibility_matches_the_calendar_rule() -> None:
    assert CAPABILITY_FIXTURE.exists(), CAPABILITY_FIXTURE
    rows = [
        json.loads(line) for line in CAPABILITY_FIXTURE.read_text().splitlines() if line.strip()
    ]
    assert rows, "fixture must not be empty"
    seen: set[str] = set()
    confidences: set[str] = set()
    for row in rows:
        raw = row["raw"]
        confidences.add(raw["visible_confidence"])
        if raw["visible_confidence"] == "acceptance_datetime":
            expected_visible = visible_session(pd.Timestamp(raw["acceptance_datetime_et"]))
        else:
            assert raw["acceptance_datetime_et"] is None, row["id"]
            expected_visible = next_us_equity_session(pd.Timestamp(raw["filing_date"]).date())
        assert raw["visible_session"] == expected_visible.isoformat(), row["id"]
        assert raw["entry_session"] == entry_session(expected_visible).isoformat(), row["id"]
        # visible_at on the record must not be earlier than the entry open it claims
        assert row["visible_at"][:10] == raw["entry_session"], row["id"]
        assert row["dedupe_key"] not in seen
        seen.add(row["dedupe_key"])
    # both visibility regimes have to be exercised, or the 13G path is untested
    assert confidences == {"acceptance_datetime", "filing_date_only"}


REAL_HEADER = b"""<SEC-DOCUMENT>0000004457-16-000068.txt : 20160212
<SEC-HEADER>0000004457-16-000068.hdr.sgml : 20160212
<ACCEPTANCE-DATETIME>20160211185532
ACCESSION NUMBER:\t\t0000004457-16-000068
CONFORMED SUBMISSION TYPE:\tSC 13D
FILED AS OF DATE:\t\t20160212
GROUP MEMBERS:\t\tBLACKWATER INVESTMENTS, INC

SUBJECT COMPANY:\t

\tCOMPANY DATA:\t
\t\tCOMPANY CONFORMED NAME:\t\t\tAMERCO /NV/
\t\tCENTRAL INDEX KEY:\t\t\t0000004457
\t\tSTANDARD INDUSTRIAL CLASSIFICATION:\tSERVICES [7510]

\tFILING VALUES:
\t\tFORM TYPE:\t\tSC 13D

\tFORMER COMPANY:\t
\t\tFORMER CONFORMED NAME:\tAMERCO
\t\tDATE OF NAME CHANGE:\t19770926

FILED BY:\t\t

\tCOMPANY DATA:\t
\t\tCOMPANY CONFORMED NAME:\t\t\tSHOEN EDWARD J
\t\tCENTRAL INDEX KEY:\t\t\t0000902188
</SEC-HEADER>
<DOCUMENT>
<TYPE>SC 13D
<TEXT>
<html><body>Item 4. Purpose of Transaction The group intends to vote together.
Item 5. Interest in Securities of the Issuer</body></html>
</TEXT>
</DOCUMENT>
"""


def test_parse_submission_reads_central_index_key_not_only_cik() -> None:
    """Real EDGAR headers spell the CIK ``CENTRAL INDEX KEY``.

    A 150-filing pilot (2026-09-16) came back with 150/150 null issuers
    because the parser only accepted the short ``CIK:`` spelling, which
    would have silently dropped every event in the study.
    """
    row = parse_submission(
        REAL_HEADER,
        accession="0000004457-16-000068",
        index_form_type="SC 13D",
        index_date_filed="2016-02-12",
        max_bytes=320_000,
    )
    assert row["issuer_cik"] == 4457
    assert row["issuer_name"] == "AMERCO /NV/"
    assert row["filer_ciks"] == "902188"
    assert row["filer_names"] == "SHOEN EDWARD J"
    # FILED AS OF DATE is YYYYMMDD in the header and must come out ISO
    assert row["filing_date"] == "2016-02-12"
    assert row["acceptance_datetime_et"] == "20160211185532"
