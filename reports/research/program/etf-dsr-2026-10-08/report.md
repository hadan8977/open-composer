# T-20261005-31 ETF 四条子策略：试验数登记与 DSR（协调码 R1005-T31）

只测量，不改任何策略、规格或门槛。数据：`results.json`（同目录），脚本：`compute.py`（`scripts/run_capped.sh --mem 1.5G -- uv run python reports/research/program/etf-dsr-2026-10-08/compute.py`，约 8 分钟）。DSR 用 `open_composer/research/scorecard_v2.py::dsr`，口径取 `config/evaluation-standard-v2.json` 的 `dsr` 段：`n_eff = 1+(N-1)(1-平均两两相关)`，`var_sr` = 族内各变体年化夏普的横截面方差。P1 档门槛 DSR >= 0.70（`tiers.P1_paper_incubation.dsr_min`）。

## 一页结论（主结果 = 近期窗口 2024-01-08..2026-09-17，N = n_high）

| 子策略 | n_low | n_high(=n_used) | 近期超额夏普 | DSR 近期 | DSR 全期 | DSR 近期 @n_low | 近期 DSR 跌破 0.70 的 N | 过 P1 的 DSR |
|---|---|---|---|---|---|---|---|---|
| S1 | 104 | 278 | 1.31 | 0.6995 | 0.8312 | 0.768 | 276 | **否** |
| S2 | 106 | 294 | 1.65 | 0.8364 | 0.9080 | 0.886 | 3371 | **是** |
| S3 | 120 | 317 | 1.60 | 0.8151 | 0.9163 | 0.866 | 2270 | **是** |
| C2 | 25 | 47 | 1.59 | 0.5664 | 0.3417 | 0.691 | 24 | **否** |

读法：
- S2、S3 在近期和全期、在 N 的 0.5 至 5 倍内都过 0.70；近期 DSR 跌破 0.70 要 N 分别达到 3371、2270（远高于登记数 294、317）。
- **S1 近期 DSR = 0.6995，按严格口径不过 P1**，但差 0.0005，等于踩线：N 取 n_low=104 时 0.768（过），n_high=278 时 0.6995（不过），跌破 0.70 的 N=276（登记上界 278）。结论取决于把哪些相邻试验算进族里，不能说"明确过"也不能说"明确不过"；全期 DSR 0.831 过。
- **C2 近期 DSR = 0.566，不过**；n_low=25 时 0.691 仍不过，N 取 0.5 倍（23.5）才 0.703。全期 DSR 0.342 更低。跌破 0.70 的 N 仅 24。C2 的族里夏普离散度大（var_sr 0.54，族内最高夏普 2.46），期望最大夏普被抬到 1.49，而 C2 自己 1.59。（C2 的 spec 描述里写的"20 变体后 DSR 0.77"用的是另一套 var_sr/N，本次按标准 config 口径重算，两者不矛盾也不能互相替代。）
- 对 10-15 的 S3+C2 试点提议：S3 的 DSR 前提满足；**C2 的 DSR 前提不满足**，需要在提议里写明（n_low=25 时 0.691 仍低于 0.70；N 取 0.5 倍 0.703 刚好过线；把相关性假设提到 0.8 才到 0.759，而可重跑变体的实测相关只有 0.41）。

## 方法与假设（四条共用）

