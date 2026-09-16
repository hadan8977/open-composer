"""H-20260916-01 step 0: the Form 4 parser and its point-in-time visibility rule.

Two things are pinned here, because both are places where an insider
pipeline silently becomes a look-ahead pipeline:

* :func:`collect_sec_insider_transactions.assemble_parsed_frame` -- the
  SUBMISSION / REPORTINGOWNER / NONDERIV_TRANS join. Driven by the tiny
  synthetic TSVs under ``data/fixtures/capabilities/`` (SEC column layout,
  synthetic issuers/owners, no real personal data).
* The visibility rule itself: a filing is usable only from the **next US
  equity session after FILING_DATE**, never from TRANS_DATE. The capability
  fixture ``data/fixtures/capabilities/sec_form4_insider.jsonl`` is checked
  row by row against ``market_calendar.next_us_equity_session``, so a
  fixture that quietly claims earlier visibility fails the suite.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from open_composer.market_calendar import next_us_equity_session
from scripts.build_insider_features import visible_session
from scripts.collect_sec_insider_transactions import (
    NONDERIV_TRANS_USECOLS,
    PARSED_COLUMNS,
    REPORTINGOWNER_USECOLS,
    SUBMISSION_OPTIONAL_USECOLS,
    SUBMISSION_USECOLS,
    assemble_parsed_frame,
    parse_form4_xml,
)

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "data" / "fixtures" / "capabilities"
CAPABILITY_FIXTURE = FIXTURES / "sec_form4_insider.jsonl"


def _read_fixture(name: str, usecols: tuple[str, ...]) -> pd.DataFrame:
    frame = pd.read_csv(FIXTURES / name, sep="\t", dtype="string", quoting=3)
    for column in usecols:
        if column not in frame.columns:
            frame[column] = pd.Series(pd.NA, index=frame.index, dtype="string")
    return frame[list(usecols)]


@pytest.fixture(scope="module")
def parsed() -> pd.DataFrame:
    return assemble_parsed_frame(
        submission=_read_fixture(
            "sec_form4_submission_sample.tsv",
            SUBMISSION_USECOLS + SUBMISSION_OPTIONAL_USECOLS,
        ),
        owners=_read_fixture("sec_form4_reportingowner_sample.tsv", REPORTINGOWNER_USECOLS),
        transactions=_read_fixture("sec_form4_nonderiv_trans_sample.tsv", NONDERIV_TRANS_USECOLS),
        source_dataset="fixture:synthetic",
    )


def test_parsed_frame_has_the_declared_schema(parsed: pd.DataFrame) -> None:
    assert list(parsed.columns) == list(PARSED_COLUMNS)
    # 9 transaction rows x owners, minus nothing: accession ...006 has two
    # owners, so its single transaction yields two rows.
    assert len(parsed) == 10
    assert parsed["filing_date"].notna().all()


def test_symbol_is_upper_cased_and_issuer_cik_is_kept(parsed: pd.DataFrame) -> None:
    row = parsed.loc[parsed["accession"] == "0000000000-26-000001"].iloc[0]
    assert row["issuer_symbol"] == "AAPL"  # fixture writes it lower-case
    assert int(row["issuer_cik"]) == 320193


def test_owner_relationship_tokens_become_flags(parsed: pd.DataFrame) -> None:
    def row(accession: str, owner_seq: int = 0) -> pd.Series:
        match = parsed.loc[(parsed["accession"] == accession) & (parsed["owner_seq"] == owner_seq)]
        return match.iloc[0]

    officer = row("0000000000-26-000001")
    assert bool(officer["is_officer"]) and not bool(officer["is_director"])
    both = row("0000000000-26-000004")
    assert bool(both["is_director"]) and bool(both["is_officer"])
    ten_percent = row("0000000000-26-000003")
    assert bool(ten_percent["is_ten_percent_owner"])
    other = parsed.loc[
        (parsed["accession"] == "0000000000-26-000006") & (parsed["is_other_relationship"])
    ]
    assert len(other) == 1


def test_joint_filings_get_owner_seq_and_owner_count(parsed: pd.DataFrame) -> None:
    joint = parsed.loc[parsed["accession"] == "0000000000-26-000006"]
    assert len(joint) == 2
    assert sorted(int(value) for value in joint["owner_seq"]) == [0, 1]
    assert set(int(value) for value in joint["owner_count"]) == {2}
    # Summing only owner_seq == 0 rows must not double count the transaction.
    assert float(joint.loc[joint["owner_seq"] == 0, "shares"].sum()) == 4000.0
    assert joint["reporting_owner_cik"].nunique() == 2
    assert set(joint["reporting_owner_cik"]) == {"0009000005", "0009000006"}


def test_transaction_codes_and_amounts_are_normalized(parsed: pd.DataFrame) -> None:
    codes = parsed.set_index("accession")["trans_code"]
    assert codes["0000000000-26-000001"] == "P"
    assert codes["0000000000-26-000005"] == "S"
    exercise = parsed.loc[parsed["accession"] == "0000000000-26-000007"]
    assert sorted(exercise["trans_code"]) == ["F", "M"]
    buy = parsed.loc[parsed["accession"] == "0000000000-26-000001"].iloc[0]
    assert float(buy["shares"]) == 1200.0
    assert float(buy["price_per_share"]) == 21.5
    assert float(buy["shares_owned_after"]) == 41200.0
    assert buy["acquired_disposed"] == "A"
    assert buy["direct_or_indirect"] == "D"
    indirect = parsed.loc[parsed["accession"] == "0000000000-26-000003"].iloc[0]
    assert indirect["direct_or_indirect"] == "I"


def test_10b5_1_flag_is_tri_state(parsed: pd.DataFrame) -> None:
    def flag(accession: str) -> object:
        values = parsed.loc[parsed["accession"] == accession, "is_10b5_1"].unique()
        assert len(values) == 1
        return values[0]

    assert bool(flag("0000000000-26-000005")) is True
    assert bool(flag("0000000000-26-000001")) is False
    # An empty AFF10B5ONE cell (and, for pre-2023q2 vintages, a missing
    # column) must stay null rather than collapse to False.
    assert pd.isna(flag("0000000000-26-000007"))


def test_missing_aff10b5one_column_yields_all_null() -> None:
    submission = _read_fixture(
        "sec_form4_submission_sample.tsv", SUBMISSION_USECOLS + SUBMISSION_OPTIONAL_USECOLS
    )
    submission = submission.drop(columns=["AFF10B5ONE"])
    submission["AFF10B5ONE"] = pd.Series(pd.NA, index=submission.index, dtype="string")
    frame = assemble_parsed_frame(
        submission=submission,
        owners=_read_fixture("sec_form4_reportingowner_sample.tsv", REPORTINGOWNER_USECOLS),
        transactions=_read_fixture("sec_form4_nonderiv_trans_sample.tsv", NONDERIV_TRANS_USECOLS),
        source_dataset="fixture:synthetic",
    )
    assert frame["is_10b5_1"].isna().all()


def test_trans_date_can_precede_filing_date_by_months(parsed: pd.DataFrame) -> None:
    """A late filing is normal and must not be silently dropped or re-dated."""
    late = parsed.loc[parsed["accession"] == "0000000000-26-000004"].iloc[0]
    assert late["trans_date"] == pd.Timestamp("2026-06-15")
    assert late["filing_date"] == pd.Timestamp("2026-09-08")
    assert late["trans_date"] < late["filing_date"]


# --------------------------------------------------------------------------
# the point-in-time visibility rule
# --------------------------------------------------------------------------


def _capability_rows() -> list[dict]:
    with CAPABILITY_FIXTURE.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def test_visible_session_is_the_next_us_equity_session() -> None:
    # Thursday -> Friday, Friday -> Monday, Friday before Labor Day -> Tuesday.
    assert visible_session(pd.Timestamp("2026-09-10")) == pd.Timestamp("2026-09-11")
    assert visible_session(pd.Timestamp("2026-09-11")) == pd.Timestamp("2026-09-14")
    assert visible_session(pd.Timestamp("2026-09-04")) == pd.Timestamp("2026-09-08")


@pytest.mark.parametrize("row", _capability_rows(), ids=lambda row: row["id"])
def test_capability_fixture_visibility_follows_filing_date(row: dict) -> None:
    filing_date = pd.Timestamp(row["raw"]["filing_date"])
    visible_at = pd.Timestamp(row["visible_at"])
    expected_session = pd.Timestamp(next_us_equity_session(filing_date.date()))
    assert visible_at.tz_convert("America/New_York").normalize().tz_localize(None) == (
        expected_session
    )
    assert visible_at > pd.Timestamp(row["published_at"])
    assert visible_at >= pd.Timestamp(row["fetched_at"])


@pytest.mark.parametrize("row", _capability_rows(), ids=lambda row: row["id"])
def test_capability_fixture_never_uses_trans_date_as_visibility(row: dict) -> None:
    trans_date = pd.Timestamp(row["raw"]["trans_date"])
    visible_at = pd.Timestamp(row["visible_at"]).tz_convert("America/New_York").tz_localize(None)
    assert visible_at.normalize() > trans_date


def test_late_filing_is_not_visible_at_its_transaction_date() -> None:
    """The regression this whole convention exists to prevent."""
    late = next(
        row for row in _capability_rows() if row["raw"]["accession"] == "0000000000-26-000004"
    )
    trans_date = pd.Timestamp(late["raw"]["trans_date"])
    visible_at = pd.Timestamp(late["visible_at"]).tz_convert("America/New_York").tz_localize(None)
    assert trans_date == pd.Timestamp("2026-06-15")
    assert (visible_at.normalize() - trans_date).days > 80


def test_capability_fixture_matches_the_registry_entry() -> None:
    from open_composer.capabilities.registry import get_capability

    capability = get_capability("events.sec_form4_insider", ROOT)
    assert capability.kind == "event"
    assert capability.status == "trial"
    assert capability.provider == "sec"
    assert capability.env == ["SEC_USER_AGENT"]
    assert (ROOT / capability.fixture) == CAPABILITY_FIXTURE
    assert set(capability.use_for) == {"insider_confirmation_gate", "cross_sectional_feature"}
    joined = " | ".join(capability.caveats)
    assert "TRANS_DATE is never used as visibility" in joined
    assert "10b5-1" in joined
    assert "personal names" in joined


# --------------------------------------------------------------------------
# the tail collector's Form 4 XML parser
# --------------------------------------------------------------------------

FORM4_XML = b"""<?xml version="1.0"?>
<ownershipDocument>
  <documentType>4</documentType>
  <periodOfReport>2026-09-08</periodOfReport>
  <aff10b5One>0</aff10b5One>
  <issuer>
    <issuerCik>0000320193</issuerCik>
    <issuerTradingSymbol>aapl</issuerTradingSymbol>
  </issuer>
  <reportingOwner>
    <reportingOwnerId><rptOwnerCik>0009000001</rptOwnerCik></reportingOwnerId>
    <reportingOwnerRelationship>
      <isDirector>0</isDirector>
      <isOfficer>1</isOfficer>
      <isTenPercentOwner>0</isTenPercentOwner>
    </reportingOwnerRelationship>
  </reportingOwner>
  <nonDerivativeTable>
    <nonDerivativeTransaction>
      <transactionDate><value>2026-09-08</value></transactionDate>
      <transactionCoding><transactionCode>P</transactionCode></transactionCoding>
      <transactionAmounts>
        <transactionShares><value>1200</value></transactionShares>
        <transactionPricePerShare><value>21.50</value></transactionPricePerShare>
        <transactionAcquiredDisposedCode><value>A</value></transactionAcquiredDisposedCode>
      </transactionAmounts>
      <postTransactionAmounts>
        <sharesOwnedFollowingTransaction><value>41200</value></sharesOwnedFollowingTransaction>
      </postTransactionAmounts>
      <ownershipNature>
        <directOrIndirectOwnership><value>D</value></directOrIndirectOwnership>
      </ownershipNature>
    </nonDerivativeTransaction>
  </nonDerivativeTable>
