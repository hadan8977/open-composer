# alpaca-fee-schedule

- URL: https://files.alpaca.markets/disclosures/library/BrokFeeSched.pdf
- fetched_at: 2026-10-06T17:07Z (UTC, task T-20261006-12)
- kind: official-fee-schedule
- published/version: PDF titled "BrokFeeSched - Template (Oct 1, 2026)"
- evidence grade: official (template)

## Key excerpts (verbatim unless marked [paraphrase])

- Equities: SEC Transaction Fee "$0.0000206 * Trade Value", sells only. FINRA TAF "$0 per share", sells only. FINRA CAT "$0.000003 per executed equivalent share", buys and sells.
- Margin: default margin lending interest rate 6.25%; Alpaca Elite 100k 4.75%.
- "Free (no locate or stock borrow fees on Easy-to-Borrow Securities)"; Hard-to-Borrow: locate fee quoted per share via Locates API, daily borrow fee per security.
- Options: ORF $0.015 per contract (buys and sells); SEC $0.0000206 x value; TAF $0 per contract.
- Caveat: the PDF calls itself a template dated Oct 1, 2026; TAF $0 should be re-checked against FINRA before relying on it.
