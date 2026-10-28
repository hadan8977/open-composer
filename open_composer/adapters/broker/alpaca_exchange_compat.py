"""Preserve the broker's TXSE exchange label while retaining SDK validation.

The Oct19 paper responses contain TXSE in both assets and positions. The
installed SDK rejects that exact value before the book can inspect holdings.
Only this additional exchange label is accepted; unknown labels still fail.
Request paths, filtering, retries and all order methods remain SDK behavior.
"""

from typing import Literal

from alpaca.common.utils import validate_symbol_or_asset_id
from alpaca.trading.client import TradingClient
from alpaca.trading.enums import AssetExchange
from alpaca.trading.models import Asset, Position
from pydantic import TypeAdapter


class BrokerAsset(Asset):
    exchange: AssetExchange | Literal["TXSE"]


class BrokerPosition(Position):
    exchange: AssetExchange | Literal["TXSE"]


class ExchangeCompatibleTradingClient(TradingClient):
    """SDK client with narrowly extended read-response models, no write override."""

    def get_all_positions(self):
        response = self.get("/positions")
        if self._use_raw_data:
            return response
        return TypeAdapter(list[BrokerPosition]).validate_python(response)

    def get_open_position(self, symbol_or_asset_id):
        identity = validate_symbol_or_asset_id(symbol_or_asset_id)
        response = self.get(f"/positions/{identity}")
        if self._use_raw_data:
            return response
        return BrokerPosition.model_validate(response)

    def get_all_assets(self, filter=None):
        params = filter.to_request_fields() if filter is not None else {}
        response = self.get("/assets", params)
        if self._use_raw_data:
            return response
        return TypeAdapter(list[BrokerAsset]).validate_python(response)

    def get_asset(self, symbol_or_asset_id):
        identity = validate_symbol_or_asset_id(symbol_or_asset_id)
        response = self.get(f"/assets/{identity}")
        if self._use_raw_data:
            return response
        return BrokerAsset.model_validate(response)
