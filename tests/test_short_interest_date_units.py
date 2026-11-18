"""Current DATE Parquet and original timestamp Parquet join the same session."""
from datetime import date

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from scripts import build_short_interest_features as native


@pytest.mark.parametrize("date_type", [pa.date32(), pa.timestamp("ns")])
def test_adv_joins_native_session_without_changing_volume_or_missingness(tmp_path, monkeypatch, date_type):
    stamps = [date(2026, 10, 16)] * 4
    if pa.types.is_timestamp(date_type):
        stamps = [pd.Timestamp(x) for x in stamps]
    table = pa.table({
        "symbol": ["A", "B", "C", "OTHER"],
        "trade_date": pa.array(stamps, type=date_type),
        "close": [20.0, 0.0, np.nan, 10.0],
        "dollar_adv_63": [120.0, 100.0, 200.0, 40.0],
    })
    pq.write_table(table, tmp_path / "2026.parquet")
    monkeypatch.setattr(native, "DAILY_ROOT", tmp_path)
    actual = native.load_adv_shares(2026, {"A", "B", "C"})
    grid = pd.DataFrame({"symbol": ["A", "B", "C"], "trade_date": pd.to_datetime(stamps[:3])})
    result = grid.merge(actual, on=["symbol", "trade_date"], how="left", validate="one_to_one")
    assert result.adv_shares_63.tolist()[0] == 6.0
    assert result.adv_shares_63.iloc[1:].isna().all()
    assert result.trade_date.tolist() == pd.to_datetime(stamps[:3]).tolist()
