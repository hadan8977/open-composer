# Cboe Regulatory Circular RG13-118 / C2 RG13-041 (August 29, 2013)

URL: https://cdn.cboe.com/resources/regulation/circulars/regulatory/RG-C2-2013-041.pdf
Retrieved: 2026-09-29 (this session) -- WebFetch could not parse the raw PDF
bytes; downloaded via curl and extracted with `pdftotext -layout` instead.
Full text read (52 lines), not a search-engine summary.

## Official rule text (verbatim, per the circular)
"in the case of such an option expiring on or after February 1, 2015, the
third Friday of the expiration month of such option contract, unless
designated as 'Grandfathered' ..., or if such Friday is a day on which the
exchange on which such option is listed is not open for business, the
preceding day on which such exchange is open for business."

## Relevance to this iteration
This is the OFFICIAL exchange rule (not a blog or practitioner summary)
defining standard monthly option expiration as the third Friday of the
month, with an explicit holiday rule: if the third Friday is a non-trading
day, expiration shifts to the PRECEDING trading day. This directly confirms
the construction used by this iteration's `entry_dates_for_friday` /
`exit_dates_same_week` calendar helpers (scripts/screen_batches/
h20260928_42_opex_week.py): when the third Friday is a holiday (e.g. Good
Friday, tested in tests/test_h20260928_42_opex_week.py's 2025-04 case), the
WEEK variant's exit signal falls on the last trading day at or before that
Friday within the same calendar week -- the same "preceding trading day"
principle the exchange itself uses to define expiration, not an invented
convention.
