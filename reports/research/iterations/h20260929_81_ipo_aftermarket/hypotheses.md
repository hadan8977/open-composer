# Hypotheses: h20260929_81_ipo_aftermarket

## Hypothesis

A: buying an IPO three sessions before its first trading day + 26 calendar days QP date (entry next open) and holding to QP+2 or QP+5 earns a benchmark-adjusted cumulative return net of tiered costs that is at least +1.0% pooled 2016-2026 (t >= 2.5) and from 2024 (n >= 100), because underwriters initiate coverage at quiet-period expiry (Bradley-Jordan-Ritter 2003). B: IPOs with R5 >= +20% (first open to fifth close) decline over the next 20 sessions enough to pay at least 3% net after costs and tiered borrow from 2024 (t >= 2).

## Failure mode

The mandatory quiet period fell from 25 to 40 to 10 days (FINRA 2241, 2015), so day 25 is no longer a regulatory date and there may be nothing left; the BJR effect was measured in the 1996-2000 bubble; R5 is measured from the first open and not from the offer price; IPO shares are often unborrowable so the B family is an upper bound; the ADV proxy is inflated by IPO-week volume; delisted names drop out of windows with missing exit prices (survivorship).

## Measurement

scripts/run_h20260929_81_ipo_aftermarket.py: benchmark-adjusted CAR by entry year, tiered round-trip costs, IPO-date clustered t, QP shift +-10/+-60 and 200 random-date placebos, mirror family C, leave-out of the top-3 B winners; results.json gate_checks.

## Stop/Pivot criterion

Both families fail their frozen conditions: write 'IPO aftermarket calendar windows closed', registry refuted, no ledger and no added variants. A passing family alone is screened per runbook section 5 (K1/K2, DSR with 12 trials, 20 bp check, K2 increment over S3 >= 0.05).
