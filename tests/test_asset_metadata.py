"""Tests for open_composer.research.features.asset_metadata."""

from __future__ import annotations

import pandas as pd
import pytest

from open_composer.research.features.asset_metadata import (
    fetch_alpaca_asset_metadata,
    is_probable_fund_or_etf,
    load_or_fetch_asset_metadata,
)

# Calibration set from a live spot check on 2026-09-06 (see module docstring):
# name -> expected is_probable_fund_or_etf.
_CALIBRATION = {
    "State Street SPDR S&P 500 ETF Trust": True,
    "Invesco QQQ Trust, Series 1": True,
    "Apple Inc. Common Stock": False,
    "iShares Russell 2000 ETF": True,
    "SPDR Gold Trust, SPDR Gold Shares": True,
    "JPMorgan Equity Premium Income ETF": True,
    "ARK Innovation ETF": True,
    "Realty Income Corporation": False,
    "Ares Capital Corporation Common Stock": False,
    "Alibaba Group Holding Limited American Depositary Shares, each represents "
    "eight Ordinary Shares": False,
    "PIMCO Dynamic Income Fund": True,
    "BERKSHIRE HATHAWAY Class B": False,
    "Alphabet Inc. Class A Common Stock": False,
    "Ford Motor Company": False,
    "AT&T Inc.": False,
    "AGNC Investment Corp. Common Stock": False,
    "Annaly Capital Management. Inc.": False,
}


@pytest.mark.parametrize("name,expected", sorted(_CALIBRATION.items()))
def test_is_probable_fund_or_etf_matches_the_calibration_set(name: str, expected: bool) -> None:
    assert is_probable_fund_or_etf(name) is expected


def test_is_probable_fund_or_etf_handles_empty_name() -> None:
    assert is_probable_fund_or_etf("") is False


def test_fetch_alpaca_asset_metadata_requires_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ALPACA_API_KEY_ID", raising=False)
    monkeypatch.delenv("ALPACA_API_SECRET_KEY", raising=False)
    with pytest.raises(RuntimeError, match="ALPACA_API_KEY_ID"):
        fetch_alpaca_asset_metadata()


class _FakeAsset:
    def __init__(self, symbol: str, name: str) -> None:
        self.symbol = symbol
        self.name = name
        self.exchange = "NASDAQ"
        self.tradable = True
        self.fractionable = True


class _FakeTradingClient:
    def __init__(self, *_args: object, **_kwargs: object) -> None:
        pass

    def get_all_assets(self, _request: object) -> list[_FakeAsset]:
        return [
            _FakeAsset("AAPL", "Apple Inc. Common Stock"),
            _FakeAsset("SPY", "State Street SPDR S&P 500 ETF Trust"),
        ]


def test_fetch_alpaca_asset_metadata_labels_rows_from_the_live_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ALPACA_API_KEY_ID", "test-key")
    monkeypatch.setenv("ALPACA_API_SECRET_KEY", "test-secret")
    monkeypatch.setattr(
        "alpaca.trading.client.TradingClient",
        _FakeTradingClient,
    )
    frame = fetch_alpaca_asset_metadata()
    assert set(frame["symbol"]) == {"AAPL", "SPY"}
    labels = dict(zip(frame["symbol"], frame["is_probable_fund_or_etf"], strict=True))
    assert labels == {"AAPL": False, "SPY": True}


def test_load_or_fetch_asset_metadata_uses_the_cache_without_a_network_call(
    tmp_path: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    cache_path = tmp_path / "asset_metadata.parquet"  # type: ignore[operator]
    frame = pd.DataFrame(
        {
            "symbol": ["AAPL"],
            "name": ["Apple Inc. Common Stock"],
            "exchange": ["NASDAQ"],
            "tradable": [True],
            "fractionable": [True],
            "is_probable_fund_or_etf": [False],
        }
    )
    frame.to_parquet(cache_path, index=False)

    def _boom() -> pd.DataFrame:
        raise AssertionError("must not hit the network when the cache exists")

    monkeypatch.setattr(
        "open_composer.research.features.asset_metadata.fetch_alpaca_asset_metadata", _boom
    )
    loaded = load_or_fetch_asset_metadata(cache_path)
    pd.testing.assert_frame_equal(loaded, frame)
