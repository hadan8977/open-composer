from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, cast

import pandas as pd
from nautilus_trader.backtest.config import (
    BacktestDataConfig,
    BacktestEngineConfig,
    BacktestRunConfig,
    BacktestVenueConfig,
    ImportableFeeModelConfig,
    ImportableFillModelConfig,
)
from nautilus_trader.backtest.node import BacktestNode
from nautilus_trader.common.config import LoggingConfig
from nautilus_trader.config import ImportableStrategyConfig, StrategyConfig
from nautilus_trader.core.correctness import PyCondition
from nautilus_trader.core.data import Data
from nautilus_trader.model.custom import customdataclass
from nautilus_trader.model.data import Bar, BarSpecification, BarType, DataType
from nautilus_trader.model.enums import BarAggregation, OrderSide, PriceType
from nautilus_trader.model.events.order import OrderFilled
from nautilus_trader.model.identifiers import ClientId, InstrumentId, Symbol, Venue
from nautilus_trader.model.instruments.equity import Equity
from nautilus_trader.model.objects import Currency, Price, Quantity
from nautilus_trader.persistence.catalog.parquet import ParquetDataCatalog
from nautilus_trader.persistence.wranglers import BarDataWrangler
from nautilus_trader.trading.strategy import Strategy

from open_composer.analytics import (
    build_performance_metrics,
    evaluate_execution_reality,
    exposure_pct_from_trades,
    trade_pnls,
    trade_return_pcts,
    turnover_ratio_from_trades,
)
from open_composer.analytics.benchmark import build_buy_hold_benchmark
from open_composer.analytics.data_sanity import evaluate_backtest_data_sanity
from open_composer.engines.signal_engine import build_signal
from open_composer.expressions import evaluate_rule_block
from open_composer.models.backtest import BacktestRun, Trade
from open_composer.models.signal import Signal
from open_composer.models.strategy_spec import StrategySpec

OPEN_COMPOSER_DATA_CLIENT_ID = ClientId("OPEN_COMPOSER")


@dataclass
class _OpenTrade:
    entry_time: datetime
    entry_price: float
    shares: float
    entry_fee: float


@dataclass
class NautilusBacktestCollector:
    spec: StrategySpec
    run_id: str
    version_id: str | None
    spec_hash: str | None
    starting_equity: float
    signals: list[Signal] = field(default_factory=list)
    trades: list[Trade] = field(default_factory=list)
    total_fees: float = 0.0
    last_close: float | None = None
    equity_curve: list[float] = field(default_factory=list)
    open_trade: _OpenTrade | None = None
    trades_by_day: dict[str, int] = field(default_factory=dict)
    pending_entry: bool = False
    pending_exit: bool = False

    def __post_init__(self) -> None:
        self.equity_curve.append(self.starting_equity)

    def record_signal(self, timestamp: datetime, action: str, price: float) -> Signal:
        signal = build_signal(
            spec=self.spec,
            run_id=self.run_id,
            timestamp=timestamp,
            action=action,
            source="backtest",
            price=price,
            version_id=self.version_id,
            spec_hash=self.spec_hash,
            execution_backend="nautilus_backtest",
        )
        self.signals.append(signal)
        return signal

    def record_fill(
        self,
        *,
        order_side: OrderSide,
        timestamp: datetime,
        shares: float,
        price: float,
        commission: float,
    ) -> None:
        self.total_fees += commission
        if order_side == OrderSide.BUY:
            self.pending_entry = False
            self.open_trade = _OpenTrade(
                entry_time=timestamp,
                entry_price=price,
                shares=shares,
                entry_fee=commission,
            )
            return
        if order_side == OrderSide.SELL:
            self.pending_exit = False
            if self.open_trade is None:
                return
            gross_pnl = self.open_trade.shares * (price - self.open_trade.entry_price)
            pnl = gross_pnl - self.open_trade.entry_fee - commission
            denom = self.open_trade.shares * self.open_trade.entry_price + self.open_trade.entry_fee
            return_pct = (pnl / denom) * 100 if denom else 0.0
            self.trades.append(
                Trade(
                    entry_time=self.open_trade.entry_time,
                    exit_time=timestamp,
                    entry_price=self.open_trade.entry_price,
                    exit_price=price,
                    shares=self.open_trade.shares,
                    entry_fee=self.open_trade.entry_fee,
                    exit_fee=commission,
                    gross_pnl=gross_pnl,
                    pnl=pnl,
                    return_pct=return_pct,
                )
            )
            self.open_trade = None

    def record_bar_close(self, close_price: float) -> None:
        self.last_close = close_price
        self.equity_curve.append(self.end_equity())

    def mark_to_market_pnl(self) -> float:
        realized = sum(trade.pnl for trade in self.trades)
        if self.open_trade is None:
            return realized
        close_price = self.last_close or self.open_trade.entry_price
        unrealized = (
            self.open_trade.shares * (close_price - self.open_trade.entry_price)
            - self.open_trade.entry_fee
        )
        return realized + unrealized

    def end_equity(self) -> float:
        return self.starting_equity + self.mark_to_market_pnl()


