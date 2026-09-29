Source: https://github.com/timmKal01/sec-filing-full-text-search
Fetched 2026-09-29 (WebFetch summary).
The tool calls efts.sec.gov (the SEC full-text search endpoint behind sec.gov search): no key needed, coverage back to 2001, parameters query/forms/date range, output has company, CIK, form type, filing date, item codes, accession number. Confirmed locally 2026-09-29: efts.sec.gov/LATEST/search-index returns hits per FILE with _source.adsh/ciks/file_date/form/items, 100 per page, from= pagination, total capped at 10,000.
