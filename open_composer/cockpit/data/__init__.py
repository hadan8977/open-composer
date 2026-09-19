"""Read-only data aggregation layer for the cockpit.

Moved from the old dashboard package's catalog module.
"""

from open_composer.cockpit.data.catalog import (
    DashboardCatalogArtifacts,
    build_dashboard_catalog,
    build_feature_packet_records,
    write_dashboard_catalog,
    write_dashboard_review_markdown,
)

__all__ = [
    "DashboardCatalogArtifacts",
    "build_dashboard_catalog",
    "build_feature_packet_records",
    "write_dashboard_catalog",
    "write_dashboard_review_markdown",
]
