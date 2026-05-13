from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class BuyHoldBenchmark:
    return_pct: float | None
    alpha_pct: float | None
    start_price: float | None
    end_price: float | None


def build_buy_hold_benchmark(
    frame: pd.DataFrame,
    strategy_return_pct: float,
) -> BuyHoldBenchmark:
    if frame.empty or "open" not in frame.columns or "close" not in frame.columns:
        return BuyHoldBenchmark(None, None, None, None)
    start_price = _first_positive(frame["open"])
    end_price = _last_positive(frame["close"])
    if start_price is None or end_price is None:
        return BuyHoldBenchmark(None, None, start_price, end_price)
    return_pct = ((end_price / start_price) - 1) * 100
    return BuyHoldBenchmark(
        return_pct=return_pct,
        alpha_pct=strategy_return_pct - return_pct,
        start_price=start_price,
        end_price=end_price,
    )


def _first_positive(series: pd.Series) -> float | None:
    values = [float(value) for value in series.dropna().tolist() if float(value) > 0]
    return values[0] if values else None


def _last_positive(series: pd.Series) -> float | None:
    values = [float(value) for value in series.dropna().tolist() if float(value) > 0]
    return values[-1] if values else None
