# Dyl, Yuksel & Zaynutdinova (2019), "Price reversals and price continuations following large price movements", Journal of Business Research 95, pp. 1-12

Fetched: 2026-09-29 via WebSearch (Claude built-in). Listings: ScienceDirect `https://www.sciencedirect.com/science/article/abs/pii/S014829631830420X` (403 on WebFetch, abstract indexed via search only), SSRN working paper `https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3468645` (403 on WebFetch), RePEc listing `https://ideas.repec.org/a/eee/jbrese/v95y2019icp1-12.html`. This is the **2015-era replication** the brief's "search once more for 2015-2026 replications" asked for -- the newest independent test of the Chan/Savor mechanism located this pass; no post-2020 replication was found (consistent with the 2026-09-29 intel pass's finding).

## Claim (abstract level, via WebSearch synthesis of the indexed abstract -- not independently read in full; see limitations)

- Sample: extreme one-day price changes, **1986-2015**.
- Consistent with overreaction/underreaction hypotheses: investors **overreact to non-information-based price movements** (-> reversal) and **underreact to public announcements with firm-specific information** (-> continuation/drift). Same qualitative pattern as Chan (2003) and Savor (2012), independently re-tested through 2015.
- **Smaller firms and firms with lower institutional ownership** are more likely to show reversals (vs. continuations), and the **magnitude of both reversals and continuations is larger** for smaller/lower-institutional-ownership firms -- corroborates Chan (2003)'s "concentrated in small, illiquid stocks" robustness finding.
- **Decay finding, directly relevant to this iteration's expected magnitude**: liquidity improvement following the **post-decimalization period** (stocks began trading in decimals instead of fractions starting 2001) **reduced the magnitude of both price reversals and continuations**. This is a documented decline in effect size as market microstructure improved, over a sample that ends in 2015 -- a decade before our TEST window. No claim in this source about the 2020s.

## Limitations for this iteration

- Abstract-level synthesis only; ScienceDirect and SSRN both returned HTTP 403 on WebFetch this pass, so the exact quantitative magnitudes (percent reversal, t-stats) were not independently read from the primary text, only from the WebSearch-indexed abstract summary. Recorded as `claim_only`, not `source_verified`.
- No 2020s (post-2020) independent replication of the Chan/Savor no-news-reversal / bad-news-drift mechanism was found in this search pass (3 targeted WebSearch queries; see search-log.jsonl entries appended 2026-09-29 for this iteration). Given the paper's own decay finding (magnitude shrinks as liquidity improves) and no fresher evidence, the 2024-2026 TEST window magnitude is genuinely unverified going in -- this iteration's job is to measure it locally, not assume Chan/Savor-era magnitudes still hold.
