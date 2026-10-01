from __future__ import annotations

import importlib.util
import json
import sys
from datetime import date, datetime
from pathlib import Path

import polars as pl

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "check_feature_invariance.py"
spec = importlib.util.spec_from_file_location("check_feature_invariance", SCRIPT)
assert spec is not None and spec.loader is not None
mod = importlib.util.module_from_spec(spec)
sys.modules["check_feature_invariance"] = mod
spec.loader.exec_module(mod)

CUT = date(2026, 1, 5)


def _old_frame() -> pl.DataFrame:
    rows = []
    for day in (date(2026, 1, 2), date(2026, 1, 5)):
        for symbol, value in (("AAA", 1.0), ("BBB", 2.0), ("CCC", None)):
            rows.append(
                {
                    "symbol": symbol,
                    "trade_date": datetime.combine(day, datetime.min.time()),
                    "x": value,
                    "flag": True,
                }
            )
    return pl.DataFrame(rows, schema_overrides={"x": pl.Float64})


def _write(tmp_path: Path, name: str, frame: pl.DataFrame) -> Path:
    path = tmp_path / name
    frame.write_parquet(path)
    return path


def _appended(frame: pl.DataFrame, n_rows: int, day: date) -> pl.DataFrame:
    extra = pl.DataFrame(
        {
            "symbol": [f"S{i}" for i in range(n_rows)],
            "trade_date": [datetime.combine(day, datetime.min.time())] * n_rows,
            "x": [1.0] * n_rows,
            "flag": [True] * n_rows,
        }
    )
    return pl.concat([frame, extra])


def _run(tmp_path: Path, new: pl.DataFrame, old: pl.DataFrame, **kwargs) -> dict:
    return mod.compare(
        _write(tmp_path, "new.parquet", new),
        _write(tmp_path, "old.parquet", old),
        date_col="trade_date",
        cut=CUT,
        keys=["symbol", "trade_date"],
        **kwargs,
    )


def test_identical_history_with_appended_rows_passes(tmp_path: Path) -> None:
    old = _old_frame()
    new = _appended(old, 3, date(2026, 1, 6))
    result = _run(tmp_path, new, old)
    assert result["keys_equal"] is True
    assert result["max_changed_share"] == 0.0
    assert result["pass"] is True
    assert result["n_new_dates"] == 1
    assert result["last_date"] == "2026-01-06"
    assert result["coverage_ratio"] == 1.0
    assert result["columns"]["x"]["changed_rows"] == 0


def test_both_nan_is_equal_and_tolerance_applies(tmp_path: Path) -> None:
    old = _old_frame()
    new = old.with_columns(
        pl.when(pl.col("symbol") == "BBB")
        .then(pl.col("x") + 1e-12)
        .otherwise(pl.col("x"))
        .alias("x")
    )
    result = _run(tmp_path, new, old)
    assert result["columns"]["x"]["changed_rows"] == 0
    assert result["pass"] is True


def test_changed_values_and_null_flips_are_counted(tmp_path: Path) -> None:
    old = _old_frame()
    new = old.with_columns(
        pl.when(pl.col("symbol") == "AAA").then(pl.col("x") + 0.5).otherwise(pl.col("x")).alias("x")
    ).with_columns(
        pl.when(pl.col("symbol") == "CCC").then(pl.lit(7.0)).otherwise(pl.col("x")).alias("x")
    )
    result = _run(tmp_path, new, old)
    # AAA changed on 2 rows and CCC null -> value on 2 rows out of 6 joined rows
    assert result["rows_joined"] == 6
    assert result["columns"]["x"]["changed_rows"] == 4
    assert abs(result["max_changed_share"] - 4 / 6) < 1e-12
    assert result["pass"] is False
    assert {row["symbol"] for row in result["top_changed_symbols"]} == {"AAA", "CCC"}


def test_key_set_difference_fails(tmp_path: Path) -> None:
    old = _old_frame()
    new = old.filter(pl.col("symbol") != "BBB")
    result = _run(tmp_path, new, old)
    assert result["keys_equal"] is False
    assert result["n_keys_only_old"] == 2
    assert result["pass"] is False


def test_rows_after_cut_are_ignored_and_coverage_ratio(tmp_path: Path) -> None:
    old = _old_frame()
    # Old table also has a row after the cut that must not be compared.
    old_after = pl.concat(
        [
            old,
            pl.DataFrame(
                {
                    "symbol": ["AAA"],
                    "trade_date": [datetime(2026, 1, 6)],
                    "x": [9.0],
                    "flag": [True],
                }
            ),
        ]
    )
    new = _appended(old, 1, date(2026, 1, 6))  # 1 row per new date vs 3 per old date
    result = _run(tmp_path, new, old_after)
    assert result["pass"] is True
    assert abs(result["coverage_ratio"] - 1 / 3) < 1e-12


def test_main_writes_json_and_returns_exit_code(tmp_path: Path) -> None:
    old = _old_frame()
    new = _appended(old, 3, date(2026, 1, 6))
    new_path = _write(tmp_path, "n.parquet", new)
    old_path = _write(tmp_path, "o.parquet", old)
    out = tmp_path / "out" / "r.json"
    code = mod.main(
        [
            "--new",
            str(new_path),
            "--old",
            str(old_path),
            "--date-col",
            "trade_date",
            "--cut",
            "2026-01-05",
            "--keys",
            "symbol,trade_date",
            "--out",
            str(out),
        ]
    )
    assert code == 0
    payload = json.loads(out.read_text())
    assert payload["pass"] is True
    assert payload["n_new_dates"] == 1


def test_diagnostic_locates_changes_in_time(tmp_path: Path) -> None:
    old = _old_frame()
    last = datetime(2026, 1, 5)
    new = old.with_columns(
        pl.when(pl.col("trade_date") == last)
        .then(pl.col("x") + 1.0)
        .otherwise(pl.col("x"))
        .alias("x")
    )
    result = _run(tmp_path, new, old, trim_dates=1)
    diag = result["diagnostic"]
    assert diag["first_changed_date"] == "2026-01-05"
    assert diag["last_changed_date"] == "2026-01-05"
    assert diag["settled_to_date"] == "2026-01-02"
    assert diag["settled_max_changed_share"] == 0.0
    assert result["pass"] is False


def test_null_key_component_matches_itself(tmp_path: Path) -> None:
    old = pl.DataFrame(
        {
            "cik": [1, 1],
            "period_start": [None, datetime(2025, 1, 1)],
            "trade_date": [datetime(2026, 1, 2), datetime(2026, 1, 2)],
            "x": [1.0, 2.0],
        }
    )
    new = old.clone()
    result = mod.compare(
        _write(tmp_path, "n.parquet", new),
        _write(tmp_path, "o.parquet", old),
        date_col="trade_date",
        cut=CUT,
        keys=["cik", "period_start", "trade_date"],
    )
    assert result["keys_equal"] is True
    assert result["rows_joined"] == 2
    assert result["pass"] is True