1. **序列**：现行规格的日净收益（每边 10 bp，信号日收盘、次日开盘成交）减去 BIL 日收益（标准的 `excess_over: BIL`）。S1/S2/S3 用冻结引擎 `scripts/run_h20260918_05_recent_menu.py`、`run_h20260922_05_salvage.py`、`run_h20260928_23_s1_s2_rebalance_timing.py` 在 2015-01-02 起的面板上重建，**5 个调仓偏移（信号日后移 0..4 个交易日）等权平均**（`offsets_blend`），偏移 0 与 `salvage.run_cell` 逐日一致（最大绝对差 S1 0.0e+00、S2 6.9e-18、S3 1.4e-17）。S1 周频，5 个偏移就是一周五个交易日；S2/S3 月频，5 个偏移是月末后第 0..4 个交易日。现行规格：S1 无叠加层；S2 下行波动率目标 0.156；S3 波动率目标 0.40 加 QQQ 逢低加档（目标 0.60、持有 10 日）。C2 是日历锚定规则（单一版本，无调仓偏移），序列取 `reports/research/screens/h20260928_20_recent_opt/returns.parquet` 的 `C2__o00__net10`，减 BIL。
2. **窗口**：近期 = 2024-01-08（config 的 `recent_window_start`）至面板末 2026-09-17，676 个交易日；全期 = 2017-01-03（252 日回看和 260 日最短历史之后）至 2026-09-17，2440 个交易日。两个窗口各自重算 var_sr 与相关。
3. **重跑与假设**：能重跑的变体（H-20260918-05 的 104 格，其中 64 个轮动格同样做 5 偏移等权、40 个趋势格为单序列；各叠加层格；C2 族取筛选日收益文件）用于量测 var_sr 与相关。重跑不了的变体（只有汇总指标或没有收益文件的）计入 N，其两两相关**假设为 0.5**；总的平均相关 = 按配对数加权的（量测配对的实测相关、含不可重跑成员配对的 0.5）。各条的假设配对占比见下，写在 `results.json` 的 `*_detail.share_of_pairs_with_assumed_corr_0.5`。
4. **N 的取法**：`n_low` = 当前规格被选出之前、直接塑造该规格的变体（含叠加层的选择）；`n_high` = n_low 加同一机制族里其它所有看过的变体（含之后的描述性检验）。**主结果取 n_high**（S3 按简报从严；S1/S2/C2 沿用同一规则，保持一致）。对照放在 `n_low` 和 0.5/1/2/5 倍列。
5. **不可数的试验**：S3 的 2023-2025 补救设计里，H-20260923-09（归因）没有候选清单，H-20260928-13 清单为空（预算 80 但未登记候选）；只在报告或备注里提及的变体无法计数。已用 2 倍、5 倍 N 的敏感性行覆盖（S3 近期 DSR 在 5 倍 N=1585 时 0.722，仍过 0.70）。
6. **局限**：(a) var_sr 是跨族成员的横截面方差，族里混有杠杆趋势格、不同菜单格，离散度偏大，对 S1/S2/S3 是保守的；对 C2 则族里混入了差别很大的日历规则，同样保守。(b) 平均相关的 0.5 假设占 86%-88%（S1-S3）与 31%（C2）的配对，改为 0.3 或 0.8 的结果列在 `sensitivity_corr_at_n_used`，对 S1 的结论有影响（0.3 时 0.673，0.8 时 0.760）。(c) 窗口末端同在 2026-09-17，近期窗口含 2026 年留出窗，所以这是"含已看数据"的 DSR，不是样本外检验。(d) 偏移 0..4 与 21 个偏移的分布不同，21 偏移的描述性结果见 H-20260928-01 与 -23。

## S1  `us_etf_sector_rotation_252_top2_weekly`

### 试验族（每项来源路径）

| 变体族 | 个数 | 计入 n_low | 来源 | 重跑量测 |
|---|---|---|---|---|
| H-20260918-05 grid: 64 rotation cells (4 menus x lookback{63,126,252,blend} x top_n{1,2} x {monthly,weekly}) + 40 levered-trend cells | 104 | 是 | `reports/research/iterations/h20260918_05_recent_menu/candidate-manifest.json` | 是 |
| H-20260918-06 ETF pool: 96 cells (8 score x leverage families) | 96 | 否 | `reports/research/iterations/h20260918_06_etf_pool/candidate-manifest.json` | 否（假设相关 0.5） |
| Giants sweep 2026-09-22: 24 cells (F1 TQQQ RSI hedge, F2, F4, F5, F6 industry trend, F7) | 24 | 否 | `reports/research/iterations/giants_sweep_20260922/candidate-manifest.json` | 否（假设相关 0.5） |
| H-20260922-04 RSI-branch rotation: 16 cells | 16 | 否 | `reports/research/iterations/h20260922_04_rsi_branch/candidate-manifest.json` | 否（假设相关 0.5） |
| H-20260927-01 sleeve combination: 7 candidates | 7 | 否 | `reports/research/iterations/h20260927_01_sleeve_combination/candidate-manifest.json` | 否（假设相关 0.5） |
| H-20260928-40 equity ETF menus: 24 candidates | 24 | 否 | `reports/research/iterations/h20260928_40_equity_etf_menus/candidate-manifest.json` | 否（假设相关 0.5） |
| H-20260922-05 path A, S1 vol-target cells 0.086/0.114 (tested, not adopted) | 2 | 否 | `reports/research/iterations/h20260922_05_salvage/candidate-manifest.json` | 是 |
| H-20260928-23 S1 weekly rebalance-day offsets O00..O04 (descriptive) | 5 | 否 | `reports/research/iterations/h20260928_23_s1_rebalance_timing/candidate-manifest.json` | 否（假设相关 0.5） |

