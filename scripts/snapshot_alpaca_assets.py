"""D7 step 1: one read-only snapshot of the Alpaca Trading API assets list (paper base URL).

A single ``GET /v2/assets?status=active&asset_class=us_equity`` through the same
``TradingClient(paper=True).get_all_assets`` call the repo already uses
(``open_composer/research/features/asset_metadata.py``).  No order endpoint is touched.
Saved: symbol, tradable, shortable, easy_to_borrow, marginable, fractionable, exchange,
status, asset_class, to ``data/research/equity_book/borrow/alpaca_assets_<YYYYMMDD>.parquet``.
Credentials stay in the client; they are never printed or written.

    uv run python scripts/snapshot_alpaca_assets.py
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402

OUT_DIR = ROOT / "data" / "research" / "equity_book" / "borrow"
COLUMNS = [
    "symbol",
    "tradable",
    "shortable",
    "easy_to_borrow",
    "marginable",
    "fractionable",
    "exchange",
    "status",
    "asset_class",
]


def _enum_text(value: object) -> str:
    return str(getattr(value, "value", value))


def assets_to_frame(assets: list) -> pd.DataFrame:
    """Normalize SDK ``Asset`` objects (or any object with the same attributes)."""
    rows = [
        {
            "symbol": a.symbol,
            "tradable": bool(a.tradable),
            "shortable": bool(a.shortable),
            "easy_to_borrow": bool(a.easy_to_borrow),
            "marginable": bool(a.marginable),
            "fractionable": bool(a.fractionable),
            "exchange": _enum_text(a.exchange),
            "status": _enum_text(a.status),
            "asset_class": _enum_text(a.asset_class),
        }
        for a in assets
    ]
    return pd.DataFrame(rows, columns=COLUMNS).drop_duplicates("symbol").reset_index(drop=True)


def main() -> int:
    import os

    from alpaca.trading.client import TradingClient
    from alpaca.trading.enums import AssetClass, AssetStatus
    from alpaca.trading.requests import GetAssetsRequest
    from dotenv import load_dotenv

    load_dotenv(dotenv_path=ROOT / ".env")
    key, secret = os.getenv("ALPACA_API_KEY_ID"), os.getenv("ALPACA_API_SECRET_KEY")
    if not key or not secret:
        raise SystemExit("ALPACA_API_KEY_ID / ALPACA_API_SECRET_KEY are not configured")
    client = TradingClient(key, secret, paper=True)
    assets = client.get_all_assets(
        GetAssetsRequest(status=AssetStatus.ACTIVE, asset_class=AssetClass.US_EQUITY)
    )
    frame = assets_to_frame(list(assets))
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUT_DIR / f"alpaca_assets_{datetime.now(UTC).strftime('%Y%m%d')}.parquet"
    frame.to_parquet(path, index=False)
    print(
        f"wrote {path.relative_to(ROOT)}: {len(frame)} assets, "
        f"tradable {int(frame['tradable'].sum())}, shortable {int(frame['shortable'].sum())}, "
        f"easy_to_borrow {int(frame['easy_to_borrow'].sum())}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
