from __future__ import annotations

from open_composer.research import core_beta_satellite_core as _core
from open_composer.research.core_beta_satellite_core import (
    ACTIVE_BETA_ROUTE_LABEL,
    CoreBetaSatelliteDataset,
    CoreBetaSatelliteParams,
    _all_trade_symbols,
    _effective_lookback,
    _target_snapshot,
    core_beta_satellite_params_from_label,
    core_beta_satellite_target_weight_snapshot,
    load_core_beta_satellite_dataset,
)

fetch_ohlcv = _core.fetch_ohlcv
_ORIGINAL_FETCH_OHLCV = fetch_ohlcv


def run_core_beta_satellite_router_research(*args, **kwargs):
    if fetch_ohlcv is not _ORIGINAL_FETCH_OHLCV:
        _core.fetch_ohlcv = fetch_ohlcv
    return _core.run_core_beta_satellite_router_research(*args, **kwargs)


__all__ = [
    "ACTIVE_BETA_ROUTE_LABEL",
    "CoreBetaSatelliteDataset",
    "CoreBetaSatelliteParams",
    "_all_trade_symbols",
    "_effective_lookback",
    "_target_snapshot",
    "core_beta_satellite_params_from_label",
    "core_beta_satellite_target_weight_snapshot",
    "fetch_ohlcv",
    "load_core_beta_satellite_dataset",
    "run_core_beta_satellite_router_research",
]
