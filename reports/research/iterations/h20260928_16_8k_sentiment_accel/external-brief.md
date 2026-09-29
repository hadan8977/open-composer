# External Brief: h20260928_16_8k_sentiment_accel

Full machine-readable version: `external-brief.json`. 8 sources read in full (not just titles),
3 of them primary papers (Engelberg-McLean-Pontiff 2018, Tetlock 2007, Kakushadze 2016).

## Key findings

1. **LLM_Alpha** (github.com/quangkhaidataka/LLM_Alpha): fully specified sent_accel construction,
   OOS Sharpe +0.78 net of 5bp (2022-2024), but the author's own H2-2021 validation gate FAILED
   (IR=-1.50) and was self-overridden, and the alpha t-stat (+1.35) is not significant. Cheapest
   possible falsification test: zero new data needed.
2. **Independent check caught a misattribution**: the repo cites Engelberg-McLean-Pontiff (2018) as
   the source of its "negate the acceleration" sign convention. Reading EMP2018's own abstract shows
   it is about anomaly returns being larger on news/earnings days generally, not a
   sentiment-acceleration-reversal claim specifically. Tetlock (2007) is a closer real precedent
   (media pessimism -> price pressure -> reversion), but at the market level, not cross-sectionally.
   This pilot reports BOTH sign conventions rather than assuming the repo's attribution is correct.
3. **Data provenance**: 8-K filings (SEC EDGAR) and financial news (GDELT in the source; our own
   Alpaca/Benzinga news_packets store here) are both free/public; DeepSeek's API is OpenAI-compatible,
   matching this repo's existing scoring client exactly.
4. **Deferred**: the source's full purge(5)+embargo(5) walk-forward CV harness (Lopez de Prado 2018,
   summarized via Wikipedia's purged-cross-validation page since the book itself is not freely
   accessible) is NOT built in this pilot -- only the raw feature IC is checked first, per the
   direction's own decision rule.

See `direction-review.json` for the full receipt (queries, quotes, snapshot hashes) and
`reports/harness/source_cards/h20260928_16_8k_sentiment_accel.jsonl` for the verified source cards.
