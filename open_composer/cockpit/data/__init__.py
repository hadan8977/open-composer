"""Read-only data aggregation layer for the cockpit.

`catalog.py` moved here from the old dashboard package's catalog module (T1).
`health.py` (T3) is a sibling module in this same package -- it is imported by
the cockpit's always-resident FastAPI process and has none of `catalog.py`'s
dependencies (no strategy specs, no paper controls, no pandas).

The names below are exported lazily (PEP 562 module `__getattr__`) rather than
with a top-level `from .catalog import ...`, because `catalog.py` pulls in
most of `open_composer.models` / `open_composer.paper_controls` /
`open_composer.strategy_*`, which pull in pandas/numpy -- measured at roughly
90MB resident just to import, on this box. A plain package-level import runs
`__init__.py` (this file) before any sibling module, so an eager import here
would tax at every submodule of this package, including `health.py`, even
though nothing in this repo actually imports these names from
`open_composer.cockpit.data` (every caller uses
`open_composer.cockpit.data.catalog` directly; see `cli.py` and
`tests/test_cockpit_catalog.py`). Keep it lazy so that stays true without
carrying the cost.
"""

from __future__ import annotations

from typing import Any

__all__ = [
    "DashboardCatalogArtifacts",
    "build_dashboard_catalog",
    "build_feature_packet_records",
    "write_dashboard_catalog",
    "write_dashboard_review_markdown",
]


def __getattr__(name: str) -> Any:
    if name in __all__:
        from open_composer.cockpit.data import catalog

        return getattr(catalog, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