n_low = 104，n_high = n_used = 278。

### 数字

| 项 | 近期 | 全期 |
|---|---|---|
| 窗口 | 2024-01-08..2026-09-17 | 2017-01-03..2026-09-17 |
| 交易日数 | 676 | 2440 |
| 年化超额夏普（对 BIL） | 1.309 | 0.758 |
| PSR(0) | 0.9819 | 0.9894 |
| 偏度 | -0.42 | -0.80 |
| 峰度 | 7.74 | 13.50 |
| var_sr（年化夏普横截面方差） | 0.1392 | 0.0282 |
| 可重跑变体数 | 106 | 106 |
| 平均两两相关（含假设部分） | 0.520 | 0.516 |
| 其中可重跑变体的实测相关 | 0.638 | 0.612 |
| 假设相关 0.5 的配对占比 | 0.86 | 0.86 |
| n_eff | 134.0 | 135.0 |
| 期望最大夏普 SR0（年化） | 0.982 | 0.443 |
| **DSR** | **0.6995** | **0.8312** |
| 跌破 0.70 时的 N | 276 | 4741 |

敏感性（N 取 n_used 的倍数，DSR）：

| N | 0.5x | 1x | 2x | 5x | n_low |
|---|---|---|---|---|---|
| 近期 | 0.748 | 0.699 | 0.651 | 0.587 | 0.768 |
| 全期 | 0.861 | 0.831 | 0.800 | 0.758 | 0.873 |

相关假设敏感性（近期、N = n_used，把平均相关固定为 0.3/0.5/0.8）：0.673 / 0.697 / 0.760。

- series = mean of 5 rebalance offsets (signal day +0..+4 sessions), 10 bp per side, next-open fills, minus BIL daily return; O00 reproduces salvage.run_cell (max abs diff 0.00e+00).
- rerun variants (measured var_sr / corr): the 104-cell H-20260918-05 grid (rotation cells 5-offset blended, trend cells single) plus the listed overlay cells; all other family members are not rerun and enter N with an assumed pairwise corr 0.5.

## S2  `us_etf_growth_rotation_blend_top2_monthly`

### 试验族（每项来源路径）

