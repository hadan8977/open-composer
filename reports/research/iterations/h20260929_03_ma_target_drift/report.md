# Report: h20260929_03_ma_target_drift

Verdict: **refuted** (all four signal cards rejected; the post-announcement drift is negative, not positive).

## Data pipeline
EDGAR full-text search (phrases "Agreement and Plan of Merger" / "Agreement and Plan of Reorganization", 8-K, monthly windows 2016-01..2026-09) -> 11,415 candidate 8-Ks (Item 1.01, not completion) -> 10,791 with a ticker (94.5%) -> code rule -> 1,484 first target announcements (by year 2016-2026: 176, 150, 140, 118, 88, 136, 131, 128, 146, 162, 109). Hand check: 4 draws of 25 (`data/features/sec_8k_ma_announcements/SAMPLE_CHECK.md`); fresh draw with the final rule 2/25 = 8% false positives; earlier rule versions 8-20%. Date problems (8-K filed 2+ sessions after signing): about 5%. Only 576 of 1,484 events (38.8%) sit in the tradable signal_card universe (top 3000 by ADV, close >= 5, symbol found in the price panel: 70% of events have a panel symbol).

## Signal cards (`reports/research/signal-cards/`, next-open entry, 10/20 bp per side)
| card | horizon | events | CAR mean | t (dates) | recent CAR (2024+) | book excess 20bp | 20bp 2024+ | flags |
|---|---|---|---|---|---|---|---|---|
| ma_target_all | 20d | 596 | -0.75% | -2.36 | -1.36% | -16.2%/yr | -21.9%/yr | t>=3 False, beats_redated True, 20bp False, 20bp recent False |
| ma_target_t3 | 20d | 335 | -0.62% | -1.33 | -1.31% | -9.4%/yr | -11.3%/yr | t>=3 False, beats_redated True, 20bp False, 20bp recent False |
| ma_target_all_h60 | 60d | 596 | -1.33% | -1.59 | -2.21% | -10.1%/yr | -15.0%/yr | t>=3 False, beats_redated True, 20bp False, 20bp recent False |
| ma_target_t3_h60 | 60d | 335 | -0.63% | -0.48 | -2.79% | -8.0%/yr | -18.1%/yr | t>=3 False, beats_redated True, 20bp False, 20bp recent False |

beats_redated is true only because the real CAR (negative) is lower than all 20 re-dated placebos (placebo CAR between +2.1% and +5.1% at 20d); the card admits only positive edges, so all four are rejected by `signal_card.admission`.

## Where the premium is (scripts/analyze_ma_target_car_path.py, excess vs universe mean, `car_path_diagnostic.json`)
All tradable targets (n 576): days -20..-6 +3.28% (t 6.2, n 571); days -5..-1 +5.69% (t 10.2, n 575); day 0 close-to-close +16.95% (t 14.5, n 576); close-day0 to open-day1 gap +0.31% (t 2.0, n 575); after entry at next open: h1 +0.04% (t 0.5, n 575), h5 +0.08% (t 0.5, n 574), h10 -0.14% (t -0.6, n 574), h20 -0.63% (t -1.9, n 573), h60 -1.22% (t -1.5, n 391).
t3 tier (n 321): days -5..-1 +5.83% (t 7.0, n 320); day 0 +19.62% (t 11.6, n 321); h20 -0.55% (t -1.2, n 320); h60 -0.55% (t -0.4, n 204).
2024+ (n 152): days -5..-1 +4.58% (t 5.4, n 151); day 0 +17.75% (t 8.0, n 152); h20 -1.38% (t -2.5, n 151).
The premium is fully in the price by the next open: the run-up before the 8-K plus the day-0 reaction are large, and everything after entry is flat to negative.

## Not tested
Hold-to-close (needs completion status/offer price; not free at announcement time and would select surviving deals), price-to-offer conditioning, hedged versions. The 2025 working paper claiming Sharpe > 2.1 (abstract only) is not reproduced by this fixed-horizon design; it probably relies on deal-level variables not in this table.

## Statuses
workflow_pass true, research_pass false, llm_contribution_pass false, paper_ready_pass false.