</ownershipDocument>
"""


def test_form4_xml_parser_matches_the_quarterly_schema() -> None:
    frame = parse_form4_xml(
        FORM4_XML, accession="0000000000-26-000001", source_dataset="tail:20260908"
    )
    assert list(frame.columns) == list(PARSED_COLUMNS)
    assert len(frame) == 1
    row = frame.iloc[0]
    assert row["issuer_symbol"] == "AAPL"
    assert int(row["issuer_cik"]) == 320193
    assert row["reporting_owner_cik"] == "0009000001"
    assert bool(row["is_officer"]) and not bool(row["is_director"])
    assert row["trans_code"] == "P"
    assert float(row["shares"]) == 1200.0
    assert float(row["price_per_share"]) == 21.5
    assert row["acquired_disposed"] == "A"
    assert row["direct_or_indirect"] == "D"
    assert bool(row["is_10b5_1"]) is False
    # filing_date is supplied by the caller from the EDGAR index, never from
    # periodOfReport, which is a transaction period and not a visibility date.
    assert pd.isna(row["filing_date"])


def test_form4_xml_parser_tolerates_a_namespaced_document() -> None:
    namespaced = FORM4_XML.replace(
        b"<ownershipDocument>", b'<ownershipDocument xmlns="http://www.sec.gov/edgar/ownership">'
    )
    frame = parse_form4_xml(namespaced, accession="x", source_dataset="tail:test")
    assert len(frame) == 1
