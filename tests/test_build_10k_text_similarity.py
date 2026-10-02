"""Offline tests for scripts/build_10k_text_similarity.py (hand-written HTML)."""

from __future__ import annotations

import importlib.util
import io
import json
import math
import sys
import zipfile
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
_spec = importlib.util.spec_from_file_location(
    "build_10k_text_similarity", ROOT / "scripts" / "build_10k_text_similarity.py"
)
mod = importlib.util.module_from_spec(_spec)
sys.modules["build_10k_text_similarity"] = mod
_spec.loader.exec_module(mod)


def words(prefix: str, n: int) -> str:
    """n distinct-ish letter-only words, e.g. 'alpha beta ...' keyed by prefix."""
    letters = "abcdefghij"
    return " ".join(prefix + letters[i % 10] + letters[(i // 10) % 10] for i in range(n))


def doc(*blocks: str) -> bytes:
    return ("<html><body>" + "".join(blocks) + "</body></html>").encode()


def test_toc_duplicate_heading_takes_longest_body() -> None:
    rf_body = words("riskword", 120)
    html = doc(
        "<div>Item 1A. Risk Factors</div><div>Item 1B. Unresolved Staff Comments</div>",
        "<div>Item 1. Business</div><p>" + words("biz", 80) + "</p>",
        "<div>Item 1A. Risk Factors</div><p>" + rf_body + "</p>",
        "<div>Item 1B. Unresolved Staff Comments</div><p>none</p>",
        "<div>Item 2. Properties</div><p>office</p>",
    )
    out = mod.parse_document(html)
    assert out["found_rf"]
    assert out["n_rf"] >= 120
    assert "riskwordaa" in out["rf"]
    assert not any(k.startswith("biz") for k in out["rf"])


def test_cross_reference_inside_sentence_is_not_a_heading() -> None:
    html = doc(
        "<div>Item 1. Business</div><p>see Item 1A. Risk Factors for more. "
        + words("biz", 90)
        + "</p>",
        "<div>Item 1A. Risk Factors</div><p>" + words("rk", 60) + "</p>",
        "<div>Item 1B. Unresolved</div>",
    )
    out = mod.parse_document(html)
    assert out["found_rf"]
    assert not any(k.startswith("biz") for k in out["rf"])


def test_sections_end_at_1b_and_7a() -> None:
    html = doc(
        "<div>Item 1A. Risk Factors</div><p>" + words("rk", 60) + "</p>",
        "<div>Item 1B. Unresolved</div><p>" + words("unres", 60) + "</p>",
        "<div>Item 7. Management's Discussion</div><p>" + words("md", 70) + "</p>",
        "<div>Item 7A. Quantitative</div><p>" + words("quant", 60) + "</p>",
        "<div>Item 8. Financial Statements</div><p>" + words("fin", 60) + "</p>",
    )
    out = mod.parse_document(html)
    assert out["n_rf"] > 60 and not any(k.startswith("unres") for k in out["rf"])
    assert out["n_mda"] > 70 and not any(k.startswith("quant") for k in out["mda"])
    assert out["found_mda"]


def test_rf_may_end_at_item_2() -> None:
    html = doc(
        "<div>Item 1A. Risk Factors</div><p>" + words("rk", 60) + "</p>",
        "<div>Item 2. Properties</div><p>" + words("prop", 60) + "</p>",
    )
    out = mod.parse_document(html)
    assert out["found_rf"] and not any(k.startswith("prop") for k in out["rf"])


def test_tables_and_ix_header_and_hidden_removed() -> None:
    html = doc(
        '<div style="display:none"><ix:header>hiddenheader gibberish</ix:header></div>',
        "<table><tr><td>tablecell tablecell</td></tr></table>",
        '<p style="display: none">invisibletext</p>',
        "<p>visibleword and tail</p>",
    )
    out = mod.parse_document(html)
    full = out["full"]
    assert "visibleword" in full and "tail" in full
    for gone in ("hiddenheader", "gibberish", "tablecell", "invisibletext"):
        assert gone not in full


def test_blocks_do_not_glue_words() -> None:
    out = mod.parse_document(doc("<p>alpha</p><p>beta</p><div>gamma</div>delta"))
    assert set(out["full"]) == {"alpha", "beta", "gamma", "delta"}


def test_tokenize_rules() -> None:
    c = mod.tokenize("Alpha a 10K don't x2 " + "z" * 21 + " " + "y" * 20 + " Alpha")
    assert c["alpha"] == 2
    assert c["don"] == 1
    assert "a" not in c and "t" not in c and "k" not in c
    assert "z" * 21 not in c and c["y" * 20] == 1


def test_cosine_and_jaccard_hand_computed() -> None:
    a = {"x": 1, "y": 2}
    b = {"x": 2, "y": 1, "z": 1}
    # dot=4, |a|=sqrt5, |b|=sqrt6
    assert mod.cosine(a, b) == pytest.approx(4 / math.sqrt(30))
    assert mod.jaccard(a, b) == pytest.approx(2 / 3)
    assert mod.cosine(a, a) == pytest.approx(1.0)
    assert mod.jaccard(a, {"q": 1}) == 0.0


def test_similarity_missing_below_50_words() -> None:
    big = {"w": 60}
    small = {"w": 49}
    cos, jac = mod.similarity(big, small)
    assert math.isnan(cos) and math.isnan(jac)
    assert math.isnan(mod.similarity(big, None)[0])
    assert mod.similarity(big, {"w": 50})[0] == pytest.approx(1.0)


def _filing(acc: str, date: str, counts: dict | None) -> dict:
    return {"accession": acc, "filing_date": pd.Timestamp(date), "counts": counts}


def test_pair_gap_boundaries() -> None:
    c = {"full": {"w": 100}, "rf": {"w": 60}, "mda": None}
    rows = mod.pair_filings(
        [
            _filing("a", "2020-01-01", c),
            _filing("b", "2020-10-27", c),  # gap 300 -> pair
            _filing("c", "2021-10-26", c),  # gap 364 -> pair
            _filing("d", "2022-01-04", c),  # gap 70 -> no pair
            _filing("e", "2023-03-09", c),  # gap 429 -> pair
            _filing("f", "2024-05-12", c),  # gap 430 -> pair
            _filing("g", "2025-07-17", c),  # gap 431 -> no pair
            _filing("h", "2026-01-01", c),  # gap 168 -> no pair
        ]
    )
    flags = {r["accession"]: r["has_pair"] for r in rows}
    gaps = {r["accession"]: r["gap_days"] for r in rows}
    assert gaps["b"] == 300 and gaps["e"] == 429 and gaps["f"] == 430
    assert flags == dict(a=False, b=True, c=True, d=False, e=True, f=True, g=False, h=False)
    pair = next(r for r in rows if r["accession"] == "b")
    assert pair["prev_accession"] == "a"
    assert pair["cos_full"] == pytest.approx(1.0)
    assert math.isnan(pair["cos_mda"])  # section missing -> NaN, not zero


def test_pair_skipped_when_a_document_failed() -> None:
    c = {"full": {"w": 100}, "rf": None, "mda": None}
    rows = mod.pair_filings([_filing("a", "2020-01-01", None), _filing("b", "2021-01-01", c)])
    assert not rows[1]["has_pair"]


def test_resume_skips_completed_ciks() -> None:
    progress = {"completed_ciks": [2, 4]}
    assert mod.pending_ciks([1, 2, 3, 4, 5], progress, resume=True) == [1, 3, 5]
    assert mod.pending_ciks([1, 2, 3], progress, resume=False) == [1, 2, 3]


def test_cik_map_drops_short_links_and_picks_longest() -> None:
    links = pd.DataFrame(
        {
            "symbol": ["A", "A", "A", "B"],
            "cik": [1, 2, 3, 4],
            "link_first_date": pd.to_datetime(["2016-01-01", "2022-03-08", "2018-01-01", None]),
            "link_last_date": pd.to_datetime(["2026-01-01", "2022-03-08", "2020-12-31", None]),
        }
    )
    dates = pd.bdate_range("2019-01-01", "2019-01-10")
    members = pd.DataFrame(
        {
            "symbol": ["A"] * len(dates) + ["B"] * 2 + ["C"],
            "trade_date": list(dates) + list(dates[:2]) + [dates[0]],
        }
    )
    out = mod.build_cik_map(members, links)
    a = out[out["symbol"] == "A"]
    # cik 2 spans 0 days (dropped), cik 1 (10y) beats cik 3 (3y) on the covered dates
    assert list(a["cik"]) == [1]
    assert a.iloc[0]["first_date"] == dates[0] and a.iloc[0]["last_date"] == dates[-1]
    assert list(out[out["symbol"] == "B"]["cik"]) == [4]  # undated link is open-ended
    assert "C" not in set(out["symbol"])


def test_cik_map_splits_runs_when_cik_changes() -> None:
    links = pd.DataFrame(
        {
            "symbol": ["A", "A"],
            "cik": [1, 2],
            "link_first_date": pd.to_datetime(["2018-06-01", "2019-06-01"]),
            "link_last_date": pd.to_datetime(["2019-05-31", "2019-12-31"]),
        }
    )
    dates = pd.to_datetime(["2019-05-30", "2019-05-31", "2019-06-03"])
    members = pd.DataFrame({"symbol": "A", "trade_date": dates})
    out = mod.build_cik_map(members, links)
    assert list(out["cik"]) == [1, 2]
    assert out.iloc[0]["last_date"] == dates[1] and out.iloc[1]["first_date"] == dates[2]


def test_index_filings_filters_form_and_dates_and_reads_pages() -> None:
    def block(forms_dates: list[tuple[str, str]], prefix: str) -> dict:
        n = len(forms_dates)
        return {
            "form": [f for f, _ in forms_dates],
            "filingDate": [d for _, d in forms_dates],
            "accessionNumber": [f"{prefix}-{i}" for i in range(n)],
            "acceptanceDateTime": [f"{d}T21:11:55.000Z" for _, d in forms_dates],
            "reportDate": ["2020-01-01"] * n,
            "primaryDocument": [f"doc{i}.htm" for i in range(n)],
        }

    recent = block([("10-K", "2020-02-01"), ("10-K/A", "2020-03-01"), ("10-Q", "2020-05-01")], "r")
    page = block([("10-K", "2014-10-27"), ("10-K", "2014-01-02")], "p")
    main = {
        "filings": {
            "recent": recent,
            "files": [
                {"name": "CIK0000000007-submissions-001.json", "filingTo": "2015-08-23"},
                {"name": "CIK0000000007-submissions-002.json", "filingTo": "2013-01-01"},
            ],
        }
    }
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("CIK0000000007.json", json.dumps(main))
        zf.writestr("CIK0000000007-submissions-001.json", json.dumps(page))
    with zipfile.ZipFile(buf) as zf:
        rows, missing = mod.index_filings(zf, 7)
    assert missing == 0
    assert sorted(r["filing_date"] for r in rows) == ["2014-10-27", "2020-02-01"]
    row = next(r for r in rows if r["accession"] == "r-0")
    assert row["url"] == "https://www.sec.gov/Archives/edgar/data/7/r0/doc0.htm"


def test_heading_only_tables_keep_section_boundaries_but_no_table_text() -> None:
    html = doc(
        "<table><tr><td>Item 1A.</td><td>Risk Factors</td></tr></table>",
        "<p>" + words("rk", 60) + "</p>",
        "<table><tr><td>Item 1B.</td><td>Unresolved Staff Comments</td></tr></table>",
        "<table><tr><td>Item 7.</td><td>Management Discussion</td></tr></table>",
        "<p>" + words("md", 60) + "</p>",
        "<table><tr><td>Item 7A.</td><td>Market Risk</td></tr></table>",
        "<table><tr><td>revenuecell</td><td>" + words("num", 80) + "</td></tr></table>",
    )
    out = mod.parse_document(html, want_snippets=True)
    assert out["found_rf"] and out["found_mda"]
    assert out["n_rf"] == 60 and out["n_mda"] == 60  # markers and heading words not counted
    assert "revenuecell" not in out["full"] and "unresolved" not in out["full"]
    assert "item" not in out["full"]
    assert out["snippets"]["rf"][0].startswith("rkaa")
