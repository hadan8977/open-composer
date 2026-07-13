from __future__ import annotations

from pathlib import Path

import pandas as pd

from open_composer.research.momentum_data_refresh import refresh_momentum_research_data


def test_refresh_appends_without_rewriting_existing_bytes(tmp_path: Path) -> None:
    originals = _write_existing(tmp_path)

    result = refresh_momentum_research_data(tmp_path, fetcher=_fetcher_with_one_new_bar)

    assert result.status == "ok"
    assert all(row["appended_records"] == 1 for row in result.payload["rows"])
    for symbol, original in originals.items():
        path = _path(tmp_path, symbol)
        assert path.read_bytes().startswith(original)


def test_refresh_is_idempotent_for_duplicate_provider_rows(tmp_path: Path) -> None:
    _write_existing(tmp_path)
    first = refresh_momentum_research_data(tmp_path, fetcher=_fetcher_with_one_new_bar)
    second = refresh_momentum_research_data(tmp_path, fetcher=_fetcher_with_one_new_bar)

    assert first.status == "ok"
    assert second.status == "ok"
    assert all(row["appended_records"] == 0 for row in second.payload["rows"])


def test_refresh_preserves_snapshot_when_provider_fails(tmp_path: Path) -> None:
    originals = _write_existing(tmp_path)

    def fail(*args, **kwargs):
        raise RuntimeError("provider unavailable")

    result = refresh_momentum_research_data(tmp_path, fetcher=fail)

    assert result.status == "blocked"
    assert all(row["snapshot_preserved"] is True for row in result.payload["rows"])
    for symbol, original in originals.items():
        assert _path(tmp_path, symbol).read_bytes() == original


def test_refresh_does_not_append_extended_hours_bars(tmp_path: Path) -> None:
    _write_existing(tmp_path)

    def extended_fetcher(*args, **kwargs):
        frame = _fetcher_with_one_new_bar(*args, **kwargs)
        extended = frame.iloc[-1].copy()
        extended["timestamp"] = "2026-07-10T21:00:00+00:00"
        return pd.concat([frame, pd.DataFrame([extended])], ignore_index=True)

    result = refresh_momentum_research_data(tmp_path, fetcher=extended_fetcher)

    assert result.status == "ok"
    for symbol in ("QQQ", "TQQQ"):
        timestamps = pd.to_datetime(pd.read_csv(_path(tmp_path, symbol))["timestamp"], utc=True)
        assert pd.Timestamp("2026-07-10T21:00:00Z") not in set(timestamps)


def _write_existing(root: Path) -> dict[str, bytes]:
    rows = [
        {
            "timestamp": "2026-07-10T13:30:00+00:00",
            "open": 100.0,
            "high": 101.0,
            "low": 99.0,
            "close": 100.5,
            "volume": 1000,
        }
    ]
    originals = {}
    for symbol in ("QQQ", "TQQQ"):
        path = _path(root, symbol)
        path.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(rows).to_csv(path, index=False)
        originals[symbol] = path.read_bytes()
    return originals


def _fetcher_with_one_new_bar(root, symbol, timeframe, start, end, feed, use_cache):
    return pd.DataFrame(
        [
            {
                "timestamp": "2026-07-10T13:30:00+00:00",
                "open": 100.0,
                "high": 101.0,
                "low": 99.0,
                "close": 100.5,
                "volume": 1000,
            },
            {
                "timestamp": "2026-07-10T14:00:00+00:00",
                "open": 100.5,
                "high": 102.0,
                "low": 100.0,
                "close": 101.5,
                "volume": 1200,
            },
        ]
    )


def _path(root: Path, symbol: str) -> Path:
    return root / "data/research/alpaca_minute" / f"{symbol.lower()}_30m_alpaca_iex.csv"
