"""Shared market breadth, benchmark trend and macro data by session close."""

from pathlib import Path

DERIVED_ROOT = Path(__file__).resolve().parents[4] / "market-data" / "derived"


def load_market_state(root: Path = DERIVED_ROOT, **kwargs):
    """Require ``known_at < decision_at`` (UTC regular close) for next-session use.

    FRED columns use prior observations from the currently published vintage.
    """
    import pandas as pd

    return pd.read_parquet(root / "market_state.parquet", **kwargs)
