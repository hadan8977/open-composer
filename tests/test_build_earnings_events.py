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

from datetime import date

from scripts.build_earnings_events import (
    ExhibitCandidate,
    filing_matches,
    html_to_text,
    parse_document_table,
    parse_items,
    pick_ex99,
    sha256_hex,
    to_utc_iso,
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
# Acceptance timestamp (Eastern -> UTC)
# --------------------------------------------------------------------------


def test_to_utc_iso_handles_est_offset():
    # 2024-01-25 is EST (UTC-5): 16:30 ET -> 21:30 UTC.
    assert to_utc_iso("2024-01-25T16:30:15.000Z") == "2024-01-25T21:30:15Z"


def test_to_utc_iso_handles_edt_offset():
    # 2024-07-25 is EDT (UTC-4): 16:30 ET -> 20:30 UTC.
    assert to_utc_iso("2024-07-25T16:30:00.000Z") == "2024-07-25T20:30:00Z"


def test_to_utc_iso_handles_missing_value():
    assert to_utc_iso(None) is None
    assert to_utc_iso("") is None


def test_to_utc_iso_is_a_real_date_type_sanity_check():
    # Not a functional assertion -- just documents that the raw acceptance
    # date used elsewhere (accept_date[:10]) stays comparable to ISO dates.
    result = to_utc_iso("2024-01-25T16:30:15.000Z")
    assert date.fromisoformat(result[:10]) == date(2024, 1, 25)
