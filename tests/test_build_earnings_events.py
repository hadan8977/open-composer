"""T1 (plan-earnings-text-forward-test-2026-09-22): fixture-based unit tests
for the earnings-event table builder. No network access -- everything here
runs against literal strings and small in-memory fixtures, matching the
card's "no network" test scope.

Three things are pinned, because each is a place this table could silently
mis-scope or mis-select:

* :func:`filing_matches` -- the T1 scope filter (8-K with Item 2.02 among
  its comma-separated Items) must not admit other forms or 8-Ks without
  2.02, and must not choke on missing/empty Items.
* :func:`pick_ex99` -- EX-99.1 wins outright; EX-99.2 (or later) is only
  used as a fallback when its filing-index description mentions
  results/earnings/quarter, per the plan's fallback rule.
* :func:`html_to_text` -- tables are dropped whole (not just detagged, which
  would leave numeric noise from every row), scripts/styles are dropped,
  and remaining text survives with normalized whitespace.
"""

from __future__ import annotations

import json
from datetime import date

import pandas as pd
import pytest

import scripts.build_earnings_events as bee
from scripts.build_earnings_events import (
    ExhibitCandidate,
    eastern_wallclock_to_utc_iso,
    filing_matches,
    html_to_text,
    parse_accepted,
    parse_document_table,
    parse_items,
    pick_ex99,
    sha256_hex,
    to_utc_iso,
    undo_double_shift,
)

# --------------------------------------------------------------------------
# Items filter
# --------------------------------------------------------------------------


def test_parse_items_splits_and_strips():
    assert parse_items("2.02,9.01") == ["2.02", "9.01"]
    assert parse_items("2.02, 9.01") == ["2.02", "9.01"]
    assert parse_items("") == []
    assert parse_items(None) == []


def test_filing_matches_requires_8k_and_item_202():
    assert filing_matches("8-K", "2.02,9.01") is True
    assert filing_matches("8-K", "2.02") is True


def test_filing_matches_rejects_other_forms():
    assert filing_matches("10-Q", "2.02") is False
    assert filing_matches("8-K/A", "2.02") is False  # amendments are a distinct form string


def test_filing_matches_rejects_missing_item_202():
    assert filing_matches("8-K", "9.01") is False
    assert filing_matches("8-K", "") is False
    assert filing_matches("8-K", None) is False


def test_filing_matches_form_case_and_whitespace_insensitive():
    assert filing_matches(" 8-k ", "2.02") is True


# --------------------------------------------------------------------------
# EX-99 pick
# --------------------------------------------------------------------------


def test_pick_ex99_prefers_ex99_1():
    candidates = [
        ExhibitCandidate(
            doc_type="EX-99.2", description="INVESTOR PRESENTATION", href="/a/ex992.htm"
        ),
        ExhibitCandidate(
            doc_type="EX-99.1", description="PRESS RELEASE DATED JAN 25, 2024", href="/a/ex991.htm"
        ),
    ]
    picked = pick_ex99(candidates)
    assert picked is not None
    assert picked.href == "/a/ex991.htm"


def test_pick_ex99_falls_back_to_ex99_2_with_matching_description():
    candidates = [
        ExhibitCandidate(
            doc_type="EX-99.2", description="Q4 2023 RESULTS PRESS RELEASE", href="/a/ex992.htm"
        ),
    ]
    picked = pick_ex99(candidates)
    assert picked is not None
    assert picked.href == "/a/ex992.htm"


def test_pick_ex99_ignores_ex99_2_without_matching_description():
    candidates = [
        ExhibitCandidate(
            doc_type="EX-99.2", description="AUDIT COMMITTEE CHARTER", href="/a/ex992.htm"
        ),
    ]
    assert pick_ex99(candidates) is None


def test_pick_ex99_none_when_no_ex99_present():
    candidates = [
        ExhibitCandidate(doc_type="EX-10.1", description="CREDIT AGREEMENT", href="/a/ex101.htm"),
        ExhibitCandidate(doc_type="8-K", description="FORM 8-K", href="/a/main.htm"),
    ]
    assert pick_ex99(candidates) is None


