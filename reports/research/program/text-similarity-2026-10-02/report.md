# 10-K text similarity data (T-20261002-03)

Status: complete; pending lead review. Data step only: no returns, IC or group performance computed.

- CIKs in universe 4491, with a 10-K in the index 4023, completed 4023.
- Filings in index 35637, processed 35596, pairs 31199 (0.876 of processed filings).
- fetch fail rate 0.0000 {'ok': 35596}; parse fail rate 0.0006 {'ok': 35575, 'too_large': 20, 'error:ValueError': 1}.
- Filed 2016+ (32636 filings): rf_found 0.956, mda_found 0.954.
- Pairs by year: {2015: 322, 2016: 2588, 2017: 2686, 2018: 2722, 2019: 2759, 2020: 2794, 2021: 2849, 2022: 2983, 2023: 3082, 2024: 2961, 2025: 2859, 2026: 2594}.
- Requests 34592, elapsed 13818 s, code 588b2c7b73.

## Quantiles (5/25/50/75/95)

- cos_full: 0.9937 / 0.9977 / 0.9987 / 0.9992 / 0.9996 (n=31197)
- cos_rf: 0.9880 / 0.9966 / 0.9984 / 0.9992 / 0.9997 (n=29620)
- cos_mda: 0.9744 / 0.9896 / 0.9939 / 0.9963 / 0.9983 (n=29522)
- jac_full: 0.7734 / 0.8528 / 0.8873 / 0.9132 / 0.9420 (n=31197)
- jac_rf: 0.7288 / 0.8486 / 0.8968 / 0.9330 / 0.9710 (n=29620)
- jac_mda: 0.6024 / 0.7327 / 0.7971 / 0.8505 / 0.9117 (n=29522)
- gap_days: 351.0000 / 363.0000 / 364.0000 / 367.0000 / 377.0000 (n=31199), min 300, max 430

## Mechanical criteria on the processed subset

- fetch_fail_rate<=0.03: PASS
- parse_fail_rate<=0.03: PASS
- mda_found_2016_plus>=0.90: PASS
- rf_found_2016_plus>=0.80: PASS
- pairs_over_filings>=0.70: PASS
- cos_full_median_in_[0.80,0.999]: PASS
- no_early_visible_day: PASS
- visible_day earlier than filing_date-1d: 0 pairs; null visible_day among 2016+ pairs: 44

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

