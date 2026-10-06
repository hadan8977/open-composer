"""Tests for scripts/fetch_dolthub_options.py using fake API responses (no network)."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pandas as pd
import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "fetch_dolthub_options.py"
spec = importlib.util.spec_from_file_location("fetch_dolthub_options", SCRIPT)
assert spec and spec.loader
fdo = importlib.util.module_from_spec(spec)
sys.modules["fetch_dolthub_options"] = fdo
spec.loader.exec_module(fdo)


def ok(rows: list[dict[str, str]]) -> tuple[int, str]:
    return 200, json.dumps({"query_execution_status": "Success", "rows": rows})


class Script:
    """Fake opener that replays a scripted list of responses and records URLs."""

    def __init__(self, responses: list) -> None:
        self.responses = list(responses)
        self.urls: list[str] = []

    def __call__(self, url: str, timeout: float) -> tuple[int, str]:
        self.urls.append(url)
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def make_client(responses: list) -> tuple[object, Script, list[float]]:
    script = Script(responses)
    sleeps: list[float] = []
    client = fdo.Client(opener=script, sleep=sleeps.append, log=lambda m: None)
    return client, script, sleeps


def test_backoff_on_429_and_5xx_then_success() -> None:
    client, script, sleeps = make_client(
        [(429, "slow down"), (503, "busy"), TimeoutError("t"), ok([{"a": "1"}])]
    )
    rows = client.query("SELECT 1")
    assert rows == [{"a": "1"}]
    assert client.retries == 3
    assert sleeps == [5.0, 10.0, 20.0]  # exponential
    assert client.statuses == {"429": 1, "503": 1, "0": 1, "200": 1}
    assert len(script.urls) == 4


def test_backoff_is_capped_and_gives_up() -> None:
    client, _, sleeps = make_client([(500, "x")] * 4)
    client.max_retries = 3
    client.base_delay = 100.0
    client.max_delay = 250.0
    with pytest.raises(fdo.ApiError):
        client.query("SELECT 1")
    assert sleeps == [100.0, 200.0, 250.0]


def test_client_error_is_not_retried() -> None:
    client, script, _ = make_client([(400, "bad sql")])
    with pytest.raises(fdo.ApiError):
        client.query("SELECT")
    assert len(script.urls) == 1


def test_upstream_503_reported_as_http_400_is_retried() -> None:
    body = json.dumps(
        {"query_execution_status": "Error", "query_execution_message": "Received status code 503"}
    )
    client, _, _ = make_client([(400, body), ok([{"x": "1"}])])
    assert client.query("SELECT 1") == [{"x": "1"}]
    assert client.retries == 1


def test_failed_execution_status_is_retried() -> None:
    running = (200, json.dumps({"query_execution_status": "Running", "rows": []}))
    client, _, _ = make_client([running, ok([{"x": "1"}])])
    assert client.query("SELECT 1") == [{"x": "1"}]
    assert client.retries == 1


def test_pagination_offsets_until_short_page() -> None:
    full = [{"i": str(i)} for i in range(fdo.PAGE_LIMIT)]
    client, script, _ = make_client([ok(full), ok(full), ok([{"i": "last"}])])
    rows = client.paged("SELECT i FROM t", "i")
    assert len(rows) == 2 * fdo.PAGE_LIMIT + 1
    assert "OFFSET+0" in script.urls[0] or "OFFSET%200" in script.urls[0]
    assert "OFFSET%201000" in script.urls[1] or "OFFSET+1000" in script.urls[1]
    assert "OFFSET%202000" in script.urls[2] or "OFFSET+2000" in script.urls[2]
    assert "ORDER+BY+i" in script.urls[0] or "ORDER%20BY%20i" in script.urls[0]


def test_pagination_exact_multiple_needs_empty_final_page() -> None:
    full = [{"i": str(i)} for i in range(fdo.PAGE_LIMIT)]
    client, script, _ = make_client([ok(full), ok([])])
    assert len(client.paged("SELECT i FROM t", "i")) == fdo.PAGE_LIMIT
    assert len(script.urls) == 2


def test_symbol_validation_blocks_injection() -> None:
    with pytest.raises(ValueError):
        fdo.check_symbol("SPY'; DROP TABLE x;--")
    with pytest.raises(ValueError):
        fdo.chain_sql(["SPY"], "2024-01-01' OR '1'='1")
    with pytest.raises(ValueError):
        fdo.agg_sql(["SPY"], [])
    assert "act_symbol IN ('SPY', 'QQQ')" in fdo.chain_sql(["SPY", "QQQ"], "2024-06-14")


def test_agg_sql_uses_date_in_list_prefix() -> None:
    sql = fdo.agg_sql(["SPY"], ["2024-06-13", "2024-06-14"])
    assert "date IN ('2024-06-13', '2024-06-14')" in sql
    assert "GROUP BY date, act_symbol" in sql
    assert "date >=" not in sql  # a range scan would 504


def test_shuffle_is_deterministic_and_prefix_is_a_sample() -> None:
    days = [f"2024-01-{d:02d}" for d in range(1, 29)]
    a = fdo.shuffled_days("SPY", days)
    assert a == fdo.shuffled_days("SPY", list(reversed(days)))
    assert sorted(a) == days and a != days
    assert fdo.shuffled_days("QQQ", days) != a


def test_interleave_round_robin() -> None:
    out = list(fdo.interleave([[("A", "1"), ("A", "2")], [("B", "1")], [("C", "1"), ("C", "2")]]))
    assert out == [("A", "1"), ("B", "1"), ("C", "1"), ("A", "2"), ("C", "2")]


def test_checkpoint_periodic_flush_and_resume(tmp_path: Path) -> None:
    cp = fdo.Checkpoint.load(tmp_path / "cp.json", every=3)
    cp.mark("chain", "SPY:2024-01-02")
    assert [cp.tick() for _ in range(3)] == [False, False, True]
    cp.flush()
    reloaded = fdo.Checkpoint.load(tmp_path / "cp.json", every=3)
    assert reloaded.is_done("chain", "SPY:2024-01-02")
    assert not reloaded.is_done("chain", "SPY:2024-01-03")
    assert reloaded.request_count == 3


def test_agg_job_batches_dates_writes_parquet_and_resumes(tmp_path: Path) -> None:
    row = {"date": "2024-06-14", "act_symbol": "SPY", "n_rows": "126", "n_exp": "3"}
    client, script, _ = make_client([ok([row]), ok([row])])
    cp = fdo.Checkpoint.load(tmp_path / "cp.json", every=200)
    days = ["2024-06-13", "2024-06-14", "2024-06-17"]
    fdo.Runner(client, cp, tmp_path).job_agg(["SPY"], days, batch_dates=2)
    assert len(script.urls) == 2  # 3 dates in batches of 2
    frame = pd.read_parquet(tmp_path / "agg" / "agg_2024-06-13_2d.parquet")
    assert int(frame["n_rows"].iloc[0]) == 126 and frame["act_symbol"].iloc[0] == "SPY"
    cp2 = fdo.Checkpoint.load(tmp_path / "cp.json", every=200)
    fdo.Runner(client, cp2, tmp_path).job_agg(["SPY"], days, batch_dates=2)
    assert len(script.urls) == 2  # resume requested nothing


def test_chain_job_samples_known_days_and_checkpoints(tmp_path: Path) -> None:
    agg = pd.DataFrame({"date": ["2024-06-13", "2024-06-14", "2024-06-17"]})
    (tmp_path / "agg").mkdir()
    agg.to_parquet(tmp_path / "agg" / "agg_2024-06-13_3d.parquet", index=False)
    pd.DataFrame().to_parquet(tmp_path / "agg" / "agg_2019-07-05_100d.parquet", index=False)
    chain_row = {
        "date": "2024-06-14",
        "act_symbol": "SPY",
        "expiration": "2024-06-28",
        "strike": "540.00",
        "call_put": "Call",
        "bid": "1.0",
        "ask": "1.1",
        "vol": "0.12",
        "delta": "0.5",
    }
    client, script, _ = make_client([ok([chain_row]), ok([chain_row])])
    cp = fdo.Checkpoint.load(tmp_path / "cp.json", every=200)
    fdo.Runner(client, cp, tmp_path).job_chain(["SPY"], max_units=2, flush_units=1)
    assert len(script.urls) == 2
    assert len(list((tmp_path / "option_chain").glob("part_*.parquet"))) == 2
    done = json.loads((tmp_path / "cp.json").read_text())["done"]["chain"]
    assert len(done) == 2
    client2, script2, _ = make_client([ok([chain_row])])
    cp2 = fdo.Checkpoint.load(tmp_path / "cp.json", every=200)
    fdo.Runner(client2, cp2, tmp_path).job_chain(["SPY"], max_units=None, flush_units=10)
    assert len(script2.urls) == 1  # only the remaining day
    assert len(json.loads((tmp_path / "cp.json").read_text())["done"]["chain"]) == 3


def test_volhist_weekdays_only_skips_weekend_cells_and_includes_end(tmp_path: Path) -> None:
    from datetime import date

    row = {"date": "2024-06-14", "act_symbol": "SPY", "iv_current": "0.2"}
    client, script, _ = make_client([ok([row])] * 10)
    cp = fdo.Checkpoint.load(tmp_path / "cp.json", every=200)
    # Fri 2024-06-14 .. Tue 2024-06-18: Fri, Mon, Tue fetched; Sat, Sun skipped
    fdo.Runner(client, cp, tmp_path).job_volhist(
        None, date(2024, 6, 14), date(2024, 6, 18), 1, weekdays_only=True
    )
    assert len(script.urls) == 3
    names = sorted(p.name for p in (tmp_path / "volatility_history").glob("all_*.parquet"))
    assert names == ["all_2024-06-14.parquet", "all_2024-06-17.parquet", "all_2024-06-18.parquet"]
    client2, script2, _ = make_client([ok([row])] * 10)
    cp2 = fdo.Checkpoint.load(tmp_path / "cp2.json", every=200)
    fdo.Runner(client2, cp2, tmp_path / "other").job_volhist(
        None, date(2024, 6, 14), date(2024, 6, 16), 1
    )
    assert len(script2.urls) == 3  # default keeps weekends


def test_volhist_workers_fetch_all_windows_and_resume(tmp_path: Path) -> None:
    import threading
    from datetime import date

    lock = threading.Lock()
    urls: list[str] = []

    def opener(url: str, timeout: float) -> tuple[int, str]:
        with lock:
            urls.append(url)
        return ok([{"date": "2024-06-14", "act_symbol": "SPY", "iv_current": "0.2"}])

    def build() -> tuple[object, object]:
        client = fdo.Client(opener=opener, sleep=lambda s: None, log=lambda m: None)
        return client, fdo.Checkpoint.load(tmp_path / "cp.json", every=200)

    client, cp = build()
    fdo.Runner(client, cp, tmp_path).job_volhist(
        None, date(2024, 6, 10), date(2024, 6, 16), 1, weekdays_only=True, workers=3
    )
    assert len(urls) == 5  # Mon..Fri, weekend cells skipped
    assert cp.request_count == 5 and client.requests_made == 5
    assert len(list((tmp_path / "volatility_history").glob("all_*.parquet"))) == 5
    client2, cp2 = build()
    fdo.Runner(client2, cp2, tmp_path).job_volhist(
        None, date(2024, 6, 10), date(2024, 6, 16), 1, weekdays_only=True, workers=3
    )
    assert len(urls) == 5  # everything already in the checkpoint


def test_main_passes_workers_and_newest_first(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    seen: dict[str, object] = {}

    def fake(self, symbols, start, end, window, weekdays_only=False, workers=1, newest_first=False):
        seen.update(workers=workers, newest_first=newest_first, weekdays_only=weekdays_only)

    monkeypatch.setattr(fdo.Runner, "job_volhist", fake)
    code = fdo.main(
        [
            "--jobs", "volhist", "--volhist-all", "--volhist-window-days", "1",
            "--weekdays-only", "--workers", "4", "--newest-first",
            "--start", "2024-06-10", "--end", "2024-06-12", "--cache", str(tmp_path),
        ]
    )  # fmt: skip
    assert code == 0
    assert seen == {"workers": 4, "newest_first": True, "weekdays_only": True}
