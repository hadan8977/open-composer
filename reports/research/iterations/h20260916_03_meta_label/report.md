# H-20260916-03 元标签仓位分档 — 结果

- 生成时间：2026-09-16T02:12:26.529991+00:00｜一级信号：`step13_m0b_mom_over_vol63_uni500_k50_gate_off`（未改动）
- 样本外区间：2020-04-03 → 2026-09-04（329 个调仓周，26 个季度，每季重训）
- 成本与执行：主成本 10 bp/边、压力成本 25 bp/边、`next_open`（周五收盘信号 → 下一交易日开盘成交）、现金腿 BIL，与 Step 13 完全一致
- 账本：这一轮不经过 `loop.run_experiment`，所以 `reports/research/ledger/experiments.jsonl` 一行都没写；表里的合同 v2 判定是 `reference_only` 披露，不构成晋级资格。

## 结论（先看这一段）

**假设被否定。** 两个二级模型（逻辑回归、LightGBM）都命中了卡上的停止条件：logit 命中 2 条（2_placebo_improvement_lt_50pct_of_real, 4_net_cagr_within_3pp_of_baseline）；lgbm 命中 2 条（2_placebo_improvement_lt_50pct_of_real, 4_net_cagr_within_3pp_of_baseline）。

- logit：同波动 SPY 超额从 -11.5% 改善到 -5.4%（+6.1 个百分点，达到了卡上要求的 3 个百分点），最大回撤从 -28.3% 改善到 -14.1%；但把标签在每周内部随机打乱（5 个种子）以后，占位版本的改善均值是 +6.0 个百分点，是真实版本的 99%，也就是说改善几乎全部来自“仓位只上到一半”，不是来自模型挑对了股票；同时 CAGR 从 30.3% 掉到 17.5%，远超卡上容许的 3 个百分点。
- lgbm：同波动 SPY 超额从 -11.5% 改善到 -3.8%（+7.7 个百分点，达到了卡上要求的 3 个百分点），最大回撤从 -28.3% 改善到 -16.9%；但把标签在每周内部随机打乱（5 个种子）以后，占位版本的改善均值是 +3.9 个百分点，是真实版本的 51%，也就是说改善几乎全部来自“仓位只上到一半”，不是来自模型挑对了股票；同时 CAGR 从 30.3% 掉到 20.1%，远超卡上容许的 3 个百分点。

一句话：**这套标签定义下的元标签不是过滤器，是一个去杠杆器**。平均持仓暴露掉到 50% 左右（概率几乎全部落在 0.4–0.6 的 1% 档），回撤和同波动超额都按比例变好，收益也按比例变差；随机标签能做到同样的事。

## 对照表（2024-01-02 起的近窗，与合同 v2 同窗口）

| 方案 | 2024→ CAGR | 最大回撤 | 同波动 SPY 超额 | 周胜率 | 每周双边换手 | 平均持仓暴露 |
|---|---:|---:|---:|---:|---:|---:|
| 等权 2%（基线） | 30.3% | -28.3% | -11.5% | 61.6% | 0.28 | 100.0% |
| 分档 logit（真实标签） | 17.5% | -14.1% | -5.4% | 62.3% | 0.16 | 50.7% |
| 分档 logit（占位，5 个种子均值） | 18.0% | -14.7% | -5.5% | 62.5% | 0.14 | 50.0% |
| 分档 lgbm（真实标签） | 20.1% | -16.9% | -3.8% | 60.9% | 0.33 | 49.3% |
| 分档 lgbm（占位，5 个种子均值） | 16.4% | -15.6% | -7.6% | 61.7% | 0.29 | 50.4% |
| SPY | 20.9% | -18.8% | 基准 | 59.0% | 0 | 100% |
| MTUM | 29.8% | -21.0% | — | 59.0% | 0 | 100% |
| SPMO | 37.4% | -20.1% | — | 57.0% | 0 | 100% |

SPY/MTUM/SPMO 三行取自合同 v2 的 `reference_disclosures`（2024-01-02..2026-09-08, close-to-close, no cost, SIP daily archive）。

## 全样本外窗口（含 2020-2023）

| 方案 | CAGR | 最大回撤 | 同波动 SPY 超额 | 周胜率 |
|---|---:|---:|---:|---:|
| 等权 2%（基线） | 28.7% | -39.9% | -7.5% | 56.7% |
| 分档 logit（真实标签） | 17.4% | -20.1% | -3.5% | 57.0% |
| 分档 logit（占位，5 个种子均值） | 16.4% | -20.6% | -3.4% | 57.3% |
| 分档 lgbm（真实标签） | 17.0% | -24.5% | -3.9% | 56.1% |
| 分档 lgbm（占位，5 个种子均值） | 15.9% | -21.6% | -4.5% | 57.0% |

