"""Tests for the pure parts of scripts/forward_record_t70.py (T-20261004-70)."""

from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import forward_record_t70 as m  # noqa: E402


def _series(vals: list[float], start: str = "2026-09-01") -> pd.Series:
    return pd.Series(vals, index=pd.bdate_range(start, periods=len(vals)))


def test_seg_stats_basic() -> None:
    r = _series([0.01, -0.02, 0.03])
    st = m.seg_stats(r)
    assert st["days"] == 3
    assert math.isclose(st["cum_return"], 1.01 * 0.98 * 1.03 - 1.0)
    assert math.isclose(st["ann_vol"], float(r.std(ddof=1)) * math.sqrt(252.0))
    # drawdown: peak 1.01 then 0.9898
    assert math.isclose(st["max_dd"], 0.98 - 1.0)
    assert st["sharpe_meaningful"] is False


def test_seg_stats_one_day_and_empty() -> None:
    one = m.seg_stats(_series([-0.01]))
    assert one["days"] == 1
    assert one["sharpe"] is None
    assert one["ann_vol"] is None
    assert math.isclose(one["max_dd"], -0.01)  # drawdown from the starting NAV of 1.0
    gain = m.seg_stats(_series([0.02]))
    assert gain["max_dd"] == 0.0
    empty = m.seg_stats(_series([]))
    assert empty["days"] == 0 and empty["cum_return"] is None


def test_seg_stats_sharpe_uses_excess_over_rf() -> None:
    r = _series([0.01, 0.02, 0.0, 0.01])
    rf = pd.Series(0.01, index=r.index)
    ex = r - rf
    expected = float(ex.mean() / ex.std(ddof=1) * math.sqrt(252.0))
    assert math.isclose(m.seg_stats(r, rf)["sharpe"], expected)


def test_forward_z_formula() -> None:
    rng = np.random.default_rng(1)
    base = pd.Series(rng.normal(0.001, 0.01, 500))
    fwd = pd.Series([0.003] * 25)
    z = m.forward_z(fwd, base)
    sd = float(base.std(ddof=1))
    assert math.isclose(z["z"], (0.003 - float(base.mean())) / (sd / 5.0))
    assert z["n_forward"] == 25
    assert m.forward_z(pd.Series([], dtype=float), base)["z"] is None


def test_tracking_stats_worst3() -> None:
    d = _series([0.001, -0.02, 0.0, -0.01, -0.03, 0.002])
    t = m.tracking_stats(d)
    assert t["days"] == 6
    assert [w["diff"] for w in t["worst3"]] == [-0.03, -0.02, -0.01]
    assert math.isclose(t["mean"], float(d.mean()))


def test_split_segments_with_and_without_paper() -> None:
    idx = pd.bdate_range("2026-08-28", "2026-10-02")
    seg = m.split_segments(idx, "2026-09-01", "2026-09-17", "2026-09-21")
    assert seg["design_seen"][0] == pd.Timestamp("2026-09-01")
    assert seg["design_seen"][-1] == pd.Timestamp("2026-09-17")
    assert list(seg["oos_shadow"]) == [pd.Timestamp("2026-09-18")]
    assert seg["paper"][0] == pd.Timestamp("2026-09-21")
    assert seg["paper"][-1] == pd.Timestamp("2026-10-02")
    nop = m.split_segments(idx, "2026-09-01", "2026-09-17", None)
    assert len(nop["paper"]) == 0
    assert nop["oos_shadow"][0] == pd.Timestamp("2026-09-18")
    assert nop["oos_shadow"][-1] == pd.Timestamp("2026-10-02")


def test_last_seen_session_respects_close_time() -> None:
    idx = pd.bdate_range("2026-09-14", "2026-09-22")
    # committed 13:49 UTC on 09-18: the 09-18 close (20:00 UTC) is not yet seen
    assert m.last_seen_session(idx, "2026-09-18 13:49:34") == "2026-09-17"
    # committed after the close
    assert m.last_seen_session(idx, "2026-09-18 21:00:00") == "2026-09-18"
    # committed on a weekend: Friday is the last seen session
    assert m.last_seen_session(idx, "2026-09-20 10:00:00") == "2026-09-18"


def _entries() -> list[dict]:
    return [
        {"date": "2026-09-18", "candidate": "S1", "path": "a.json", "sha256": "11" * 32},
        {"date": "2026-09-18", "candidate": "S2", "path": "b.json", "sha256": "22" * 32},
        {"date": "2026-09-21", "candidate": "S1", "path": "c.json", "sha256": "33" * 32},
    ]


def test_chain_links_and_verifies() -> None:
    rows = m.build_chain(_entries())
    assert rows[0]["prev_hash"] == m.GENESIS
    assert rows[1]["prev_hash"] == rows[0]["chain_hash"]
    assert rows[2]["prev_hash"] == rows[1]["chain_hash"]
    assert m.verify_chain(rows) == (True, None)


def test_chain_detects_tampering() -> None:
    rows = m.build_chain(_entries())
    rows[1]["sha256"] = "ff" * 32
    ok, bad = m.verify_chain(rows)
    assert ok is False and bad == 1
    rows = m.build_chain(_entries())
    rows[2]["prev_hash"] = "0" * 64
    assert m.verify_chain(rows) == (False, 2)


def test_file_sha256(tmp_path: Path) -> None:
    f = tmp_path / "x.txt"
    f.write_bytes(b"abc")
    assert m.file_sha256(f) == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