| 变体族 | 个数 | 计入 n_low | 来源 | 重跑量测 |
|---|---|---|---|---|
| H-20260918-05 grid: 64 rotation cells (4 menus x lookback{63,126,252,blend} x top_n{1,2} x {monthly,weekly}) + 40 levered-trend cells | 104 | 是 | `reports/research/iterations/h20260918_05_recent_menu/candidate-manifest.json` | 是 |
| H-20260922-05 path A, S2 vol-target cells 0.117/0.156 (0.156 adopted) | 2 | 是 | `reports/research/iterations/h20260922_05_salvage/candidate-manifest.json` | 是 |
| H-20260918-06 ETF pool: 96 cells (8 score x leverage families) | 96 | 否 | `reports/research/iterations/h20260918_06_etf_pool/candidate-manifest.json` | 否（假设相关 0.5） |
| Giants sweep 2026-09-22: 24 cells (F1 TQQQ RSI hedge, F2, F4, F5, F6 industry trend, F7) | 24 | 否 | `reports/research/iterations/giants_sweep_20260922/candidate-manifest.json` | 否（假设相关 0.5） |
| H-20260922-04 RSI-branch rotation: 16 cells | 16 | 否 | `reports/research/iterations/h20260922_04_rsi_branch/candidate-manifest.json` | 否（假设相关 0.5） |
| H-20260927-01 sleeve combination: 7 candidates | 7 | 否 | `reports/research/iterations/h20260927_01_sleeve_combination/candidate-manifest.json` | 否（假设相关 0.5） |
| H-20260928-40 equity ETF menus: 24 candidates | 24 | 否 | `reports/research/iterations/h20260928_40_equity_etf_menus/candidate-manifest.json` | 否（假设相关 0.5） |
| H-20260928-23 S2 monthly rebalance-day offsets O00..O20 (descriptive) | 21 | 否 | `reports/research/iterations/h20260928_23_s1_s2_rebalance_timing/candidate-manifest.json` | 否（假设相关 0.5） |

n_low = 106，n_high = n_used = 294。

### 数字

| 项 | 近期 | 全期 |
|---|---|---|
| 窗口 | 2024-01-08..2026-09-17 | 2017-01-03..2026-09-17 |
| 交易日数 | 676 | 2440 |
| 年化超额夏普（对 BIL） | 1.647 | 0.889 |
| PSR(0) | 0.9955 | 0.9967 |
| 偏度 | -0.47 | -0.55 |
| 峰度 | 6.23 | 5.92 |
| var_sr（年化夏普横截面方差） | 0.1508 | 0.0294 |
| 可重跑变体数 | 106 | 106 |
| 平均两两相关（含假设部分） | 0.519 | 0.515 |
| 其中可重跑变体的实测相关 | 0.643 | 0.616 |
| 假设相关 0.5 的配对占比 | 0.87 | 0.87 |
| n_eff | 142.1 | 143.1 |
| 期望最大夏普 SR0（年化） | 1.030 | 0.455 |
| **DSR** | **0.8364** | **0.9080** |
| 跌破 0.70 时的 N | 3371 | 83185 |

敏感性（N 取 n_used 的倍数，DSR）：

| N | 0.5x | 1x | 2x | 5x | n_low |
|---|---|---|---|---|---|
| 近期 | 0.871 | 0.836 | 0.800 | 0.748 | 0.886 |
| 全期 | 0.927 | 0.908 | 0.887 | 0.857 | 0.936 |

相关假设敏感性（近期、N = n_used，把平均相关固定为 0.3/0.5/0.8）：0.817 / 0.834 / 0.879。

- series = mean of 5 rebalance offsets (signal day +0..+4 sessions), 10 bp per side, next-open fills, minus BIL daily return; O00 reproduces salvage.run_cell (max abs diff 6.94e-18).
- rerun variants (measured var_sr / corr): the 104-cell H-20260918-05 grid (rotation cells 5-offset blended, trend cells single) plus the listed overlay cells; all other family members are not rerun and enter N with an assumed pairwise corr 0.5.

## S3  `us_etf_levered_rotation_63_top2_monthly`

### 试验族（每项来源路径）

