# Decision record: h20260923_13_orb_stocks_in_play

## Path

`orb_stocks_in_play_screen`, three preregistered candidates (SIP01 long-only at the paper's own
parameters, SIP02 long-only at a stricter liquidity floor, SIP03 a long-short diagnostic never
eligible for promotion), plus two preregistered controls (RD random-direction, RL random-non-in-
play-liquid-stock) and one reused reference (the already-refuted ETF-ORB simplification).

## Decision

**FINAL (reviewed by the main session 2026-09-24; see the review note at the end).**

- Decision: stop (keep refuted). SIP01 and SIP02 -- the two promotable long-only candidates --
  were backtested on both completed windows (`select`, 2023-09-18..2025-12-31, frozen; `report_2026`,
  2026-01-02..2026-09-17, reported for continuity only) at the primary cost cell (10bp/side,
  same-bar-conservative stop fill) and against the RD/RL placebo controls, exactly as preregistered
  in `search-space.json`. **Neither candidate clears a single one of the two preregistered
  `select_window_frozen` gates** (e: CAGR >= 50% and max DD >= -35% at 10bp; f: beat >= 90% of the
  combined RD+RL placebo draws) -- 0 of 3 evaluated sub-checks pass for SIP01, 0 of 3 for SIP02:
  - SIP01: CAGR -27.1% (need >= 50%), max DD -51.3% (need >= -35%), placebo-beat-rate 50% (need
    >= 90%; SIP01 beats its RD control (-27.1% vs RD median -42.9%) but loses to its RL control
    (-27.1% vs RL median -22.5%), so 1 of 2 controls beaten, not 2 of 2).
  - SIP02: CAGR -19.7% (need >= 50%), max DD -39.3% (need >= -35%), placebo-beat-rate 50% (SIP02
    also loses to its own RL control: -19.7% vs RL median -5.8%).
  - Both candidates are unambiguously negative in `report_2026` too (SIP01 -18.2% CAGR/-2.96
    Sharpe, SIP02 -23.4% CAGR/-6.05 Sharpe), so this is not an artifact of one window.
  - Cost sensitivity does not rescue either candidate: even at `commission_only` (zero bps, the
    paper's own cost convention), SIP01 select is -12.5% CAGR and SIP02 select is -6.6% CAGR --
    both still deeply negative before any bp-based cost is applied.
  - Per `search-space.json`'s own `fallback_if_none_pass`: **"keep refuted
    (dir:orb_stocks_in_play_relative_volume stays closed)"** -- this is that fallback, triggered
    exactly as pre-specified, on data that did not exist when the rule was written.
  - This matches `hypotheses.md`'s own preregistered Stop/Pivot criterion verbatim: "If, at the
    backtest step, neither SIP01 nor SIP02 clears the adoption rule ... the verdict is 'keep
    refuted' ... not reopened except with new disclosed data, a new published selection rule, or a
    materially resolved feasibility gap -- not by re-tuning SIP01/SIP02's filters after a partial
    result." No goalposts were moved and no thresholds were adjusted after seeing these results.
- SIP03 (long-short, never promotable, diagnostic only) is also deeply negative on both completed
  windows (select -82.4% CAGR / -18.90 Sharpe at 10bp; report_2026 -77.2% CAGR / -13.36 Sharpe) and
  even at `commission_only` cost, matching the paper's own cost model exactly (select -50.6%,
  report_2026 -45.8%) -- but **this cannot yet be read as "the paper's edge is gone,"** because
  design (2016-2022, the only window overlapping the paper's own 2016-2023 study period) has not
  been run in this pass. Until design exists, SIP03's poor number only says "this candidate loses
  money in a period the paper never claimed to cover" -- it does not distinguish an unfaithful
  replication from a decayed edge. See `report.md`'s "SIP03 fidelity vs. the published paper"
  section for the full breakdown and the resumable design-window command.
- The design-window run (still pending, per the task's phased scope for this pass) is **not**
  a reopening of the promotion question above -- `select_window_frozen` is fully evaluated and
  fails outright regardless of what design shows. Running design remains worthwhile purely as the
  disclosed fidelity diagnostic already named in `report.md`, and as reusable negative/positive
  evidence for any future paper-fidelity question in this author lineage, at the resumable cost
  already quoted in `report.md`'s "Window status" section (three capped `run_capped.sh` stage
  invocations plus a cheap report rerun).

## Reason

Both promotable candidates were run to completion on the frozen select window and the reported
2026-to-date window, at the exact preregistered primary cost cell, stop-fill variant, position
sizing (`candidate-manifest.json`'s per-candidate `leverage_cap`), and RD/RL control design -- no
rule, parameter, window, candidate, or gate was changed to produce or interpret this result. The
select-window gates were preregistered specifically to answer the promotion question without
requiring the design window, and they answer it decisively: both candidates miss every sub-check,
by wide margins (not a near-miss on any one gate), and neither beats a same-mechanics random-stock
control on this data. Per the research mission's own rule against relaxing thresholds after seeing
results ("不事后放宽门槛") and against reopening a refuted path without new disclosed information
("已被否定的路线，只有新增可指认的信息...才能重开"), the correct action now is to record this as
refuted for promotion, not to defer the call until design is available or to adjust the gate to a
narrower claim.

## Deviations and notes

- The individual-stock paper describes no profit target; this dossier removes the 10R target this
  project's own ETF-proxy script (`scripts/run_h20260918_02_orb_etf.py`) added by analogy from a
  different paper -- a disclosed correction, not a departure from the primary source.
- Leverage cap is preregistered at a house default of 1.0x for SIP01/SIP02 (a disclosed departure
  from the paper's own 4x), pending an explicit broker-authorization decision on margin/PDT
  eligibility for the account this would eventually paper-trade from; SIP03 uses the paper's own
  4x for fidelity-checking purposes only.
- The published 2.81 Sharpe headline is a combined long+short number with no long-only split ever
  reported; SIP01/SIP02 (long-only, the primary candidates) are explicitly not expected to
  reproduce it, and SIP03 (long-short) exists only to sanity-check implementation fidelity, never
  for promotion.

### Deviations disclosed during the backtest pass (this round)

- Doji is `candle_open == candle_close` exactly (the paper's own rule), correcting a 5%-of-range
  approximation used in this project's earlier ETF-proxy script -- a disclosed correction, not a
  change to any preregistered rule of this dossier.
- **2023 minute-archive coverage bug, found and fixed mid-pass:** an earlier "prefer the month-
  sharded layout exclusively" fix (predating this backtest run) silently dropped ~40% of 2023
  symbol-day coverage (453,076 rows), because 2023 -- uniquely among 2016-2026 -- has bars split
  across a legacy whole-year shard and a month-sharded layout that do **not** fully duplicate each
  other, contradicting this project's own adapter-module docstring. Caught via direct parquet
  footer inspection before it reached the select-window results; fixed with a two-pass
  month-primary + legacy-fallback read (Stage 1 aggregate level and Stage 3 per-day level), and
  the 2023 cache and every downstream selection/outcome file were rebuilt and re-verified. No
  preregistered rule, parameter, or window changed -- this was a data-completeness bug in reading
  already-preregistered inputs, disclosed per the task's data-integrity hard rule.
- Stage 2/3 needed several memory- and runtime-reduction passes (categorical dtypes, a
  mathematically-exact per-year merge split verified byte-identical to the single-merge baseline, a
  date-range pre-trim with lookback margin, and a per-(shard,symbol) read cache for Stage 3) to fit
  this box's memory cap without changing any simulated value -- each was verified against an
  unoptimized baseline (or by spot-checking known symbols/dates) before being trusted for the real
  run. These are implementation-efficiency changes only, not changes to the preregistered mechanism.
- A new "Trade economics" table (gross R/trade, capped gross R/trade, net R/trade, win rate,
  cost-in-R distribution, both stop-fill variants) and a "SIP03 fidelity vs. the published paper"
  section were added to `report.md` at the coordinator's request, on top of the preregistered
  metrics -- reporting additions only, no effect on the gate evaluations above. While building the
  first table, an internal-consistency bug was found and fixed: the existing `r_multiple`/"gross R"
  field is a theoretical, uncapped (full-1%-risk-sized) R-multiple that does not shrink when
  `leverage_cap` binds, so it did not reconcile against `cost_r`/net R for SIP01/SIP02 (whose 1.0x
  cap binds on nearly every trade against a tight 10%-of-ATR14 stop -- capped gross R/trade runs
  roughly 35-65% of the theoretical figure's magnitude in every completed cell). A new
  `sized_gross_r_multiple` field (the actual, leverage-capped position's gross R) was added so
  `capped gross R - cost-in-R == net R` holds exactly per trade; this is additive (nothing existing
  was removed or redefined) and covered by two new regression tests
  (`test_sized_gross_r_reconciles_with_cost_r_and_net_r_when_cap_binds`,
  `test_sized_gross_r_equals_uncapped_r_when_cap_does_not_bind`). This is itself a finding worth
  keeping: for a 1.0x leverage cap against a 10%-of-ATR stop, position-size capping is a
  first-order drag on realized returns, comparable in size to (and separate from) the transaction-
  cost drag -- relevant to any future candidate in this family that considers raising the cap.

## Next iteration suggestion

This specific candidate set (SIP01/SIP02/SIP03 exactly as preregistered in `candidate-
manifest.json`) is closed per `search-space.json`'s `fallback_if_none_pass`. Per `hypotheses.md`'s
own Stop/Pivot criterion, `dir:orb_stocks_in_play_relative_volume` is not reopened except with new
disclosed data, a new published selection rule, or a materially resolved feasibility gap -- not by
re-tuning SIP01/SIP02's filters after this partial-window result, and not by treating the still-
pending design window as a reason to defer or soften this call.

Two bounded, optional follow-ups remain, neither of which reopens the promotion question:
1. Run the design window (2016-01-04..2022-12-30) purely as the disclosed SIP03-vs-paper fidelity
   diagnostic named in `report.md` -- resumable with the three `run_capped.sh` commands already
   printed in `report.md`'s "Window status" section plus a report rerun. This would tell us whether
   the paper's own headline is reproducible at all in this implementation, independent of whether
   the mechanism still works today; it is knowledge for the next paper-fidelity question in this
   author lineage, not a reopening of this direction.
2. The RL-control finding -- both SIP01 and SIP02 lose to a same-mechanics random-liquid-stock
   control on the select window -- is reusable negative evidence: the top-20-by-relative-volume
   selection step itself appears to subtract value versus no selection at all, on this recent data.
   Any future gap/volume-scanner-style selection idea should be checked against this finding before
   new compute is spent on a structurally similar ranking mechanism.


## Main-session review note (2026-09-24) -- final

The verdict **stop** stands, and it does not depend on the stop-fill assumption.

**The stop-fill sensitivity is large.**
- SIP01 at 10 bp, `same_bar_conservative`: select -27.1%/yr, 2026 -18.2%/yr.
- SIP01 at 10 bp, `one_bar_late`: select -2.2%/yr, 2026 +23.0%/yr.
- SIP03 at commission-only, `one_bar_late`, select: Sharpe 3.75, close to the paper's 2.81. The paper's result looks reproducible only under lenient intrabar sequencing.

**Neither variant is realistic.**
- `same_bar_conservative` assumes the stop fires whenever the entry bar's range touches it, which is pessimistic.
- `_simulate_sip_outcome` fills stops at `stop_loss_price` even when a bar opens beyond the stop, so gap-throughs are filled too favourably in both variants.
- `one_bar_late` also never checks the entry bar's adverse move. Its losses are effectively capped near 1R when the real exit would be worse, so it is optimistic.
- The truth lies between the two and would need sub-minute (tick) data for the entry minute.

**Why the verdict survives.** Even the optimistic `one_bar_late` fills leave SIP01/SIP02 far from the frozen gates at the 1.0x cap:
- CAGR must be >= 50% (G1) or >= 30% with Sharpe >= 2 (G1');
- the select window is negative for both candidates at 10 bp.

A tick-resolved fill study therefore cannot change promotion and is not queued.

**Reopen only if:**
- the owner allows leverage above 1x for this sleeve (the paper uses 4x), and a tick-resolved fill model shows a positive select window at 10 bp;
- or a published post-2023 live record of the paper's rules appears.
