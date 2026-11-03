"""Imported collection functions and consolidation use the isolated destination."""
from datetime import date

import pandas as pd

from open_composer.research.news import collector
from scripts import build_book_v12_current_units as units


def test_imported_functions_write_only_private_daily_and_annual_paths(tmp_path, monkeypatch):
    view = tmp_path / "view"
    view.mkdir()
    unrelated = tmp_path / "existing"
    unrelated.mkdir()
    original = unrelated / "2026.parquet"
    original.write_bytes(b"preserved shared cache")
    monkeypatch.setattr(collector, "NEWS_PACKETS_ROOT", unrelated)
    monkeypatch.setattr(collector, "DAILY_ROOT", unrelated / "_daily")
    frame = pd.DataFrame({"id": [1], "created_at": ["2026-11-02T12:00:00Z"], "headline": ["Fixture"]})
    monkeypatch.setattr(collector, "collect_day", lambda *args, **kwargs: frame.copy())
    module = units.load_native(view, "collect_alpaca_news_packets")
    result = module.collect_historical_range(date(2026, 11, 2), date(2026, 11, 2))
    output = module.consolidate_year(2026)
    assert result.days_fetched == 1
    assert output == view / "data/features/news_packets/2026.parquet"
    assert (view / "data/features/news_packets/_daily/2026-11-02.parquet").exists()
    pd.testing.assert_frame_equal(pd.read_parquet(output), frame)
    assert original.read_bytes() == b"preserved shared cache"
    assert not (unrelated / "_daily").exists()