| 变体族 | 个数 | 计入 n_low | 来源 | 重跑量测 |
|---|---|---|---|---|
| H-20260918-05 grid: 64 rotation cells (4 menus x lookback{63,126,252,blend} x top_n{1,2} x {monthly,weekly}) + 40 levered-trend cells | 104 | 是 | `reports/research/iterations/h20260918_05_recent_menu/candidate-manifest.json` | 是 |
| H-20260922-02 S3 vol-target/brake grid: 3 targets x 2 brakes x 2 lookbacks | 12 | 是 | `reports/research/iterations/h20260922_02_s3_voltarget/candidate-manifest.json` | 否（假设相关 0.5） |
| H-20260922-05 path B dip-boost cells: boost target {0.55,0.60} x hold {5,10} | 4 | 是 | `reports/research/iterations/h20260922_05_salvage/candidate-manifest.json` | 是 |
| H-20260918-06 ETF pool: 96 cells (8 score x leverage families) | 96 | 否 | `reports/research/iterations/h20260918_06_etf_pool/candidate-manifest.json` | 否（假设相关 0.5） |
| Giants sweep 2026-09-22: 24 cells (F1 TQQQ RSI hedge, F2, F4, F5, F6 industry trend, F7) | 24 | 否 | `reports/research/iterations/giants_sweep_20260922/candidate-manifest.json` | 否（假设相关 0.5） |
| H-20260922-04 RSI-branch rotation: 16 cells | 16 | 否 | `reports/research/iterations/h20260922_04_rsi_branch/candidate-manifest.json` | 否（假设相关 0.5） |
| H-20260923-10 levered lanes: 5 candidates | 5 | 否 | `reports/research/iterations/h20260923_10_levered_lanes/candidate-manifest.json` | 否（假设相关 0.5） |
| H-20260923-11 S3 bear guard: 5 candidates | 5 | 否 | `reports/research/iterations/h20260923_11_s3_bear_guard/candidate-manifest.json` | 否（假设相关 0.5） |
| H-20260923-12 S3 defense-first: 3 candidates | 3 | 否 | `reports/research/iterations/h20260923_12_s3_defense_first/candidate-manifest.json` | 否（假设相关 0.5） |
| H-20260927-01 sleeve combination: 7 candidates | 7 | 否 | `reports/research/iterations/h20260927_01_sleeve_combination/candidate-manifest.json` | 否（假设相关 0.5） |
| H-20260928-01 S3 rebalance tranching / offsets: 22 candidates | 22 | 否 | `reports/research/iterations/h20260928_01_s3_rebalance_tranching/candidate-manifest.json` | 否（假设相关 0.5） |
| H-20260928-04 S3 alt-diversifier batch 1: 19 candidates | 19 | 否 | `reports/research/iterations/h20260928_04_s3_alt_div_batch1/candidate-manifest.json` | 否（假设相关 0.5） |

n_low = 120，n_high = n_used = 317。

### 数字

| 项 | 近期 | 全期 |
|---|---|---|
| 窗口 | 2024-01-08..2026-09-17 | 2017-01-03..2026-09-17 |
| 交易日数 | 676 | 2440 |
| 年化超额夏普（对 BIL） | 1.599 | 0.919 |
| PSR(0) | 0.9946 | 0.9975 |
| 偏度 | -0.40 | -0.61 |
| 峰度 | 5.91 | 6.82 |
| var_sr（年化夏普横截面方差） | 0.1499 | 0.0303 |
| 可重跑变体数 | 109 | 109 |
| 平均两两相关（含假设部分） | 0.517 | 0.514 |
| 其中可重跑变体的实测相关 | 0.646 | 0.620 |
| 假设相关 0.5 的配对占比 | 0.88 | 0.88 |
| n_eff | 153.6 | 154.6 |
| 期望最大夏普 SR0（年化） | 1.037 | 0.467 |
| **DSR** | **0.8151** | **0.9163** |
| 跌破 0.70 时的 N | 2270 | 131456 |

敏感性（N 取 n_used 的倍数，DSR）：

| N | 0.5x | 1x | 2x | 5x | n_low |
|---|---|---|---|---|---|
| 近期 | 0.852 | 0.815 | 0.776 | 0.722 | 0.866 |
| 全期 | 0.934 | 0.916 | 0.896 | 0.868 | 0.941 |

相关假设敏感性（近期、N = n_used，把平均相关固定为 0.3/0.5/0.8）：0.794 / 0.813 / 0.861。

- series = mean of 5 rebalance offsets (signal day +0..+4 sessions), 10 bp per side, next-open fills, minus BIL daily return; O00 reproduces salvage.run_cell (max abs diff 1.39e-17).
- rerun variants (measured var_sr / corr): the 104-cell H-20260918-05 grid (rotation cells 5-offset blended, trend cells single) plus the listed overlay cells; all other family members are not rerun and enter N with an assumed pairwise corr 0.5.
- S3 counts are a floor: variants mentioned only in reports or notes of the 2023-2025 salvage designs (H-20260923-09 attribution has no manifest, H-20260928-13 manifest is empty) are not countable and are covered by the 2x and 5x sensitivity rows.

