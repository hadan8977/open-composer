from __future__ import annotations

from open_composer.research import beta_router_core as _core
from open_composer.research.beta_router_core import (
    BetaRouterDataset,
    BetaRouterMetrics,
    BetaRouterParams,
    _effective_lookback,
    backtest_beta_router_params,
    beta_params_from_label,
    beta_target_weight_snapshot,
    load_beta_router_dataset,
)

fetch_ohlcv = _core.fetch_ohlcv
_ORIGINAL_FETCH_OHLCV = fetch_ohlcv


def run_beta_exposure_router_research(*args, **kwargs):
    if fetch_ohlcv is not _ORIGINAL_FETCH_OHLCV:
        _core.fetch_ohlcv = fetch_ohlcv
    return _core.run_beta_exposure_router_research(*args, **kwargs)


__all__ = [
    "BetaRouterDataset",
    "BetaRouterMetrics",
    "BetaRouterParams",
    "_effective_lookback",
    "backtest_beta_router_params",
    "beta_params_from_label",
    "beta_target_weight_snapshot",
    "fetch_ohlcv",
    "load_beta_router_dataset",
    "run_beta_exposure_router_research",
]
