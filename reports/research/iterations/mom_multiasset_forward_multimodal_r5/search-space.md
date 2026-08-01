# Search Space: mom_multiasset_forward_multimodal_r5

The search space is exactly eight candidates across six paths. D01 and D02 are deterministic controls; M01 and M02 are fold-local trained models; L01 uses only four frozen LLM-derived formula factors; C01 combines those formulas with the matched M01 model; F01 must reproduce M01 when the formula modality is absent; P01 is a seeded shuffled-formula placebo and is selection prohibited.

There is no parameter sweep inside R5. Model hyperparameters, seeds, formulas, data, folds, costs, benchmarks, fallbacks and top-three equal weighting are fixed before evaluation. Any post-result variant is a new iteration and increments the cumulative trial count.

All eight candidates may run the matched historical transfer evaluation, but history through 2026-07-17 is already globally exposed. Promotion therefore requires the separately locked forward epoch beginning no earlier than 2026-07-30, followed by execution, safety and matched Paper TCA gates.
