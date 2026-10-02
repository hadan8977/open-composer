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


def _price_frames() -> tuple[pl.DataFrame, pl.DataFrame]:
    days = [datetime(2026, 1, 2), datetime(2026, 1, 5)]
    rows = []
    for day in days:
        for symbol, close, ret in (("AAA", 10.0, 0.01), ("BBB", 100.0, 0.02), ("CCC", 50.0, 0.03)):
            rows.append({"symbol": symbol, "trade_date": day, "close": close, "ret_1": ret})
    old = pl.DataFrame(rows)
    return old.clone(), old


def test_price_aware_tolerance_absorbs_rounding_only(tmp_path: Path) -> None:
    new, old = _price_frames()
    # AAA close 10 -> price_tol/close = 0.004: a 0.003 move is rounding, 0.006 is a change.
    new = new.with_columns(
        pl.when(pl.col("symbol") == "AAA")
        .then(
            pl.when(pl.col("trade_date") == datetime(2026, 1, 2))
            .then(pl.col("ret_1") + 0.003)
            .otherwise(pl.col("ret_1") + 0.006)
        )
        .otherwise(pl.col("ret_1"))
        .alias("ret_1")
    )
    plain = _run(tmp_path, new, old)
    assert plain["columns"]["ret_1"]["changed_rows"] == 2
    aware = _run(tmp_path, new, old, price_col="close", price_tol=0.04, price_aware_spec=["ret_1"])
    assert aware["columns"]["ret_1"]["changed_rows"] == 1
    assert aware["columns"]["ret_1"]["price_aware"] is True
    # BBB close 100 -> price_tol/close = 0.0004, tighter than the 1e-9 floor? no: larger, so
    # a 0.0003 move on BBB is still rounding.
    new2 = old.with_columns(
        pl.when(pl.col("symbol") == "BBB")
        .then(pl.col("ret_1") + 0.0003)
        .otherwise(pl.col("ret_1"))
        .alias("ret_1")
    )
    ok = _run(tmp_path, new2, old, price_col="close", price_tol=0.04, price_aware_spec=["ret_1"])
    assert ok["columns"]["ret_1"]["changed_rows"] == 0


def test_exclude_and_attribute_symbols(tmp_path: Path) -> None:
    new, old = _price_frames()
    new = new.with_columns(
        pl.when(pl.col("symbol").is_in(["AAA", "BBB"]))
        .then(pl.col("ret_1") + 0.5)
        .otherwise(pl.col("ret_1"))
        .alias("ret_1")
    )
    result = _run(tmp_path, new, old, exclude_symbols={"AAA"}, attribute_symbols={"BBB"})
    assert result["rows_joined"] == 6
    assert result["excluded_rows"] == 2
    assert result["excluded_changed_rows"] == 2
    assert result["rows_evaluated"] == 4
    assert result["columns"]["ret_1"]["changed_rows"] == 2
    assert abs(result["columns"]["ret_1"]["changed_share"] - 0.5) < 1e-12
    assert result["unattributed_changed_rows"] == 0
    assert result["attributed_changed_rows"] == 2
    other = _run(tmp_path, new, old, attribute_symbols={"CCC"})
    assert other["unattributed_changed_rows"] == 4


def test_columns_exclude_cols_and_start_window(tmp_path: Path) -> None:
    new, old = _price_frames()
    new = new.with_columns(
        pl.when(pl.col("trade_date") == datetime(2026, 1, 2))
        .then(pl.col("close") + 1.0)
        .otherwise(pl.col("close"))
        .alias("close")
    )
    only_ret = _run(tmp_path, new, old, columns_spec=["re:^ret_"])
    assert list(only_ret["columns"]) == ["ret_1"]
    assert only_ret["pass"] is True
    no_close = _run(tmp_path, new, old, exclude_cols_spec=["close"])
    assert "close" not in no_close["columns"]
    windowed = _run(tmp_path, new, old, start=date(2026, 1, 5))
    assert windowed["rows_joined"] == 3
    assert windowed["columns"]["close"]["changed_rows"] == 0
    full = _run(tmp_path, new, old)
    assert full["columns"]["close"]["changed_rows"] == 3


def test_allowed_only_new_and_only_old_keys(tmp_path: Path) -> None:
    new, old = _price_frames()
    new = pl.concat(
        [
            new.filter(
                ~((pl.col("symbol") == "CCC") & (pl.col("trade_date") == datetime(2026, 1, 5)))
            ),
            pl.DataFrame(
                {
                    "symbol": ["NEW"],
                    "trade_date": [datetime(2026, 1, 2)],
                    "close": [5.0],
                    "ret_1": [0.0],
                }
            ),
        ]
    )
    bad = _run(tmp_path, new, old)
    assert bad["keys_equal"] is False and bad["keys_ok"] is False
    assert bad["n_keys_only_new_unallowed"] == 1
    assert bad["n_keys_only_old_unallowed"] == 1
    good = _run(
        tmp_path,
        new,
        old,
        allow_only_new=({"NEW"}, set()),
        allow_only_old=(set(), {("CCC", "2026-01-05")}),
    )
    assert good["keys_equal"] is False
    assert good["keys_ok"] is True
    assert good["pass"] is True
    partial = _run(tmp_path, new, old, allow_only_new=({"NEW"}, set()))
    assert partial["keys_ok"] is False


