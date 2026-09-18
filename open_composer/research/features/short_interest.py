"""Column contract for the FINRA short-interest feature table (H-20260916-07).

The table itself is built by ``scripts/build_short_interest_features.py`` into
``data/features/short_interest/{year}.parquet`` with the usual
``symbol, trade_date`` key, so it loads through
``panel.load_feature_panel(..., extra_feature_roots=[SHORT_INTEREST_ROOT])``
and through a per-library screen loader unchanged.

This module holds only the names, so the builder, any screen and the twin-cell
driver resolve the same list and cannot drift apart. It imports nothing but
``pathlib``, matching ``feature_sets.py``'s rule that importing a registry
never touches the filesystem.

Semantics (the builder's module docstring is the full specification):

* Every row carries the **latest short-interest record whose visibility date is
  on or before the row's own ``trade_date``**. FINRA's ``settlementDate`` is
  never a visibility date: it precedes publication by 7 US equity sessions, so
  using it would be a pure look-ahead of a week and a half.
  ``visible_date = next_us_equity_session(publication_date)``, i.e. nothing may
  condition on a snapshot during its own publication session.
* ``days_to_cover`` is FINRA's own ``daysToCoverQuantity`` (short position
  divided by FINRA's average daily volume, which excludes non-media trades).
  It is null, not zero, when the record's ``average_daily_volume`` is not
  positive -- FINRA's field documents 0 as its *default*, which is not a
  measurement.
* ``short_interest_ratio`` is ``short_interest_shares`` divided by our own
  63-session average share volume at ``trade_date``
  (``dollar_adv_63 / close`` from ``data/features/daily``). **It is not
  percent-of-float**: this repo has no shares-outstanding or float source, so
  the card's "float proxy if available" branch does not apply and the ADV
  branch is the one implemented. Reading it as short interest as a fraction of
  float would be wrong by orders of magnitude.
* ``dtc_change_vs_prior`` is this record's ``days_to_cover`` minus the
  ``days_to_cover`` of the same symbol's previous published record (by
  settlement date), not a day-over-day change: the underlying series only
  moves twice a month.
* ``dtc_cross_sectional_pct`` is the percentile of ``days_to_cover`` **within
  that day's point-in-time top-500 ADV pool**, which is the pool the momentum
  book is drawn from, so a "top 20% days-to-cover" cut means the same thing in
  the screen and in the gate. Rows whose symbol is in the 501-1000 band are
  scored against the same top-500 reference distribution rather than against
  their own band, so the column has one meaning everywhere.
* ``staleness_days`` counts US equity sessions from the record's
  ``visible_date`` to ``trade_date`` (0 on the first session the record may be
  used). It is a sawtooth that resets twice a month and is published mostly as
  a negative control: anything a days-to-cover column "predicts" that this
  column predicts equally well is a calendar artifact, not short-interest
  information.
* Metadata columns (``settlement_date``, ``publication_date``, ``visible_date``,
  ``short_interest_shares``, ``finra_average_daily_volume``, ``adv_shares_63``,
  ``si_record_present``) are not factors and are excluded from
  :data:`SHORT_INTEREST_COLUMNS`, which is what a screen's multiple-testing
  denominator counts.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SHORT_INTEREST_ROOT = ROOT / "data" / "features" / "short_interest"

#: Non-key feature columns of ``data/features/short_interest/{year}.parquet``,
#: in table order. These five are the card's own list.
SHORT_INTEREST_COLUMNS: tuple[str, ...] = (
    "days_to_cover",
    "short_interest_ratio",
    "dtc_change_vs_prior",
    "dtc_cross_sectional_pct",
    "staleness_days",
)

#: Point-in-time provenance and raw inputs kept next to the factors so a
#: report can quote coverage and staleness without reopening the raw archive.
SHORT_INTEREST_METADATA_COLUMNS: tuple[str, ...] = (
    "settlement_date",
    "publication_date",
    "visible_date",
    "short_interest_shares",
    "finra_average_daily_volume",
    "adv_shares_63",
    "si_record_present",
)

#: The cross-sectional pool ``dtc_cross_sectional_pct`` is ranked within, and
#: the pool the momentum book is selected from.
CROSS_SECTIONAL_POOL_TOP_N = 500

#: The "avoid" condition of the card: days-to-cover in the highest 20% of the
#: top-500 cross-section. One number, defined once, so the pre-check, the
#: screen and the gate cannot disagree about what "top 20%" means.
AVOID_PERCENTILE_THRESHOLD = 0.80
