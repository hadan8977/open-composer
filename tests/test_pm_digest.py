"""Tests for scripts/pm_digest.py (T-20261002-45) on synthetic snapshots; no network."""

from __future__ import annotations

import importlib.util
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


digest = _load("pm_digest")
shadow = sys.modules["pm_release_shadow"]
NOW = datetime(2026, 10, 2, 14, 0, tzinfo=UTC)
STRIKES = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6]
PRICES = [0.95, 0.80, 0.55, 0.20, 0.05, 0.01]


def poly_frame(stamp: str, price_a: float, price_b: float) -> pd.DataFrame:
    rows = []
    for market_id, group, price in (("1", "fed_oct", price_a), ("2", "recession", price_b)):
        rows.append(
            {
                "fetched_at_utc": stamp,
                "market_id": market_id,
                "question": f"Question {market_id}?",
                "watch_group": group,
                "yes_price": price,
                "volume": 2_500_000.0,
                "volume_24h": 40_000.0,
                "closed": False,
            }
        )
    return pd.DataFrame(rows)


def kalshi_frame(close: str = "2026-10-14T12:25:00Z") -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "fetched_at_utc": "2026-10-02T13:00:00+00:00",
                "series_ticker": "KXCPI",
                "event_ticker": "KXCPI-26SEP",
                "market_ticker": f"KXCPI-26SEP-T{k}",
                "strike_type": "greater",
                "floor_strike": k,
                "yes_bid": p - 0.01,
                "yes_ask": p + 0.01,
                "last_price": p,
                "close_time": close,
            }
            for k, p in zip(STRIKES, PRICES, strict=True)
        ]
    )


def write(root: Path, kind: str, day: str, hms: str, frame: pd.DataFrame) -> None:
    folder = root / kind / f"date={day}"
    folder.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(folder / f"part-{hms}.parquet", index=False)


@pytest.fixture
def history(tmp_path, monkeypatch):
    rows = [
        {
            "series": "KXCPI",
            "release_date": pd.Timestamp("2026-01-01") + pd.Timedelta(days=30 * i),
            "event_ticker": f"KXCPI-OLD{i}",
            "U": 0.1,
        }
        for i in range(10)
    ]
    path = tmp_path / "ru.parquet"
    pd.DataFrame(rows).to_parquet(path)
    monkeypatch.setattr(shadow, "RELEASE_UNCERTAINTY", path)


def build(root: Path, watchlist: Path | None = None):
    return digest.build_digest(
        root, now=NOW, shadow_dir=root / "h1_shadow", watchlist_path=watchlist or root / "none.yaml"
    )


def test_list_snapshots_and_nearest(tmp_path):
    for day, hms in (("2026-09-25", "130000"), ("2026-10-01", "130500"), ("2026-10-02", "130000")):
        write(tmp_path, "polymarket_hourly", day, hms, poly_frame("x", 0.5, 0.1))
    snaps = digest.list_snapshots(tmp_path / "polymarket_hourly")
    assert [s[0].isoformat() for s in snaps][-1] == "2026-10-02T13:00:00+00:00"
    latest = snaps[-1][0]
    hit = digest.nearest(snaps, latest - digest.HORIZONS[0][1], digest.HORIZONS[0][2], latest)
    assert hit and hit[0].isoformat() == "2026-10-01T13:05:00+00:00"
    assert (
        digest.nearest(snaps, latest - digest.HORIZONS[0][1], digest.timedelta(minutes=1), latest)
        is None
    )


