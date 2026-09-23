# External brief: h20260923_14_news_hf_reaction

Direction `dir:high_freq_news_return_underreaction_drift`
(`reports/research/harvest/directions.jsonl`), evidence
`reports/research/intel/I-20260923-07-owner-five-directions-wave.md` section
4. Full source list with quotes: `external-brief.json`; the subset bound to
verified snapshots and quote-matched source cards: `direction-review.json`.

## What was read

The construction was pinned from the authors' own 2019 working-paper draft
("News Momentum", Hao Jiang, Sophia Zhengzi Li, Hao Wang, hosted at Duke's
economics seminar archive), read by direct PDF page rendering since the
fetch tooling could not extract machine-readable text from this specific
file. The same construction was later published as "Pervasive underreaction:
evidence from high-frequency data", Journal of Financial Economics 141
(2021): 573-599 -- confirmed independently via Hao Jiang's own CV (a
different PDF, found while searching for a free full-text copy) and via
Crossref's bibliographic record for the SSRN DOI, whose abstract matches the
working-paper draft's abstract verbatim.

## What was pinned, with sources

- Window: 1 overnight interval (prior 4:00pm close to current 9:45am price)
  + 25 intraday 15-minute intervals (9:45am-4:00pm).
- News-to-interval rule: regular-hours news -> same-interval 15-minute
  return; weekend/holiday/pre-9:45/post-4:00pm news -> the nearest
  subsequent overnight interval.
- Daily aggregation: compound the news-flagged intervals into `news_return`,
  the rest into `non_news_return`; the two multiply out to the plain
  close-to-close return exactly.
- Sort/holding: decile sort at the close, equal-weighted, one-week
  overlapping holding period; gross long-short spread 3.34%/month
  (t=11.72), FFC4 alpha 3.37%/month, 2000-2012.
- Overnight news is more than half the paper's sample -- corroborated
  independently on our own data (57.1% of 2024+ news arrives outside regular
  hours).

## What was NOT found

No 2023-2025 independent replication or critique of the HF construction
itself. One 2026-04 working paper ("Dissecting Momentum in China") builds on
the same news/non-news decomposition idea but at day-level (not 15-minute)
granularity, monthly (not weekly) horizon, on Chinese equities, and finds a
null result (0.10%/month, t=0.31) -- a disclosed caution about adaptation
risk, not a like-for-like refutation. The ~18bp-cost/~1.37%-net figure
already carried in the direction registry could not be re-verified against
the working-paper draft's readable sections (no transaction-cost analysis
found there); flagged rather than silently repeated.

## Local data facts (see data-feasibility.json for full detail)

News: 684,876 articles, effective coverage 2024-01-01+, second-level
`visible_at` precision confirmed, 57.1% outside regular trading hours.
Minute bars: 2023+, confirmed already split-adjusted. Symbol match: ~70.6%
of news-mentioned symbols have matching minute bars (one-month probe,
January 2024). One real month built end-to-end (2025-06): 10,073 rows, 3,279
symbols, exact identity check, zero nulls/infs.
