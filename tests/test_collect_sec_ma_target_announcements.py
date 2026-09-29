from __future__ import annotations

import importlib.util
import json
import sys
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "collect_sec_ma", ROOT / "scripts" / "collect_sec_ma_target_announcements.py"
)
assert _spec and _spec.loader
ma = importlib.util.module_from_spec(_spec)
sys.modules["collect_sec_ma"] = ma
_spec.loader.exec_module(ma)


class FakeResponse:
    def __init__(self, status: int, payload: bytes = b"") -> None:
        self.status_code = status
        self.content = payload


class FakeHttp:
    def __init__(self, responses: list[FakeResponse]) -> None:
        self.responses = list(responses)
        self.calls: list[dict] = []

    def get(self, url, params=None, headers=None):
        self.calls.append({"url": url, "params": params, "headers": headers})
        return self.responses.pop(0)


def fts_page(hits: list[dict], total: int) -> FakeResponse:
    body = {
        "hits": {
            "total": {"value": total},
            "hits": [
                {
                    "_id": f"{h['adsh']}:x.htm",
                    "_source": {
                        "adsh": h["adsh"],
                        "ciks": [h.get("cik", "0000000001")],
                        "display_names": ["Acme Inc.  (CIK 0000000001)"],
                        "file_date": "2024-03-05",
                        "form": "8-K",
                        "file_type": h.get("file_type", "8-K"),
                        "items": h.get("items", ["1.01", "9.01"]),
                    },
                }
                for h in hits
            ],
        }
    }
    return FakeResponse(200, json.dumps(body).encode())


def make_client(responses: list[FakeResponse]) -> tuple[ma.SecClient, FakeHttp, list[float]]:
    http = FakeHttp(responses)
    sleeps: list[float] = []
    client = ma.SecClient(min_interval=0.0, client=http, sleep=sleeps.append)
    return client, http, sleeps


def test_backoff_on_429_then_success() -> None:
    client, http, sleeps = make_client(
        [FakeResponse(429), FakeResponse(503), FakeResponse(200, b"ok")]
    )
    status, body = client.get("https://x/y")
    assert (status, body) == (200, b"ok")
    assert len(http.calls) == 3
    assert [s for s in sleeps if s >= 5] == [5.0, 10.0]


def test_backoff_gives_up_and_returns_last_status() -> None:
    client, _, _ = make_client([FakeResponse(403)] * 3)
    status, _ = client.get("https://x/y", retries=3)
    assert status == 403


def test_range_header_sent() -> None:
    client, http, _ = make_client([FakeResponse(206, b"abc")])
    client.get("https://x/y", max_bytes=1000)
    assert http.calls[0]["headers"] == {"Range": "bytes=0-999"}


def test_search_window_paginates_until_total() -> None:
    p1 = fts_page([{"adsh": f"0001-24-{i:06d}"} for i in range(100)], total=130)
    p2 = fts_page([{"adsh": f"0002-24-{i:06d}"} for i in range(30)], total=130)
    client, http, _ = make_client([p1, p2])
    hits, total = ma.search_window(client, '"x"', "8-K", date(2024, 3, 1), date(2024, 3, 31))
    assert total == 130 and len(hits) == 130
    assert [c["params"]["from"] for c in http.calls] == [0, 100]


def test_search_window_splits_when_capped() -> None:
    capped = fts_page([{"adsh": "0009-24-000001"}], total=10_000)
    left = fts_page([{"adsh": "0001-24-000001"}], total=1)
    right = fts_page([{"adsh": "0002-24-000001"}], total=1)
    client, http, _ = make_client([capped, left, right])
    hits, _ = ma.search_window(client, '"x"', "8-K", date(2024, 3, 1), date(2024, 3, 31))
    assert {h["adsh"] for h in hits} == {"0001-24-000001", "0002-24-000001"}
    assert http.calls[1]["params"]["startdt"] == "2024-03-01"
    assert http.calls[2]["params"]["enddt"] == "2024-03-31"


def test_month_windows() -> None:
    w = ma.month_windows("2023-11", "2024-02")
    assert w[0] == (date(2023, 11, 1), date(2023, 11, 30))
    assert w[-1] == (date(2024, 2, 1), date(2024, 2, 29))
    assert len(w) == 4


