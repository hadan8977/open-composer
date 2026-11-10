import pandas as pd
import pytest

from scripts import build_short_interest_features as m


@pytest.mark.parametrize("shift", [0, 2])
@pytest.mark.parametrize("symbols", [{"A"}, set(), None])
def test_source_projection_keeps_records_dates_nulls_and_placebo(
    tmp_path, monkeypatch, shift, symbols
):
    path = tmp_path / "parsed.parquet"
    rows = []
    for symbol in ("A", "B"):
        for day, volume in (("2024-01-02", 10.0), ("2024-01-04", 0.0), ("2024-02-01", 20.0)):
            rows.append(
                {
                    "symbol": symbol,
                    "settlement_date": pd.Timestamp(day),
                    "publication_date": pd.Timestamp(day),
                    "visible_date": pd.Timestamp(day),
                    "short_interest_shares": 100.0,
                    "average_daily_volume": volume,
                    "days_to_cover": 3.0,
                }
            )
    rows.append(rows[0].copy())
    pd.DataFrame(rows).to_parquet(path, index=False, row_group_size=2)
    monkeypatch.setattr(m, "PARSED_PATH", path)
    sessions = pd.date_range("2024-01-01", "2024-01-10", freq="B")
    actual = m.load_records(symbols=symbols, sessions=sessions, shift_days=shift, seed=22)
    original_read = pd.read_parquet

    def legacy_read(*args, **kwargs):
        kwargs.pop("filters", None)
        return original_read(*args, **kwargs)

    monkeypatch.setattr(pd, "read_parquet", legacy_read)
    expected = m.load_records(symbols=symbols, sessions=sessions, shift_days=shift, seed=22)
    pd.testing.assert_frame_equal(actual, expected, check_exact=True)
    if symbols == {"A"}:
        assert len(actual) == 3 and set(actual.symbol) == {"A"}
    elif symbols == set():
        assert actual.empty
    assert actual.loc[actual.average_daily_volume.eq(0), "days_to_cover"].isna().all()
