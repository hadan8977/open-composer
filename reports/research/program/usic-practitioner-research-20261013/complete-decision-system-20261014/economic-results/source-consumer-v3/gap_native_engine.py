"""Construct the single CASH native venue used by all reviewed cells."""

from decimal import Decimal

from frame_producer import SYMBOLS
from gap_adapter import GapNativeStrategy as MartinNativeStrategy
from nautilus_policy_adapter import MartinAdapterConfig
from nautilus_trader.backtest.engine import BacktestEngine
from nautilus_trader.config import BacktestEngineConfig, CacheConfig, LoggingConfig
from nautilus_trader.model.currencies import USD
from nautilus_trader.model.enums import AccountType, BookType, OmsType
from nautilus_trader.model.identifiers import InstrumentId, Symbol, Venue
from nautilus_trader.model.instruments import Equity
from nautilus_trader.model.objects import Money, Price, Quantity


def make_engine(
    parameters, candidate, route, cost_bps, bindings, initial_factors=None, *, optimize_runtime=True
):
    engine = BacktestEngine(
        BacktestEngineConfig(
            logging=LoggingConfig(bypass_logging=True),
            cache=CacheConfig(tick_capacity=1, bar_capacity=1),
        )
    )
    engine.add_venue(
        venue=Venue("SIM"),
        oms_type=OmsType.NETTING,
        account_type=AccountType.CASH,
        starting_balances=[Money(20000, USD)],
        base_currency=USD,
        book_type=BookType.L2_MBP,
        use_message_queue=False,
    )
    ids = []
    for s in SYMBOLS:
        id = InstrumentId.from_str(s + ".SIM")
        ids.append(str(id))
        engine.add_instrument(
            Equity(
                id,
                Symbol(s),
                USD,
                5,
                Price.from_str("0.00001"),
                Quantity.from_int(1),
                0,
                0,
                maker_fee=Decimal(str(cost_bps / 10000)),
                taker_fee=Decimal(str(cost_bps / 10000)),
                info={"source_quote_evidence": "conditional_OHLC_or_observed_BBO_synthetic_L2"},
            )
        )
    strategy = MartinNativeStrategy(
        MartinAdapterConfig(
            instrument_ids=ids,
            parameters=parameters,
            candidate=candidate,
            route=route,
            cost_bps_per_side=cost_bps,
            spec_sha256=bindings["spec"],
            input_sha256=bindings["input"],
            contract_sha256=bindings["contract"],
            cell_id=bindings.get("cell", "inert"),
            initial_physical_shares_per_native_unit=initial_factors or {},
            optimize_runtime=optimize_runtime,
        )
    )
    engine.add_strategy(strategy)
    return engine, strategy
