# 10-K text similarity data (T-20261002-03)

Status: PARTIAL; pending lead review. Data step only: no returns, IC or group performance computed.

- CIKs in universe 4491, with a 10-K in the index 4023, completed 218.
- Filings in index 35637, processed 2428, pairs 2204 (0.908 of processed filings).
- fetch fail rate 0.0000 {'ok': 2428}; parse fail rate 0.0000 {'ok': 2428}.
- Filed 2016+ (2169 filings): rf_found 0.957, mda_found 0.947.
- Pairs by year: {2015: 44, 2016: 212, 2017: 213, 2018: 211, 2019: 208, 2020: 205, 2021: 202, 2022: 195, 2023: 191, 2024: 187, 2025: 180, 2026: 156}.
- Requests 1383, elapsed 481 s, code 74ffdaa16e.

## Quantiles (5/25/50/75/95)

- cos_full: 0.9947 / 0.9979 / 0.9987 / 0.9992 / 0.9996 (n=2204)
- cos_rf: 0.9864 / 0.9958 / 0.9979 / 0.9989 / 0.9996 (n=2100)
- cos_mda: 0.9765 / 0.9911 / 0.9945 / 0.9966 / 0.9987 (n=2076)
- jac_full: 0.7976 / 0.8579 / 0.8904 / 0.9139 / 0.9432 (n=2204)
- jac_rf: 0.7219 / 0.8418 / 0.8952 / 0.9326 / 0.9761 (n=2100)
- jac_mda: 0.6529 / 0.7542 / 0.8109 / 0.8616 / 0.9224 (n=2076)
- gap_days: 357.1500 / 364.0000 / 364.0000 / 366.0000 / 371.0000 (n=2204), min 318, max 427

## Mechanical criteria on the processed subset

- fetch_fail_rate<=0.03: PASS
- parse_fail_rate<=0.03: PASS
- mda_found_2016_plus>=0.90: PASS
- rf_found_2016_plus>=0.80: PASS
- pairs_over_filings>=0.70: PASS
- cos_full_median_in_[0.80,0.999]: PASS
- no_early_visible_day: FAIL
- visible_day earlier than filing_date-1d: 2 pairs; null visible_day among 2016+ pairs: 5

## Section-boundary spot checks (first / last 200 characters)

### cik 1750 0001047469-14-006243
- rf start: ITEM 1A. RISK FACTORS The following is a description of the principal risks inherent in our business. We are affected by factors that adversely impact the commercial aviation industry. As a provider o
- rf end: ensed mechanics, to conduct our business, or if we experience a significant or prolonged work stoppage. These and similar events may adversely affect our results of operations and financial condition.
- mda start: ITEM 7. MANAGEMENT'S DISCUSSION AND ANALYSIS OF FINANCIAL CONDITION AND RESULTS OF OPERATIONS (Dollars in millions) Forward-Looking Statements Management's Discussion and Analysis of Financial Conditi
- mda end: Type Contracts. This new standard will be effective for us beginning June 1, 2017. We are currently evaluating the impact of the adoption of this new standard on our consolidated financial statements.

### cik 1750 0001047469-15-006136
- rf start: ITEM 1A. RISK FACTORS The following is a description of the principal risks inherent in our business. We are affected by factors that adversely impact the commercial aviation industry. As a provider o
- rf end: ensed mechanics, to conduct our business, or if we experience a significant or prolonged work stoppage. These and similar events may adversely affect our results of operations and financial condition.
- mda start: ITEM 7. MANAGEMENT'S DISCUSSION AND ANALYSIS OF FINANCIAL CONDITION AND RESULTS OF OPERATIONS (Dollars in millions) Forward-Looking Statements Management's Discussion and Analysis of Financial Conditi
- mda end: ard will be effective for us beginning June 1, 2016 with early adoption permitted. We are currently evaluating the impact of the adoption of this new standard on our consolidated financial statements.