def test_pick_ex99_matches_earnings_and_quarter_keywords_too():
    candidates = [
        ExhibitCandidate(
            doc_type="EX-99.3", description="THIRD QUARTER EARNINGS SLIDES", href="/a/ex993.htm"
        ),
    ]
    picked = pick_ex99(candidates)
    assert picked is not None
    assert picked.href == "/a/ex993.htm"


def test_parse_document_table_from_index_html_fixture():
    index_html = """
    <html><body>
    <table class="tableFile" summary="Document Format Files">
      <tr><th>Seq</th><th>Description</th><th>Document</th><th>Type</th><th>Size</th></tr>
      <tr><td>1</td><td>FORM 8-K</td>
          <td><a href="/Archives/edgar/data/1/a/main.htm">main.htm</a></td>
          <td>8-K</td><td>5000</td></tr>
      <tr><td>2</td><td>PRESS RELEASE DATED JANUARY 25, 2024</td>
          <td><a href="/Archives/edgar/data/1/a/ex991.htm">ex991.htm</a></td>
          <td>EX-99.1</td><td>12000</td></tr>
    </table>
    <table class="tableFile" summary="Data Files">
      <tr><th>Seq</th><th>Document</th><th>Type</th><th>Size</th></tr>
      <tr><td>1</td><td><a href="/Archives/edgar/data/1/a/x.xml">x.xml</a></td>
          <td>EX-101.INS</td><td>900</td></tr>
    </table>
    </body></html>
    """
    candidates = parse_document_table(index_html)
    types = [c.doc_type for c in candidates]
    assert "EX-99.1" in types
    picked = pick_ex99(candidates)
    assert picked is not None
    assert picked.href.endswith("ex991.htm")
    # Only the first ("Document Format Files") table is parsed, not the XBRL
    # "Data Files" table -- EX-101.INS must not leak in.
    assert "EX-101.INS" not in types


# --------------------------------------------------------------------------
# HTML -> text
# --------------------------------------------------------------------------


def test_html_to_text_strips_tags_and_unescapes_entities():
    raw = "<html><body><p>Net income rose 12% &amp; revenue grew.</p></body></html>"
    text = html_to_text(raw)
    assert text == "Net income rose 12% & revenue grew."


def test_html_to_text_drops_whole_tables():
    raw = """
    <p>Third quarter results follow.</p>
    <table><tr><td>Revenue</td><td>100</td></tr><tr><td>EPS</td><td>1.23</td></tr></table>
    <p>Guidance is unchanged.</p>
    """
    text = html_to_text(raw)
    assert "Revenue" not in text
    assert "100" not in text
    assert "1.23" not in text
    assert "Third quarter results follow." in text
    assert "Guidance is unchanged." in text


def test_html_to_text_drops_script_and_style_blocks():
    raw = "<style>.x{color:red}</style><script>var x=1;</script><p>Body text.</p>"
    text = html_to_text(raw)
    assert "color" not in text
    assert "var x" not in text
    assert text == "Body text."


def test_html_to_text_collapses_whitespace_and_preserves_paragraph_breaks():
    raw = "<p>First   paragraph.</p><p>Second\nparagraph.</p>"
    text = html_to_text(raw)
    assert text == "First paragraph.\n\nSecond paragraph."


def test_sha256_hex_is_deterministic_and_content_sensitive():
    assert sha256_hex("abc") == sha256_hex("abc")
    assert sha256_hex("abc") != sha256_hex("abd")


# --------------------------------------------------------------------------
# Acceptance timestamp (fixed 2026-10-04, T-20261004-52 / pitfall #61)
# --------------------------------------------------------------------------

