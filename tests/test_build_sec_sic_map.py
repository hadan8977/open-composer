from __future__ import annotations

import importlib.util
import json
import sys
import zipfile
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "build_sec_sic_map", ROOT / "scripts/build_sec_sic_map.py"
)
assert SPEC and SPEC.loader
mod = importlib.util.module_from_spec(SPEC)
sys.modules["build_sec_sic_map"] = mod
SPEC.loader.exec_module(mod)

SICCODES48 = """\
 1 Agric  Agriculture
          0100-0199 Agricultural production - crops
          0700-0799 Agricultural services

 2 Food   Food Products
          2000-2009 Food and kindred products
          2010-2019 Meat products

48 Other  Almost Nothing
          4950-4959 Sanitary services
"""

SICCODES12 = """\
 1 NoDur  Consumer Nondurables -- Food
          0100-0999
          2000-2399

11 Money  Finance
          6000-6999

12 Other  Other -- Mines, Constr
"""


def test_parse_french_siccodes_ranges_and_names():
    ranges, names = mod.parse_french_siccodes(SICCODES48)
    assert names == {1: "Agric", 2: "Food", 48: "Other"}
    assert ranges[0] == (100, 199, 1)
    assert (2010, 2019, 2) in ranges
    assert ranges[-1] == (4950, 4959, 48)


def test_parse_ranges_without_description_and_empty_other():
    ranges, names = mod.parse_french_siccodes(SICCODES12)
    assert names[12] == "Other"
    assert all(industry != 12 for _, _, industry in ranges)
    assert (6000, 6999, 11) in ranges


def test_sic_to_industry_range_edges_and_fallback():
    ranges, names = mod.parse_french_siccodes(SICCODES48)
    assert mod.map_sic_to_industry(100, ranges, names, 48) == (1, "Agric")
    assert mod.map_sic_to_industry(199, ranges, names, 48) == (1, "Agric")
    assert mod.map_sic_to_industry(200, ranges, names, 48) == (48, "Other")
    assert mod.map_sic_to_industry(2009, ranges, names, 48) == (2, "Food")
    assert mod.map_sic_to_industry(2010, ranges, names, 48) == (2, "Food")
    assert mod.map_sic_to_industry(2020, ranges, names, 48) == (48, "Other")
    assert mod.map_sic_to_industry(4959, ranges, names, 48) == (48, "Other")
    assert mod.map_sic_to_industry(None, ranges, names, 48) == (48, "Other")


def test_ff12_fallback_goes_to_other():
    ranges, names = mod.parse_french_siccodes(SICCODES12)
    assert mod.map_sic_to_industry(6199, ranges, names, 12) == (11, "Money")
    assert mod.map_sic_to_industry(1000, ranges, names, 12) == (12, "Other")
    assert mod.map_sic_to_industry(None, ranges, names, 12) == (12, "Other")


def _history() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "cik": [111, 222, 333],
            "symbol": ["ABC", "ABC", "XYZ"],
            "first_date": pd.to_datetime(["2016-01-04", "2021-03-01", "2016-01-04"]),
            "last_date": pd.to_datetime(["2020-12-31", "2026-09-01", "2018-01-01"]),
        }
    )


def test_symbol_cik_join_with_reused_symbol_and_fallback():
    links = mod.build_symbol_cik_links(
        ["ABC", "BRK.B", "NEW", "NONE"], _history(), {"BRK-B": 1067983, "NEW": 999}
    )
    assert mod.ciks_for_symbol_on(links, "ABC", "2019-06-30") == [111]
    assert mod.ciks_for_symbol_on(links, "ABC", "2022-06-30") == [222]
    assert mod.ciks_for_symbol_on(links, "ABC", "2021-01-15") == []  # gap between the two CIKs
    assert mod.ciks_for_symbol_on(links, "BRK.B", "2024-01-31") == [
        1067983
    ]  # normalized, open-ended
    assert mod.ciks_for_symbol_on(links, "NEW", "2016-01-31") == [999]
    assert "NONE" not in set(links["symbol"])
    fallback = links[links["symbol"] == "NEW"].iloc[0]
    assert pd.isna(fallback["link_first_date"]) and fallback["link_source"] == "company_tickers"
    assert (links[links["symbol"] == "ABC"]["link_source"] == "history").all()