## 二级模型的验证表现

| 变体 | 季度数 | 平均 AUC | 中位 AUC | AUC≥0.55 的季度占比 | 与真实超额的 rank IC |
|---|---:|---:|---:|---:|---:|
| real/logit | 26 | 0.5038 | 0.5068 | 19.2% | +0.0030 |
| real/lgbm | 26 | 0.5048 | 0.5096 | 7.7% | +0.0141 |
| placebo1/logit | 26 | 0.5015 | 0.5025 | 0.0% | -0.0008 |
| placebo1/lgbm | 26 | 0.4986 | 0.5002 | 3.8% | -0.0094 |
| placebo2/logit | 26 | 0.4997 | 0.5038 | 0.0% | +0.0221 |
| placebo2/lgbm | 26 | 0.4979 | 0.4968 | 0.0% | +0.0218 |
| placebo3/logit | 26 | 0.4967 | 0.4958 | 0.0% | +0.0113 |
| placebo3/lgbm | 26 | 0.5037 | 0.5015 | 3.8% | +0.0181 |
| placebo4/logit | 26 | 0.5064 | 0.5059 | 3.8% | -0.0206 |
| placebo4/lgbm | 26 | 0.4904 | 0.4921 | 3.8% | -0.0006 |
| placebo5/logit | 26 | 0.4963 | 0.4962 | 0.0% | -0.0162 |
| placebo5/lgbm | 26 | 0.4926 | 0.4920 | 0.0% | +0.0092 |

逻辑回归系数最大的四个特征及其符号稳定性（1.00 = 每个季度符号都一样）：

| 特征 | 平均系数 | 平均绝对系数 | 多数符号 | 符号稳定性（全部 26 个窗） |
|---|---:|---:|---:|---:|
| `vol_63` | -0.0970 | 0.1015 | -1 | 0.85 |
| `dist_from_252d_high` | -0.0941 | 0.0941 | -1 | 1.00 |
| `momentum_pct` | +0.0626 | 0.0709 | +1 | 0.88 |
| `weeks_in_book` | -0.0409 | 0.0521 | -1 | 0.73 |

## 分档占比（样本外每周每只持仓）

| 变体 | 0 档 | 1% 档 | 2% 档 |
|---|---:|---:|---:|
| real_logit | 1.4% | 95.8% | 2.7% |
| placebo1_logit | 0.0% | 100.0% | 0.0% |
| placebo2_logit | 0.0% | 100.0% | 0.0% |
| placebo3_logit | 0.0% | 100.0% | 0.0% |
| placebo4_logit | 0.1% | 99.8% | 0.1% |
| placebo5_logit | 0.1% | 99.8% | 0.1% |
| real_lgbm | 16.8% | 67.8% | 15.4% |
| placebo1_lgbm | 7.7% | 84.1% | 8.2% |
| placebo2_lgbm | 8.3% | 82.2% | 9.4% |
| placebo3_lgbm | 10.6% | 80.3% | 9.1% |
| placebo4_lgbm | 7.4% | 82.9% | 9.7% |
| placebo5_lgbm | 8.7% | 81.4% | 9.8% |

## 否定判据（卡上写死的四条，任一命中即停）

### logit

- **PASS** `1_vol_matched_excess_improvement_ge_3pp`：vol-matched SPY excess -0.1150 -> -0.0545 (improvement +0.0605, needs >= +0.0300)
- **FAIL** `2_placebo_improvement_lt_50pct_of_real`：real improvement +0.0605; placebo improvement over 5 seeds mean +0.0597 (min +0.0488, max +0.0691); mean ratio 0.987, worst-seed ratio 1.142
- **PASS** `3_validation_auc_ge_0_55_or_stable_signs`：mean validation AUC 0.5038; sign stability over the last 4 refits 1.00 (logit coefficients: last 4 1.00, all 26 0.73; quarterly rank-IC: last 4 0.50, all 26 0.50) -- card stops only when AUC < 0.55 *and* signs are unstable
- **FAIL** `4_net_cagr_within_3pp_of_baseline`：recent-window net CAGR 0.3034 -> 0.1748 (shortfall +0.1286, turnover/rebalance 0.280 -> 0.159)

### lgbm