INDEX_HTML = """
<div class="formGrouping">
 <div class="infoHead">Filing Date</div>
 <div class="info">2025-10-31</div>
 <div class="infoHead">Accepted</div>
 <div class="info">2025-10-31 06:01:26</div>
 <div class="infoHead">Documents</div>
 <div class="info">91</div>
</div>
"""


def test_parse_accepted_reads_the_accepted_field_only():
    assert parse_accepted(INDEX_HTML) == "2025-10-31 06:01:26"
    assert parse_accepted("<html>no such field</html>") is None


@pytest.mark.parametrize(
    ("eastern", "utc"),
    [
        ("2025-03-07 16:05:00", "2025-03-07T21:05:00Z"),  # EST before the 03-09 switch
        ("2025-03-10 16:05:00", "2025-03-10T20:05:00Z"),  # EDT after it
        ("2025-10-31 06:01:26", "2025-10-31T10:01:26Z"),  # EDT
        ("2025-11-01 16:05:00", "2025-11-01T20:05:00Z"),  # EDT before the 11-02 switch
        ("2025-11-03 16:05:00", "2025-11-03T21:05:00Z"),  # EST after it
    ],
)
def test_eastern_wallclock_to_utc_iso_across_dst_switches(eastern, utc):
    assert eastern_wallclock_to_utc_iso(eastern) == utc


def test_eastern_wallclock_to_utc_iso_rejects_garbage():
    assert eastern_wallclock_to_utc_iso(None) is None
    assert eastern_wallclock_to_utc_iso("") is None
    assert eastern_wallclock_to_utc_iso("31/10/2025 06:01") is None


def test_to_utc_iso_reads_the_api_value_as_utc():
    # The submissions API value is already a true UTC instant.
    assert to_utc_iso("2024-01-25T21:30:15.000Z") == "2024-01-25T21:30:15Z"
    assert to_utc_iso("2024-07-25T20:30:00.000Z") == "2024-07-25T20:30:00Z"
    assert to_utc_iso(None) is None
    assert to_utc_iso("") is None
    assert to_utc_iso("not a time") is None


@pytest.mark.parametrize(
    ("true_utc", "hours"),
    [
        ("2025-03-07T21:05:00Z", 5),  # Friday before the 03-09 switch (EST)
        ("2025-03-10T20:05:00Z", 4),  # Monday after it (EDT)
        ("2025-10-31T10:01:26Z", 4),
        ("2025-11-03T21:05:00Z", 5),  # Monday after the 11-02 switch (EST)
        ("2025-12-01T12:00:00Z", 5),
        ("2025-07-01T12:00:00Z", 4),
    ],
)
def test_undo_double_shift_is_the_inverse_of_the_old_bug(true_utc, hours):
    from datetime import UTC, datetime, timedelta

    raw = datetime.fromisoformat(true_utc.replace("Z", "+00:00"))
    old_stored = raw.replace(tzinfo=None).replace(tzinfo=bee._EASTERN).astimezone(UTC)
    assert old_stored - raw == timedelta(hours=hours)  # the old bug, reproduced
    assert undo_double_shift(old_stored.strftime("%Y-%m-%dT%H:%M:%SZ")) == true_utc
    assert undo_double_shift(None) is None


def test_undo_double_shift_matches_index_time_for_a_known_filing():
    # Index page says 2025-10-31 06:01:26 ET (EDT) = 10:01:26Z; the old table
    # held 14:01:26Z.
    assert undo_double_shift("2025-10-31T14:01:26Z") == "2025-10-31T10:01:26Z"
    assert eastern_wallclock_to_utc_iso("2025-10-31 06:01:26") == "2025-10-31T10:01:26Z"


# --------------------------------------------------------------------------
# End-to-end build against a fake HTTP layer
# --------------------------------------------------------------------------

