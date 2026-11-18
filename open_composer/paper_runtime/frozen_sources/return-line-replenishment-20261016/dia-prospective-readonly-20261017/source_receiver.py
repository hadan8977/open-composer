"""One exact canonical source/page/vector receiver for current and future use."""

import csv
import io
import re
import zipfile
from datetime import datetime
from pathlib import Path

from common import OUT, binding, load

URL = (
    "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/F-F_Research_Data_Factors_CSV.zip"
)
ENDPOINTS = {
    "raw-bars": "https://data.alpaca.markets/v2/stocks/bars",
    "actions": "https://data.alpaca.markets/v1/corporate-actions",
}


def canonical(path, expected):
    p = Path(path)
    e = Path(expected).absolute()
    assert p.is_absolute() and p == e and p.resolve() == e, "Noncanonical source consumer/alias"
    return p


def read_context(path):
    """Derived context names are identities too, even for identical bytes."""
    return load(canonical(path, path))


def bind_context(path):
    return binding(canonical(path, path))


def bound_time(value):
    t = datetime.fromisoformat(value)
    limit = datetime.fromisoformat(
        read_context(OUT / "frozen-calendar.json")["final_reception_bound_utc"]
    )
    assert t.tzinfo is not None and t < limit, (
        "Source receipt after absolute bound or unknown timestamp"
    )
    return t


def check_binding(b, expected):
    p = canonical(b["path"], expected)
    assert binding(p) == b
    return p


def capture(folder):
    folder = Path(folder).absolute()
    canonical(folder, OUT / "source-captures" / folder.name)
    complete = read_context(folder / "complete.json")
    bound_time(complete["at_utc"])
    localpath = check_binding(complete["local"], folder / "local-reception.json")
    local = load(localpath)
    bound_time(local["at_utc"])
    check_binding(local["selected_ADV"], folder / "selected-ADV.parquet")
    check_binding(complete["publication"], folder / "publication-head.json")
    pages = {k: [] for k in ENDPOINTS}
    seen = set()
    assert complete["source_receipts"], "No received source pages"
    for b in complete["source_receipts"]:
        p = Path(b["path"])
        kind = p.parent.name
        assert kind in pages and re.fullmatch(r"GET\d{2}\.json", p.name) and str(p) not in seen
        seen.add(str(p))
        check_binding(b, folder / kind / p.name)
        pages[kind].append(p)
    data = {k: [] for k in pages}
    for kind, paths in pages.items():
        paths.sort()
        assert paths and [p.name for p in paths] == [
            f"GET{i:02}.json" for i in range(1, len(paths) + 1)
        ]
        expected_raw = {str(p.with_suffix(".raw")) for p in paths}
        actual_raw = {str(p) for p in (folder / kind).iterdir() if p.suffix.lower() == ".raw"}
        assert expected_raw == actual_raw, "Unlisted/partial source page"
        actual_meta = {
            p.name for p in (folder / kind).iterdir() if re.fullmatch(r"GET\d{2}\.json", p.name)
        }
        assert actual_meta == {p.name for p in paths}
        assert {p.name for p in (folder / kind).glob("*.started.json")} == {
            p.stem + ".started.json" for p in paths
        }, "Partial started source page"
        cursor = None
        for p in paths:
            r = load(p)
            start = read_context(p.with_name(p.stem + ".started.json"))
            assert r["status"] == 200 and r["endpoint"] == start["endpoint"] == ENDPOINTS[kind]
            assert r["params"] == start["params"] and r["requested_at_utc"] == start["at_utc"]
            assert bound_time(r["requested_at_utc"]) <= bound_time(r["received_at_utc"])
            assert r["params"].get("page_token") == cursor
            raw = check_binding(r["response"], p.with_suffix(".raw"))
            obj = load(raw)
            cursor = r["next_page_token"]
            assert obj.get("next_page_token") == cursor
            if kind == "raw-bars":
                assert all(
                    r["params"][k] == v
                    for k, v in [
                        ("feed", "sip"),
                        ("adjustment", "raw"),
                        ("asof", "-"),
                        ("timeframe", "1Day"),
                    ]
                )
            data[kind].append((raw, obj))
        assert cursor is None, "Incomplete source pagination"
    return dict(complete=complete, local=local, pages=data)


def september():
    folder = OUT / "source-captures/factor-202609"
    selected = folder / "selected.json"
    r = load(canonical(selected, selected))
    assert r["month"] == "2026-09"
    bound_time(r["received_at_utc"])
    receipt = check_binding(r["receipt"], folder / "receipt.json")
    meta = load(receipt)
    bound_time(meta["at_utc"])
    started = read_context(folder / "request-started.json")
    assert started["url"] == URL and bound_time(started["at_utc"]) <= bound_time(meta["at_utc"])
    assert meta["status"] == 200 and meta["final_url"] == URL
    raw = check_binding(meta["source"], folder / "official-ff3.zip")
    assert {p.name for p in folder.iterdir() if p.suffix.lower() == ".zip"} == {"official-ff3.zip"}
    with zipfile.ZipFile(raw) as z:
        assert len(z.namelist()) == 1 and z.namelist()[0].lower().endswith(".csv")
        text = z.read(z.namelist()[0]).decode("utf-8-sig")
    rows = [row for row in csv.reader(io.StringIO(text)) if row and row[0].strip() == "202609"]
    assert len(rows) <= 1
    assert r["available"] == bool(rows)
    if rows:
        values = [float(x) / 100 for x in rows[0][1:5]]
        assert len(values) == 4 and all(abs(v) < 1 for v in values)
        assert [r[k] for k in ["Mkt-RF", "SMB", "HML", "RF"]] == values, (
            "Selected vector not derived from bound official raw bytes"
        )
    return r


def september_context():
    """Freeze the available OR unavailable append and its exact source chain."""
    row = september()
    folder = OUT / "source-captures/factor-202609"
    return dict(
        month=row["month"],
        available=row["available"],
        vector={k: row[k] for k in ["Mkt-RF", "SMB", "HML", "RF"]} if row["available"] else None,
        files={
            n: bind_context(folder / n)
            for n in ["selected.json", "request-started.json", "receipt.json", "official-ff3.zip"]
        },
    )