def test_extract_sic_record_present_and_missing():
    doc = {
        "cik": "1045810",
        "name": "NVIDIA CORP",
        "sic": "3674",
        "sicDescription": "Semiconductors & Related Devices",
        "formerNames": [{"name": "OLD NAME", "from": "1999-01-01", "to": "2000-01-01"}],
    }
    rec = mod.extract_sic_record(doc)
    assert rec["sic"] == 3674 and rec["entity_name"] == "NVIDIA CORP"
    assert rec["former_names_count"] == 1
    for missing in ({"name": "X"}, {"name": "X", "sic": ""}, {"name": "X", "sic": "0"}):
        rec = mod.extract_sic_record(missing)
        assert rec["sic"] is None and rec["former_names_count"] == 0


def test_pagination_members_skipped_and_bulk_read(tmp_path):
    assert mod.is_cik_member("CIK0001045810.json")
    assert not mod.is_cik_member("CIK0001045810-submissions-001.json")
    assert not mod.is_cik_member("notes.txt")
    archive = tmp_path / "submissions.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("CIK0000000111.json", json.dumps({"name": "A", "sic": "2010"}))
        zf.writestr(
            "CIK0000000111-submissions-001.json", json.dumps({"name": "PAGE", "sic": "9999"})
        )
        zf.writestr("CIK0000000222.json", json.dumps({"name": "B"}))
    records = mod.read_bulk_records(archive, {111, 222, 333})
    assert set(records) == {111, 222}  # 333 absent from the archive
    assert records[111]["sic"] == 2010 and records[222]["sic"] is None


def test_assemble_and_lookup_prefers_covering_link():
    links = mod.build_symbol_cik_links(["ABC"], _history(), {})
    definitions = {
        48: mod.parse_french_siccodes(SICCODES48),
        12: mod.parse_french_siccodes(SICCODES12),
    }
    records = {
        111: {"sic": 2010, "sic_description": "Meat", "entity_name": "Old Co"},
        222: {"sic": None, "sic_description": None, "entity_name": "New Co"},
    }
    sic_map = mod.assemble_sic_map(
        links,
        records,
        definitions,
        source="submissions_bulk",
        fetched_at_utc="2026-10-01T00:00:00Z",
    )
    assert list(sic_map.columns) == mod.OUTPUT_COLUMNS
    old = sic_map[sic_map["cik"] == 111].iloc[0]
    assert (old["ff48"], old["ff48_name"], old["ff12"], old["ff12_name"]) == (2, "Food", 1, "NoDur")
    new = sic_map[sic_map["cik"] == 222].iloc[0]
    assert pd.isna(new["sic"]) and (new["ff48"], new["ff12"]) == (48, 12)
    row, verified = mod.lookup_sic_row(sic_map, "ABC", "2019-06-30")
    assert row["cik"] == 111 and verified
    # outside every link period: nearest non-null-SIC link, flagged unverified
    row, verified = mod.lookup_sic_row(sic_map, "ABC", "2024-01-31")
    assert row["cik"] == 111 and not verified
    assert mod.lookup_sic_row(sic_map, "ZZZ", "2024-01-31") == (None, False)


def test_mapped_symbol_months_strict_vs_any_period():
    links = mod.build_symbol_cik_links(["ABC"], _history(), {})
    sic_map = links.assign(sic=pd.array([2010, 2010], dtype="Int64"))
    panel = pd.DataFrame(
        {
            "symbol": ["ABC", "ABC", "ABC", "QQQ"],
            "month_end": pd.to_datetime(["2019-01-31", "2021-01-29", "2030-01-31", "2019-01-31"]),
        }
    )
    strict = mod.mapped_symbol_months(panel, sic_map)
    assert strict.tolist() == [True, False, False, False]
    lenient = mod.mapped_symbol_months(panel, sic_map, strict_dates=False)
    assert lenient.tolist() == [True, True, True, False]


def test_checkpoint_resume_skips_done_and_tolerates_truncated_line(tmp_path):
    path = tmp_path / "ck.jsonl"
    path.write_text(json.dumps({"cik": 5, "sic": 1}) + "\n" + '{"cik": 6, "si')
    assert set(mod.load_checkpoint(path)) == {5}

    class FakeClient:
        def __init__(self):
            self.urls = []

        def get(self, url):
            self.urls.append(url)
            if url.endswith("0000000007.json"):
                return 200, json.dumps({"name": "S", "sic": "3674"}).encode()
            if url.endswith("0000000008.json"):
                return 404, b""
            return 429, b""

    client = FakeClient()
    out = mod.fetch_api_records(client, {5, 7, 8, 9}, path)
    assert all("0000000005" not in u for u in client.urls)
    assert out[7]["sic"] == 3674 and out[8]["sic"] is None and 9 not in out
    # a rerun does not refetch 7/8 but retries the 429 one
    client2 = FakeClient()
    mod.fetch_api_records(client2, {5, 7, 8, 9}, path)
    assert len(client2.urls) == 1 and client2.urls[0].endswith("0000000009.json")
