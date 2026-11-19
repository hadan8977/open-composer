"""SEC shares and estimated float at the daily SIP universe's decision open."""

from pathlib import Path

import pandas as pd

from open_composer.adapters.data.sip_parquet import MARKET_DATA

FILENAME = "shares_outstanding.parquet"


def load_shares_outstanding(root: Path = MARKET_DATA / "derived", **kwargs) -> pd.DataFrame:
    """Read by (session, security_id), using parquet filters for a date range.

    Shares outstanding come from the SEC cover page. Estimated float divides
    reported public float USD by the as-of raw close. Both counts use session
    split units. Each disclosure retains its own acceptance time and accession.
    """
    return pd.read_parquet(root / FILENAME, **kwargs)
