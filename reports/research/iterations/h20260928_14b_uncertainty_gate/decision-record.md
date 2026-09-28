# Decision Record: h20260928_14b_uncertainty_gate

Preregistered 2026-09-28 before any gated return was computed. Closed out
2026-09-28 after Step 2 (training on Modal) and Step 3 (gate/eval locally)
ran to completion. Card `H-20260928-31`, queue block `T-20260928-14`,
registry row `dir:regime_trust_uncertainty_gate_momentum_ranker`. Full
numeric results: `report.md`, `results.json`, `cache/*`.

## P1 (single path: uncertainty_gate_t1_book, 3 candidates)

- Path: uncertainty_gate_t1_book (u1, u2, u3)
- Decision: **stop.** 0 of 3 candidates pass stage 1. Every candidate fails
  every one of its own preregistered stage-1 stop conditions on the anchor
  window: U1 and U2 both score AUROC 0.522 (indistinguishable from a 0.50
  coin flip) for flagging above-median-future-drawdown days, both make the
  anchor-window drawdown *worse* than unguarded (not better) while their
  own 200-seed block/circular-shift placebo shows ~0 improvement, and both
  fail the owner's Sharpe-vs-vol-matched-control rule (U1 gap +0.050 < 0.10;
  U2 gap -0.219, badly negative). U3 fails its own 200-seed
  random-quintile-drop placebo (real Sharpe 0.755 below the placebo's 90th
  percentile of 1.039 -- excluding the model's own "most uncertain" quintile
  performs worse than excluding a random quintile) and the owner rule
  (gap -0.324).
- Reason: card H-20260928-31 asked whether a TRAINED ensemble-disagreement
  (DEUP-style epistemic uncertainty) signal -- distinct in mechanism from
  the already-refuted rule-based crash guard (H-20260924-02, which failed by
  reducing to de-leveraging or an arbitrary calendar schedule) and the
  already-refuted position-size meta-label (dir:meta_labeling_position_tiers)
  -- could raise the T1 book's Sharpe, not just cut its drawdown. This had
  not been tested locally before. The result here is a genuine, more basic
  negative than either prior refutation: the trained signal is not even
  directionally informative about the book's own future drawdown risk in
  this window (AUROC ~0.50), so there is no signal left for a sizing or
  selection rule to exploit, regardless of how the threshold/exposure/
  exclusion parameters are chosen.
- Next iteration suggestion: do not re-tune the three candidates' quantile
  thresholds (0.80/0.90), exposure levels (0.5/0.0), exclusion fraction
  (20%), or ensemble size (k=15) against this same window -- that would be
  exactly the post-hoc fitting `docs/research-mission.zh.md` prohibits, and
  the AUROC result (essentially 0.50) makes clear no nearby threshold choice
  would fix an absence of signal. If this direction is reopened, it needs
  one of: (a) a genuinely different feature set for the ensemble (this round
  used price-volume-only `kt.BASE_FEATURE_COLUMNS`; the source paper does
  not disclose its own feature set, so a richer feature set -- fundamentals,
  insider, short-interest, already available per T-20260928-09/10's parallel
  multi-source ranker -- is a distinguishable, not-yet-tried variant); (b) a
  different epistemic-uncertainty proxy closer to the paper's own
  rank-displacement DEUP predictor rather than plain bootstrap-ensemble
  standard deviation; or (c) new evidence (e.g. a full read of the paper's
  methods section, not just its abstract) that the paper's own construction
  differs materially from this round's operationalization in a way that
  would plausibly change the AUROC result. Absent one of those, the honest
  conclusion is that a bootstrap-LightGBM-disagreement signal on
  price-volume features alone does not carry usable information about this
  book's own drawdown risk, and effort is better spent on the owner's
  already-queued next steps (per `docs/current-view.zh.md`).
- reopen_if: a materially different feature set or uncertainty-proxy
  construction is proposed with a stated reason to expect a different AUROC
  result, or a full (not abstract-only) reading of arXiv 2603.13252's
  methods section surfaces a mechanism this round's operationalization does
  not capture.

## T1 book rebalance-day-offset note

T1 is a daily 1/20-overlapping-cohort book: a new 1/30-weighted cohort
forms every session and is held for 20 sessions, so there is no single
periodic rebalance day and therefore no rebalance-day-offset distribution
to report (unlike a monthly- or weekly-formation book). This is a property
of the book construction, not a result of this iteration.

## Timing-lag design (recorded before backtesting, unchanged by the run)

Every training label (20-session forward cross-sectional rank) is formed
using information available at the label's own formation date, with the
label itself defined so its outcome is only known 20 sessions later --
walk-forward training therefore purges (drops) the most recent >=21
trading sessions of labels before each annual retrain date, so no
not-yet-realized label leaks into training. The uncertainty ensemble's
predictions at date t use only the model trained up through the most
recent completed retrain date at or before t (an expanding, strictly
non-anticipating window). Book-level U(t) is computed from u_i(t) values
that are themselves already point-in-time (available at the close of t);
z(t) is U(t)'s quantile within U's OWN trailing 252-session history up to
and including t (never a value after t). The gate multiplier for session s
is decided from z(s-1) -- one settlement lag, applied the same way
`run_h20260924_02_momentum_crash_guard.py`'s `settle_market` lags an
independent (non-book-return) series. Confirmed by
`tests/test_h20260928_14b_uncertainty_gate.py` (settle_1session and
trailing_quantile timing-discipline tests) and by the actual first
out-of-sample year (2017, per `cache/train_meta.json`) landing well after
data availability, not before it.

## Implementation bug found and fixed before scoring

See `report.md`'s "Bug found and fixed before scoring" section:
`trailing_quantile`'s original all-window-finite requirement made z(t)
finite on only 1 of 2,692 sessions; relaxed to a 90%-coverage floor (window
length and both quantile thresholds unchanged) before any candidate was
scored. Regression-tested.