@dataclass(frozen=True)
class NautilusBacktestArtifacts:
    run: BacktestRun
    signals: list[Signal]
    trades: list[Trade]


class OpenComposerFeatureData(Data):
    __annotations__ = {
        "instrument_id": InstrumentId,
        "factor_name": str,
        "source": str,
        "field": str,
        "value": float,
    }


OpenComposerFeatureData = customdataclass(OpenComposerFeatureData)


class OpenComposerNautilusStrategyConfig(StrategyConfig, frozen=True):
    instrument_id: InstrumentId
    bar_type: BarType
    spec: dict[str, Any]
    root_path: str
    collector_key: str
    starting_equity: float = 100_000.0
    base_currency: str = "USD"


class OpenComposerNautilusStrategy(Strategy):
    def __init__(self, config: OpenComposerNautilusStrategyConfig) -> None:
        super().__init__(config)
        self.spec = StrategySpec.model_validate(config.spec)
        self.root_path = Path(config.root_path)
        self._collector = _require_collector(config.collector_key)
        self._instrument = None
        self._history: list[dict[str, Any]] = []
        self._position_open = False
        self._custom_feature_values = {
            name: getattr(factor, "default", 0.0)
            for name, factor in self.spec.factors.items()
            if factor.source in {"llm_feature", "feature_packet"}
        }

    def on_start(self) -> None:
        self._instrument = self.cache.instrument(self.config.instrument_id)
        if self._instrument is None:
            self.log.error(f"Could not find instrument for {self.config.instrument_id}")
            self.stop()
            return
        self.subscribe_bars(self.config.bar_type)
        if self._custom_feature_values:
            self.subscribe_data(
                DataType(OpenComposerFeatureData),
                client_id=OPEN_COMPOSER_DATA_CLIENT_ID,
                instrument_id=self.config.instrument_id,
            )

    def on_data(self, data: Any) -> None:  # noqa: ANN401
        if isinstance(data, OpenComposerFeatureData):
            self._custom_feature_values[data.factor_name] = data.value

    def on_bar(self, bar: Bar) -> None:
        if bar.is_single_price():
            return

        row = {
            "timestamp": pd.Timestamp(bar.ts_event, unit="ns", tz="UTC"),
            "open": bar.open.as_double(),
            "high": bar.high.as_double(),
            "low": bar.low.as_double(),
            "close": bar.close.as_double(),
            "volume": bar.volume.as_double(),
        }
        row.update(self._custom_feature_values)
        self._history.append(row)
        frame = pd.DataFrame.from_records(self._history)
        timestamp = datetime.fromtimestamp(bar.ts_event / 1_000_000_000, tz=UTC)
        close_price = float(bar.close.as_double())
        self._collector.record_bar_close(close_price)

        entry_mask = evaluate_rule_block(
            frame,
            self.spec.entry.all,
            self.spec.entry.any,
            self.spec.factors,
            root=self.root_path,
            symbol=self.spec.primary_symbol,
        )
        exit_mask = evaluate_rule_block(
            frame,
            self.spec.exit.all,
            self.spec.exit.any,
            self.spec.factors,
            root=self.root_path,
            symbol=self.spec.primary_symbol,
        )

        if not self._position_open and not self._collector.pending_entry:
            day_key = timestamp.date().isoformat()
            day_count = self._collector.trades_by_day.get(day_key, 0)
            if bool(entry_mask.iloc[-1]) and day_count < self.spec.risk.max_trades_per_day:
                self._collector.record_signal(timestamp, "entry", close_price)
                quantity = self._order_quantity(close_price)
                if quantity <= 0:
                    return
                self._collector.pending_entry = True
                self._collector.trades_by_day[day_key] = day_count + 1
                self._buy(quantity)
            return

        stop_hit = self.spec.risk.stop_loss_pct is not None and close_price <= self._stop_price()
        take_hit = self.spec.risk.take_profit_pct is not None and close_price >= self._take_price()
        if self._position_open and not self._collector.pending_exit:
            if bool(exit_mask.iloc[-1]) or stop_hit or take_hit:
                self._collector.record_signal(timestamp, "exit", close_price)
                self._collector.pending_exit = True
                self.close_all_positions(self.config.instrument_id)

    def on_order_filled(self, event: OrderFilled) -> None:
        order_side = event.order_side
        timestamp = datetime.fromtimestamp(event.ts_event / 1_000_000_000, tz=UTC)
        shares = event.last_qty.as_double()
        price = event.last_px.as_double()
        commission = event.commission.as_double()
        self._collector.record_fill(
            order_side=order_side,
            timestamp=timestamp,
            shares=shares,
            price=price,
            commission=commission,
        )
        if order_side == OrderSide.BUY:
            self._position_open = True
        elif order_side == OrderSide.SELL:
            self._position_open = False

    def on_order_rejected(self, event: Any) -> None:  # noqa: ANN401
        self._collector.pending_entry = False
        self._collector.pending_exit = False

    def on_order_denied(self, event: Any) -> None:  # noqa: ANN401
        self._collector.pending_entry = False
        self._collector.pending_exit = False

    def on_order_canceled(self, event: Any) -> None:  # noqa: ANN401
        self._collector.pending_entry = False
        self._collector.pending_exit = False

    def on_stop(self) -> None:
        self.cancel_all_orders(self.config.instrument_id)
        self.unsubscribe_bars(self.config.bar_type)

    def _buy(self, quantity: float) -> None:
        order = self.order_factory.market(
            instrument_id=self.config.instrument_id,
            order_side=OrderSide.BUY,
            quantity=self._instrument.make_qty(Decimal(str(quantity))),
        )
        self.submit_order(order)

    def _order_quantity(self, close_price: float) -> float:
        account = self.portfolio.account(self.config.instrument_id.venue)
        if account is not None:
            balance = account.balance_total()
            if balance is not None:
                equity = balance.as_double()
            else:
                equity = self.config.starting_equity
        else:
            equity = self.config.starting_equity
        notional = equity * self.spec.risk.max_position_weight
        if close_price <= 0:
            return 0.0
        return notional / close_price

    def _entry_price(self) -> float:
        if self._collector.open_trade is not None:
            return self._collector.open_trade.entry_price
        return self._collector.last_close or 0.0

    def _stop_price(self) -> float:
        entry_price = self._entry_price()
        return entry_price * (1 - self.spec.risk.stop_loss_pct / 100)

    def _take_price(self) -> float:
        entry_price = self._entry_price()
        return entry_price * (1 + self.spec.risk.take_profit_pct / 100)


