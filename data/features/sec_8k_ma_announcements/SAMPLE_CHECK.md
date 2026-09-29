# SAMPLE_CHECK: EDGAR merger-target 8-K table (T-20260929-03)

Table: `data/features/sec_8k_ma_announcements/` (built by `scripts/collect_sec_ma_target_announcements.py`).
Sampling: random draws from rows with `is_target_rule` and `is_first_for_cik_365d`. I read the first ~400-1500 characters of the Item 1.01 text of each row myself (25 rows per draw); the classification of the 11,415 candidates is by code rule only. Read date: 2026-09-29.

## Result summary (false positive = filer is not the acquired party in a new definitive agreement)

| draw | rule version | rows | false positives | rate | note |
|---|---|---|---|---|---|
| A | v1 (first pass, 2024 only) | 25 | 2 (ZCAR, NASC) | 8% | plus 1 date-uncertain (SNPO) |
| B | v2 (added amendment/holdco/SPAC-name exclusions, all years) | 25 | 5 (RTIX, UFS, NDSN, MKUL, FRME) | 20% | above the 15% bar, so rules were fixed |
| C | v3 (added Company-definition binding, filer-survives, completion 2.01, sub-of-filer) | 25 | 3 (NEO, TRKK, ISUN) + 1 unverified (KNDI) | 12-16% | fixed NEO/TRKK; ISUN needs name-collision handling (left) |
| D | v4 final (amendment-heading fix) | 25 | 2 before last fix (DAN, GAN), 1 ambiguous (HUN) | 8% | fresh draw never used to tune, GAN fixed after |

Final rule applied to all four draws (kept rows still counted as events): A 23/25 kept, B 21/25 kept, C 23/25 kept, D 24/25 kept. Estimate on the fresh draw D: 2/25 = 8% false positives (95% binomial interval about 1% to 26%), 1 more ambiguous. Because draws B and C were used to fix rules they are biased low afterwards; D is the honest number. Pooled over the four draws the pre-fix false-positive count is 12/100 (12%); the bar of 15% is met by the final rule on the fresh draw, so the table is not blocked_data.

Date problems (8-K accepted 2+ sessions after the deal was signed or announced, so the event date is late and part of the reaction is already priced): 4 of 75 rows in draws A, C and D that I could date (SNPO, STRZA, PACB, KCG 1 day). That is about 5% of events with a late 8-K; the diagnostic `car_path_diagnostic.json` (pre-announcement CAR) will show its footprint.

Independent evidence the filers are targets: the same CIK files DEFA14A / SC 14D9-C (target-side documents; the acquirer of a cash deal does not) within 5 sessions after the 8-K for 62.5% of rule-target rows versus 8.0% of non-target candidate 8-Ks (`has_target_followup_5d`). DEFM14A / completion information is not used anywhere.

