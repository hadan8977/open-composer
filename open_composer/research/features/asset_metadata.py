"""Alpaca asset-metadata cache used to exclude ETFs/funds from the Step 11
stock universe (docs/plan-step-11-ml-first-loop-2026-09-06.zh.md section 3.2:
"剔除 ETF/基金（符号列表用 Alpaca 资产元数据里的 asset_class/名称过滤,做不到就
用简单规则并记录）").

**Verified interactively against the live Alpaca asset list on 2026-09-06**:
``asset_class`` does NOT distinguish a common stock from an ETF -- both SPY
and AAPL report ``AssetClass.US_EQUITY``, and the ``attributes`` list
(``fractional_eh_enabled``, ``has_options``, ``options_late_close``,
``overnight_tradable``) carries nothing fund-related either. So this module
takes the plan's documented fallback: a name-keyword heuristic on the asset's
``name`` field. Calibrated against a 17-symbol spot check spanning ETFs
(SPY/QQQ/IWM/GLD/JEPI/ARKK), REITs organized as trusts or corporations
(O/AGNC/NLY), a BDC (ARCC), an ADR ("...Ordinary Shares" in the name -- BABA),
a closed-end fund (PDI), and plain common stock (AAPL/GOOGL/F/T/BRK.B) -- see
the Step 11 ledger for the full table. It is deliberately keyword-list-based
rather than "contains TRUST" or "contains SHARES": several legitimate equity
REITs use "Trust" as their legal suffix (e.g. Vornado Realty Trust, Federal
Realty Investment Trust) and ADR names routinely say "...represents N Ordinary
Shares" / "...Depositary Shares", so both bare words are false-positive traps.
Known residual imprecision (recorded, not fixed): a small/new ETF issuer not
in ``_FUND_KEYWORDS`` slips through as a "stock"; this is a one-directional
risk (contaminates the universe with a handful of extra ETFs) rather than
wrongly excluding real operating companies, which is the direction that would
silently shrink the tradable universe.

This module never opens ``.env`` itself. Like ``scripts/fetch_sip_universe.py``
before it, it reads already-loaded ``ALPACA_API_KEY_ID`` /
``ALPACA_API_SECRET_KEY`` from the process environment (populated by whichever
caller already ran ``load_dotenv()`` -- e.g. ``scripts/build_feature_universe.py``).
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import pandas as pd

DEFAULT_CACHE_PATH = Path("data/features/universe/_asset_metadata.parquet")

#: Case-insensitive substrings/patterns that flag an asset name as a fund/ETF
#: rather than a plain operating company. See module docstring for the
#: calibration set and the reasoning for what is deliberately NOT here
#: (bare "TRUST", bare "SHARES").
_FUND_KEYWORDS = re.compile(
    r"(?:"
    r"\bETF\b|\bETN\b|EXCHANGE[- ]TRADED|INDEX FUND|TRUST FUND|MUTUAL FUND|"
    r"CLOSED-END FUND|\bFUND\b|"
    r"ISHARES|SPDR|VANGUARD|PROSHARES|DIREXION|INVESCO|WISDOMTREE|VANECK|"
    r"GLOBAL X|FIRST TRUST|SCHWAB STRATEGIC|GRANITESHARES|SIMPLIFY|"
    r"YIELDMAX|ADVISORSHARES|\bPACER\b|ALPS ETF|\bARK\b|"
    r"JPMORGAN EQUITY PREMIUM|DIMENSIONAL FUND|GOLDMAN SACHS.*ETF|PIMCO.*FUND"
    r")",
    re.IGNORECASE,
)


def is_probable_fund_or_etf(name: str) -> bool:
    """Name-keyword heuristic; see module docstring for calibration and caveats."""
    return bool(_FUND_KEYWORDS.search(name or ""))


def fetch_alpaca_asset_metadata() -> pd.DataFrame:
    """One ``get_all_assets`` call for the full active US-equity list (same
    call ``scripts/fetch_sip_universe.py::load_universe`` already makes, so
    this is a known-fast, already-exercised code path -- not a new per-symbol
    loop). Columns: ``symbol, name, exchange, tradable, fractionable,
    is_probable_fund_or_etf``.
    """
    from alpaca.trading.client import TradingClient
    from alpaca.trading.enums import AssetClass, AssetStatus
    from alpaca.trading.requests import GetAssetsRequest

    key = os.getenv("ALPACA_API_KEY_ID")
    secret = os.getenv("ALPACA_API_SECRET_KEY")
    if not key or not secret:
        raise RuntimeError(
            "ALPACA_API_KEY_ID / ALPACA_API_SECRET_KEY are not configured in the "
            "process environment; run via a caller that has already called "
            "load_dotenv() (e.g. scripts/build_feature_universe.py)"
        )
    client = TradingClient(key, secret, paper=True)
    assets = client.get_all_assets(
        GetAssetsRequest(status=AssetStatus.ACTIVE, asset_class=AssetClass.US_EQUITY)
    )
    rows = [
        {
            "symbol": asset.symbol,
            "name": asset.name or "",
            "exchange": str(asset.exchange),
            "tradable": bool(asset.tradable),
            "fractionable": bool(asset.fractionable),
        }
        for asset in assets
    ]
    frame = pd.DataFrame(rows)
    frame["is_probable_fund_or_etf"] = frame["name"].map(is_probable_fund_or_etf)
    return frame


def load_or_fetch_asset_metadata(
    cache_path: Path | str = DEFAULT_CACHE_PATH, *, refresh: bool = False
) -> pd.DataFrame:
    """Load the cached metadata parquet, fetching and caching it once if absent."""
    path = Path(cache_path)
    if path.exists() and not refresh:
        return pd.read_parquet(path)
    frame = fetch_alpaca_asset_metadata()
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(path, index=False)
    return frame
