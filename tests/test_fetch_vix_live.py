from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import fetch_vix_live as fv  # noqa: E402

DAYS = pd.bdate_range("2025-01-02", periods=300)


def _fred(days: pd.DatetimeIndex, values: list[float]) -> str:
    rows = "\n".join(f"{d:%Y-%m-%d},{v:.2f}" for d, v in zip(days, values, strict=True))
    return "observation_date,VIXCLS\n" + rows + "\n"


def _cboe(days: pd.DatetimeIndex, values: list[float]) -> str:
    rows = "\n".join(
        f"{d:%m/%d/%Y},{v:.6f},{v:.6f},{v:.6f},{v:.6f}" for d, v in zip(days, values, strict=True)
    )
    return "DATE,OPEN,HIGH,LOW,CLOSE\n" + rows + "\n"


def _getter(fred: str, cboe: str):
    return lambda url: fred if url == fv.FRED_URL else cboe


def test_appends_cboe_days_after_fred(tmp_path: Path) -> None:
    vals = [15.0 + (i % 7) for i in range(len(DAYS))]
    rc = fv.run(tmp_path, _getter(_fred(DAYS[:-2], vals[:-2]), _cboe(DAYS, vals)))
    assert rc == fv.EXIT_OK
    out = pd.read_csv(tmp_path / "VIXCLS.csv")
    assert len(out) == len(DAYS)
    assert out["observation_date"].iloc[-1] == f"{DAYS[-1]:%Y-%m-%d}"
    assert out["VIXCLS"].iloc[-1] == vals[-1]


def test_overlap_mismatch_keeps_old_file(tmp_path: Path) -> None:
    (tmp_path / "VIXCLS.csv").write_text("observation_date,VIXCLS\n2025-01-02,15.0\n")
    vals = [15.0] * len(DAYS)
    bad = list(vals)
    bad[10] = 16.0
    rc = fv.run(tmp_path, _getter(_fred(DAYS, vals), _cboe(DAYS, bad)))
    assert rc == fv.EXIT_CHECK
    assert (tmp_path / "VIXCLS.csv").read_text().count("\n") == 2


def test_fetch_error_returns_2(tmp_path: Path) -> None:
    def boom(url: str) -> str:
        raise OSError("network down")

    assert fv.run(tmp_path, boom) == fv.EXIT_FETCH
    assert not (tmp_path / "VIXCLS.csv").exists()


def test_fred_missing_marker_dropped() -> None:
    s = fv.parse_fred("observation_date,VIXCLS\n2025-01-02,15.0\n2025-01-03,.\n")
    assert list(s.index.strftime("%Y-%m-%d")) == ["2025-01-02"]
