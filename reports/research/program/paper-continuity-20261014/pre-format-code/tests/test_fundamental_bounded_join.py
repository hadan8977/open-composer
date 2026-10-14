import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd


def test_issuer_chunks_preserve_visibility_aliases_and_duplicate_price_rows():
    path = Path(__file__).parents[1] / 'scripts/build_sec_xbrl_fundamentals.py'
    spec = importlib.util.spec_from_file_location('fundamental_bounded_test', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    dates = pd.date_range('2026-01-01', periods=5)
    positions = dict(zip(dates, range(5), strict=True))
    events = pd.DataFrame([
        {'cik': 11, 'event_idx': 1, 'last_report_idx': 1, 'total_assets': 100.0},
        {'cik': 11, 'event_idx': 3, 'last_report_idx': 3, 'total_assets': 150.0},
        {'cik': 22, 'event_idx': 0, 'last_report_idx': 0, 'total_assets': 200.0},
    ])
    mapping = {'A': 11, 'A_ALIAS': 11, 'B': 22}
    price = pd.DataFrame([
        ('A', dates[0]), ('A', dates[2]), ('A', dates[4]),
        ('A_ALIAS', dates[2]), ('B', dates[2]), ('B', dates[2]),
        ('UNMAPPED', dates[4]),
    ], columns=['symbol', 'trade_date'])
    full = module.merge_daily_prices(price, events, mapping, positions)
    chunks = pd.concat([
        module.merge_daily_prices(price[price.symbol.isin(names)], events, mapping, positions)
        for names in (['A','A_ALIAS'], ['B'])
    ]).sort_values(['trade_date','symbol'], ignore_index=True)
    pd.testing.assert_frame_equal(full, chunks)
    assert len(full) == 6
    assert np.isnan(full.iloc[0].total_assets)
    assert full.loc[full.symbol.eq('A'), 'total_assets'].iloc[1:].tolist() == [100.0,150.0]
    assert full.loc[full.symbol.eq('A_ALIAS'), 'days_since_report'].tolist() == [1.0]
    assert full.loc[full.symbol.eq('B'), 'days_since_report'].tolist() == [2.0,2.0]
