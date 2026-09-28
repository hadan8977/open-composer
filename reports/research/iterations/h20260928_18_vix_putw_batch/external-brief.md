# External Brief: h20260928_18_vix_putw_batch

Eight sources were opened for T-20260928-18: the WisdomTree PUTW launch
press release and Cboe's official PUT index fact sheet (grounding PUTW's
mechanism and inception), two academic/practitioner studies of the CBOE
PutWrite Index's historical performance (Bondarenko 2019, Ennis Knupp 2008),
a recent (2025) arXiv paper on put-writing position sizing, a tertiary note
on Whaley's foundational BuyWrite index methodology, Cboe's own PutWrite
methodology document, and the Alvarez Quant Trading VIX-regime post kept for
the audit trail even though its candidate is out of scope this round. See
`external-brief.json` for full per-source detail. The decisive new evidence
this round is not a web source but a direct Alpaca API probe: PUTW is not
served by Alpaca (our only market-data/broker vendor) at all, confirmed
against five known-tradable control ETFs.