## C2  `us_etf_eom_sector_blend_monthly`

### 试验族（每项来源路径）

| 变体族 | 个数 | 计入 n_low | 来源 | 重跑量测 |
|---|---|---|---|---|
| H-20260928-05 batch 2: 7 candidates (EOM_REVERSAL_SPY = E0 and FRONT_RUN_SECTOR_TOP2 = S0 are counted once, in the next line) | 5 | 是 | `reports/research/iterations/h20260928_05_registry_etf_batch2/candidate-manifest.json` | 是 |
| H-20260928-20 recent-regime optimisation: 20 candidates (E0..E7, S0..S_ABSFILTER, C1, C2) | 20 | 是 | `reports/research/iterations/h20260928_20_recent_regime_opt/candidate-manifest.json` | 是 |
| H-20260928-42 opex week calendar: 8 candidates (its 12 PLACEBO_* controls are not search trials and are excluded from N and from the variance/correlation) | 8 | 否 | `reports/research/iterations/h20260928_42_opex_week/candidate-manifest.json` | 是 |
| H-20260930-10 industry seasonality: 6 candidates | 6 | 否 | `reports/research/iterations/h20260930_10_industry_seasonality/candidate-manifest.json` | 是 |
| H-20260930-01 rebalancing front-run: 8 candidates (no returns file -> not rerun) | 8 | 否 | `reports/research/iterations/h20260930_01_rebalancing_front_run/candidate-manifest.json` | 否（假设相关 0.5） |

n_low = 25，n_high = n_used = 47。

### 数字

| 项 | 近期 | 全期 |
|---|---|---|
| 窗口 | 2024-01-08..2026-09-17 | 2017-01-03..2026-09-17 |
| 交易日数 | 676 | 2440 |
| 年化超额夏普（对 BIL） | 1.592 | 0.748 |
| PSR(0) | 0.9958 | 0.9892 |
| 偏度 | 0.39 | -0.43 |
| 峰度 | 8.19 | 10.83 |
| var_sr（年化夏普横截面方差） | 0.5415 | 0.1944 |
| 可重跑变体数 | 39 | 39 |
| 平均两两相关（含假设部分） | 0.440 | 0.478 |
| 其中可重跑变体的实测相关 | 0.413 | 0.468 |
| 假设相关 0.5 的配对占比 | 0.31 | 0.31 |
| n_eff | 26.8 | 25.0 |
| 期望最大夏普 SR0（年化） | 1.491 | 0.881 |
| **DSR** | **0.5664** | **0.3417** |
| 跌破 0.70 时的 N | 24 | 11 |

敏感性（N 取 n_used 的倍数，DSR）：

| N | 0.5x | 1x | 2x | 5x | n_low |
|---|---|---|---|---|---|
| 近期 | 0.703 | 0.566 | 0.434 | 0.286 | 0.691 |
| 全期 | 0.501 | 0.342 | 0.217 | 0.110 | 0.486 |

相关假设敏感性（近期、N = n_used，把平均相关固定为 0.3/0.5/0.8）：0.523 / 0.588 / 0.759。

- C2 is calendar-anchored (one version, no rebalance-day offsets): the single series is C2__o00__net10 of reports/research/screens/h20260928_20_recent_opt/returns.parquet (10 bp per side, next-open fills), minus BIL.
- rerun variants = every o00 net10 column of the screen return files for batch 2 (5 non-duplicate candidates), the 20 recent-regime variants, the opex-week (non-placebo) and industry-seasonality screens; H-20260930-01 (8) has no returns file and enters N with assumed corr 0.5.

## 文件

- `results.json`（全部数字，含各窗口的敏感性、n_eff、var_sr、可重跑成员的夏普列表）
- `compute.py`（可复跑）