def test_digest_shows_changes_versus_24h_and_7d(tmp_path, history):
    write(tmp_path, "polymarket_hourly", "2026-09-25", "130000", poly_frame("a", 0.50, 0.05))
    write(tmp_path, "polymarket_hourly", "2026-10-01", "130000", poly_frame("b", 0.80, 0.07))
    write(tmp_path, "polymarket_hourly", "2026-10-02", "130000", poly_frame("c", 0.835, 0.075))
    write(tmp_path, "kalshi_hourly", "2026-10-02", "130000", kalshi_frame())
    text, summary = build(tmp_path)
    assert text.splitlines()[1].startswith("仅供研究与决策参考")
    assert "83.5% (24h +3.5pp, 7d +33.5pp; 总量 $2.5M, 24h $40k)" in text
    assert "7.5% (24h +0.5pp, 7d +2.5pp" in text
    assert summary["warnings"] == [] and summary["polymarket_markets"] == 2
    assert len(text.splitlines()) <= 40


def test_missing_history_is_na_not_an_error(tmp_path, history):
    write(tmp_path, "polymarket_hourly", "2026-10-02", "130000", poly_frame("c", 0.5, 0.1))
    write(tmp_path, "kalshi_hourly", "2026-10-02", "130000", kalshi_frame())
    text, _ = build(tmp_path)
    assert "24h n/a, 7d n/a" in text


def test_kalshi_section_has_implied_moments_and_u_rel(tmp_path, history):
    write(tmp_path, "polymarket_hourly", "2026-10-02", "130000", poly_frame("c", 0.5, 0.1))
    write(tmp_path, "kalshi_hourly", "2026-10-02", "130000", kalshi_frame())
    text, summary = build(tmp_path)
    (item,) = summary["kalshi_upcoming"]
    assert item["event"] == "KXCPI-26SEP" and item["release_date"] == "2026-10-14"
    assert item["std"] > 0 and item["U_rel"] == pytest.approx(item["std"] / 0.1, rel=1e-3)
    assert "KXCPI-26SEP: 隐含均值" in text and "U_rel" in text


def test_events_beyond_ten_sessions_are_left_out(tmp_path, history):
    write(tmp_path, "polymarket_hourly", "2026-10-02", "130000", poly_frame("c", 0.5, 0.1))
    write(tmp_path, "kalshi_hourly", "2026-10-02", "130000", kalshi_frame("2026-11-10T13:25:00Z"))
    text, summary = build(tmp_path)
    assert summary["kalshi_upcoming"] == [] and "窗口内没有已开盘的宏观事件" in text


def test_stale_and_missing_snapshots_are_reported_on_top(tmp_path, history):
    write(tmp_path, "polymarket_hourly", "2026-10-02", "090000", poly_frame("c", 0.5, 0.1))
    text, summary = build(tmp_path)  # Kalshi missing, Polymarket 5 hours old
    top = "\n".join(text.splitlines()[:5])
    assert "Kalshi 没有任何快照" in top and "Polymarket 最新快照是 5.0 小时前" in top
    assert len(summary["warnings"]) == 2


def test_shadow_line_shows_latest_day(tmp_path, history):
    write(tmp_path, "polymarket_hourly", "2026-10-02", "130000", poly_frame("c", 0.5, 0.1))
    write(tmp_path, "kalshi_hourly", "2026-10-02", "130000", kalshi_frame())
    folder = tmp_path / "h1_shadow"
    folder.mkdir()
    day = {
        "record_type": "day",
        "release_date": "2026-09-11",
        "day_U_rel": 1.234,
        "would_hold": True,
        "fomc_day": False,
    }
    (folder / "signals.jsonl").write_text(json.dumps(day) + "\n")
    text, _ = build(tmp_path)
    assert "发布日 2026-09-11，day_U_rel 1.23，would_hold=True" in text
    assert "累计非FOMC发布日 1/60" in text


def test_main_writes_the_dated_file(tmp_path, history, capsys):
    write(tmp_path, "polymarket_hourly", "2026-10-02", "130000", poly_frame("c", 0.5, 0.1))
    write(tmp_path, "kalshi_hourly", "2026-10-02", "130000", kalshi_frame())
    assert digest.main(["--out-root", str(tmp_path), "--now", "2026-10-02T14:00:00Z"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert Path(out["file"]).name == "2026-10-02.md" and Path(out["file"]).exists()