### cik 1750 0001047469-16-014299
- rf start: ITEM 1A. RISK FACTORS The following is a description of the principal risks inherent in our business. We are affected by factors that adversely impact the commercial aviation industry. As a provider o
- rf end: ensed mechanics, to conduct our business, or if we experience a significant or prolonged work stoppage. These and similar events may adversely affect our results of operations and financial condition.
- mda start: ITEM 7. MANAGEMENT'S DISCUSSION AND ANALYSIS OF FINANCIAL CONDITION AND RESULTS OF OPERATIONS (Dollars in millions) Forward-Looking Statements Management's Discussion and Analysis of Financial Conditi
- mda end:  the fourth quarter of fiscal 2016 which resulted in the reclassification of deferred tax assets of $58.3 million from current assets to noncurrent liabilities as of May 31, 2015. 32 Table of Contents

### cik 3197 000156459016015157
- rf start: An investment in our securities involves a high degree of risk. You should carefully consider the risk factors described below, together with the other information included in this Annual Report on Fo
- rf end: s, to make a tender offer or otherwise acquire substantial amounts of our common stock or to launch other takeover attempts that a shareholder might consider to be in such shareholder’s best interest.
- mda start: Management’s discussion and analysis (“MD&A”) should be read in conjunction with the consolidated financial statements and accompanying notes included in Item 8 of this Annual Report on Form 10-K, whi
- mda end: ootnote disclosures. The Company is currently evaluating the impact of the adoption of ASU 2014-09 on the Company’s consolidated financial statements and has not yet determined the method of adoption.

### cik 3570 000000357016000284
- rf start: The following are some of the important factors that could affect our financial performance or could cause actual results to differ materially from estimates or expectations contained in our forward-l
- rf end: ny of the restructuring transactions is determined to be taxable for U.S. federal income tax purposes for any reason, following a deconsolidation, we could incur significant income tax liabilities. 34
- mda start: Introduction The following discussion and analysis presents management’s view of our business, financial condition and overall performance and should be read in conjunction with our Consolidated Finan
- mda end: me among other factors. Recent Accounting Standards For descriptions of recently issued accounting standards, see Note 19—Recent Accounting Standards of our Notes to Consolidated Financial Statements.


## Notes

- requests/elapsed_seconds cover only the second fetch run (06:16-06:24 UTC, 122 CIKs, 1383 requests, 481 s); the first run (06:03-06:15 UTC, part_0000: 96 CIKs, 1045 filings, about 1045 requests, about 750 s) lost its counters when it was stopped by SIGTERM at a CIK boundary. Total requests about 2428.
- Run 1 was stopped because the main process kept per-filing term counts in memory (about 650 MB after 12 min); fixed by dropping counts after pairing, run 2 and later are unaffected. Parser and output of part_0000 are identical.
- Parser rule added during the trial: a table whose whole text is a short 'Item N' heading leaves a one-line marker (code only, stripped before tokenizing); without it, trial 1 had mda_found 0.867 / rf_found 0.881 because many filings lay out headings as one-row tables. All other table text is removed as preregistered.
- no_early_visible_day FAIL: 2 pairs (cik 36047 filing_date 2021-03-01, visible_day 2021-02-26; cik 47518 filing_date 2018-11-19, visible_day 2018-11-16) have acceptanceDateTime earlier than the filing date by more than one day in SEC data; visible_day follows acceptanceDateTime as preregistered; lead to decide.
- cos_full median 0.9987 sits close to the 0.999 upper bound of the sanity range (raw term-frequency cosine without stop-word removal is dominated by function words, as preregistered).
- Next command: setsid nohup scripts/run_capped.sh --mem 1.8G -- uv run python scripts/build_10k_text_similarity.py fetch --resume --max-minutes 120 > logs/t20261002_03_fetch3.log 2>&1 &  (rate about 80 filings/min => about 7 h for the remaining 33.2k filings); then merge and python scripts/summarize_10k_text_similarity.py --snippets data/features/text_similarity/_trial2/_snippets.json data/features/text_similarity/_snippets_extra.json
