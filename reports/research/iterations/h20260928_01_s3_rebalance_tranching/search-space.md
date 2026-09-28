# Search space: h20260928_01_s3_rebalance_tranching

One path, 22 candidates, no training, no parameter search.

- O00..O20: live S3 with the monthly signal close moved 0..20 sessions after month end.
  O00 is the live rule. O01..O20 are descriptive only (timing-luck distribution) and cannot
  be adopted from this run.
- T4: four equal tranches at offsets 0/5/10/15, netted in one account. The only adoption
  candidate, compared with O00 under the four conditions in candidate-manifest.json.
- Costs 10 bp per side primary, 20 bp stress; next-open fills.
