# External brief: h20260923_13_orb_stocks_in_play

Individual-stock opening-range breakout filtered by opening relative volume ("Stocks in Play"),
Zarattini, Barbon & Aziz, "A Profitable Day Trading Strategy For The U.S. Equity Market" (SSRN
4729284, first version 2024-02-16). Read in full from the primary PDF this pass (not just the
abstract or a secondary paraphrase): 46KB of extracted text, every section, references included.

## What the paper actually says (with the exact rules, not a summary of a summary)

Universe: ~7,000 NYSE+Nasdaq stocks, 2016-01-01..2023-12-31, sourced from CRSP with IQFeed
intraday data, explicitly free of survivorship bias ("For instance, Twitter, which was delisted on
October 27, 2022, is included in our database") and explicitly **unadjusted** for splits/dividends
("this intraday data remained unadjusted for stock splits or dividends, ensuring that the database
was not influenced by any retrospective price adjustments"). Base eligibility: price>$5, 14-day
average volume>=1,000,000 shares/day, 14-day ATR>$0.50. Stocks-in-Play adds: Relative Volume (first
5-minute volume / trailing-14-day average of the same window) >=100%, trade only the top 20 by that
ratio.

Mechanics: 5-minute opening range (09:30-09:34:59 ET); a **stop order** (paper's own words: "not to
be confused with a stop loss order") is placed at the range's own high or low in the direction of
that range's move; an exact-open-equals-close doji places no order; the protective stop is 10% of
the 14-day ATR from the executed entry; if not stopped, the position closes at 4:00pm ET. **No
profit target is described anywhere in the individual-stock section.** Sizing: 1% of the capital
deployed to a position is put at risk per trade; maximum leverage 4x ("in accordance with...US
FINRA-regulated brokers"). Starting capital $25,000; commission $0.0035/share (Interactive Brokers
Pro-Tiered, Dec 2023).

Reported results, 2016-2023, **long and short combined** (no split ever published): Base strategy
(no relative-volume filter) -- 29% total return, 3.2% annualized, Sharpe 0.48, max drawdown 13%.
Stocks-in-Play (top-20 by relative volume) -- 1,637% total, 41.6% annualized, Sharpe 2.81, max
drawdown 12%, annualized alpha 35.8%, beta 0.00. S&P 500 buy-and-hold over the same window -- 198%
total, 14.2% annualized, Sharpe 0.78, max drawdown 34%.

## Where the independent replication agrees, and where it does not

QuantConnect's research post (`quantconnect.com/research/18444`) reimplements the mechanism in C#
and confirms the shape: a `StopMarketOrder` at the opening range's high/low, the identical
relative-volume formula, a leverage-scaled per-slot sizing formula that resolves the paper's own
less explicit sizing language. It differs in two disclosed ways: (1) it substitutes "the 1,000 most
liquid US Equities... above $5/share... ATR>$0.50" for the paper's $1,000,000-share-volume floor,
explicitly because "any universe size we selected produces a Sharpe ratio above 2" in their own
sweep, not because it is equivalent; (2) it backtests **only 2016**, "the first year of the paper's
backtest period," reporting a 2.396 Sharpe against a 0.836 Sharpe SPY benchmark over that single
year -- not multi-year evidence. The same page's own comment thread surfaces two further,
unverified but concrete risks: a QuantConnect user (Yuri Lopukhov) found that minute-resolution
backtests place the protective stop one bar later than live trading would ("entry order may be
filled at 9:35:01... in backtesting it will be placed at 9:36:00"), and another user (AleNoc)
reported Alpaca paper trading rejecting some of this strategy's stop orders as a "wash trade."

The same author group's own 2026-07-08 follow-up (paywalled preview read) studied the **plain
single-ETF** simplification on SPY 2008-2025 and found it "fails to generate meaningful net-of-fee
returns" in its vanilla form -- consistent with, not contrary to, this project's own already-
refuted `dir:orb_etf_opening_range_breakout` (H-20260918-02/L-20260918-02: random-direction placebo
captured 92.7-92.9% of real OOS return). No fresher-than-2024 evidence specific to the
individual-stock Stocks-in-Play mechanism was found this pass.

## Why this is a genuinely different question from what this project has already refuted

`dir:orb_etf_opening_range_breakout` tested a fixed-symbol ETF breakout with no cross-sectional
selection step and failed because the residual return was generic intraday beta, not an
opening-range signal (caught by a random-direction placebo). This iteration is scoped, per the
registry row's own `reopen_if` clause, to a mechanistically different question: does the
relative-volume selection layer itself add anything beyond generic intraday beta in liquid,
volatile names? Two controls are preregistered specifically to test that: RD (same selection,
random direction) repeats the ETF study's own successful placebo; RL (same mechanics, random
non-in-play liquid stocks) is new here and targets the selection layer directly -- the one
ingredient the ETF study could not test because it has no selection step to ablate.
`dir:cross_sectional_gap_fade` (a related Concretum mechanism, `not_executable`) found its edge
concentrated in an illiquid short leg this project cannot trade -- a structural reminder reflected
in SIP02's stricter liquidity floor and in scoping SIP03 (long-short) as a diagnostic only, never
promotable, given the paper's own headline is a combined long+short number with no long-only split
ever reported.

## Data feasibility: what this pass found, concretely

`scripts/fetch_sip_universe.py`'s `load_universe()` calls Alpaca's `get_all_assets(status=ACTIVE,
asset_class=US_EQUITY)` -- a **current** tradable-asset snapshot, not a point-in-time historical
listing. The only survivorship-bias-corrected archive found locally, `data/sip-delisted/` (~4,833
symbols per `by_year/_MANIFEST.json`), is **daily-bar only** -- direct listing confirms no `minute`
subdirectory exists anywhere under it. `data/sip/minute/_LAYOUT.json` carries its own disclosed
warning that shards 0-316 of each year were written under an earlier, different batch-size layout
and "hold a different symbol slice than their index implies under the current layout." `data/sip-
hist/minute` (2016-2022, the proposed design window) has no per-symbol shard index at all. And
`fetch_sip_universe.py` requests `adjustment="all"` (fully split+dividend adjusted), while the
paper explicitly used unadjusted data. None of these four facts were previously verified by this
project for this direction; the registry row's own status before this pass was "feasibility
unresolved -- needs a small dev-period check," and this brief is that check's evidence trail, not
its resolution -- data-feasibility.json accordingly authorizes zero evaluation runs this pass and
names each gap as the concrete next step.

## Sources

See `direction-review.json` (8 sources, each bound to a verified card with a snapshot sha256 and a
verbatim quote) and `reports/harness/source_cards/h20260923_13_orb_stocks_in_play.jsonl`. Snapshots
under `sources/`: `orb_paper.pdf` / `orb_paper.text.txt` (the primary paper, full text), `orb_qc.html`
/ `orb_qc.text.txt` (QuantConnect replication and its comment thread), `orb_author_2026.html` /
`orb_author_2026.text.txt` (the 2026-07-08 SPY-only self-critique preview) -- all copied byte-
identical from this project's own 2026-09-21 fetch (`reports/research/intel/sources/20260921-
alternatives/`), re-verified by hash this pass rather than re-fetched, per the mission's "reuse
existing implementations...before allocating compute" rule.
