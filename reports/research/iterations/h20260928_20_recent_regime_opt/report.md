# Report: h20260928_20_recent_regime_opt

Optimization round over the two batch-2 candidates the owner liked on
2026-09-28 (EOM_REVERSAL_SPY, FRONT_RUN_SECTOR_TOP2). 20 preregistered
candidates (E family base+7, S family base+9, C family 2 combinations) run
via `scripts/screen_batch.py --batch h20260928_20_recent_opt --iteration
h20260928_20_recent_regime_opt`. Source: leaderboard at
`reports/research/screens/h20260928_20_recent_opt/leaderboard.json`,
recomputed per-family DSR and replacement-rule verdicts at
`results.json`.

## Base reproduction check

| | select Sharpe | anchor Sharpe |
|---|---:|---:|
| E0 this round | 1.3390 | 1.2406 |
| batch-2 EOM_REVERSAL_SPY | 1.34 | 1.24 |
| S0 this round | 0.7504 | 1.4022 |
| batch-2 FRONT_RUN_SECTOR_TOP2 | 0.75 | 1.40 |

Both bases reproduce batch-2's numbers to 4+ decimal places (well within the
0.01 tolerance) -- confirms E0/S0 are byte-for-byte the same rule as
batch-2's `w_eom_reversal_spy` / `w_front_run_sector_top2` (also verified
directly in `tests/test_screen_recent_opt_rules.py`).

## E family (base E0)

Replacement rule: (a) select10 >= base+0.10, (b) 2026 not below base by
>0.10, (c) select20 >= base+0.10. E0's own numbers: select10=1.3390,
select20=1.1712, 2026=-0.5740.

| variant | select10 | select20 | 2026 | anchor | stress | (a) | (b) | (c) | qualifies |
|---|---:|---:|---:|---:|---:|---|---|---|---|
| E0 (base) | 1.3390 | 1.1712 | -0.5740 | 1.2406 | 0.5845 | -- | -- | -- | base |
| E1 (win5) | 0.2914 | 0.1799 | 1.0463 | 0.4843 | 0.1404 | no | yes | no | no |
| E2 (win10) | 0.5476 | 0.3902 | 1.5274 | 0.5882 | 0.4367 | no | yes | no | no |
| E3 (thresh -1%) | 0.8801 | 0.7674 | -0.6937 | 0.5503 | 0.2805 | no | yes | no | no |
| E4 (QQQ) | 0.9048 | 0.8086 | -1.0915 | 0.5322 | 0.6531 | no | no | no | no |
| E5 (hold10) | 2.0003 | 1.6474 | -0.7890 | 1.5282 | 0.1668 | yes | no | yes | no |
| E6 (hold-4thFri) | 1.3124 | 1.0562 | -0.5050 | 1.3166 | 0.3146 | no | yes | no | no |
| E7 (magscale) | 1.1006 | 0.9441 | -1.0154 | 0.8150 | 0.4384 | no | no | no | no |

**Verdict: no E-family variant qualifies. E0 stands unchanged.** E5 is the
only variant clearing condition (a) (select10=2.0003, well above the 1.4390
bar) but it fails the 2026-contamination guard (b): its 2026 Sharpe
(-0.7890) is 0.215 below E0's, more than the 0.10 allowed drop -- its
apparent select-window edge does not carry into the still-open 2026 window
consistently with E0, so it is not treated as a genuine improvement per the
owner's literal rule. Note E1/E2 (the source's own tested formation-window
robustness check) both underperform E0's select Sharpe by a wide margin,
consistent with Graziani (2024)'s own A.1.4 finding that only the last
week's return (E0's own formation) has predictive power.

## S family (base S0)

S0's own numbers: select10=0.7504, select20=0.6414, 2026=3.0080.

| variant | select10 | select20 | 2026 | anchor | stress | (a) | (b) | (c) | qualifies |
|---|---:|---:|---:|---:|---:|---|---|---|---|
| S0 (base) | 0.7504 | 0.6414 | 3.0080 | 1.4022 | 0.4517 | -- | -- | -- | base |
| S1 (top1) | 0.4707 | 0.3729 | 3.1178 | 1.2717 | 0.5561 | no | yes | no | no |
| S2 (top3) | 0.8076 | 0.6981 | 3.1232 | 1.4243 | 0.4161 | no | yes | yes | no |
| S_AVG3 | 0.2930 | 0.1799 | 2.3428 | 0.7237 | 0.6981 | no | no | no | no |
| S_AVG5 | 0.6793 | 0.5832 | 4.0842 | 1.4333 | 0.4973 | no | yes | no | no |
| S_SHIFT0 (true seasonality) | 1.2006 | 1.0749 | 1.6446 | 1.4569 | 0.3024 | yes | no | yes | no |
| S_SHIFT2 | 0.8165 | 0.7131 | 0.6371 | 0.6652 | 0.7657 | no | no | yes | no |
| S_11SECTORS | 0.5727 | 0.4619 | 2.9813 | 1.2260 | 0.4305 | no | yes | no | no |
| S_INVVOL | 0.7752 | 0.6574 | 2.7487 | 1.3497 | 0.4298 | no | yes | yes | no |
| S_ABSFILTER | 0.6713 | 0.5494 | 3.0080 | 1.4668 | 0.1801 | no | yes | no | no |

