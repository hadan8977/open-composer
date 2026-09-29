"""T-20260928-41 batch screening: single-country developed/emerging-market
equity ETF cross-sectional momentum rotation, for `scripts/screen_batch.py
--batch h20260928_41_country_etf_rotation --iteration
h20260928_41_country_etf_rotation`.

Reuses, unedited: `h20260928_40_equity_etf_menus.make_rotation_fn` (imported
directly from that sibling batch module, not copied) -- the exact same
cross-sectional-momentum-with-absolute-momentum-filter-vs-SHY mechanism S1-S3
and T-40's FACTOR/INDUSTRY menus already use. No new momentum formula,
absolute-momentum rule or weighting scheme is introduced; only the menu
(ticker list) and grid changes.

Menu, 9 single-country equity ETFs, all US-exchange-listed and Alpaca-
tradable (owner ruling 2026-09-29, `reports/research/control/
autonomous-queue.md` T-20260928-41 notes: "etf是可以的，是美股里能买到的就算" --
single-country equity ETFs are in scope, they are equity, not the cross-asset
bond/gold/commodity/dollar sleeves the owner separately dropped):
    EWJ (Japan), EWG (Germany), EWU (UK), EWA (Australia), EWC (Canada),
    EWZ (Brazil), INDA (India), EWY (South Korea), EWT (Taiwan).
Source (mechanism only, not sample/numbers): Quantpedia "Momentum Factor
Effect in Country Equity Indexes" (https://quantpedia.com/strategies/
momentum-factor-effect-in-country-equity-indexes) -- 18 MSCI country
indexes, 1975-2014, momentum + low-volatility timing; this batch borrows only
the cross-sectional-momentum-across-country-equities mechanism, never that
paper's own sample-period return/Sharpe numbers, which is why K1/K2 are
tested fresh here.

Grid: the queue task's own plan text (`autonomous-queue.md` T-20260928-41)
states "回看 {63, 252} 日 x 排名前 N {1, 2} x 月度调仓 = 8 个候选" -- but
2 (lookback) x 2 (top_n) x 1 (monthly-only) = 4, not 8; the queue text's own
arithmetic is internally inconsistent, and the executing brief for this round
states the count explicitly as 8. The only grid that reaches 8 while
preserving the stated lookback/top_n values is adding T-40's own monthly/
weekly rebalance split (`REBAL_FREQ = {"MO": "M", "WK": "W"}`, identical to
T-40's own INDUSTRY/FACTOR grid): lookback {63, 252} x top_n {1, 2} x rebal
{MO, WK} = 8. Resolved this way rather than guessing a different lookback/
top_n set, since it reuses an already-frozen grid axis from the sibling
batch instead of inventing a new one. Candidate id: `COUNTRY_L{lookback}_
N{top_n}_{MO|WK}`.

Rule per candidate (identical mechanism to T-40's `make_rotation_fn`): at
each rebalance date, rank the 9 country ETFs by
`base.momentum_score(close, str(lookback))`; take the top `top_n`; apply the
absolute-momentum filter (a pick is kept only if its score beats SHY's own
score over the same lookback); equal-weight the survivors. A candidate never
returns SHY itself -- the screening lane's own `ScreenCandidate.weights_fn`
remainder convention puts any unallocated weight into SHY automatically.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scripts" / "screen_batches"))

import h20260928_40_equity_etf_menus as t40  # noqa: E402

COUNTRY_MENU: tuple[str, ...] = (
    "EWJ",
    "EWG",
    "EWU",
    "EWA",
    "EWC",
    "EWZ",
    "INDA",
    "EWY",
    "EWT",
)

LOOKBACKS: tuple[int, ...] = (63, 252)
TOP_NS: tuple[int, ...] = (1, 2)
REBAL_FREQ: dict[str, str] = {"MO": "M", "WK": "W"}

SOURCE_CARD = "quantpedia_country_etf_momentum_rotation_2026"

SPECS: list[dict] = []
for _lb in LOOKBACKS:
    for _tn in TOP_NS:
        for _rebal_id, _freq in REBAL_FREQ.items():
            _cand_id = f"COUNTRY_L{_lb}_N{_tn}_{_rebal_id}"
            SPECS.append(
                {
                    "id": _cand_id,
                    "name": (
                        f"COUNTRY menu cross-sectional momentum rotation, "
                        f"lookback={_lb}d, top_n={_tn}, rebal={_rebal_id}"
                    ),
                    "source_card": SOURCE_CARD,
                    "universe": COUNTRY_MENU,
                    "freq": _freq,
                    "fn": t40.make_rotation_fn(COUNTRY_MENU, _lb, _tn),
                }
            )

assert len(SPECS) == 8, f"expected 8 candidates, got {len(SPECS)}"
assert len({spec["id"] for spec in SPECS}) == 8, "duplicate candidate ids"
