# Hypotheses: h20260929_80_dat_vs_coin

## Hypothesis

After 2024-01-11 the price ratio of a bitcoin/ether treasury stock (or miner basket) to its coin, when high relative to its 120/250-session history, is followed over the next 20 sessions by DAT underperformance of a beta-hedged coin leg (Z family, IC negative); alternatively relative weakness of 10 percent over 20/60 sessions continues (M family, IC positive).

## Failure mode

(a) premium can persist or widen (Elm Wealth; 3.9x in 2021-02) so IC is not significantly negative; (b) one or two premium cycles give few independent episodes; (c) price ratio conflates premium with leverage and preferred issuance (no holdings data); (d) short leg unborrowable or expensive; (e) stress window uses spot legs with 25 bp costs; (f) miner basket entry dates and reused tickers contaminate the series.

## Measurement

scripts/run_h20260929_80_dat_ic.py ic: Spearman IC, Newey-West lag 20 t, 500 random-alignment placebos, independent episode counts per pair x signal x window; results.json gate_checks.

## Stop/Pivot criterion

Stop unless at least one (pair, signal) cell passes all frozen conditions (anchor sign + |t| >= 2.0, stress same sign where data, >= 6 anchor episodes). No variants after results.