def run_nautilus_backtest(
    spec: StrategySpec,
    frame: pd.DataFrame,
    root: Path,
    *,
    run_id_value: str,
    version_id: str | None = None,
    spec_hash: str | None = None,
    start_equity: float = 100_000.0,
    backend_plan_path: str | None = None,
) -> NautilusBacktestArtifacts:
    PyCondition.is_true(
        len(spec.universe) == 1,
        "NautilusTrader adapter currently supports a single-symbol universe",
    )

    collector = NautilusBacktestCollector(
        spec=spec,
        run_id=run_id_value,
        version_id=version_id,
        spec_hash=spec_hash,
        starting_equity=start_equity,
    )
    _register_collector(run_id_value, collector)
    try:
        bar_type = _build_bar_type(spec)
        instrument = _build_equity_instrument(bar_type, spec)
        catalog_root = root / "reports" / "runs" / "nautilus" / "catalogs" / run_id_value
        catalog_root.mkdir(parents=True, exist_ok=True)
        catalog = ParquetDataCatalog.from_uri(catalog_root.resolve().as_uri())
        bars = _build_bars(frame, bar_type, instrument)
        feature_data = _build_feature_data(spec, root, instrument.id)
        catalog.write_data([instrument])
        catalog.write_data(bars)
        if feature_data:
            catalog.write_data(feature_data)

        strategy_config = ImportableStrategyConfig(
            strategy_path="open_composer.adapters.execution.nautilus_runtime:OpenComposerNautilusStrategy",
            config_path="open_composer.adapters.execution.nautilus_runtime:OpenComposerNautilusStrategyConfig",
            config={
                "instrument_id": instrument.id,
                "bar_type": bar_type,
                "spec": spec.model_dump(mode="json"),
                "root_path": str(root),
                "collector_key": run_id_value,
                "starting_equity": start_equity,
                "base_currency": "USD",
            },
        )

        venue = BacktestVenueConfig(
            name=str(bar_type.instrument_id.venue),
            oms_type="NETTING",
            account_type="CASH",
            starting_balances=[f"{start_equity:.2f} USD"],
            base_currency="USD",
            bar_execution=True,
            trade_execution=False,
            fill_model=_fill_model_config(spec),
            fee_model=_fee_model_config(spec),
        )
        engine = BacktestEngineConfig(
            strategies=[strategy_config],
            logging=LoggingConfig(log_level="ERROR", log_colors=False, print_config=False),
        )
        data_configs = [
            BacktestDataConfig(
                catalog_path=str(catalog_root.resolve()),
                data_cls="nautilus_trader.model.data:Bar",
                instrument_ids=[instrument.id.value],
                bar_types=[str(bar_type)],
            )
        ]
        if feature_data:
            data_configs.append(
                BacktestDataConfig(
                    catalog_path=str(catalog_root.resolve()),
                    data_cls=(
                        "open_composer.adapters.execution.nautilus_runtime:OpenComposerFeatureData"
                    ),
                    instrument_id=instrument.id,
                    client_id=OPEN_COMPOSER_DATA_CLIENT_ID.value,
                )
            )

        run_config = BacktestRunConfig(
            venues=[venue],
            data=data_configs,
            engine=engine,
            raise_exception=True,
            dispose_on_completion=True,
        )

        results = BacktestNode(configs=[run_config]).run()
        if not results:
            msg = "NautilusTrader backtest produced no result"
            raise RuntimeError(msg)

        result = results[0]
        end_equity = collector.end_equity()
        total_return_pct = ((end_equity / start_equity) - 1) * 100 if start_equity else 0.0
        metrics = build_performance_metrics(
            collector.equity_curve,
            spec.timeframe,
            trade_pnls=trade_pnls(collector.trades),
            trade_return_pcts=trade_return_pcts(collector.trades),
            exposure_pct=exposure_pct_from_trades(collector.trades, frame),
            turnover_ratio=turnover_ratio_from_trades(collector.trades, start_equity),
        )
        execution_reality = evaluate_execution_reality(frame, collector.trades)
        benchmark = build_buy_hold_benchmark(frame, total_return_pct)
        data_provenance = frame.attrs.get("data_source_mode")
        data_provider = frame.attrs.get("data_source_provider")
        assumptions = [
            "Signals are evaluated inside NautilusTrader on bar callbacks.",
            "Orders are market orders on the backtest engine.",
            "Position sizing uses max_position_weight against current account equity.",
            (
                "Buy-and-hold benchmark uses first available open to final close over the same "
                "data window."
            ),
            "Commission uses the instrument fee model when available.",
            "Nonzero slippage is approximated with Nautilus' probabilistic fill model.",
            "Execution reality uses conservative OHLCV-only liquidity proxies.",
            "Open positions are marked to the latest close recorded by the collector.",
            f"NautilusTrader result run_id: {result.run_id}",
            (
                "BacktestNode totals: "
                f"{result.total_orders} orders, "
                f"{result.total_positions} positions, "
                f"{result.total_events} events."
            ),
        ]
        if data_provenance:
            provider_label = str(data_provider or spec.data.source)
            assumptions.insert(
                0,
                f"Data provenance: {provider_label} {data_provenance.replace('_', ' ')}.",
            )
        if feature_data:
            assumptions.append(
                "Feature packet factors were replayed as NautilusTrader custom data events."
            )
        run = BacktestRun(
            run_id=run_id_value,
            strategy_name=spec.name,
            strategy_id=spec.name,
            version_id=version_id,
            spec_hash=spec_hash,
            strategy_backend=spec.execution.backend,
            execution_backend="nautilus_backtest",
            symbol=spec.primary_symbol,
            timeframe=spec.timeframe,
            bars=len(frame),
            signals=len(collector.signals),
            trades=len(collector.trades),
            start_equity=start_equity,
            end_equity=end_equity,
            total_return_pct=total_return_pct,
            buy_hold_return_pct=benchmark.return_pct,
            alpha_vs_buy_hold_pct=benchmark.alpha_pct,
            annualized_return_pct=metrics.annualized_return_pct,
            sharpe_ratio=metrics.sharpe_ratio,
            annualized_volatility_pct=metrics.annualized_volatility_pct,
            max_drawdown_pct=metrics.max_drawdown_pct,
            downside_volatility_pct=metrics.downside_volatility_pct,
            sortino_ratio=metrics.sortino_ratio,
            calmar_ratio=metrics.calmar_ratio,
            win_rate_pct=metrics.win_rate_pct,
            profit_factor=metrics.profit_factor,
            average_trade_return_pct=metrics.average_trade_return_pct,
            exposure_pct=metrics.exposure_pct,
            turnover_ratio=metrics.turnover_ratio,
            total_fees=collector.total_fees,
            backend_plan_path=backend_plan_path,
            execution_reality=execution_reality,
            assumptions=assumptions,
        )
        run.data_sanity = evaluate_backtest_data_sanity(
            spec=spec,
            frame=frame,
            run=run,
            trades=collector.trades,
        )
        return NautilusBacktestArtifacts(
            run=run,
            signals=collector.signals,
            trades=collector.trades,
        )
    finally:
        _unregister_collector(run_id_value)


