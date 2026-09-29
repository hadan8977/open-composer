from __future__ import annotations

import importlib.util
import io
import sys
import zipfile
from datetime import date
from pathlib import Path

import polars as pl
import pytest

_SPEC = importlib.util.spec_from_file_location(
    "fetch_sec_ftd", Path(__file__).resolve().parents[1] / "scripts" / "fetch_sec_ftd.py"
)
assert _SPEC and _SPEC.loader
ff = importlib.util.module_from_spec(_SPEC)
sys.modules["fetch_sec_ftd"] = ff
_SPEC.loader.exec_module(ff)

TEXT = (
    "SETTLEMENT DATE|CUSIP|SYMBOL|QUANTITY (FAILS)|DESCRIPTION|PRICE\n"
    "20260601|000361105|AIR|1,234|AAR CORP|85.66\n"
    "20260615|000361105|AIR|500|AAR CORP|.\n"
    "20260615|123456789|XYZ|77|SOME CO|\n"
    "20260615|123456780|ABC|88|OTHER CO|abc\n"
    "20260615|123456781|BAD|notanumber|BROKEN|1.0\n"
    "Trailer record count |4\n"
    "\n"
)


def _zip(text: str, name: str = "cnsfails202606a.txt") -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(name, text.encode("latin-1"))
    return buf.getvalue()


class FakeResp:
    def __init__(self, status: int, content: bytes = b"", headers: dict | None = None):
        self.status_code = status
        self.content = content
        self.headers = headers or {}


class FakeSession:
    def __init__(self, script):
        self.script = list(script)
        self.urls: list[str] = []
        self.headers: dict = {}

    def get(self, url: str, timeout: int = 0):
        self.urls.append(url)
        item = self.script.pop(0) if self.script else FakeResp(404)
        return item(url) if callable(item) else item


def _client(script):
    sleeps: list[float] = []
    ticks = iter(range(0, 100_000))
    client = ff.Client(
        session=FakeSession(script),
        sleep=sleeps.append,
        clock=lambda: float(next(ticks)),
        min_interval=0.0,
    )
    return client, sleeps


def test_file_keys_and_url():
    keys = ff.file_keys((2026, 11), date(2027, 1, 20))
    assert keys == [
        ("202611", "a"),
        ("202611", "b"),
        ("202612", "a"),
        ("202612", "b"),
        ("202701", "a"),
        ("202701", "b"),
    ]
    assert (
        ff.file_url("202606", "b")
        == "https://www.sec.gov/files/data/fails-deliver-data/cnsfails202606b.zip"
    )


def test_user_agent_has_no_email():
    assert "@" not in ff.USER_AGENT
    assert "open-composer-research" in ff.USER_AGENT


def test_parse_handles_trailer_bad_price_and_bad_quantity():
    frame, st = ff.parse_ftd_text(TEXT)
    assert frame.height == 4
    assert st == {"rows": 4, "skipped_lines": 2, "bad_price": 3}
    assert frame["quantity"].to_list() == [1234, 500, 77, 88]
    assert frame["price"].to_list() == [85.66, None, None, None]
    assert frame.schema == pl.Schema(ff.SCHEMA)
    assert frame["settlement_date"][0] == date(2026, 6, 1)


def test_parse_zip_latin1():
    frame, _ = ff.parse_zip(_zip(TEXT.replace("AAR CORP", "CAF\xc9 CORP")))
    assert frame["description"][0] == "CAF\xc9 CORP"


def test_cutoff_and_available_date_pit_rule():
    # a-file: after the last calendar day of the month; b-file: after the 16th of next month
    assert ff.cutoff_date("202606", "a") == date(2026, 6, 30)
    assert ff.cutoff_date("202606", "b") == date(2026, 7, 16)
    assert ff.cutoff_date("202612", "b") == date(2027, 1, 16)
    days = [date(2026, 6, 29), date(2026, 6, 30), date(2026, 7, 1), date(2026, 7, 16)]
    days += [date(2026, 7, 17), date(2026, 7, 20)]
    assert ff.available_date("202606", "a", days) == date(2026, 7, 1)
    # strictly after the 16th (a session on the 16th itself is too early)
    assert ff.available_date("202606", "b", days) == date(2026, 7, 17)
    assert ff.available_date("202606", "b", days[:4]) is None
    # cutoff on a weekend rolls to the next session
    assert ff.available_date("202608", "a", [date(2026, 8, 28), date(2026, 9, 1)]) == date(
        2026, 9, 1
    )


def test_backoff_on_403_then_success_and_pacing():
    client, sleeps = _client(
        [FakeResp(403), FakeResp(429, headers={"Retry-After": "40"}), FakeResp(200, b"ok")]
    )
    resp = client.get("u")
    assert resp.status_code == 200
    assert client.backoff_total_s == 5.0 + 40.0
    assert 5.0 in sleeps and 40.0 in sleeps


def test_backoff_caps_and_gives_up():
    client, sleeps = _client([FakeResp(503)] * (ff.MAX_RETRIES + 1))
    with pytest.raises(ff.RateLimitedError):
        client.get("u")
    assert max(sleeps) == ff.BACKOFF_CAP_S
    assert sleeps[:3] == [5.0, 10.0, 20.0]


def test_404_returned_not_raised_and_other_status_raises():
    client, _ = _client([FakeResp(404)])
    assert client.get("u").status_code == 404
    client, _ = _client([FakeResp(418)])
    with pytest.raises(RuntimeError):
        client.get("u")


def test_run_resumes_and_records_404(tmp_path):
    good = _zip(TEXT)
    # first call: a-file ok, b-file 404
    client, _ = _client([FakeResp(200, good), FakeResp(404)])
    s1 = ff.run(client, tmp_path, (2026, 6), date(2026, 6, 30), log=lambda m: None)
    assert s1["fetched_now"] == 1
    assert s1["not_published_404"] == ["cnsfails202606b"]
    assert (tmp_path / "cnsfails202606a.parquet").exists()
    assert not (tmp_path / "cnsfails202606b.parquet").exists()
    # second call resumes: the a-file is not requested again, only the b-file
    client2, _ = _client([FakeResp(200, good)])
    s2 = ff.run(client2, tmp_path, (2026, 6), date(2026, 6, 30), log=lambda m: None)
    assert s2["already_present"] == 1 and s2["fetched_now"] == 1
    assert client2.session.urls == [ff.file_url("202606", "b")]
    back = pl.read_parquet(tmp_path / "cnsfails202606a.parquet")
    assert back.height == 4


def test_run_limit(tmp_path):
    client, _ = _client([FakeResp(200, _zip(TEXT))] * 5)
    s = ff.run(client, tmp_path, (2026, 1), date(2026, 3, 1), limit=2, log=lambda m: None)
    assert s["fetched_now"] == 2
