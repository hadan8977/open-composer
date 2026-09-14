"""Timeframe-agnostic bar-cycle execution plumbing (Step 14).

Plan: ``docs/plan-step-14-timeframe-agnostic-bar-cycle-runner-2026-09-11.zh.md``.
Three protocols so any StrategySpec timeframe (1m/5m/15m/30m/1h/4h/daily) can
be run through one runner (``scripts/run_bar_cycle.py``) instead of a new
one-off script per cadence: :mod:`open_composer.execution.bar_source`
(``BarSource``) and :mod:`open_composer.execution.signal_engine`
(``SignalEngine``).
"""
