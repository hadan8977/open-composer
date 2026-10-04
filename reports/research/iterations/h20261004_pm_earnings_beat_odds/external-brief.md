# External Brief: h20261004_pm_earnings_beat_odds

Structured entries are in `external-brief.json` (10 sources; 3 primary papers or preprints read in full or from the archive, 4 secondary summaries of the two SSRN earnings papers, 3 API or dataset probes). Summary:

1. **Goldstein, Li and Wang (2026-09-03, read in full)**: a one-point rise in Polymarket's Trump probability goes with 13 bp of next-day return of Trump trades (2024 election, in-sample, gross of costs). The only paper that trades a prediction-market price; one event, no replication.
2. **Diercks, Katz and Wright (FEDS 2026-010)**: Kalshi macro distributions are accurate forecasts; no stock-return test.
3. **Gomez-Cram, Guo, Jensen and Kung (SSRN 5933475, secondary only)**: contract-implied probabilities classify 77 percent one day ahead against 62 percent for analysts; an author says the contracts added a lot to their announcement regression. SSRN returned 403; coefficients unread.
4. **Rabetti, Shao and Zhang (SSRN 6649938, secondary only)**: 469 contracts, 2025-09..2026-02, 78.5 percent hit rate against a 75.9 percent beat base rate, which is weak discrimination.
5. **Polymarket Gamma and CLOB probes (2026-10-04)**: 1354 resolved earnings events with ticker, consensus EPS in the slug, end time and volume; hourly history is retrievable per resolved token in windows.
6. **Polymarket-v1 (arXiv 2606.04217 and Hugging Face, cc-by-4.0)**: an on-chain trade archive up to 2026-04, a fallback source not used first.

The evidence changed the design in four ways (see `candidate_matrix_revisions`): within-week rank instead of the raw level, costs, shorts and a shuffle gate instead of a single in-sample series, a volume and freshness filter for thin contracts, and no number from the unread earnings papers in the design.
