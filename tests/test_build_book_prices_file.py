"""T-20261002-41: post-close prices file from the local SIP archives (synthetic fixtures only)."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from open_composer.book_paper.post_close import tca
from scripts import build_book_prices_file as bp
from scripts import run_book_v12_daily as driver

NY = ZoneInfo("America/New_York")
EDT_DAY = date(2026, 9, 17)  # 15:45 ET = 19:45 UTC
EST_DAY = date(2026, 12, 1)  # 15:45 ET = 20:45 UTC (after the November change)


def et(day: date, hour: int, minute: int) -> datetime:
    return datetime(day.year, day.month, day.day, hour, minute, tzinfo=NY).astimezone(UTC)


def write_shard(path: Path, rows: list[tuple[str, datetime, float]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame = pd.DataFrame(rows, columns=["symbol", "timestamp", "close"])
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
    frame["open"] = frame["close"]
    frame.to_parquet(path, index=False)


def minute_rows(symbol: str, day: date, closes: dict[tuple[int, int], float]):
    return [(symbol, et(day, h, m), px) for (h, m), px in closes.items()]


def daily_rows(symbol: str, closes: dict[date, float]):
    # daily bars are labelled with midnight New York
    return [
        (symbol, datetime(d.year, d.month, d.day, tzinfo=NY).astimezone(UTC), px)
        for d, px in closes.items()
    ]


def make_sip(tmp_path: Path, day: date, *, daily: bool = True) -> Path:
    sip = tmp_path / "sip"
    month = f"{day.month:02d}"
    if daily:
        write_shard(
            sip / "daily" / str(day.year) / "shard-0000.parquet",
            daily_rows("AAA", {day - timedelta(days=1): 9.0, day: 10.0})
            + daily_rows("BBB", {day: 20.0}),
        )
    write_shard(
        sip / "minute" / str(day.year) / month / "shard-0000.parquet",
        # AAA: exact bars around the snapshot; the 15:45 bar must not be used
        minute_rows(
            "AAA",
            day,
            {(15, 43): 1.43, (15, 44): 1.44, (15, 45): 1.45, (15, 59): 1.59},
        )
        # BBB: last bar before the snapshot is 15:41 -> fallback
        + minute_rows("BBB", day, {(15, 40): 2.40, (15, 41): 2.41, (15, 50): 2.50}),
    )
    return sip


# ---------------------------------------------------------------------------
# snapshot bar choice
# ---------------------------------------------------------------------------
def test_snapshot_uses_the_1544_bar_in_edt(tmp_path):
    sip = make_sip(tmp_path, EDT_DAY)
    prices, fallback, _ = bp.snapshot_closes(sip, ["AAA"], EDT_DAY)
    assert prices == {"AAA": 1.44}  # bar labelled 15:44 ET (19:44 UTC), not the 15:45 bar
    assert "AAA" not in fallback
    assert bp.snapshot_time_utc(EDT_DAY) == datetime(2026, 9, 17, 19, 45, tzinfo=UTC)


def test_snapshot_uses_the_1544_bar_in_est(tmp_path):
    sip = tmp_path / "sip"
    rows = minute_rows("AAA", EST_DAY, {(15, 43): 1.43, (15, 44): 1.44, (15, 45): 1.45})
    # the same UTC wall time as the EDT snapshot (19:44 UTC = 14:44 ET) must be ignored
    rows.append(("AAA", datetime(2026, 12, 1, 19, 44, tzinfo=UTC), 9.99))
    write_shard(sip / "minute" / "2026" / "12" / "shard-0000.parquet", rows)
    prices, fallback, _ = bp.snapshot_closes(sip, ["AAA"], EST_DAY)
    assert prices == {"AAA": 1.44}
    assert fallback == {}
    assert bp.snapshot_time_utc(EST_DAY) == datetime(2026, 12, 1, 20, 45, tzinfo=UTC)


def test_fallback_to_an_earlier_bar_is_used_and_recorded(tmp_path):
    sip = make_sip(tmp_path, EDT_DAY)
    prices, fallback, _ = bp.snapshot_closes(sip, ["AAA", "BBB"], EDT_DAY)
    assert prices["BBB"] == 2.41  # 15:41 bar; the 15:50 bar is after the snapshot
    assert fallback == {"BBB": {"bar_label_et": "15:41", "bar_ends_minutes_before_1545": 3}}


def test_beyond_ten_minutes_the_name_is_missing(tmp_path):
    sip = tmp_path / "sip"
    day = EDT_DAY
    write_shard(
        sip / "minute" / "2026" / "09" / "shard-0000.parquet",
        # label 15:34 ends 15:35 = exactly 10 minutes before: allowed; 15:33 ends 15:34: too old
        minute_rows("EDGE", day, {(15, 34): 3.34})
        + minute_rows("OLD", day, {(15, 33): 4.33, (10, 0): 4.0}),
    )
    prices, fallback, _ = bp.snapshot_closes(sip, ["EDGE", "OLD"], day)
    assert prices == {"EDGE": 3.34}
    assert fallback["EDGE"]["bar_ends_minutes_before_1545"] == 10
    reasons = bp._missing_reasons(sip, "minute", ["OLD", "NONE"], day)
    assert "no minute bar in 15:34-15:44" in reasons["OLD"]
    assert reasons["NONE"] == "no minute bar on the date"


# ---------------------------------------------------------------------------
# official close, freshness, schema
# ---------------------------------------------------------------------------
def test_official_close_is_read_from_the_daily_archive(tmp_path):
    sip = make_sip(tmp_path, EDT_DAY)
    closes, files = bp.official_closes(sip, ["AAA", "BBB", "ZZZ"], EDT_DAY)
    assert closes == {"AAA": 10.0, "BBB": 20.0}  # day D only, not D-1 (9.0); ZZZ absent
    assert len(files) == 1
    est = tmp_path / "est"
    write_shard(
        est / "daily" / "2026" / "shard-0000.parquet", daily_rows("AAA", {EST_DAY: 5.5})
    )  # midnight ET is 05:00 UTC in winter
    assert bp.official_closes(est, ["AAA"], EST_DAY)[0] == {"AAA": 5.5}


def test_payload_fields_and_missing_reasons(tmp_path):
    sip = make_sip(tmp_path, EDT_DAY)
    now = datetime(2026, 9, 17, 22, 40, 5, tzinfo=UTC)
    payload = bp.build_prices(EDT_DAY, ["AAA", "BBB", "ZZZ"], sip_root=sip, now=now)
    assert payload["execution_date"] == "2026-09-17"
    assert payload["built_at_utc"] == "2026-09-17T22:40:05Z"
    assert payload["official_close"] == {"AAA": 10.0, "BBB": 20.0}
    assert payload["snapshot_1545"] == {"AAA": 1.44, "BBB": 2.41}
    assert payload["snapshot_fallback"].keys() == {"BBB"}
    assert payload["missing_official_close"] == ["ZZZ"]
    assert payload["missing_snapshot"] == ["ZZZ"]
    assert "not in archive" in payload["missing_reasons"]["official_close"]["ZZZ"]
    assert "adjustment=all" in payload["price_basis"]
    assert payload["sources"]["network"] == "none"
    assert payload["restated_after_execution_date"] == []


def test_restatement_after_the_date_is_flagged(tmp_path):
    sip = make_sip(tmp_path, EDT_DAY)
    lines = [
        {"detected_at": "2026-09-17T22:03:00+00:00", "symbol": "AAA"},  # evening of D: fine
        {"detected_at": "2026-09-25T22:03:00+00:00", "symbol": "BBB"},  # later: flagged
        {"detected_at": "not a time", "symbol": "AAA"},
    ]
    (sip / "daily" / "_restatements.jsonl").write_text("\n".join(json.dumps(x) for x in lines))
    assert bp.restated_after(sip, ["AAA", "BBB"], EDT_DAY) == ["BBB"]


def test_not_fresh_when_the_date_has_no_daily_bar(tmp_path, capsys):
    sip = make_sip(tmp_path, EDT_DAY)
    target = tmp_path / "t.json"
    target.write_text(json.dumps({"weights": {"AAA": 0.1}}))
    later = date(2026, 9, 18)
    with pytest.raises(bp.DataNotFresh):
        bp.build_prices(later, ["AAA"], sip_root=sip)
    out = tmp_path / "out.json"
    code = bp.main(
        [
            "--execution-date",
            later.isoformat(),
            "--symbols-from",
            str(target),
            "--sip-root",
            str(sip),
            "--out",
            str(out),
        ]
    )
    assert code == bp.EXIT_NOT_FRESH == 2
    assert not out.exists()
    assert "not fresh" in capsys.readouterr().out


def test_not_fresh_when_the_minute_archive_has_no_bar_of_the_date(tmp_path):
    sip = make_sip(tmp_path, EDT_DAY)
    write_shard(
        sip / "daily" / "2026" / "shard-0001.parquet", daily_rows("AAA", {date(2026, 9, 18): 11.0})
    )
    with pytest.raises(bp.DataNotFresh, match="minute"):
        bp.build_prices(date(2026, 9, 18), ["AAA"], sip_root=sip)
    payload = bp.build_prices(date(2026, 9, 18), ["AAA"], sip_root=sip, require_minute=False)
    assert payload["missing_snapshot"] == ["AAA"]


def test_schema_is_what_reconcile_reads(tmp_path):
    sip = make_sip(tmp_path, EDT_DAY)
    out = tmp_path / "prices" / "2026-09-17.json"
    target = tmp_path / "t.json"
    target.write_text(json.dumps({"weights": {"AAA": 0.1, "BBB": -0.1}}))
    path, _ = bp.build_and_write(EDT_DAY, root=tmp_path, inputs=[target], sip_root=sip, out=out)
    prices = json.loads(path.read_text())
    # cli.reconcile reads prices["official_close"] and prices.get("snapshot_1545", {}): both
    # symbol -> positive float maps usable by post_close.tca / realized_exposures
    for key in ("official_close", "snapshot_1545"):
        assert prices[key] and all(isinstance(v, float) and v > 0 for v in prices[key].values())
    fills = [
        {"symbol": "AAA", "side": "buy", "filled_qty": 10.0, "filled_avg_price": 10.01},
        {"symbol": "BBB", "side": "sell", "filled_qty": 5.0, "filled_avg_price": 19.99},
    ]
    result = tca(fills, prices["official_close"], prices["snapshot_1545"])
    assert result["n_with_reference_vs_official_close_bp"] == 2
    assert result["fills"][0]["vs_official_close_bp"] == pytest.approx(10.0)
    assert result["n_with_reference_vs_snapshot_1545_bp"] == 2


# ---------------------------------------------------------------------------
# symbols
# ---------------------------------------------------------------------------
def write_inputs(root: Path, day: date, decision: date, account: str = "quant1") -> list[Path]:
    base = root / "reports" / "paper" / "book" / account
    target = base / "targets" / f"{decision.isoformat()}.json"
    plan = base / "plans" / f"{day.isoformat()}.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    plan.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(
            {
                "weights": {"AAA": 0.05, "BBB": -0.05, "SGOV": 0.9},
                "reference_prices": {"UNIVERSEONLY": 1.0, "AAA": 9.0},
                "exposures": {"UNIVERSEONLY": {}},
                "core_symbol": "SGOV",
                "hedge_symbol": "SPY",
            }
        )
    )
    plan.write_text(
        json.dumps(
            {
                "decision_date": decision.isoformat(),
                "orders": [{"symbol": "OLDPOS", "side": "sell"}, {"symbol": "AAA", "side": "buy"}],
                "post_trade_qty": {"AAA": 5, "KEPT": 3},
            }
        )
    )
    return [plan, target]


def test_symbol_union_from_plan_and_target_files(tmp_path):
    q1 = write_inputs(tmp_path, EDT_DAY, date(2026, 9, 16), "quant1")
    q2 = write_inputs(tmp_path, EDT_DAY, date(2026, 9, 16), "quant2")
    symbols, origin = bp.collect_symbols([*q1, *q2])
    assert symbols == ["AAA", "BBB", "KEPT", "OLDPOS", "SGOV", "SPY"]
    assert "UNIVERSEONLY" not in symbols  # reference prices alone do not add a name
    assert any(o.startswith("plan_orders:") for o in origin["OLDPOS"])
    assert any(o.startswith("target_weights:") for o in origin["BBB"])
    assert bp.discover_inputs(tmp_path, EDT_DAY) == [*q1, *q2]
    with pytest.raises(bp.InputsError):
        bp.collect_symbols([])
    empty = tmp_path / "empty.json"
    empty.write_text("{}")
    with pytest.raises(bp.InputsError):
        bp.collect_symbols([empty])
    assert bp.main(["--execution-date", "2026-09-17", "--symbols-from", str(empty)]) == 3


# ---------------------------------------------------------------------------
# driver --reconcile
# ---------------------------------------------------------------------------
def driver_args(tmp_path: Path, sip: Path) -> list[str]:
    return [
        "--reconcile",
        "--execution-date",
        "2026-09-17",
        "--root",
        str(tmp_path),
        "--sip-root",
        str(sip),
        "--lock-file",
        str(tmp_path / "l"),
        "--log-file",
        str(tmp_path / "x.log"),
    ]


def test_driver_reconcile_builds_the_prices_file_then_reconciles(tmp_path, monkeypatch):
    sip = make_sip(tmp_path, EDT_DAY)
    write_inputs(tmp_path, EDT_DAY, date(2026, 9, 16), "quant1")
    write_inputs(tmp_path, EDT_DAY, date(2026, 9, 16), "quant2")
    prices_file = tmp_path / "reports/paper/book/prices/2026-09-17.json"
    calls: list[list[str]] = []

    def fake_runner(cmd, **kwargs):
        assert prices_file.is_file()  # the builder ran before any reconcile command
        calls.append(list(cmd))
        return SimpleNamespace(returncode=0, stdout="filled=1", stderr="")

    monkeypatch.setattr(driver.subprocess, "run", fake_runner)
    assert driver.main(driver_args(tmp_path, sip)) == 0
    assert [c[c.index("--account") + 1] for c in calls] == ["quant1", "quant2"]
    for cmd in calls:
        assert cmd[-4:-2] == ["--date", "2026-09-17"]
        assert cmd[-2:] == ["--prices-file", str(prices_file)]
        assert "reconcile" in cmd and "book-paper" in cmd
    payload = json.loads(prices_file.read_text())
    assert payload["official_close"]["AAA"] == 10.0
    assert "OLDPOS" in payload["missing_official_close"]  # a name the archive does not hold


def test_driver_reconcile_only_the_named_accounts(tmp_path, monkeypatch):
    # from 10-07 (C1006-ACCT) quant2 has no v1.2 plan; the crons pass --accounts quant1
    sip = make_sip(tmp_path, EDT_DAY)
    write_inputs(tmp_path, EDT_DAY, date(2026, 9, 16), "quant1")
    calls: list[list[str]] = []
    monkeypatch.setattr(
        driver.subprocess,
        "run",
        lambda cmd, **kw: (
            calls.append(list(cmd)) or SimpleNamespace(returncode=0, stdout="", stderr="")
        ),
    )
    assert driver.main(driver_args(tmp_path, sip)) == driver.EXIT_REFUSED  # no quant2 plan
    assert calls == []
    assert driver.main([*driver_args(tmp_path, sip), "--accounts", "quant1"]) == 0
    assert [c[c.index("--account") + 1] for c in calls] == ["quant1"]


def test_driver_reconcile_exit_codes(tmp_path, monkeypatch):
    sip = make_sip(tmp_path, EDT_DAY)
    called: list[list[str]] = []
    monkeypatch.setattr(
        driver.subprocess,
        "run",
        lambda cmd, **kw: (
            called.append(list(cmd)) or SimpleNamespace(returncode=1, stdout="", stderr="")
        ),
    )
    # no plan files -> refused
    assert driver.main(driver_args(tmp_path, sip)) == driver.EXIT_REFUSED == 3
    write_inputs(tmp_path, EDT_DAY, date(2026, 9, 16), "quant1")
    write_inputs(tmp_path, EDT_DAY, date(2026, 9, 16), "quant2")
    # the reconcile command fails -> 5
    assert driver.main(driver_args(tmp_path, sip)) == driver.EXIT_COMMAND == 5
    assert len(called) == 1
    # archive without the date -> 2 and no command
    called.clear()
    stale = tmp_path / "stale-sip"
    write_shard(
        stale / "daily" / "2026" / "shard-0000.parquet", daily_rows("AAA", {date(2026, 9, 1): 1.0})
    )
    assert driver.main(driver_args(tmp_path, stale)) == driver.EXIT_FRESH == 2
    assert called == []
    # existing daily records -> nothing to do
    for account in ("quant1", "quant2"):
        record = tmp_path / "reports/paper/book" / account / "daily" / "2026-09-17.json"
        record.parent.mkdir(parents=True, exist_ok=True)
        record.write_text("{}")
    assert driver.main(driver_args(tmp_path, sip)) == 0
    assert called == []
