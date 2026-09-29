# Search Space: h20260929_11_multiq_sue

One path, `multiq_sue_screen`, 8 batch candidates, budget 8 (<=24, single-mechanism lightweight exemption). Model grid inside the path: 7 alphas x 3 l1_ratios chosen by time-series CV inside each training set (not counted as candidates because selection never sees test-year data).

Keep-eligible: ENET_TOP50, ENET_TOP20, ENET_MOM_TOP50. Reference: SUE1_TOP50, MOM12_1_TOP50, EW_POOL. Placebos: RAND_TOP50, ENET_SHUF_TOP50. Information only outside the harness: ENET_LS.

Cost 10bp primary / 20bp stress per side, frozen screen_lane contract. Benchmark family: S3, baselines, placebos, SHY. Wave 9.2 band: not applicable (single-mechanism screen_lane batch).
