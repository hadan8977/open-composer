"""Check year filtering after windows and symbol-block parity of the existing join."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from build_daily_features import write_bounded_year
from open_composer.research.features.daily_features import build_daily_features, join_intraday_rolling_features
from open_composer.research.features.intraday_daily import INTRADAY_DAILY_COLUMNS


def test_bounded_year_retains_prior_year_windows_and_complete_intraday_history(tmp_path):
    dates = pd.bdate_range("2020-11-02", "2021-02-19")
    rows = []
    intra = []
    rng = np.random.default_rng(42)
    for symbol in ("AAA", "BBB", "SPY"):
        price = 100.0
        for i, day in enumerate(dates):
            price *= 1 + rng.normal(0, .01)
            rows.append(dict(symbol=symbol, timestamp=day, open=price*.999,
                             close=price, volume=100_000+i))
            # Sparse source coverage is retained, including January warm-up.
            if i % 7 != 0:
                intra.append({"symbol": symbol, "trade_date": day,
                    **{c: rng.normal() for c in INTRADAY_DAILY_COLUMNS if c not in ("symbol", "trade_date")}})
    bars = tmp_path / "bars.parquet"
    intraday = tmp_path / "intraday.parquet"
    pd.DataFrame(rows).to_parquet(bars, index=False)
    source = pd.DataFrame(intra).sample(frac=1, random_state=7).reset_index(drop=True)
    source.to_parquet(intraday, index=False)
    expected = build_daily_features([str(bars)], ["AAA", "BBB"], memory_limit="200MB")
    expected = expected.loc[expected.trade_date.dt.year == 2021]
    expected = join_intraday_rolling_features(expected, source).sort_values(["symbol", "trade_date"]).reset_index(drop=True)
    destination = tmp_path / "output.parquet"
    summary = write_bounded_year([str(bars)], ["AAA", "BBB"], 2021,
        destination, intraday, "200MB", symbol_chunk=1)
    actual = pd.read_parquet(destination).reset_index(drop=True)
    pd.testing.assert_frame_equal(actual, expected, check_exact=False, rtol=1e-12, atol=1e-12)
    assert summary["rows"] == len(expected)
    assert np.isfinite(actual.loc[actual.trade_date.eq(pd.Timestamp("2021-01-04")), "ret_21"]).all()
