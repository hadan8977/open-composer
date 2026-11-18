"""Exact native prefix/tail behavior across the bounded writer's batch boundary."""

import numpy as np
import pandas as pd
import pytest

from scripts import build_book_v12_current_units as units


def test_composition_keeps_old_values_order_nulls_and_only_later_rows(tmp_path):
    old = pd.DataFrame({
        "symbol": [f"S{i}" for i in range(8205)],
        "trade_date": pd.to_datetime(["2026-10-16"] * 8205),
        "value": np.arange(8205, dtype=float),
        "record_present": [True] * 8205,
    })
    old.loc[8191, "value"] = np.nan
    fresh = old.iloc[-3:].copy()
    fresh["value"] = -99.0
    tail = pd.DataFrame({
        "symbol": ["NEW", "S0"],
        "trade_date": pd.to_datetime(["2026-10-19", "2026-10-20"]),
        "value": [np.nan, 1.25], "record_present": [False, True],
    })
    fresh = pd.concat([fresh, tail], ignore_index=True)
    a, b, dest = [tmp_path / name for name in ("old.parquet", "built.parquet", "out.parquet")]
    old.to_parquet(a, index=False)
    fresh.to_parquet(b, index=False)
    proof = units.compose_short_volume_prefix(a, b, dest, "trade_date")
    pd.testing.assert_frame_equal(
        pd.read_parquet(dest), pd.concat([old, tail], ignore_index=True), check_exact=True
    )
    assert (proof["old_rows"], proof["new_rows"]) == (8205, 2)
    assert proof["row_groups_verified_exactly"] == 3


def test_incompatible_schema_does_not_replace_existing_output(tmp_path):
    a, b, dest = [tmp_path / name for name in ("old.parquet", "built.parquet", "out.parquet")]
    pd.DataFrame({"trade_date": pd.to_datetime(["2026-10-16"]), "value": [1.0]}).to_parquet(a, index=False)
    pd.DataFrame({"trade_date": pd.to_datetime(["2026-10-19"]), "value": ["changed"]}).to_parquet(b, index=False)
    dest.write_bytes(b"preserved")
    with pytest.raises(ValueError, match="schema changed"):
        units.compose_short_volume_prefix(a, b, dest, "trade_date")
    assert dest.read_bytes() == b"preserved"