def _build_bars(frame: pd.DataFrame, bar_type: BarType, instrument: Equity) -> list[Bar]:
    normalized = frame.copy()
    normalized["timestamp"] = pd.to_datetime(normalized["timestamp"], utc=True)
    for column in ["open", "high", "low", "close", "volume"]:
        normalized[column] = pd.to_numeric(normalized[column], errors="raise")
    normalized = normalized.sort_values("timestamp").reset_index(drop=True)
    wrangled = BarDataWrangler(bar_type, instrument).process(
        normalized.set_index("timestamp", drop=True)
    )
    return list(wrangled)


def _build_feature_data(
    spec: StrategySpec,
    root: Path,
    instrument_id: InstrumentId,
) -> list[OpenComposerFeatureData]:
    rows: list[OpenComposerFeatureData] = []
    for factor_name, factor in spec.factors.items():
        if factor.source not in {"llm_feature", "feature_packet"}:
            continue
        if not factor.path or not factor.field:
            continue
        path = Path(factor.path)
        if not path.is_absolute():
            path = root / path
        if not path.exists():
            continue
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                raw = json.loads(line)
                if not isinstance(raw, dict):
                    continue
                packet_symbol = str(raw.get("symbol", "")).upper()
                if packet_symbol and packet_symbol not in {spec.primary_symbol.upper(), "*"}:
                    continue
                value = _feature_packet_value(raw, factor.field)
                if value is None or "timestamp" not in raw:
                    continue
                numeric_value = _numeric_feature_value(value)
                if numeric_value is None:
                    continue
                timestamp = pd.Timestamp(raw["timestamp"])
                ts_event = _timestamp_nanos(timestamp)
                fetched_at = raw.get("fetched_at") or raw.get("published_at") or raw["timestamp"]
                ts_init = _timestamp_nanos(pd.Timestamp(cast(str, fetched_at)))
                rows.append(
                    OpenComposerFeatureData(
                        instrument_id=instrument_id,
                        factor_name=factor_name,
                        source=factor.source,
                        field=factor.field,
                        value=numeric_value,
                        ts_event=ts_event,
                        ts_init=ts_init,
                    )
                )
    return sorted(rows, key=lambda item: (item.ts_event, item.factor_name))


