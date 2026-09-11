"""Step 13-F/M: numerically degenerate open-library columns never reach an M-grid feature set."""

from open_composer.research.features.alpha191 import ALPHA191_COLUMNS
from open_composer.research.features.feature_sets import (
    DEGENERATE_COLUMNS,
    resolve_feature_set,
)


def test_gtja017_is_degenerate_and_dropped_from_alpha191_and_all_open() -> None:
    assert "gtja017" in DEGENERATE_COLUMNS
    assert "gtja017" in ALPHA191_COLUMNS  # the build still produces it; only the registry drops it
    alpha191_cols, alpha191_roots = resolve_feature_set("alpha191")
    assert "gtja017" not in alpha191_cols
    assert len(alpha191_cols) == len(ALPHA191_COLUMNS) - 1
    assert len(alpha191_roots) == 1
    all_open_cols, _roots = resolve_feature_set("all_open")
    assert "gtja017" not in all_open_cols
    assert "gtja016" in all_open_cols