def test_announcement_items_excludes_completion() -> None:
    assert ma.is_announcement_items(["1.01", "8.01", "9.01"])
    assert not ma.is_announcement_items(["1.01", "2.01", "3.01", "5.01"])
    assert not ma.is_announcement_items(["8.01", "9.01"])


TARGET_8K = (
    "Item 1.01 Entry into a Material Definitive Agreement. On March 4, 2024, Acme Inc. "
    '(the "Company") entered into an Agreement and Plan of Merger with Big Parent Corp. '
    '("Parent") and Merger Sub Inc. ("Merger Sub"). Merger Sub will merge with and into the '
    "Company, with the Company surviving as a wholly owned subsidiary of Parent. Each share "
    "will be converted into the right to receive $12.50 per share in cash."
)
ACQUIRER_8K = (
    'Item 1.01. Big Parent Corp. ("Parent") entered into an Agreement and Plan of Merger with '
    'Merger Sub Inc. ("Merger Sub") and Acme Inc. (the "Company"). Merger Sub will merge with '
    "and into Acme Inc., with Acme Inc. surviving. Consideration is $12.50 per share in cash."
)


def test_classify_target_and_acquirer() -> None:
    t = ma.classify_filing(TARGET_8K, "Acme Inc.")
    assert t["is_target_rule"] and t["deal_type"] == "cash"
    assert "sub_merges_into_" in t["rule_reasons"]
    a = ma.classify_filing(ACQUIRER_8K, "Big Parent Corp.")
    assert not a["is_target_rule"]
    assert "sub_merges_into_other" in a["rule_reasons"]


def test_classify_acquirer_that_survives_a_merger_of_named_target() -> None:
    text = "Acme Holdings will merge with and into the Company with the Company as the survivor."
    assert not ma.classify_filing(text, "Big Parent Corp.")["is_target_rule"]


def test_classify_filer_named_in_object_position() -> None:
    text = "Merger Sub will merge with and into Acme Inc., a Delaware corporation."
    assert ma.classify_filing(text, "ACME INC")["is_target_rule"]
    assert not ma.classify_filing(text, "Zeta Corp")["is_target_rule"]


def test_classify_no_merger_clause_is_not_target() -> None:
    assert not ma.classify_filing("Item 5.02 Departure of Directors.", "Acme Inc.")[
        "is_target_rule"
    ]


def test_ex2_preamble_breaks_tie_toward_company() -> None:
    ex = (
        "AGREEMENT AND PLAN OF MERGER by and among BIG PARENT CORP., MERGER SUB INC. and "
        'ACME INC. (the "Company")'
    )
    out = ma.classify_filing("", "Acme Inc.", ex)
    assert out["target_score"] == 2 and out["is_target_rule"]
    out = ma.classify_filing("", "Big Parent Corp.", ex)
    assert not out["is_target_rule"]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("holders will receive $10 per share in cash", "cash"),
        ("at an exchange ratio of 0.5 shares", "stock"),
        ("$10 per share in cash and an exchange ratio of 0.5", "mixed"),
        ("the stockholders may make a cash election or stock election", "mixed"),
        ("nothing relevant", ""),
    ],
)
def test_deal_type(text: str, expected: str) -> None:
    assert ma.detect_deal_type(text) == expected


def test_acceptance_conversion_and_trade_date() -> None:
    utc = ma.acceptance_to_utc("20240319084430")  # EDT, UTC-4
    assert utc == pd.Timestamp("2024-03-19 12:44:30")
    winter = ma.acceptance_to_utc("20240115093000")  # EST, UTC-5
    assert winter == pd.Timestamp("2024-01-15 14:30:00")
    sessions = [date(2024, 3, 14), date(2024, 3, 15), date(2024, 3, 18)]
    # Saturday acceptance maps to the prior Friday session
    assert ma.trade_date_for("20240316120000", sessions) == date(2024, 3, 15)
    # after-hours on Friday: same session (entry is the next open in signal_card)
    assert ma.trade_date_for("20240315183000", sessions) == date(2024, 3, 15)