def _feature_packet_value(raw: dict[str, Any], field: str) -> Any:
    if field in raw:
        return raw[field]
    features = raw.get("features")
    if isinstance(features, dict) and field in features:
        return features[field]
    return None


def _numeric_feature_value(value: Any) -> float | None:
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    if isinstance(value, int | float):
        return float(value)
    return None


def _timestamp_nanos(timestamp: pd.Timestamp) -> int:
    if timestamp.tzinfo is None:
        timestamp = timestamp.tz_localize("UTC")
    else:
        timestamp = timestamp.tz_convert("UTC")
    return int(timestamp.value)


def _build_bar_type(spec: StrategySpec) -> BarType:
    instrument_id = InstrumentId(Symbol(spec.primary_symbol), Venue("NASDAQ"))
    bar_spec = _bar_spec_from_timeframe(spec.timeframe)
    return BarType(instrument_id, bar_spec)


def _build_equity_instrument(bar_type: BarType, spec: StrategySpec) -> Equity:
    taker_fee = Decimal(str(spec.costs.commission_pct))
    return Equity(
        instrument_id=bar_type.instrument_id,
        raw_symbol=Symbol(spec.primary_symbol),
        currency=Currency.from_str("USD"),
        price_precision=2,
        price_increment=Price.from_str("0.01"),
        lot_size=Quantity.from_str("1"),
        ts_event=0,
        ts_init=0,
        maker_fee=taker_fee,
        taker_fee=taker_fee,
    )


