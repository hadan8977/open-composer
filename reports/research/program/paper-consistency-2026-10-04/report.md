# T-20261004-55 paper vs research consistency (R1004-T55) — written 2026-10-04 10:24 UTC

Scripts: `scripts/paper_consistency_t55.py` (s3-flip | s3-fragility | c2-regen), `scripts/check_eom_sector_blend_parity.py --lane-returns`. Tests: `tests/test_paper_consistency_t55.py`.
Archives: pre-repair `data/live/backup-sip-daily-preswap-20261002`, current `data/sip/daily`. Both read-only. Panel end 2026-09-17 (frozen research panel).

## 1. S3 at 2026-08-31: a data flip, not a code divergence
- Same rule, same scores except SHY. 63-session score (close/close[-63]-1), pre-repair vs current:
  UPRO +0.2067% vs +0.2071%; TQQQ -16.216% vs -16.223%; SOXL -50.3%; USD -21.8%; TECL -22.8%; **SHY +0.1595% vs +0.4442%**.
- Top 2 = UPRO, TQQQ in both. TQQQ fails the filter in both. UPRO margin over SHY: **+0.047 pp (4.7 bp) pre-repair, -0.237 pp (-23.7 bp) current**. Swing 0.284 pp, all from SHY.
- renormalize_survivors: pre-repair UPRO has 100% of the base book (overlay 0.7916 -> 0.79 as paper traded); current has both picks dropped, so 100% SHY.
- SHY closes (81.52 -> 81.65 pre; 81.04 -> 81.40 current) differ by up to 0.60% over the lookback; 448 of 512 S3-symbol closes differ (all but TECL). UPRO's two endpoints moved -0.17% each, so its score did not.
- Adapter replay at the 09-17 close on the pre-repair archive (`load_price_panel`, `replay_books`, `_decide_overlay`): base book UPRO 1.0, last signal 08-31, multiplier 0.7916 (realized vol 50.53%). Matches the 09-18 paper decision. On the current archive the adapter gives SHY, same as the engine.
- Verdict: the 09-18 paper entry was correct for the data it saw; the 10-02 repair re-based SHY by ~28 bp over the window and moved the filter threshold. Which SHY series is right: 待核对 (not checked against raw prices/distributions here). Files: `s3_flip.json`.

## 2. S3 fragility, 128 month-ends 2016-01..2026-08 (net 10 bp, overlay on)
(a) Pre-repair vs current: **2 of 128 base books differ**: 2023-08-31 (UPRO+USD -> TQQQ+USD, pre margin 2.1 bp) and 2026-08-31 (UPRO -> SHY, 4.7 bp).
 Calendar-year return, current minus pre-repair: 2023 +1.00 pp, 2026 YTD +5.21 pp, 2025 -0.15 pp, other years within +-0.04 pp. Anchor CAGR 116.3% -> 118.4%, Sharpe 1.819 -> 1.844; full Sharpe 1.074 -> 1.081.
(b) i.i.d. 5 bp close noise, 50 seeds, base = current archive: **3 of 128 (2.3%) month-ends change in >=10% of seeds** (2017-03-31 32%, 2021-01-29 14%, 2023-08-31 46%); 96.9% never change.
 Decision margin (score units to nearest boundary): <10 bp in 2, <25 bp in 7, <50 bp in 12 of 128.
 Anchor 2024-01-08..2026-09-16: unperturbed CAGR 118.4% / Sharpe 1.844; seeds Sharpe mean 1.817, sd 0.028, range 1.762-1.847; CAGR mean 115.6%, sd 2.9 pp, range 109.9-118.7%.
 Full 2016-01-04..2026-09-16: unperturbed CAGR 47.2% / Sharpe 1.081; seeds Sharpe 1.075 sd 0.010 (1.056-1.092); CAGR 46.8% sd 0.6 pp.
(c) Per-slot cash (comparison only): same 3 unstable month-ends (3/128). Anchor unperturbed 104.2% / 1.660, seeds Sharpe 1.635 sd 0.027; full 44.7% / 1.035, seeds 1.029 sd 0.010. The 2 archive-differing month-ends are the same.
Reading: random noise at 5 bp rarely flips a month, but the 10-02 revision was a correlated 28 bp shift in SHY, and 12 of 128 month-ends (9%) sit within 50 bp of a boundary. The unperturbed run sits at the top of the seed distribution (in-sample selection, expected). Descriptive only; no rule or paper change. Files: `s3_fragility.json`.

## 3. C2 archive regeneration
- New file `reports/research/screens/h20260928_20_recent_opt/returns.sip-repaired-20261002.parquet` (untracked, not committed; columns C2__o00__net10/net20, 2692 rows, same index). Old `returns.parquet` md5 unchanged.
- Check: rebuilding C2 from the preswap archive reproduces the old stored file exactly (max diff 0.0), so the old file was made on that data.
- Sharpe net10 old -> new: select 1.076 -> 1.077; **anchor 1.602 -> 1.612**; holdout 2.590 -> 2.629; **stress 0.553 -> 0.537**. Anchor net20 1.455 -> 1.465. CAGR anchor 21.1% -> 21.3%.
- Daily return diff (net10): max 1.005% (2019-01-02), mean 0.0071%, median 0.0031%, p95 0.014%; 318 days > 1 bp, 20 days > 10 bp.
- Parity on the new file: `c2-parity.json` passed (0 weight mismatches, return diff 0.0, Sharpe equal). Lane Sharpe is computed from the stored file when `--lane-returns` is not the default (leaderboard.json is still pre-repair).
- C2 is not materially changed by the repair; the lane leaderboard.json/md were not rewritten.
