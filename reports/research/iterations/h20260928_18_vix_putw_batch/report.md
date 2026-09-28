# T-20260928-18: VIX and PUTW data, screening the two blocked batch-2 rules

Batch: `scripts/screen_batches/h20260928_18_vix_putw.py`, run via
`scripts/screen_batch.py --batch h20260928_18_vix_putw --iteration
h20260928_18_vix_putw_batch`. Raw leaderboard:
`reports/research/screens/h20260928_18_vix_putw/leaderboard.json` (`.md`
alongside). This report's `results.json` restates that leaderboard's single
row field for field.

## Mid-task scope change

The interactive session corrected this task partway through (owner,
2026-09-28): no cross-asset strategies. VIX_REGIME_SPY_SSO_TLT's bear leg
holds TLT, so it is dropped from this iteration entirely -- never
preregistered as a candidate, and not run. It is tracked in the registry as
`dir:spy_sso_tlt_vix_regime_rotation`, status `parked`, reopen_if "owner
reopens cross-asset". This happened before any VIX-using candidate manifest
existed, so nothing about VIX_REGIME was preregistered-then-withdrawn.

## VIX data: added successfully

`data/research/vix/VIXCLS.csv` (FRED VIXCLS, public CSV, no key) --
9,581 daily observations, 1990-01-02 through 2026-09-22. Metadata
(`VIXCLS.meta.json`) documents fetch time, PIT semantics (a VIX value dated
`t` is usable only at or after the close of `t`) and the missing-data policy
(forward-fill at most 1 trading day; a 2+ day gap stays missing). Not used
by any candidate in this iteration (see scope change above); kept for a
future equity-only VIX-timing rule.

## PUTW data: confirmed unobtainable -- vendor does not serve it

Batch 2 (`reports/research/iterations/h20260928_05_registry_etf_batch2/
data-feasibility.json`) found PUTW absent from the local `data/sip/daily`
archive and noted that `scripts/fetch_symbol_list.py`'s separate-tree design
meant even fetching it there wouldn't help, since the screening harness only
reads `data/sip/daily`. This round went one step further and checked the
vendor directly (2026-09-28, via `scripts/run_capped.sh --mem 0.5G`,
read-only):

- `TradingClient(paper=True).get_asset('PUTW')` -> `APIError 40410000
  "asset not found for PUTW"`.
- `StockHistoricalDataClient.get_stock_bars(symbol='PUTW', feed='sip')` over
  the most recent 10 trading days -> 0 rows.
- Control check, identical calls: XYLD, QYLD, JEPI, JEPQ, DIVO all resolved
  `tradable=True` / `status=ACTIVE` with bars returned.

**PUTW is not served by Alpaca at all** -- not a shard-layout or
ingestion-script limitation. `scripts/fetch_sip_universe.py`'s
`load_universe()` and `scripts/update_sip_archive.py`'s
`append_new_symbols()` both source their symbol lists from the same Alpaca
trading-asset endpoint that returns "asset not found" for PUTW, so no
existing or newly-written local ingestion script -- run through the shard
layout or otherwise -- could ever have fetched it. Per the brief's explicit
rule, the shard layout under `data/sip/daily/` was not modified or
restructured to work around this.

## Candidate result

| id | skipped | reason |
|---|---|---|
| PUTW_HOLD | yes | `missing from local panel: ['PUTW']` |

`scripts/screen_batch.py` was run for real against this manifest (not
skipped preemptively): `screen_lane.py`'s own `missing_symbols()` check,
exercised inside `evaluate_candidate()`, is the harness's normal,
already-tested handling for a candidate whose universe is not in the local
panel. No return series exists; K1/K2 cannot be judged.

## Verdict

**PUTW_HOLD: not_executable (vendor data unavailable).** Not a K1/K2
refutation -- the underlying CBOE PUT-index mechanism's own evidence
(Bondarenko 2019, Ennis Knupp 2008, Cboe's own fact sheet; see
`external-brief.json`) is untouched by this result. Reopen only if a
data-ingestion owner decision adds a vendor that actually serves PUTW, or a
different Alpaca-tradable put-write/covered-call-style proxy is proposed as
a fresh candidate.

**VIX_REGIME_SPY_SSO_TLT: out of scope (owner decision), not evaluated.**
Its data blocker (missing VIX) was in fact resolved this round.

## Next iteration suggestion

None queued from this round. If the owner later authorizes a different
market-data vendor or identifies an Alpaca-tradable put-write proxy, a new
candidate can be preregistered against the same K1/K2 keep rule. The
`data/research/vix/VIXCLS.csv` series is available immediately for any
future equity-only VIX-timing candidate within the owner's current
no-cross-asset scope.