def test_parse_submission_head_extracts_main_and_ex2() -> None:
    raw = (
        "<SEC-HEADER>\n<ACCEPTANCE-DATETIME>20240304170000\n"
        "\tCOMPANY CONFORMED NAME:\t\t\tAcme Inc.\n</SEC-HEADER>\n"
        "<DOCUMENT>\n<TYPE>8-K\n<TEXT>\n<html><body><p>Merger Sub will merge with and into "
        "the Company</p></body></html>\n</TEXT>\n</DOCUMENT>\n"
        "<DOCUMENT>\n<TYPE>EX-2.1\n<TEXT>\n<p>AGREEMENT AND PLAN OF MERGER</p>\n"
        "</TEXT>\n</DOCUMENT>\n"
    )
    parsed = ma.parse_submission_head(raw)
    assert parsed["acceptance_et"] == "20240304170000"
    assert parsed["filer_name"] == "Acme Inc."
    assert "merge with and into the Company" in parsed["main_text"]
    assert parsed["ex2_head"] == "AGREEMENT AND PLAN OF MERGER"


def test_map_cik_symbol_prefers_history_then_current() -> None:
    hist = {
        7: [
            ("OLD", date(2018, 1, 1), date(2019, 12, 31)),
            ("NEW", date(2021, 1, 1), date(2024, 1, 1)),
        ]
    }
    assert ma.map_cik_symbol(7, date(2019, 6, 1), hist, {}) == ("OLD", "form4_history")
    assert ma.map_cik_symbol(7, date(2020, 6, 1), hist, {})[1] == "form4_history_near"
    assert ma.map_cik_symbol(9, date(2020, 6, 1), hist, {9: "CUR"}) == (
        "CUR",
        "company_tickers_current",
    )
    assert ma.map_cik_symbol(9, date(2020, 6, 1), hist, {}) == (None, "unmapped")
    # stale history (> 2 years from any span) falls through to the current map
    assert ma.map_cik_symbol(7, date(2030, 1, 1), hist, {7: "CUR"}) == (
        "CUR",
        "company_tickers_current",
    )


def test_clean_symbol() -> None:
    assert ma.clean_symbol(" abc ") == "ABC"
    assert ma.clean_symbol("NONE") is None
    assert ma.clean_symbol(None) is None


def test_followup_flag_within_five_sessions() -> None:
    sessions = [date(2024, 3, d) for d in (4, 5, 6, 7, 8, 11, 12, 13)]
    events = pd.DataFrame({"cik": [1, 2], "trade_date": [date(2024, 3, 4), date(2024, 3, 4)]})
    confirm = pd.DataFrame({"cik": [1, 2], "file_date": [date(2024, 3, 5), date(2024, 3, 13)]})
    flags = ma.deal_followup_flags(events, confirm, sessions)
    assert flags.tolist() == [True, False]


def test_load_candidates_groups_files_and_filters_items(tmp_path: Path) -> None:
    def hit(adsh: str, ftype: str, items: list[str]) -> dict:
        return {
            "id": f"{adsh}:x",
            "adsh": adsh,
            "ciks": ["0000001234"],
            "names": ["Acme Inc."],
            "file_date": "2024-03-05",
            "form": "8-K",
            "file_type": ftype,
            "items": items,
        }

    d = tmp_path / "q1"
    d.mkdir()
    (d / "202403.json").write_text(
        json.dumps(
            {
                "total": 3,
                "hits": [
                    hit("A", "8-K", ["1.01", "9.01"]),
                    hit("A", "EX-2.1", ["1.01", "9.01"]),
                    hit("B", "8-K", ["1.01", "2.01", "5.01"]),
                ],
            }
        )
    )
    out = ma.load_candidates(tmp_path)
    assert out["adsh"].tolist() == ["A"]
    assert out.loc[0, "file_types"] == ["8-K", "EX-2.1"]
    assert out.loc[0, "cik"] == 1234