EX_INDEX_ROW = (
    '<table class="tableFile" summary="Document Format Files">'
    "<tr><th>Seq</th><th>Description</th><th>Document</th><th>Type</th><th>Size</th></tr>"
    '<tr><td>1</td><td>8-K</td><td><a href="/Archives/x/main.htm">main.htm</a></td>'
    "<td>8-K</td><td>1</td></tr>"
    '<tr><td>2</td><td>PRESS RELEASE</td><td><a href="/Archives/x/ex991.htm">ex991.htm</a></td>'
    "<td>EX-99.1</td><td>1</td></tr></table>"
)


def _index_page(accepted: str) -> bytes:
    return (
        f'<div class="infoHead">Accepted</div><div class="info">{accepted}</div>' + EX_INDEX_ROW
    ).encode()


class FakeClient:
    """Stands in for SecClient: serves canned payloads, records every URL."""

    def __init__(self, *, index_pages, submissions, explode_on=None):
        self.index_pages = index_pages  # accession -> accepted text or None (HTTP 404)
        self.submissions = submissions  # cik10 -> filings.recent payload
        self.explode_on = explode_on
        self.urls: list[str] = []

    def get(self, url, *, retries=5):
        self.urls.append(url)
        if url == bee.COMPANY_TICKERS_URL:
            body = {"0": {"ticker": "AAA", "cik_str": 1}, "1": {"ticker": "BBB", "cik_str": 2}}
            return 200, json.dumps(body).encode()
        if url.startswith("https://data.sec.gov/submissions/CIK"):
            cik10 = url.rsplit("CIK", 1)[1].removesuffix(".json")
            if cik10 == self.explode_on:
                raise RuntimeError("simulated crash")
            payload = {"name": f"Co {cik10}", "filings": {"recent": self.submissions[cik10]}}
            return 200, json.dumps(payload).encode()
        if url.endswith("-index.htm"):
            accession = url.rsplit("/", 1)[1].removesuffix("-index.htm")
            accepted = self.index_pages.get(accession)
            if accepted is None:
                return 404, b""
            return 200, _index_page(accepted)
        if url.endswith("ex991.htm"):
            return 200, b"<p>Results for the quarter.</p>"
        raise AssertionError(url)

    def close(self):
        pass


def _recent(accession, accepted_utc):
    return {
        "accessionNumber": [accession],
        "filingDate": [accepted_utc[:10]],
        "acceptanceDateTime": [accepted_utc],
        "form": ["8-K"],
        "items": ["2.02,9.01"],
        "primaryDocument": ["main.htm"],
    }


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    monkeypatch.setattr(bee, "ROOT", tmp_path)
    monkeypatch.setattr(bee, "UNIVERSE_DIR", tmp_path / "universe")
    monkeypatch.setattr(bee, "OUT_DIR", tmp_path / "out")
    monkeypatch.setattr(bee, "UNRESOLVED_PATH", tmp_path / "out" / "unresolved.json")
    monkeypatch.setattr(bee, "RAW_TEXT_ROOT", tmp_path / "raw")
    monkeypatch.setattr(bee, "RAW_CACHE_ROOT", tmp_path / "raw" / "_cache")
    monkeypatch.setattr(bee, "COMPANY_TICKERS_CACHE", tmp_path / "raw" / "_cache" / "ct.json")
    monkeypatch.setattr(bee, "CHECKPOINT_PATH", tmp_path / "raw" / "_cache" / "ckpt.jsonl")
    (tmp_path / "universe").mkdir()
    pd.DataFrame(
        {
            "month_end": pd.to_datetime(["2025-03-31"] * 2),
            "symbol": ["AAA", "BBB"],
            "adv_rank": [1, 2],
        }
    ).to_parquet(tmp_path / "universe" / "2025.parquet")
    return tmp_path


def _run(client):
    return bee.build(
        start=date(2025, 1, 1),
        end=date(2025, 12, 31),
        top_n=10,
        limit=None,
        refresh_tickers=True,
        client=client,
    )


def _load(sandbox):
    return pd.read_parquet(sandbox / "out" / "2025.parquet").set_index("accession")


