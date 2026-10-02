from __future__ import annotations

import importlib.util
import json
import sys
from datetime import datetime
from pathlib import Path

import polars as pl

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "t02_price_tables.py"
spec = importlib.util.spec_from_file_location("t02_price_tables", SCRIPT)
assert spec is not None and spec.loader is not None
mod = importlib.util.module_from_spec(spec)
sys.modules["t02_price_tables"] = mod
spec.loader.exec_module(mod)


def _universe(path: Path, rows: list[tuple[datetime, str]]) -> None:
    path.mkdir(parents=True, exist_ok=True)
    pl.DataFrame(
        {
            "month_end": [r[0] for r in rows],
            "symbol": [r[1] for r in rows],
            "adv_rank": [1] * len(rows),
            "dollar_adv": [1.0] * len(rows),
            "close": [10.0] * len(rows),
        }
    ).write_parquet(path / "2026.parquet")


def test_universe_compose_keeps_old_months_and_appends_new(tmp_path: Path) -> None:
    aug, sep = datetime(2026, 8, 31), datetime(2026, 9, 30)
    existing = tmp_path / "existing"
    staged = tmp_path / "staged"
    _universe(existing, [(aug, "AAA"), (aug, "BBB")])
    # the staged rebuild disagrees about August (drops BBB, adds CCC) and adds September
    _universe(staged, [(aug, "AAA"), (aug, "CCC"), (sep, "AAA"), (sep, "NEW")])
    result = mod.universe_compose(existing, staged, tmp_path / "out", "t")
    composed = pl.read_parquet(tmp_path / "out" / "2026.parquet")
    assert composed.filter(pl.col("month_end") == aug)["symbol"].to_list() == ["AAA", "BBB"]
    assert composed.filter(pl.col("month_end") == sep)["symbol"].to_list() == ["AAA", "NEW"]
    assert result["new_entrants_0930"] == ["NEW"]
    assert abs(result["jaccard_by_month_end"]["2026-08-31"]["jaccard"] - 1 / 3) < 1e-12
    assert result["coverage_ratio"] == 1.0


def _table(path: Path, rows: list[tuple[str, datetime]]) -> Path:
    pl.DataFrame(
        {"symbol": [r[0] for r in rows], "trade_date": [r[1] for r in rows]}
    ).write_parquet(path)
    return path


def test_key_diff_attributes_rows(tmp_path: Path) -> None:
    d1, d2, d3 = datetime(2026, 1, 2), datetime(2026, 1, 5), datetime(2026, 9, 1)
    stage = tmp_path / "stage"
    stage.mkdir()
    (stage / "archive_only_new_keys.txt").write_text("DRK,2026-01-02\n")
    (stage / "archive_only_old_keys.txt").write_text("TEVA,2026-01-02\n")
    (stage / "new_entrants_0930_broad.txt").write_text("NEWB\n")
    (stage / "new_entrants_0930_narrow.txt").write_text("")
    old = _table(
        tmp_path / "old.parquet",
        [("AAA", d1), ("TEVA", d1), ("GONE", d2), ("AAA", d3)],
    )
    new = _table(
        tmp_path / "new.parquet",
        [("AAA", d1), ("DRK", d1), ("NEWB", d2), ("OIG", d2), ("AAA", d3)],
    )
    result = mod.key_diff(old, new, stage, "t")
    strict = result["zones"]["strict_le_0821"]
    assert strict["only_new"]["rows"] == 3
    assert strict["only_new"]["in_archive_one_sided_rows"] == 1
    assert strict["only_new"]["new_entrants_0930_rows"] == 1
    assert strict["only_new"]["unexplained_by_symbol"] == {"OIG": 1}
    assert strict["only_old"]["in_archive_one_sided_rows"] == 1
    assert strict["only_old"]["unexplained_by_symbol"] == {"GONE": 1}


def test_swap_backs_up_and_records(tmp_path: Path) -> None:
    dest = tmp_path / "t" / "2026.parquet"
    dest.parent.mkdir()
    dest.write_bytes(b"old")
    staged = tmp_path / "staged.parquet"
    staged.write_bytes(b"new")
    record = tmp_path / "swap.json"
    entry = mod.swap("t", staged, dest, tmp_path / "bk", record, "n")
    assert dest.read_bytes() == b"new"
    assert (tmp_path / "bk" / "t" / "2026.parquet").read_bytes() == b"old"
    assert entry["sha256_before"] != entry["sha256_after"]
    assert not staged.exists()
    assert json.loads(record.read_text())["swaps"][0]["table"] == "t"
