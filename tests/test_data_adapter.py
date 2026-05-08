from __future__ import annotations

from pathlib import Path

from open_composer.adapters.data.alpaca import fetch_alpaca_bars


def test_alpaca_fetch_uses_cache_without_credentials(sample_workspace: Path) -> None:
    cache = sample_workspace / "data" / "cache" / "qqq_15m_iex.csv"
    sample = sample_workspace / "data" / "sample" / "qqq_15m.csv"
    cache.write_text(sample.read_text(encoding="utf-8"), encoding="utf-8")
    frame = fetch_alpaca_bars(sample_workspace, "QQQ", "15m", None, None, "iex")
    assert len(frame) > 0
    assert frame["close"].iloc[-1] > 0