**Verdict: no S-family variant qualifies. S0 stands unchanged.** S_SHIFT0
("true seasonality", the source's own reported-failing baseline) is the
only variant clearing condition (a), but it fails the 2026 guard (b) hard
(1.6446 vs. a required floor of 2.9080) -- consistent with Quantpedia's own
finding that the shift-0 baseline is "at best, comparable to" benchmark:
its apparent select-window win does not survive into 2026, so it is not a
genuine improvement over the front-running (shift-1) base either.

## C family (descriptive, not selection-eligible)

| variant | select10 Sharpe | beats E0 select? | beats S0 select? | beats both? |
|---|---:|---|---|---|
| C1 (EOM gate + S0 top-2) | 0.9461 | no | yes | no |
| C2 (50/50 E0+S0 blend) | 1.0759 | no | yes | no |

Neither C1 nor C2 beats both component bases; both beat S0 alone but remain
below E0 alone. No registry or base-replacement action is taken from C1/C2
(per the brief, they are context only).

## Correlation with S3 (reported for context, never used to select)

anchor / stress, from `results.json`'s `correlation_with_s3_anchor` /
`correlation_with_s3_stress`: E0 0.372/0.410, E1 0.249/0.318, E2 0.332/0.224,
E3 0.294/0.254, E4 0.336/0.399, E5 0.246/0.262, E6 0.362/0.379, E7
0.352/0.265; S0 0.379/0.340, S1 0.395/0.240, S2 0.395/0.369, S_AVG3
0.241/0.373, S_AVG5 0.301/0.359, S_SHIFT0 0.461/0.377, S_SHIFT2 0.378/0.366,
S_11SECTORS 0.395/0.335, S_INVVOL 0.357/0.341, S_ABSFILTER 0.423/0.353; C1
0.175/0.318, C2 0.445/0.416. All candidates sit in the same
low-to-moderate 0.17-0.46 band as S3 -- none is a close S3 proxy nor a
strong diversifier by this measure alone; not used in the replacement
decision.

## DSR (per family, trial_count = family variant count incl. base)

| family | trial_count | base DSR (family-scoped) | best-non-qualifying-attempt DSR |
|---|---:|---:|---:|
| E | 8 | 0.7194 (E0) | E5: 0.8605 |
| S | 10 | 0.7661 (S0) | S_SHIFT0: 0.7869 |
| C | 2 | -- | C1: 0.9630, C2: 0.9832 |

(Full per-candidate numbers in `results.json`; these differ from
`leaderboard.json`'s own `dsr_anchor` field, which pools all 20 candidates
into one trial_count of 20 -- the brief requires family-scoped counts, used
here.)

## SSO context (descriptive only, 50%/yr gate context, not an optimization)

Winning E-family rule is E0 unchanged (no replacement). E0 implemented with
SSO instead of SPY (`sso-context.json`, computed post-hoc via
`screen_lane.evaluate_candidate`, not part of the gated manifest run):
anchor Sharpe 1.496, anchor CAGR 24.0%, anchor max drawdown -9.05%. This
does not clear a 50%/yr bar and is reported only as context, not selected
on or counted in the E-family's DSR trial_count of 8.

## Checks

- Base reproduction: E0/S0 match batch-2's EOM_REVERSAL_SPY/FRONT_RUN_SECTOR_TOP2
  numbers to 4+ decimals (pass).
- Calendar-anchor guard: `scripts/screen_batch.py`'s `calendar_anchor_problems()`
  did not block the run (all 20 candidates declared `freq="D"` with explicit
  `signal_dates_fn`).
- Tests: `tests/test_screen_recent_opt_rules.py` (54 cases) pass -- no
  look-ahead for every candidate, exact reproduction of batch-2's base
  weights on synthetic data and the real panel (5 dates each), and one
  hand-computed case per family.
- Replacement rule applied literally and mechanically from `leaderboard.json`;
  no threshold was adjusted after seeing results.