Recall is not measured against a deal list. A read of 14 random rule-negative 2024 8-Ks that mention merger subsidiaries found 1 missed target (PetIQ, fixed by making the exhibit-preamble cue weak) and known misses for multi-step structures (Endeavor, Bally's, Fathom in the 2024 borderline list). Estimated recall of the phrase search plus rule: roughly 80-90% of US public-target 8-Ks with Item 1.01.

## Mapping success (CIK -> ticker)

Candidate 8-Ks (Item 1.01, not a completion 8-K, hit by the phrase search) 2016-01 to 2026-09: 11,415, of which 10,791 (94.5%) map to a symbol (Form 4 issuer history 8,359 exact + 2,195 near-date within 730 days, current company_tickers.json 237 fallback, unmapped 624). By year: 2016 93.5%, 2017 93.9%, 2018 96.2%, 2019 93.0%, 2020 95.4%, 2021 94.8%, 2022 93.1%, 2023 94.1%, 2024 94.9%, 2025 95.1%, 2026 96.5%. Only mapped candidates were fetched and classified; unmapped ones (mostly issuers with no Form 4 in the panel) are not in the table. Rule-target first events by filing year: 2016 176, 2017 150, 2018 140, 2019 118, 2020 88, 2021 136, 2022 131, 2023 128, 2024 146, 2025 162, 2026 109 (total 1,484). Share of those that are in the tradable signal_card universe (top 3000 by ADV, close >= 5, price panel present): by year (events / symbol in price panel / in tradable universe): 2016 176/120/74, 2017 150/106/60, 2018 140/88/57, 2019 118/81/53, 2020 88/62/36, 2021 136/98/49, 2022 131/91/48, 2023 128/102/49, 2024 146/111/59, 2025 162/130/59, 2026 109/90/52 (from `reports/research/iterations/h20260929_03_ma_target_drift/car_path_diagnostic.json`, `coverage_by_year`); overall 1,484 events, 1,000 with a symbol in the panel (about 70%, the rest are unmatched or unlisted tickers), 576 in the tradable universe (38.8%). Delisted targets are covered because symbols come from Form 4 issuer history and prices from `daily_broad` (which includes delisted names); current company_tickers.json alone would have missed them.

Timing: `trade_date` = last session on or before the Eastern EDGAR acceptance date; signal_card enters at the next session open, so day-0 reaction is never captured, including pre-market filings (conservative).

## Draw D (final rule, fresh) - all 25 rows

| # | symbol | filer | accepted (UTC) | trade_date | verdict |
|---|---|---|---|---|---|
| 1 | MESG | XURA, INC. | 2016-05-23 12:26:16 | 2016-05-23 | TP |
| 2 | WR | WESTAR ENERGY INC /KS | 2016-05-31 10:22:07 | 2016-05-31 | TP (merger of equals, Westar is the acquired party); agreement May 29, 8-K May 31 |
| 3 | OSHC | Ocean Shore Holding Co. | 2016-07-14 21:05:25 | 2016-07-14 | TP |
| 4 | DAN | DANA INC | 2018-03-14 20:48:03 | 2018-03-14 | FP: Dana merges with GKN driveline businesses (filer is the buyer) |
| 5 | GGP | GGP Inc. | 2018-03-27 21:25:07 | 2018-03-27 | TP |
| 6 | RPXC | RPX Corp | 2018-05-01 12:31:03 | 2018-05-01 | TP |
| 7 | PLRM | Pilgrim Bancshares, Inc. | 2018-07-25 21:03:27 | 2018-07-25 | TP |
| 8 | HF | HFF, Inc. | 2019-03-20 11:02:36 | 2019-03-20 | TP |
| 9 | ACIA | Acacia Communications, Inc. | 2019-07-09 12:44:04 | 2019-07-09 | TP |
| 10 | ROAN | ROAN RESOURCES, INC. | 2019-10-01 20:35:38 | 2019-10-01 | TP |
| 11 | CIT | CIT GROUP INC | 2020-10-20 10:37:34 | 2020-10-20 | TP |
| 12 | ECHO | Echo Global Logistics, Inc. | 2021-09-10 20:41:48 | 2021-09-10 | TP |
| 13 | FLOW | SPX FLOW, Inc. | 2021-12-15 22:14:26 | 2021-12-15 | TP |
| 14 | TWTR | TWITTER, INC. | 2022-04-26 21:10:18 | 2022-04-26 | TP |
| 15 | MANT | MANTECH INTERNATIONAL CORP | 2022-05-16 12:14:56 | 2022-05-16 | TP |
| 16 | FSTX | F-star Therapeutics, Inc. | 2022-06-23 13:25:03 | 2022-06-23 | TP |
| 17 | USER | UserTesting, Inc. | 2022-10-27 12:33:49 | 2022-10-27 | TP |
| 18 | FRG | Franchise Group, Inc. | 2023-05-11 01:49:39 | 2023-05-10 | TP |
| 19 | GTHX | G1 Therapeutics, Inc. | 2024-08-07 13:21:29 | 2024-08-07 | TP |
| 20 | GAN | GAN Ltd | 2025-02-07 13:15:21 | 2025-02-07 | FP: Second Amendment to an earlier merger agreement |
| 21 | PRA | PROASSURANCE CORP | 2025-03-20 20:58:16 | 2025-03-20 | TP |
| 22 | CORZ | Core Scientific, Inc./tx | 2025-07-07 21:08:44 | 2025-07-07 | TP |
| 23 | SEMR | SEMrush Holdings, Inc. | 2025-11-19 13:27:58 | 2025-11-19 | TP |
| 24 | KW | Kennedy-Wilson Holdings, Inc. | 2026-02-17 11:55:32 | 2026-02-17 | TP |
| 25 | HUN | Huntsman CORP | 2026-06-16 21:10:27 | 2026-06-16 | ambiguous: 2026 merger with Olin, direction not verifiable from the text read |

## Draw A (2024, rule v1)

| # | symbol | filer | accepted (UTC) | trade_date | verdict |
|---|---|---|---|---|---|
| 1 | ZCAR | Zoomcar Holdings, Inc. | 2023-12-29 22:50:48 | 2023-12-29 | FP: amendment to a 2022 de-SPAC merger agreement, filer is the post-closing company |
| 2 | ANSS | ANSYS INC | 2024-01-16 13:00:54 | 2024-01-16 | TP |
| 3 | INBX | Inhibrx, Inc. | 2024-01-23 11:35:58 | 2024-01-23 | TP |
| 4 | SNCE | Science 37 Holdings, Inc. | 2024-01-29 12:35:28 | 2024-01-29 | TP |
| 5 | HAYN | HAYNES INTERNATIONAL INC | 2024-02-05 13:36:35 | 2024-02-05 | TP |
| 6 | ZFOX | ZeroFox Holdings, Inc. | 2024-02-06 13:45:35 | 2024-02-06 | TP |
| 7 | DOMA | Doma Holdings, Inc. | 2024-03-29 10:01:46 | 2024-03-28 | TP |
| 8 | SNPO | Snap One Holdings Corp. | 2024-04-18 20:06:35 | 2024-04-18 | TP, date uncertain: agreement signed Apr 14, 8-K filed Apr 18 (4 days later; public news may predate it) |
| 9 | MTTR | Matterport, Inc./DE | 2024-04-22 13:10:15 | 2024-04-22 | TP |
| 10 | AMK | AssetMark Financial Holdings, Inc. | 2024-04-25 11:11:49 | 2024-04-25 | TP |
| 11 | AKLI | Akili, Inc. | 2024-05-29 13:14:26 | 2024-05-29 | TP |
| 12 | AAN | Aaron's Company, Inc. | 2024-06-17 11:11:31 | 2024-06-17 | TP |
| 13 | VAPO | VAPOTHERM INC | 2024-06-20 10:02:24 | 2024-06-20 | TP |
| 14 | SHCR | Sharecare, Inc. | 2024-06-21 21:29:57 | 2024-06-21 | TP |
| 15 | DM | Desktop Metal, Inc. | 2024-07-03 11:32:57 | 2024-07-03 | TP |
| 16 | CHUY | CHUY'S HOLDINGS, INC. | 2024-07-17 20:48:31 | 2024-07-17 | TP |
| 17 | SDIG | Stronghold Digital Mining, Inc. | 2024-08-21 21:43:03 | 2024-08-21 | TP |
| 18 | MNTX | Manitex International, Inc. | 2024-09-12 20:16:31 | 2024-09-12 | TP |
| 19 | NASC | Can B Corp | 2024-10-28 21:11:23 | 2024-10-28 | FP: holding-company reorganization, no third-party acquirer |
| 20 | PFIE | PROFIRE ENERGY INC | 2024-10-29 11:18:01 | 2024-10-29 | TP |
| 21 | ALTR | Altair Engineering Inc. | 2024-10-30 20:47:02 | 2024-10-30 | TP |
| 22 | LBRDA | Liberty Broadband Corp | 2024-11-13 13:37:37 | 2024-11-13 | TP |
| 23 | PTVE | Pactiv Evergreen Inc. | 2024-12-09 13:05:16 | 2024-12-09 | TP |
| 24 | PDCO | PATTERSON COMPANIES, INC. | 2024-12-11 13:01:30 | 2024-12-11 | TP |
| 25 | OMIC | Singular Genomics Systems, Inc. | 2024-12-23 21:56:51 | 2024-12-23 | TP |

## Draw B (rule v2)

| # | symbol | filer | accepted (UTC) | trade_date | verdict |
|---|---|---|---|---|---|
| 1 | BXLT | Baxalta Inc | 2016-01-11 22:16:54 | 2016-01-11 | TP |
| 2 | AMTG | Apollo Residential Mortgage, Inc. | 2016-02-26 14:06:32 | 2016-02-26 | TP |
| 3 | SPA | SPARTON CORP | 2017-07-11 20:29:04 | 2017-07-11 | TP |
| 4 | JMBA | JAMBA, INC. | 2018-08-02 13:19:21 | 2018-08-02 | TP |
| 5 | REIS | Reis, Inc. | 2018-08-30 17:21:06 | 2018-08-30 | TP |
| 6 | BDMS | BIRNER DENTAL MANAGEMENT SERVICES INC | 2018-10-03 21:09:01 | 2018-10-03 | TP |
| 7 | RTIX | RTI SURGICAL, INC. | 2018-11-07 22:04:10 | 2018-11-07 | FP: filer is the buyer (Master Transaction Agreement, its own merger sub) |
| 8 | CASM | CAS MEDICAL SYSTEMS INC | 2019-02-12 13:37:14 | 2019-02-12 | TP |
| 9 | AKS | AK STEEL HOLDING CORP | 2019-12-04 13:00:41 | 2019-12-04 | TP |
| 10 | MTSC | MTS SYSTEMS CORP | 2020-12-09 22:24:18 | 2020-12-09 | TP |
| 11 | CERN | CERNER Corp | 2021-12-22 01:06:33 | 2021-12-21 | TP |
| 12 | LHCG | LHC Group, Inc | 2022-03-29 20:30:32 | 2022-03-29 | TP |
| 13 | TVTY | TIVITY HEALTH, INC. | 2022-04-06 21:18:55 | 2022-04-06 | TP |
| 14 | UFS | Domtar CORP | 2022-07-11 20:00:33 | 2022-07-11 | FP: filer Domtar is the acquirer of Resolute |
| 15 | NDSN | NORDSON CORP | 2022-08-10 20:32:44 | 2022-08-10 | FP: filer Nordson is the acquirer of CyberOptics |
| 16 | AVEO | AVEO PHARMACEUTICALS, INC. | 2022-10-18 10:04:35 | 2022-10-18 | TP |
| 17 | MKUL | Molekule Group, Inc. | 2023-01-12 22:28:44 | 2023-01-12 | FP: completion 8-K (Items 2.01), not an announcement |
| 18 | ALR | AlerisLife Inc. | 2023-02-03 13:05:28 | 2023-02-03 | TP |
| 19 | CVT | CVENT HOLDING CORP. | 2023-03-14 21:31:03 | 2023-03-14 | TP |
| 20 | CFMS | Conformis Inc | 2023-06-23 11:45:45 | 2023-06-23 | TP |
| 21 | OLO | Olo Inc. | 2025-07-03 13:29:05 | 2025-07-03 | TP |
| 22 | MTSR | Metsera, Inc. | 2025-09-22 11:41:54 | 2025-09-22 | TP |
| 23 | FRME | FIRST MERCHANTS CORP | 2025-09-25 12:15:52 | 2025-09-25 | FP: First Merchants is the surviving acquirer of First Savings |
| 24 | RAMP | LiveRamp Holdings, Inc. | 2026-05-18 10:04:40 | 2026-05-18 | TP |
| 25 | ACA | Arcosa, Inc. | 2026-06-22 11:21:11 | 2026-06-22 | TP |

## Draw C (rule v3)

| # | symbol | filer | accepted (UTC) | trade_date | verdict |
|---|---|---|---|---|---|
| 1 | CBNJ | Cape Bancorp, Inc. | 2016-01-07 18:15:22 | 2016-01-07 | TP |
| 2 | CKP | CHECKPOINT SYSTEMS INC | 2016-03-02 12:11:37 | 2016-03-02 | TP |
| 3 | WGBS | WaferGen Bio-systems, Inc. | 2016-05-13 10:00:20 | 2016-05-13 | TP |
| 4 | STRZA | Starz | 2016-07-07 00:13:15 | 2016-07-06 | TP, date late: agreement June 30, 8-K accepted July 6 (about 4 business days) |
| 5 | KCG | KCG Holdings, Inc. | 2017-04-21 21:26:05 | 2017-04-21 | TP, 1 day after signing/announcement |
| 6 | NEO | NEOGENOMICS INC | 2018-10-26 21:23:38 | 2018-10-26 | FP: filer NeoGenomics is the acquirer of Genesis/Genoptix |
| 7 | PACB | PACIFIC BIOSCIENCES OF CALIFORNIA, INC. | 2018-11-05 21:33:11 | 2018-11-05 | TP, date late: agreement Nov 1, 8-K accepted Nov 5 |
| 8 | TRKK | Orbital Tracking Corp. | 2019-08-01 17:48:53 | 2019-08-01 | FP: filer merges its own subsidiary into itself (reincorporation) |
| 9 | IPHI | INPHI Corp | 2020-10-29 21:46:41 | 2020-10-29 | TP |
| 10 | NAV | NAVISTAR INTERNATIONAL CORP | 2020-11-09 11:13:04 | 2020-11-09 | TP |
| 11 | ISUN | ISUN, INC. | 2021-01-25 21:15:23 | 2021-01-25 | FP: filer iSun is the acquirer of iSun Energy LLC (name collision) |
| 12 | STMP | STAMPS.COM INC | 2021-07-09 21:11:28 | 2021-07-09 | TP |
| 13 | HMHC | Houghton Mifflin Harcourt Co | 2022-02-22 11:19:08 | 2022-02-22 | TP |
| 14 | KNDI | Kandi Technologies Group, Inc. | 2022-09-07 20:05:28 | 2022-09-07 | not verified: main text shows only the cover page |
| 15 | ALBO | ALBIREO PHARMA, INC. | 2023-01-09 11:05:48 | 2023-01-09 | TP |
| 16 | TMBR | Timber Pharmaceuticals, Inc. | 2023-08-21 12:11:28 | 2023-08-21 | TP |
| 17 | SILK | Silk Road Medical Inc | 2024-06-18 20:36:43 | 2024-06-18 | TP |
| 18 | CDMO | Avid Bioservices, Inc. | 2024-11-07 02:11:21 | 2024-11-06 | TP |
| 19 | NVRO | NEVRO CORP | 2025-02-06 21:05:47 | 2025-02-06 | TP |
| 20 | VIGL | Vigil Neuroscience, Inc. | 2025-05-22 10:10:45 | 2025-05-22 | TP |
| 21 | SHCO | Soho House & Co Inc. | 2025-08-18 10:09:25 | 2025-08-18 | TP |
| 22 | RNA | Avidity Biosciences, Inc. | 2025-10-27 11:28:55 | 2025-10-27 | TP |
| 23 | NATL | NCR Atleos Corp | 2026-02-26 21:26:10 | 2026-02-26 | TP |
| 24 | TERN | Terns Pharmaceuticals, Inc. | 2026-03-25 11:17:09 | 2026-03-25 | TP |
| 25 | BOW | Bowhead Specialty Holdings Inc. | 2026-08-03 12:03:12 | 2026-08-03 | TP |
