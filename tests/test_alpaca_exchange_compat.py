from copy import deepcopy
from types import SimpleNamespace

import pytest
from alpaca.trading.client import TradingClient
from alpaca.trading.enums import AssetClass, AssetExchange, AssetStatus
from alpaca.trading.models import Asset, Position
from alpaca.trading.requests import GetAssetsRequest
from pydantic import ValidationError

from open_composer.adapters.broker.alpaca_exchange_compat import (
    BrokerAsset,
    BrokerPosition,
    ExchangeCompatibleTradingClient,
)
from open_composer.book_paper.plan import read_account_state

ID = "00000000-0000-4000-8000-000000000001"


def asset(exchange="TXSE", **changes):
    return {
        "id": ID,
        "class": "us_equity",
        "exchange": exchange,
        "symbol": "EXAMPLE",
        "status": "active",
        "tradable": True,
        "marginable": False,
        "shortable": False,
        "easy_to_borrow": False,
        "fractionable": False,
    } | changes


def position(exchange="TXSE", **changes):
    return {
        "asset_id": ID,
        "symbol": "EXAMPLE",
        "exchange": exchange,
        "asset_class": "us_equity",
        "avg_entry_price": "10",
        "qty": "3",
        "side": "short",
        "cost_basis": "30",
        "current_price": "11",
        "market_value": "-33",
        "qty_available": "2",
    } | changes


def client(response, *, raw=False):
    value = ExchangeCompatibleTradingClient(
        "invented-key", "invented-secret", paper=True, raw_data=raw
    )
    calls = []

    def get(*args, **kwargs):
        calls.append((args, kwargs))
        return response

    value.get = get
    return value, calls


@pytest.mark.parametrize("model,payload", [(Asset, asset()), (Position, position())])
def test_installed_sdk_defect_is_reproduced(model, payload):
    with pytest.raises(ValidationError):
        model.model_validate(payload)


@pytest.mark.parametrize(
    "old,new,payload",
    [(Asset, BrokerAsset, asset("NYSE")), (Position, BrokerPosition, position("NASDAQ"))],
)
def test_preexisting_exchange_and_all_fields_are_identical(old, new, payload):
    assert new.model_validate(payload).model_dump() == old.model_validate(payload).model_dump()


def test_new_label_preserves_position_financial_fields_and_signed_book_quantity():
    raw = [position()]
    original = deepcopy(raw)
    c, calls = client(raw)
    c.get_account = lambda: SimpleNamespace(equity="1000", status="ACTIVE", trading_blocked=False)
    c.get_orders = lambda **kwargs: []
    state = read_account_state(c)
    assert state.positions == {"EXAMPLE": -3.0}
    assert state.position_prices == {"EXAMPLE": 11.0}
    result = BrokerPosition.model_validate(raw[0])
    assert isinstance(result, Position)
    assert result.exchange == "TXSE"
    assert result.qty_available == "2"
    assert result.cost_basis == "30"
    assert raw == original and calls == [(("/positions",), {})]


def test_assets_filter_tradability_and_borrow_rights_remain_exact():
    raw = [asset(), asset(symbol="CLOSED", tradable=False)]
    c, calls = client(raw)
    request = GetAssetsRequest(status=AssetStatus.ACTIVE, asset_class=AssetClass.US_EQUITY)
    result = c.get_all_assets(request)
    assert result[0].exchange == "TXSE"
    assert result[0].shortable is False and result[0].easy_to_borrow is False
    assert result[0].marginable is False
    assert result[1].tradable is False
    assert calls == [(("/assets", request.to_request_fields()), {})]


@pytest.mark.parametrize(
    "method,payload,path",
    [
        ("get_asset", asset(), "/assets/EXAMPLE"),
        ("get_open_position", position(), "/positions/EXAMPLE"),
    ],
)
def test_single_response_routes_make_one_request(method, payload, path):
    c, calls = client(payload)
    result = getattr(c, method)("EXAMPLE")
    assert result.exchange == "TXSE"
    assert calls == [((path,), {})]


@pytest.mark.parametrize(
    "payload",
    [
        position(exchange="UNRECEIVED_EXCHANGE"),
        position(side="invalid-side"),
        {k: v for k, v in position().items() if k != "qty"},
    ],
)
def test_bad_member_refuses_entire_position_list_without_retry_or_omission(payload):
    c, calls = client([position("NYSE"), payload])
    with pytest.raises(ValidationError):
        c.get_all_positions()
    assert len(calls) == 1


def test_missing_asset_permission_still_refuses():
    payload = asset()
    del payload["tradable"]
    c, calls = client([payload])
    with pytest.raises(ValidationError):
        c.get_all_assets()
    assert len(calls) == 1


@pytest.mark.parametrize(
    "method,payload,args",
    [
        ("get_all_positions", [position()], ()),
        ("get_all_assets", [asset()], ()),
        ("get_asset", asset(), ("EXAMPLE",)),
        ("get_open_position", position(), ("EXAMPLE",)),
    ],
)
def test_explicit_sdk_raw_mode_is_unchanged(method, payload, args):
    c, calls = client(payload, raw=True)
    assert getattr(c, method)(*args) is payload
    assert len(calls) == 1


def test_order_transport_and_account_methods_are_not_overridden():
    for name in (
        "submit_order",
        "replace_order_by_id",
        "cancel_order_by_id",
        "close_all_positions",
        "get_orders",
        "get_account",
        "_request",
        "_one_request",
    ):
        assert getattr(ExchangeCompatibleTradingClient, name) is getattr(TradingClient, name)
    assert BrokerAsset.model_validate(asset("NYSE")).exchange is AssetExchange.NYSE


def test_archive_factory_and_original_universe_filter_receive_new_exchange(monkeypatch):
    from scripts.fetch_sip_universe import _clients, load_universe

    monkeypatch.setenv("ALPACA_API_KEY_ID", "invented-source-key")
    monkeypatch.setenv("ALPACA_API_SECRET_KEY", "invented-source-secret")
    c, _ = _clients()
    assert isinstance(c, ExchangeCompatibleTradingClient)
    assert c._sandbox is True
    c.get = lambda *args, **kwargs: [
        asset(),
        asset("NYSE", symbol="ABC"),
        asset(symbol="NO", tradable=False),
    ]
    assert load_universe(c) == ["ABC", "EXAMPLE"]
