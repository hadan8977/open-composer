# H-20260923-14: signed high-frequency news-return underreaction drift

## Hypothesis

The signed short-window price reaction around each firm-specific news item,
aggregated into a daily "news return" (Jiang, Li & Wang 2019/2021,
`dir:high_freq_news_return_underreaction_drift`), predicts same-direction
drift over the following days on our own Alpaca/Benzinga news and SIP minute
bars, in a way that clears this project's own signal-library admission rule
(`reports/research/signal-cards/library-v1-manifest.json`). This is distinct
from the already-refuted `dir:news_attention_features`, which measured how
MUCH news arrived (count/novelty), never the SIGN of the price reaction to
it.

Three preregistered variants (no ranking between them; each judged
independently):

- **NHF01**: rank the raw daily `news_return`, direction +1, primary horizon
  5 sessions.
- **NHF02**: rank a trailing 5-session sum of `news_return` (zero-filled on
  non-news sessions against the PIT daily calendar), direction +1 -- does
  accumulated reaction over the paper's own one-week holding period carry
  more information than a single day's reaction?
- **NHF03**: event mode on large positive reactions only (`news_return >=
  0.0274`, the 90th percentile measured on the 2025-06 validation build),
  direction +1 -- the long-only analog of the paper's decile-10 winner
  portfolio.

## Failure mode

The feature could fail in several disclosed ways: (1) the 1-minute-bar
interval anchors are a discrete approximation of the paper's TAQ-tick-cleaned
15-minute returns and could be noisier; (2) ~29% of symbols named in news
have no matching minute bars locally (delisted/OTC/ticker mismatches),
shrinking the tradable cross-section; (3) the paper's sample is 2000-2012 and
no 2023-2025 independent replication of the HF construction itself was found
this pass; (4) a 2026 adaptation of the same decomposition to a day-level,
monthly-horizon, Chinese-equities design found a null result (not a like-for-
like replication failure, but a disclosed caution); (5) only the long leg is
executable for us, so even a real long-short effect in the source paper could
fail to show up in a long-only admission test.

## Measurement

`open_composer/research/signal_card.py`'s standard signal-card battery: rank
IC by horizon/year/tier, decile excess returns, a long-only top-30 book at 10
and 20bp, decay, shuffle and redated-event placebos, overlap with existing
controls (momentum, reversal, size, volatility). Admission is the rule
already preregistered in `library-v1-manifest.json`, reused verbatim, not
invented per-direction. This iteration's own measurement is narrower: the
feature build's internal identity check (`overall_return ==
(1+news_return)(1+non_news_return)-1`, verified exact, max abs error 0.0, on
the 2025-06 real-data validation build) and the point-in-time/overnight unit
tests in `tests/test_build_news_hf_reaction_script.py`.

## Stop/Pivot criterion

If the feature build's identity check or point-in-time tests fail, the build
is not run at scale. If the build succeeds but none of NHF01/NHF02/NHF03
passes the fixed admission rule when the main session runs
`signal_card.py --batch` on `reports/research/signal-cards/news-hf-v1-
manifest.json`, the verdict is "keep refuted" for
`dir:high_freq_news_return_underreaction_drift`, and it is not reopened
except with new disclosed data (e.g. a genuine 2023-2025 replication found
later) or a materially different construction -- not by re-tuning NHF01-03's
thresholds after seeing results.
