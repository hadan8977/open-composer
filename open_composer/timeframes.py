from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

StrategyTimeframe = Literal["1m", "5m", "15m", "30m", "1h", "4h", "daily", "weekly"]

STRATEGY_TIMEFRAMES: tuple[str, ...] = (
    "1m",
    "5m",
    "15m",
    "30m",
    "1h",
    "4h",
    "daily",
    "weekly",
)

BARS_PER_YEAR: dict[str, float] = {
    "1m": 252 * 390,
    "5m": 252 * 78,
    "15m": 252 * 26,
    "30m": 252 * 13,
    "1h": 252 * 6.5,
    "4h": 252 * 1.625,
    "daily": 252,
    "weekly": 52,
}


@dataclass(frozen=True)
class TimeframeSupport:
    provider: str
    supported: tuple[str, ...]
    paper_ready: tuple[str, ...]
    caveats: tuple[str, ...] = ()


TIMEFRAME_SUPPORT: dict[str, TimeframeSupport] = {
    "sample": TimeframeSupport(
        provider="sample",
        supported=("5m", "15m", "1h", "daily", "weekly"),
        paper_ready=(),
        caveats=("sample data is workflow smoke-test evidence only",),
    ),
    "alpaca": TimeframeSupport(
        provider="alpaca",
        supported=("1m", "5m", "15m", "30m", "1h", "4h", "daily", "weekly"),
        paper_ready=("1m", "5m", "15m", "30m", "1h", "4h", "daily", "weekly"),
        caveats=("feed permissions and SIP/IEX coverage must be verified",),
    ),
    "longbridge": TimeframeSupport(
        provider="longbridge",
        supported=("1m", "5m", "15m", "1h", "daily", "weekly"),
        paper_ready=("1m", "5m", "15m", "1h", "daily", "weekly"),
        caveats=(
            "Nasdaq Basic is not consolidated SIP data",
            "historical candlestick requests are capped by account limits",
        ),
    ),
    "nautilus_trader": TimeframeSupport(
        provider="nautilus_trader",
        supported=("1m", "5m", "15m", "30m", "1h", "4h", "daily", "weekly"),
        paper_ready=("1m", "5m", "15m", "30m", "1h", "4h", "daily", "weekly"),
        caveats=("adapter parity must be verified for the selected strategy subset",),
    ),
    "sip_parquet": TimeframeSupport(
        provider="sip_parquet",
        supported=("daily",),
        paper_ready=(),
        caveats=(
            "local research archive under data/sip/, not in capabilities/registry.yaml",
            "minute-bar exposure through fetch_ohlcv is not wired yet; "
            "call open_composer.adapters.data.sip_parquet.load_sip_bars directly for minute data",
            "research_strict acquisition tier; never paper-ready by construction",
        ),
    ),
}


def supported_timeframes(provider: str) -> tuple[str, ...]:
    support = TIMEFRAME_SUPPORT.get(provider)
    return support.supported if support else ()


def timeframe_supported(provider: str, timeframe: str) -> bool:
    return timeframe in supported_timeframes(provider)


def require_timeframe_supported(provider: str, timeframe: str) -> None:
    if timeframe_supported(provider, timeframe):
        return
    supported = ", ".join(supported_timeframes(provider)) or "none"
    msg = f"unsupported {provider} timeframe: {timeframe}; supported: {supported}"
    raise ValueError(msg)


def paper_ready_timeframes(provider: str) -> tuple[str, ...]:
    support = TIMEFRAME_SUPPORT.get(provider)
    return support.paper_ready if support else ()


def require_paper_ready_timeframe(provider: str, timeframe: str) -> None:
    if timeframe in paper_ready_timeframes(provider):
        return
    supported = ", ".join(paper_ready_timeframes(provider)) or "none"
    msg = f"unsupported paper-ready {provider} timeframe: {timeframe}; supported: {supported}"
    raise ValueError(msg)


def bars_per_year(timeframe: str) -> float:
    return float(BARS_PER_YEAR.get(timeframe, 0.0))
