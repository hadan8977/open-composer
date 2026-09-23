# signal-library-v1: summary

Admission rule (preregistered 2026-09-23T11:53:04+00:00): rank: stable_years AND beats_shuffle AND (T1 or T2 top-30 book positive excess at 20 bp in both the full and the 2024+ window at the primary horizon) AND max |t_nonoverlap| over horizons >= 2.5 with the preregistered sign; event_long: beats_redated AND t_dates >= 3 at the primary horizon AND calendar-time book positive excess at 20 bp in the full and the 2024+ window; event_exit: t_dates <= -3 at the primary horizon AND beats_redated: admitted as an exit or avoid signal only; reported_not_required: ['timely', 'distinct_from_controls']

| signal | mode | h | IC or excess | t | 2024+ | best book tier: excess/yr full / 2024+ (20 bp) | verdict |
|---|---|---|---|---|---|---|---|
| mom_12_1 | rank | 20d | 0.020 | 1.4 | 0.033 | t1: 17.7% / 43.6% | admit |
| rev_5d | rank | 5d | 0.010 | 2.6 | 0.010 | t1: -5.9% / 2.3% | reject |
| rev_21d | rank | 20d | 0.004 | 0.7 | -0.020 | t1: -0.6% / 4.0% | reject |
| high_52w | rank | 20d | 0.041 | 2.4 | 0.046 | t3: -4.5% / 0.4% | reject |
| idio_vol_63 | rank | 20d | 0.052 | 3.4 | 0.046 | t3: -2.2% / -1.2% | reject |
| max_ret_21 | rank | 20d | 0.041 | 2.7 | 0.031 | t3: -5.8% / -8.9% | reject |
| overnight_mom_21 | rank | 20d | -0.017 | -1.4 | -0.011 | t1: -1.3% / -2.7% | reject |
| intraday_rev_21 | rank | 20d | -0.003 | 0.1 | -0.029 | t3: 1.0% / -11.8% | reject |
| resid_mom | rank | 20d | 0.007 | 0.5 | 0.020 | t1: 19.4% / 40.0% | reject |
| season_2_5 | rank | 20d | 0.013 | 1.6 | 0.014 | t3: -5.7% / -2.5% | reject |
| days_to_cover | rank | 20d | 0.008 | 1.4 | 0.020 | t1: 3.4% / 12.5% | reject |
| short_vol_z21 | rank | 5d | 0.002 | 1.1 | 0.003 | t1: -14.0% / -13.3% | reject |
| news_attention | rank | 20d | -0.003 | -0.2 | -0.003 | t3: 0.0% / 0.0% | reject |
| insider_new_buy | event | 20d | 0.37% | 3.3 | 0.23% | events: -2.1% / -3.4% | reject |
| insider_cluster_buy | event | 20d | 0.78% | 5.0 | 0.45% | events: 2.4% / 0.6% | admit |
| sec_13d_new | event | 20d | -0.56% | -0.8 | -3.46% | events: -11.7% / -31.9% | reject |
| rt_bull | event | 5d | -0.40% | -3.7 | -0.88% | events: -54.4% / -68.0% | admit_exit |
| rt_reclaim | event | 5d | -0.14% | -1.0 | -0.71% | events: -45.7% / -63.8% | reject |
| rt_bear | event | 5d | -0.25% | -2.5 | -0.29% | events: -42.1% / -41.8% | reject |
