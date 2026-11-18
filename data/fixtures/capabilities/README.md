# Offline codec fixtures

Files prefixed `synthetic_` are invented, deterministic codec inputs. They contain
no received market observations, accepted research evidence, historical publication
vintages, source-account results or paper-readiness evidence. They make the native
capability validators usable in a checkout without retained research reports,
private data or credentials. Original research artifacts remain unchanged.

| Fixture | Invented payload and validation scope |
| --- | --- |
| `synthetic_operating_nav_receipt.json` | Three sessions (2024-01-02 through 2024-01-04), the required six-name inventory, two cost views, and exact byte/SHA256 bindings to the adjacent manifest and NPZ. |
| `synthetic_operating_nav_manifest.json` | Synthetic provenance and explicit array construction; not a receipt for an actual source ledger. |
| `synthetic_operating_nav_arrays.npz` | Four NAV marks per name, three net returns and the exact `gross = net + inner` bridge; no pickled arrays. |
| `synthetic_dm_author_deciles.tar.gz` | Only `txt/d_m_pt_tot.txt` and `txt/m_m_pt_tot.txt`: two daily and two monthly dates, ten ordered deciles each (40 rows). Decimal return is `(decile - 5) / 1000`, cap 1000 and count 50. |
| `synthetic_ff3_current_monthly.csv` | Three ordered months and exactly `Mkt-RF,SMB,HML,RF` in decimal units, including negative and zero values. |
| `synthetic_ff3_annual_archive_monthly.csv` | A second invented three-month vector in the same schema; it does not represent a real July archive. |
| `synthetic_fed_scheduled_statement_dates.jsonl` | Two invented EventRecord packets with explicit fixture provenance and safe visibility ordering; not actual meeting dates or archive observations. |

The receipt's calendar, alignment and bridge booleans are fields of the synthetic
test packet, not factual attestations about research sources. NPZ ZIP timestamps,
TAR metadata and the GZIP timestamp are fixed; the payloads contain no random values.
Existing strict validators check identities, dimensions, dates and arithmetic
without weaker thresholds or generic OHLCV substitution.

Registry `retained_source_artifact` paths preserve the original research-input
locations, and source URLs and readiness limits remain unchanged. Synthetic
`fixture` paths provide only portable schema coverage; actual source bytes,
timing, costs, input reception and task-specific research/paper gates still require
their original evidence.
