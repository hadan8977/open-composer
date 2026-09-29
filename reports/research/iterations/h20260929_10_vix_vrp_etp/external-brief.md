# External Brief: h20260929_10_vix_vrp_etp

Primary source: Zarattini/Aziz/Mele (2025, SSRN 5316487 / SFI RP 25-91),
"The Volatility Edge, A Dual Approach For VIX ETNs Trading" -- full text
paywalled/bot-blocked (curl and WebFetch both failed); read via an
independent from-scratch QuantConnect replication (code-level, with the
exact eVRP formula, the 4-case position-sizing table, and reported Sharpe
0.729 vs SPY buy-and-hold 0.582 over 2016-01..2026-07), cross-checked
against a WebSearch snippet of the SSRN abstract page and the Concretum
Group's own author-affiliated blog summary (2008-2025 CAGR 16.3%, Sharpe
~1.0, ~15% equity correlation). See `external-brief.json`'s `sources` list
for full citation, credibility and reflection detail (8 sources: 1 platform
replication with code, 4 reused academic papers from the prior
`mom_vix_term_structure_overlay_r1_implfix1` campaign's own verified source
cards on VIX term-structure/VRP methodology, and 3 internal-evidence
entries -- this project's own prior negative/adjacent results on VIX-timing
mechanisms and the S3 K1/K2 numeric reference).

`candidate_matrix_revisions`: none yet (first pass at this mechanism; no
mid-task coordinator revision has occurred). `topic_coverage`: dual-VIX-
signal mechanism and position sizing, VIX/VIX3M term-structure index
definition and official history, VIX-futures-vs-spot-index instrument risk
(why VIXY/UVXY cannot substitute for the index-level signals), volatility-
managed-portfolio academic grounding, deflated-Sharpe methodology, and this
project's own adjacent VIX-timing negative evidence.
