"""Tests for the 2026-09-18 ``--universe-root``/``--out-dir``/
``--extra-daily-root`` CLI additions to the four open-factor-library
builders (job 1 of the broad-universe factor rerun,
``scripts/build_{alpha158,alpha101_alpha191,osap_price,reversal_trend}_
features.py``). Each test builds tiny synthetic OHLCV parquet files under
two separate "archive roots" (a primary root standing in for
``data/sip/daily`` and an "extra" root standing in for
``data/sip-delisted/by_year``) plus a tiny universe panel, monkeypatches
each builder module's ``DAILY_ROOT`` constant (the one root the CLI
intentionally does not parameterize -- these scripts scan the real
archive, never a caller-supplied one) to the primary root, and asserts the
new CLI flags route input/output through the tmp paths -- in particular
that a symbol which exists *only* under ``--extra-daily-root`` still
appears in the output, since that is the entire point of the delisted-
backfill argument.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

from scripts import build_alpha101_alpha191_features as ba101
from scripts import build_alpha158_features as ba158
from scripts import build_osap_price_features as bosap
from scripts import build_reversal_trend_features as brt


def _write_ohlcv(path: Path, symbol: str, dates: pd.DatetimeIndex) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    n = len(dates)
    frame = pd.DataFrame(
        {
            "symbol": [symbol] * n,
            "timestamp": dates,
            "open": [10.0 + i * 0.01 for i in range(n)],
            "high": [10.5 + i * 0.01 for i in range(n)],
            "low": [9.5 + i * 0.01 for i in range(n)],
            "close": [10.2 + i * 0.01 for i in range(n)],
            "volume": [100_000] * n,
            "trade_count": [500] * n,
            "vwap": [10.1 + i * 0.01 for i in range(n)],
        }
    )
    frame.to_parquet(path, index=False)


@pytest.fixture
def archive_fixture(tmp_path: Path) -> dict:
    primary_root = tmp_path / "primary"
    extra_root = tmp_path / "extra"
    dates = pd.bdate_range("2020-01-02", periods=60)
    _write_ohlcv(primary_root / "2020" / "SURV.parquet", "SURV", dates)
    _write_ohlcv(extra_root / "2020" / "DELISTED.parquet", "DELISTED", dates)
    # A dedicated market-reference row, outside the universe panel below --
    # only the OSAP builder test needs this (its market-relative columns
    # join in a --market-symbol series that is itself excluded from the
    # per-symbol output), kept here so every fixture consumer shares one
    # archive.
    _write_ohlcv(primary_root / "2020" / "MKT.parquet", "MKT", dates)

    universe_root = tmp_path / "universe"
    universe_root.mkdir()
    panel = pd.DataFrame(
        {
            "month_end": [pd.Timestamp("2020-12-31")] * 2,
            "symbol": ["SURV", "DELISTED"],
            "adv_rank": [1, 2],
            "dollar_adv": [1_000_000.0, 500_000.0],
            "close": [10.0, 5.0],
        }
    )
    panel.to_parquet(universe_root / "2020.parquet", index=False)

    return {
        "primary_root": primary_root,
        "extra_root": extra_root,
        "universe_root": universe_root,
        "out_dir": tmp_path / "out",
    }


def _run_main(
    monkeypatch: pytest.MonkeyPatch, module: object, daily_root: Path, argv: list[str]
) -> None:
    monkeypatch.setattr(module, "DAILY_ROOT", daily_root)
    monkeypatch.setattr(sys, "argv", ["prog", *argv])
    assert module.main() == 0


def test_alpha158_builder_routes_roots_and_includes_extra_daily_root(
    monkeypatch: pytest.MonkeyPatch, archive_fixture: dict
) -> None:
    _run_main(
        monkeypatch,
        ba158,
        archive_fixture["primary_root"],
        [
            "--years",
            "2020",
            "--symbol-batch-size",
            "50",
            "--universe-root",
            str(archive_fixture["universe_root"]),
            "--out-dir",
            str(archive_fixture["out_dir"] / "alpha158"),
            "--extra-daily-root",
            str(archive_fixture["extra_root"]),
        ],
    )
    out = pd.read_parquet(archive_fixture["out_dir"] / "alpha158" / "2020.parquet")
    assert set(out["symbol"].unique()) == {"SURV", "DELISTED"}


def test_alpha101_alpha191_builder_routes_two_out_dirs(
    monkeypatch: pytest.MonkeyPatch, archive_fixture: dict
) -> None:
    _run_main(
        monkeypatch,
        ba101,
        archive_fixture["primary_root"],
        [
            "--years",
            "2020",
            "--symbol-batch-size",
            "50",
            "--universe-root",
            str(archive_fixture["universe_root"]),
            "--alpha101-out-dir",
            str(archive_fixture["out_dir"] / "alpha101"),
            "--alpha191-out-dir",
            str(archive_fixture["out_dir"] / "alpha191"),
            "--extra-daily-root",
            str(archive_fixture["extra_root"]),
        ],
    )
    out_101 = pd.read_parquet(archive_fixture["out_dir"] / "alpha101" / "2020.parquet")
    out_191 = pd.read_parquet(archive_fixture["out_dir"] / "alpha191" / "2020.parquet")
    assert set(out_101["symbol"].unique()) == {"SURV", "DELISTED"}
    assert set(out_191["symbol"].unique()) == {"SURV", "DELISTED"}


def test_osap_price_builder_routes_roots_and_includes_extra_daily_root(
    monkeypatch: pytest.MonkeyPatch, archive_fixture: dict
) -> None:
    _run_main(
        monkeypatch,
        bosap,
        archive_fixture["primary_root"],
        [
            "--years",
            "2020",
            "--symbol-batch-size",
            "50",
            "--universe-root",
            str(archive_fixture["universe_root"]),
            "--out-dir",
            str(archive_fixture["out_dir"] / "osap_price"),
            "--extra-daily-root",
            str(archive_fixture["extra_root"]),
            # OSAP's market-relative columns need a market symbol present in
            # the archive; the fixture has no real SPY row, so point it at
            # the fixture's dedicated MKT row instead of the "SPY" default.
            "--market-symbol",
            "MKT",
        ],
    )
    out = pd.read_parquet(archive_fixture["out_dir"] / "osap_price" / "2020.parquet")
    assert set(out["symbol"].unique()) == {"SURV", "DELISTED"}


def test_reversal_trend_builder_routes_roots_and_includes_extra_daily_root(
    monkeypatch: pytest.MonkeyPatch, archive_fixture: dict
) -> None:
    _run_main(
        monkeypatch,
        brt,
        archive_fixture["primary_root"],
        [
            "--years",
            "2020",
            "--symbol-batch-size",
            "50",
            "--universe-root",
            str(archive_fixture["universe_root"]),
            "--out-dir",
            str(archive_fixture["out_dir"] / "reversal_trend"),
            "--extra-daily-root",
            str(archive_fixture["extra_root"]),
        ],
    )
    out = pd.read_parquet(archive_fixture["out_dir"] / "reversal_trend" / "2020.parquet")
    assert set(out["symbol"].unique()) == {"SURV", "DELISTED"}


def test_extra_daily_root_without_parquet_files_raises(
    monkeypatch: pytest.MonkeyPatch, archive_fixture: dict, tmp_path: Path
) -> None:
    empty_extra = tmp_path / "empty_extra"
    empty_extra.mkdir()
    monkeypatch.setattr(ba158, "DAILY_ROOT", archive_fixture["primary_root"])
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "prog",
            "--years",
            "2020",
            "--universe-root",
            str(archive_fixture["universe_root"]),
            "--out-dir",
            str(archive_fixture["out_dir"] / "alpha158"),
            "--extra-daily-root",
            str(empty_extra),
        ],
    )
    with pytest.raises(SystemExit):
        ba158.main()


def test_defaults_unchanged_when_new_flags_omitted() -> None:
    """The new ``--universe-root``/``--out-dir``/``--alpha101-out-dir``/
    ``--alpha191-out-dir`` flags must default to exactly the original
    (pre-2026-09-18) module-level constants -- the mechanical-rerun
    contract that an invocation without the new flags behaves identically
    to before.
    """
    for module, out_attr, out_name in (
        (ba158, "OUT_DIR", "alpha158"),
        (bosap, "OSAP_OUT", "osap_price"),
        (brt, "OUT_ROOT", "reversal_trend"),
    ):
        assert module.UNIVERSE_ROOT == module.ROOT / "data" / "features" / "universe"
        assert getattr(module, out_attr) == module.ROOT / "data" / "features" / out_name

    assert ba101.UNIVERSE_ROOT == ba101.ROOT / "data" / "features" / "universe"
    assert ba101.ALPHA101_OUT == ba101.ROOT / "data" / "features" / "alpha101"
    assert ba101.ALPHA191_OUT == ba101.ROOT / "data" / "features" / "alpha191"
