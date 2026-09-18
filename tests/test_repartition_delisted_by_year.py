"""Alias-exclusion logic of scripts/repartition_delisted_by_year.py."""

from __future__ import annotations

import importlib

import pandas as pd

mod = importlib.import_module("scripts.repartition_delisted_by_year")


def _bars(symbol: str, start: str, periods: int) -> pd.DataFrame:
    dates = pd.bdate_range(start, periods=periods, tz="UTC")
    return pd.DataFrame(
        {
            "symbol": symbol,
            "timestamp": dates,
            "open": 1.0,
            "high": 1.0,
            "low": 1.0,
            "close": 1.0,
            "volume": 100.0,
            "trade_count": 1.0,
            "vwap": 1.0,
        }
    )


def test_load_exclusions_splits_full_aliases_from_partial_spans(tmp_path) -> None:
    table = pd.DataFrame(
        {
            "symbol": ["ANTM", "BIOS", "BIOS"],
            "matched_symbol": ["ELV", "OPCH", "OPCH"],
            "drop_all": [True, False, False],
            "drop_from": ["2016-01-04", "2016-01-04", "2019-01-01"],
            "drop_to": ["2022-06-27", "2018-06-30", "2020-01-31"],
        }
    )
    path = tmp_path / "aliases.parquet"
    table.to_parquet(path, index=False)
    drop_all, spans = mod.load_exclusions(path)
    assert drop_all == {"ANTM"}
    assert spans["symbol"].tolist() == ["BIOS", "BIOS"]
    # drop_to is exclusive and one day past the last matched day
    assert spans["drop_to"].iloc[0] == pd.Timestamp("2018-07-01", tz="UTC")


def test_load_exclusions_without_a_table_is_a_no_op(tmp_path) -> None:
    drop_all, spans = mod.load_exclusions(tmp_path / "missing.parquet")
    assert drop_all == set()
    assert spans.empty


def test_apply_exclusions_drops_whole_symbols_and_only_the_matched_span() -> None:
    frame = pd.concat(
        [
            _bars("ANTM", "2020-01-01", 10),
            _bars("BIOS", "2020-01-01", 10),
            _bars("TWTR", "2020-01-01", 10),
        ],
        ignore_index=True,
    )
    spans = pd.DataFrame(
        {
            "symbol": ["BIOS"],
            "drop_from": [pd.Timestamp("2020-01-06", tz="UTC")],
            "drop_to": [pd.Timestamp("2020-01-09", tz="UTC")],  # exclusive
        }
    )
    out = mod.apply_exclusions(frame, {"ANTM"}, spans)
    assert "ANTM" not in set(out["symbol"])
    assert (out["symbol"] == "TWTR").sum() == 10
    bios = out.loc[out["symbol"] == "BIOS", "timestamp"]
    assert len(bios) == 7
    assert not bios.between(
        pd.Timestamp("2020-01-06", tz="UTC"), pd.Timestamp("2020-01-08", tz="UTC")
    ).any()
