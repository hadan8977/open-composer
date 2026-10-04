# numerai__forum-v5-2-faith-ii
URL: https://forum.numer.ai/t/new-target-for-payouts-and-data-v5-2-faith-ii/8209/3
Fetched: 2026-10-04 18:20 UTC (text only, tags stripped)

New Target for Payouts and Data V5.2 - Faith II - #3 by svendaj - Announcements - Numerai Forum

 Numerai Forum

 New Target for Payouts and Data V5.2 - Faith II

 Announcements

 svendaj

 December 19, 2025, 7:14pm

 3

Dear Kagglers, V5.2 data are now available on Kaggle platform with weekly automatic update:

numerai data is public notebook, automatically triggered on Saturday round opening, downloading data from v5.2 Data - Numerai, and also producing 4 smaller subsampled datasets with non-overlapping data.

numerai latest tournament data is public dataset with output data of producing notebook numerai data. Dataset is updated automatically, when producing notebook is successfully executed.

You can use whichever data source as the input of your notebooks to produce Tournament submissions. Using the new dataset and new target target_ender_20, I have retrained and uploaded all public Kaggle example models:

Hello Numerai automated - basic tutorial model with improved version trained on medium feature set

numerai Feature Neutralization - Kaggle tutorial explaining FN

numerai Target Ensemble - Kaggle tutorial explaining ensembling

Numerai Example Model Sunshine - example model using both techniques above

Diagnostic data are not suggesting any improvement over v5.1, but hey it’s just backtesting. Let’s see how they will fare next year.

This is diagnostics of model trained on train.parquet with medium feature set and new target of V5.2 data:

image670×522 33.8 KB

and this same model on V5.1 data:

image676×506 35.4 KB

 1 Like

 Optimization Paradox: Advanced Feature Neutralization vs. Universal Alpha Protocol (IVAN)

 show post in topic

 Related topics

 Topic

 Replies
 Views
 Activity

 V5 "Atlas" Data Release

 Announcements

 33

 5033

 October 6, 2024

 Data V5.1 Release - Faith

 Announcements

 6

 2323

 November 7, 2025

 Target Cyrus - New Primary Target

 Announcements

 28

 5809

 May 15, 2023

 Super Massive Data Release: Deep Dive

 Data Science

 81

 22891

 November 22, 2021

 Numerai v5.3 “Quantum” Data Release

 Announcements

 9

 1127

 July 21, 2026