def test_rank_parity_and_rank_gate(tmp_path: Path) -> None:
    day = datetime(2026, 1, 2)
    symbols = [f"S{i}" for i in range(20)]
    old = pl.DataFrame(
        {
            "symbol": symbols * 2,
            "trade_date": [day] * 20 + [datetime(2026, 1, 5)] * 20,
            "a": [float(i) for i in range(20)] * 2,
            "b": [float(i) for i in range(20)] * 2,
        }
    )
    # a: monotone transform (rank identical) but every value changes; b: reversed on day 2.
    new = old.with_columns((pl.col("a") * 3.0 + 1.0).alias("a")).with_columns(
        pl.when(pl.col("trade_date") == datetime(2026, 1, 5))
        .then(19.0 - pl.col("b"))
        .otherwise(pl.col("b"))
        .alias("b")
    )
    result = _run(
        tmp_path,
        new,
        old,
        rank_parity_spec=["a", "b"],
        rank_min=0.99,
        columns_spec=["a"],
        gate="rank",
    )
    assert result["rank_cells"] == 4
    assert abs(result["rank_parity_share"] - 0.75) < 1e-12
    assert result["rank_parity_share_by_column"] == {"a": 1.0, "b": 0.5}
    assert result["rank_parity_worst"][0]["column"] == "b"
    assert abs(result["rank_parity_worst"][0]["rho"] + 1.0) < 1e-9
    assert result["pass"] is False
    only_a = _run(tmp_path, new, old, rank_parity_spec=["a"], columns_spec=["a"], gate="rank")
    assert only_a["rank_parity_share"] == 1.0
    assert only_a["max_changed_share"] == 1.0  # values did change
    assert only_a["pass"] is True  # the rank gate ignores the value-change share


def test_main_accepts_new_options(tmp_path: Path) -> None:
    new, old = _price_frames()
    new_path = _write(tmp_path, "n.parquet", new)
    old_path = _write(tmp_path, "o.parquet", old)
    excl = tmp_path / "excl.txt"
    excl.write_text("AAA\n# comment\n\n")
    out = tmp_path / "r.json"
    code = mod.main(
        [
            "--new", str(new_path), "--old", str(old_path), "--date-col", "trade_date",
            "--cut", "2026-01-05", "--keys", "symbol,trade_date", "--out", str(out),
            "--price-col", "close", "--price-aware-cols", "re:^ret_",
            "--exclude-symbols", str(excl),
            "--attribute-symbols", str(excl), "--rank-parity-cols", "ret_1", "--gate", "both",
        ]
    )  # fmt: skip
    payload = json.loads(out.read_text())
    assert code == 0
    assert payload["excluded_rows"] == 2
    assert payload["rank_parity_share"] == 1.0


def test_price_ratio_columns_scale_the_rounding_bound(tmp_path: Path) -> None:
    new, old = _price_frames()
    old = old.with_columns(pl.lit(4.0).alias("ret_252"))  # price ratio of 5: base = close / 5
    # AAA: close 10, plain bound 0.04/10 = 0.004; ratio bound = 0.004 * 5 * 6 / 2 = 0.06.
    new = old.with_columns(
        pl.when(pl.col("symbol") == "AAA")
        .then(pl.col("ret_252") + 0.03)
        .otherwise(pl.col("ret_252"))
        .alias("ret_252")
    )
    aware = _run(
        tmp_path,
        new,
        old,
        columns_spec=["ret_252"],
        price_col="close",
        price_aware_spec=["ret_252"],
    )
    assert aware["columns"]["ret_252"]["changed_rows"] == 2
    ratio = _run(
        tmp_path,
        new,
        old,
        columns_spec=["ret_252"],
        price_col="close",
        price_aware_spec=["ret_252"],
        price_ratio_spec=["ret_252"],
    )
    assert ratio["columns"]["ret_252"]["changed_rows"] == 0
    assert ratio["columns"]["ret_252"]["price_ratio"] is True
    too_big = new.with_columns(
        pl.when(pl.col("symbol") == "AAA")
        .then(pl.col("ret_252") + 0.07)
        .otherwise(pl.col("ret_252"))
        .alias("ret_252")
    )
    still = _run(
        tmp_path,
        too_big,
        old,
        columns_spec=["ret_252"],
        price_col="close",
        price_aware_spec=["ret_252"],
        price_ratio_spec=["ret_252"],
    )
    assert still["columns"]["ret_252"]["changed_rows"] == 2
