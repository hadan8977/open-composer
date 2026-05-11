"""Execution backend adapters."""

from open_composer.adapters.execution.nautilus_trader import (
    build_nautilus_backtest_plan,
    build_nautilus_paper_plan,
    build_nautilus_trader_plan,
    nautilus_trader_available,
    write_nautilus_backtest_plan,
    write_nautilus_paper_plan,
    write_nautilus_trader_plan,
)


def run_nautilus_backtest(*args, **kwargs):
    from open_composer.adapters.execution.nautilus_runtime import run_nautilus_backtest as _run

    return _run(*args, **kwargs)


__all__ = [
    "build_nautilus_backtest_plan",
    "build_nautilus_paper_plan",
    "build_nautilus_trader_plan",
    "nautilus_trader_available",
    "run_nautilus_backtest",
    "write_nautilus_backtest_plan",
    "write_nautilus_paper_plan",
    "write_nautilus_trader_plan",
]
