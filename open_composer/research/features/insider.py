"""Column contract for the Form 4 insider feature table (H-20260916-01).

The table itself is built by ``scripts/build_insider_features.py`` into
``data/features/insider/{year}.parquet`` with the usual
``symbol, trade_date`` key, so it loads through
``panel.load_feature_panel(..., extra_feature_roots=[INSIDER_ROOT])`` and
through ``scripts/screen_factors.py``'s per-library loader unchanged.

This module holds only the names, so the builder, the feature-set registry
and any screen resolve the same list and cannot drift apart. It imports
nothing but ``pathlib``, matching ``feature_sets.py``'s rule that importing
a registry never touches the filesystem.

Semantics (the builder's module docstring is the full specification):

* Every ``*_60d`` column is a trailing 60-US-equity-session window ending
  at ``trade_date`` inclusive, over filings' **visible** dates, where a
  filing becomes visible on the next session after its ``FILING_DATE``.
* ``buy`` = ``TRANS_CODE`` ``P``, ``sell`` = ``S``; ``other_count_60d``
  holds the mechanical compensation codes ``M``/``A``/``F`` and never
  contributes to a buy or a sell.
* Share/dollar/transaction counts use one row per transaction
  (``owner_seq == 0``); ``buyers_60d``/``sellers_60d`` count distinct
  reporting owners, so a jointly filed Form 4 counts once in the sums and
  once per owner in the counts.
* ``routine_buy_60d + opportunistic_buy_60d == open_market_buy_count_60d``
  and ``opportunistic_buy_60d == cmp_opportunistic_buy_60d +
  cmp_unclassified_buy_60d``. ``opportunistic_buy_60d`` is "not routine";
  the ``cmp_*`` pair splits it into Cohen-Malloy-Pomorski's own
  opportunistic group (three prior years of visible open-market trades)
  and the structurally unclassifiable remainder.
* ``days_since_last_visible_buy`` counts trading sessions since the most
  recent visible open-market buy over the whole archive, not only the
  60-session window, and is null when the issuer has never had one.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
INSIDER_ROOT = ROOT / "data" / "features" / "insider"

#: Non-key feature columns of ``data/features/insider/{year}.parquet``, in
#: table order. ``visible_at`` is metadata (the row's own session open in
#: UTC), not a factor, and is deliberately excluded.
INSIDER_COLUMNS: tuple[str, ...] = (
    "net_buy_shares_60d",
    "net_buy_usd_60d",
    "buyers_60d",
    "sellers_60d",
    "net_buyers_60d",
    "open_market_buy_count_60d",
    "open_market_sell_count_60d",
    "other_count_60d",
    "opportunistic_buy_60d",
    "routine_buy_60d",
    "cmp_opportunistic_buy_60d",
    "cmp_unclassified_buy_60d",
    "days_since_last_visible_buy",
)

#: Columns carried in the table but not scored as factors.
INSIDER_METADATA_COLUMNS: tuple[str, ...] = ("visible_at",)