def test_build_uses_index_time_and_falls_back_to_formula(sandbox):
    client = FakeClient(
        # API value is true UTC: 2025-03-10 20:05:00Z == 16:05:00 EDT.
        submissions={
            "0000000001": _recent("0000000001-25-000001", "2025-03-10T20:05:00.000Z"),
            "0000000002": _recent("0000000002-25-000002", "2025-11-03T21:05:00.000Z"),
        },
        index_pages={"0000000001-25-000001": "2025-03-10 16:05:00"},  # index fails for the 2nd
    )
    stats = _run(client)
    table = _load(sandbox)
    first = table.loc["0000000001-25-000001"]
    second = table.loc["0000000002-25-000002"]
    assert first.acceptance_source == "edgar_index"
    assert first.acceptance_utc == "2025-03-10T20:05:00Z"
    assert second.acceptance_source == "formula"
    assert second.acceptance_utc == "2025-11-03T21:05:00Z"  # EST: 16:05 ET
    assert stats.per_source == {"edgar_index": 1, "formula": 1}
    assert stats.index_formula_mismatch == 0


def test_build_prefers_index_when_it_disagrees_with_api(sandbox):
    client = FakeClient(
        submissions={
            "0000000001": _recent("0000000001-25-000001", "2025-03-10T20:05:00.000Z"),
            "0000000002": {"accessionNumber": []},
        },
        index_pages={"0000000001-25-000001": "2025-03-10 16:06:00"},
    )
    stats = _run(client)
    assert _load(sandbox).loc["0000000001-25-000001"].acceptance_utc == "2025-03-10T20:06:00Z"
    assert stats.index_formula_mismatch == 1


def test_build_resumes_from_checkpoint_without_refetching_finished_companies(sandbox):
    submissions = {
        "0000000001": _recent("0000000001-25-000001", "2025-03-10T20:05:00.000Z"),
        "0000000002": _recent("0000000002-25-000002", "2025-11-03T21:05:00.000Z"),
    }
    pages = {
        "0000000001-25-000001": "2025-03-10 16:05:00",
        "0000000002-25-000002": "2025-11-03 16:05:00",
    }
    crashing = FakeClient(submissions=submissions, index_pages=pages, explode_on="0000000002")
    with pytest.raises(RuntimeError, match="simulated crash"):
        _run(crashing)
    assert not (sandbox / "out" / "2025.parquet").exists()  # nothing half-written
    assert bee.CHECKPOINT_PATH.exists()

    resumed = FakeClient(submissions=submissions, index_pages=pages)
    _run(resumed)
    assert not any("CIK0000000001" in url for url in resumed.urls)
    assert not any("0000000001-25-000001-index" in url for url in resumed.urls)
    table = _load(sandbox)
    assert sorted(table.index) == ["0000000001-25-000001", "0000000002-25-000002"]
    assert table.loc["0000000002-25-000002"].acceptance_utc == "2025-11-03T21:05:00Z"
    assert not bee.CHECKPOINT_PATH.exists()  # cleaned up after a complete run


def test_rebuild_moves_a_filing_across_a_year_boundary_without_duplicates(sandbox):
    out = sandbox / "out"
    out.mkdir()
    stale = pd.DataFrame(
        {
            "cik": ["0000000001"],
            "ticker": ["AAA"],
            "accession": ["0000000001-25-000001"],
            # old, double-shifted: true 2025-12-31T21:00Z stored as 2026-01-01T02:00Z
            "acceptance_utc": ["2026-01-01T02:00:00Z"],
        }
    )
    stale.to_parquet(out / "2026.parquet")
    client = FakeClient(
        submissions={
            "0000000001": _recent("0000000001-25-000001", "2025-12-31T21:00:00.000Z"),
            "0000000002": {"accessionNumber": []},
        },
        index_pages={"0000000001-25-000001": "2025-12-31 16:00:00"},
    )
    _run(client)
    assert list(_load(sandbox).index) == ["0000000001-25-000001"]
    assert len(pd.read_parquet(out / "2026.parquet")) == 0