def test_spac_amendment_and_holdco_are_not_targets() -> None:
    assert ma.is_spac_name("Roth CH Acquisition V Co.")
    assert not ma.is_spac_name("Summit Materials, Inc.")
    assert not ma.classify_filing(TARGET_8K, "Blank Check Acquisition Corp")["is_target_rule"]
    amend = (
        "Item 1.01 Entry into a Material Definitive Agreement. Amendment to Merger Agreement "
        "As previously disclosed Merger Sub will merge with and into the Company."
    )
    out = ma.classify_filing(amend, "Acme Inc.")
    assert not out["is_target_rule"] and "amendment_excluded" in out["rule_reasons"]
    holdco = (
        "Item 1.01. Entry into a Material Definitive Agreement. holding company reorganization "
        "Merger Sub will merge with and into the Company."
    )
    out = ma.classify_filing(holdco, "Acme Inc.")
    assert not out["is_target_rule"] and "holdco_reorg_excluded" in out["rule_reasons"]
    # a same-day "as previously reported" 8-K is still an announcement
    assert ma.classify_filing("Item 1.01. As previously reported, " + TARGET_8K, "Acme Inc.")[
        "is_target_rule"
    ]


def test_company_defined_as_other_entity_means_filer_is_acquirer() -> None:
    text = (
        'Item 1.01. On July 5, 2022, Domtar Corporation ("Parent") entered into an Agreement and '
        'Plan of Merger with Resolute Forest Products Inc. (the "Company") and Terra Acquisition '
        'Sub Inc. ("Merger Sub"). Merger Sub will merge with and into the Company.'
    )
    assert not ma.classify_filing(text, "Domtar CORP")["is_target_rule"]
    assert ma.classify_filing(text, "Resolute Forest Products Inc")["is_target_rule"]


def test_named_company_merging_into_filer_means_filer_survives() -> None:
    text = (
        "First Savings will merge with and into First Merchants, whereupon "
        "First Merchants survives."
    )
    out = ma.classify_filing(text, "FIRST MERCHANTS CORP")
    assert not out["is_target_rule"] and "named_merges_into_filer" in out["rule_reasons"]


def test_merger_sub_that_is_subsidiary_of_filer_means_buyer() -> None:
    text = (
        'RTI Surgical, Inc. (the "Company") entered into an agreement with Holdco, a wholly owned '
        "subsidiary of the Company, and Merger Sub. Merger Sub will merge with and into "
        "the Company."
    )
    out = ma.classify_filing(text, "RTI SURGICAL, INC.")
    assert not out["is_target_rule"] and "sub_is_subsidiary_of_filer" in out["rule_reasons"]


def test_completion_item_2_01_is_excluded() -> None:
    out = ma.classify_filing(TARGET_8K, "Acme Inc.", items=["1.01", "2.01", "9.01"])
    assert not out["is_target_rule"] and "item_2_01_excluded" in out["rule_reasons"]
    assert ma.classify_filing(TARGET_8K, "Acme Inc.", items=["1.01", "9.01"])["is_target_rule"]


def test_repeated_clauses_count_once_and_registrant_definition() -> None:
    text = TARGET_8K + " " + TARGET_8K
    single = ma.classify_filing(TARGET_8K, "Acme Inc.")
    double = ma.classify_filing(text, "Acme Inc.")
    assert single["target_score"] == double["target_score"]
    reg = (
        'the Registrant ("we," "our" or the "Company") entered into an Agreement and Plan of '
        "Merger by and among the Company, Peck Mercury, Inc., a wholly-owned subsidiary of the "
        'Company (the "Merger Sub") and iSun Energy LLC. Merger Sub merged with and into iSun '
        "Energy LLC."
    )
    assert ma.company_definition_is_filer(reg, "isun") is True


def test_sub_marker_window_covers_appositive() -> None:
    text = (
        "Genoptix Merger Sub, Inc. (Merger Sub), a wholly owned subsidiary of NeoGenomics Labs, "
        "will merge with and into Genesis, the parent entity of Genoptix."
    )
    out = ma.classify_filing(text, "NEOGENOMICS INC")
    assert not out["is_target_rule"] and "sub_merges_into_other" in out["rule_reasons"]


def test_second_amendment_to_plan_of_merger_is_excluded() -> None:
    text = (
        "Item 1.01 Entry Into Material Definitive Agreement. On February 7, 2025, GAN Limited "
        '(the "Company") entered into a Second Amendment to Agreement and Plan of Merger with '
        "Parent and Merger Sub. Merger Sub will merge with and into the Company."
    )
    out = ma.classify_filing(text, "GAN Ltd")
    assert not out["is_target_rule"] and "amendment_excluded" in out["rule_reasons"]
