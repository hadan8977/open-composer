# External Brief: h20260929_21_ipo_lockup_expiry

Full structured entries (url, date, type, credibility, core claim, Open
Composer applicability, reflection) are in `external-brief.json`. Summary:

1. **Field & Hanka (2001, Journal of Finance, SSRN 205011)** -- the founding
   quantified result: 1,948-3,217 IPO share-lockup agreements, 3-day CAR
   approximately -1.5% to -1.8% at expiration, +40% permanent volume rise,
   effect concentrated in VC-backed names, stable across a ~1988-1997
   ten-year sample. Direct fetch 403'd; abstract numbers already verified
   verbatim in the existing registry row and reused rather than re-fetched.
2. **Gibbs & Hao (2018 JBF, working paper fetched and snapshotted this
   iteration)** -- informed short-selling evidence, PE-backed IPOs show NO
   effect (heterogeneity), and three named tail-risk counter-examples: Yelp
   +23% (documented short squeeze), PokerTek +14%, Odimo -33%.
3. **Damodaran (2019 practitioner substack, fetched and snapshotted this
   iteration)** -- explicit "not tradeable" verdict: about a third of
   lockups go the wrong way, effect too small relative to transaction
   costs. The central skeptical source this iteration's cost/placebo
   discipline must answer.
4. **I-20260929-01 intel pass** -- upstream trigger; located the mechanism,
   confirmed no prior registry/trial match, queued it as new work.
5. **directions.jsonl `dir:ipo_lockup_expiration_drift`** -- the exact
   registry row this iteration updates (same id) once results are in.
6. **Alpaca margin/short-selling docs + paper-trading docs** (already opened
   in the T-20260929-32 retriage, re-cited) -- ground the 360-day borrow
   convention and note Alpaca's own paper account does not simulate borrow
   fees, so this iteration's own costed numbers are the conservative
   reference.
7. **short-unlocked-retriage-2026-09-29.md** -- confirms no duplication with
   the concurrently-running T-20260929-32 session's work (different
   mechanism: insider-unlock Form 4 sales, not the lockup-expiration
   calendar event).

See `candidate_matrix_revisions` in external-brief.json for the three
design decisions this evidence drove (the IPO-to-L momentum filter as a
heterogeneity proxy, the 10%/15-position cap plus 2x-cost check for tail
risk, and keeping the ADV-tiered cost model and both placebo families as
hard, non-negotiable gates).