def _bar_spec_from_timeframe(timeframe: str) -> BarSpecification:
    mapping = {
        "1m": (1, BarAggregation.MINUTE),
        "5m": (5, BarAggregation.MINUTE),
        "15m": (15, BarAggregation.MINUTE),
        "30m": (30, BarAggregation.MINUTE),
        "1h": (1, BarAggregation.HOUR),
        "4h": (4, BarAggregation.HOUR),
        "daily": (1, BarAggregation.DAY),
        "weekly": (1, BarAggregation.WEEK),
    }
    try:
        step, aggregation = mapping[timeframe]
    except KeyError as exc:
        supported = ", ".join(mapping)
        raise ValueError(
            f"unsupported Nautilus timeframe: {timeframe}; supported: {supported}"
        ) from exc
    return BarSpecification(step, aggregation, PriceType.LAST)


def _fill_model_config(spec: StrategySpec) -> ImportableFillModelConfig:
    prob_slippage = 1.0 if spec.costs.slippage_bps > 0 else 0.0
    return ImportableFillModelConfig(
        fill_model_path="nautilus_trader.backtest.models:FillModel",
        config_path="nautilus_trader.backtest.config:FillModelConfig",
        config={
            "prob_fill_on_limit": 1.0,
            "prob_fill_on_stop": 1.0,
            "prob_slippage": prob_slippage,
            "random_seed": 7,
        },
    )


def _fee_model_config(spec: StrategySpec) -> ImportableFeeModelConfig:
    return ImportableFeeModelConfig(
        fee_model_path="nautilus_trader.backtest.models:MakerTakerFeeModel",
        config_path="nautilus_trader.backtest.config:MakerTakerFeeModelConfig",
        config={},
    )


_COLLECTORS: dict[str, NautilusBacktestCollector] = {}


def _register_collector(key: str, collector: NautilusBacktestCollector) -> None:
    _COLLECTORS[key] = collector


def _unregister_collector(key: str) -> None:
    _COLLECTORS.pop(key, None)


def _require_collector(key: str) -> NautilusBacktestCollector:
    collector = _COLLECTORS.get(key)
    if collector is None:
        msg = f"collector not registered for key: {key}"
        raise RuntimeError(msg)
    return collector