- **PASS** `1_vol_matched_excess_improvement_ge_3pp`：vol-matched SPY excess -0.1150 -> -0.0383 (improvement +0.0767, needs >= +0.0300)
- **FAIL** `2_placebo_improvement_lt_50pct_of_real`：real improvement +0.0767; placebo improvement over 5 seeds mean +0.0389 (min +0.0281, max +0.0575); mean ratio 0.507, worst-seed ratio 0.749
- **PASS** `3_validation_auc_ge_0_55_or_stable_signs`：mean validation AUC 0.5048; sign stability over the last 4 refits 1.00 (logit coefficients: last 4 1.00, all 26 0.73; quarterly rank-IC: last 4 1.00, all 26 0.58) -- card stops only when AUC < 0.55 *and* signs are unstable
- **FAIL** `4_net_cagr_within_3pp_of_baseline`：recent-window net CAGR 0.3034 -> 0.2008 (shortfall +0.1026, turnover/rebalance 0.280 -> 0.328)

## 数据口径与需要知道的坑

- **卡上写的是 2016-01 起，实际只能从 2017-01-06 起。** `momentum_252_21` 需要 252 个交易日历史，日线档案本身从 2016-01-04 开始，所以 2016 年整年这一列全是空值（`data/features/daily/2016.parquet` 里非空行数 = 0）。2016 只当暖机年加载。
- **滚动 3 年训练 + 4 周隔离 + 每季重训，最早只能从 2020Q2 开始验证。** 因此样本外从 2020Q2 起算；2024 年起的近窗是其中的一段。
- **这 26 个季度既是 AUC 的验证集，也是分档评估的样本外区间。** 分档阈值（0.4 / 0.6）和模型超参数都是卡上事先写死、没有在这些季度上调过的，所以不存在在同一段数据上选参数的问题；但也没有第三段独立数据可以再验一次，这是这一轮证据强度的上限。
- **基线在近窗算出 30.3% 而账本里那一格是 33.0%。** 两者是同一批持仓（最大回撤同为 -28.3%，完全一致），差别只在窗口边界：账本那一格的调仓表从 2024-01-08 才开始，而这里的调仓表从 2020 年就在跑，于是近窗把2024-01-02 至 01-08 这段（由 2023-12-29 的持仓产生）也算进来了，同时它也没有账本那一格在窗口内一次性建仓的 100% 换手成本。两个数都对，口径不同，不能混用。
- **有 7 个样本外调仓周是空仓周**（2020-12-24, 2021-04-09, 2021-04-16, 2021-04-23, 2022-10-21, 2022-10-28, 2026-01-02）：宇宙面板 `data/features/universe` 里存在个别只有 1 行、月末日期在月中的异常 cohort（如 2019-10-02、2021-04-02），`universe_as_of_calendar_month` 会把那一行当成当月 cohort，导致 `adv_rank <= 500` 过滤后没有可选标的。这是既有数据的毛病，不是这一轮引入的，基线和分档受影响完全一样，所以不影响对比；但要记在账上。
- **标签是“相对当周组合中位数”，这决定了分档只能在组合内部搬钱，不能做择时。** 每周正负各一半，组合层特征（SPY 距 200 日线、截面宽度）在同一周内是常数，对这个标签没有主效应可学，于是概率天然堆在 0.5 附近，几乎全部落进 1% 档，总暴露掉到 50% 左右。观察到的回撤改善主要是“少拿一半”，不是“挑对了”。
- **没有写账本。** 这一轮不走 `loop.run_experiment`，`reports/research/ledger/experiments.jsonl` 未改动；报告里的合同 v2 判定是 `reference_only` 披露，不构成任何晋级资格。

## 特征来源（哪些是现成列、哪些是我算的）

| 特征 | 来源 |
|---|---|
| `momentum_pct` | 推导：`PickCollector` 记录的该股 `momentum_252_21_over_vol_63` 在当周前 500 个可交易标的里的升序分位（1.0 = 最强）。组合只有前 50 名，光看组合内部排名看不出截面尾部在哪，所以必须在内核里记。 |
| `vol_63` | 现成列 `data/features/daily` 的 `vol_63`（63 日日波动）。 |
| `excess_21d_vs_book` | 推导：`ret_21` 减去当周组合的 `ret_21` 中位数。 |
| `weeks_in_book` | 推导：该股连续入选的周数（含当周），由导出的持仓历史算出。 |
| `dist_from_252d_high` | 现成列 `dist_from_252d_high`（距 52 周高点，<= 0）。 |
| `overnight_intraday_ratio` | 推导：`overnight_return_21d_mean / intraday_return_21d_mean`，分母绝对值 < 1e-5 记为缺失，结果截断在 ±5（两个小的带符号均值相除本身无界，不截断会主导线性模型）。 |
| `spy_gap_200sma` | 现成列 `data/features/regime_daily` 的 `spy_gap_200sma`。 |
| `breadth_50d` | 现成列 `data/features/regime_daily` 的 `breadth_50d`（截面宽度）。 |
