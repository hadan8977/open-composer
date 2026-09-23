# I-20260923-01：公开因子/异象库最近窗口收益普查

## 范围与 2026 红线

本次普查用**作者官方自己维护、随时间更新**的收益序列，不在本地数据上复现任何异象，先看哪些已发表因子在近期窗口真赚钱。五个来源：Kenneth French Data Library（因子 + 单变量十分位排序 + 49 行业）、AQR Datasets（BAB/QMJ/TSMOM/VME）、JKP Global Factor Data（jkpfactors.com，153 个因子 + 13 个主题）、Open Source Asset Pricing（openassetpricing.com，212 个 predictor 多空组合）、Hou-Xue-Zhang q-factor library（global-q.org，q5 因子 + 一个代表性测试组合）。全部由 `scripts/mine_factor_libraries.py` 下载官方原始文件、解析、算统计量，未使用任何记忆中的数字或搜索摘要里的数字。**硬性规则**：任何一条收益序列在计算任何统计量之前，都先丢弃 2026-01-01 及以后的观测；本文档不出现任何 2026 年收益数字。`manifest.json` 里记录的"文件最新日期"允许晚于 2026-01-01（那是文件元数据，不是统计量），例如 French 的文件本身更新到 2026-07，AQR 的 BAB/QMJ 文件更新到 2026-07，但用于计算的窗口最晚只到 2025-12。两个窗口：W_common = 2023-10 至 2024-12（15 个月，五个库都覆盖），W_select = 2023-10 至 2025-12（27 个月，只有覆盖到 2025-12 的库才有）。Sharpe 口径见脚本 docstring：已经是多空/零成本的序列（class b，以及 French 的 Mkt-RF、HXZ 的 R_MKT）用自身均值/波动直接算 Sharpe，不二次减 RF；只有多头组合和未减过 RF 的原始收益（class a：十分位、行业、重建的全市场组合）才减 French 的 RF 得到超额收益。stats.csv 的 `excess_convention` 列逐行记录用的是哪种口径。

## 覆盖表

| 来源 | 序列数（不分 VW/EW） | 文件最新日期（元数据） | 窗口覆盖 |
|---|---:|---|---|
| Kenneth French Data Library | 224 | 2026-07-31 | W_common + W_select |
| AQR Datasets | 5 | 2026-05-31 ~ 2026-07-31（各文件不同） | W_common + W_select |
| JKP Global Factor Data | 166（153 因子 + 13 主题） | 2025-12-31 | W_common + W_select |
| Open Source Asset Pricing | 198（212 个 predictor 中有 14 个的数据在 2023-10 前已结束，不进入任何窗口） | 2024-12-31 | 仅 W_common（release 2025.10 数据到 2024-12，未到 2025-12，按规则只报 W_common） |
| Hou-Xue-Zhang q-factor | 16（5 个 q5 因子 + 10 个 R11 动量十分位 + 1 个多空价差） | 2025-12-31 | W_common + W_select |

合计 609 个唯一序列（不分权重口径），窗口展开后 stats.csv 共 1,448 行。OSAP 的十分位/五分位另类权重压缩包（`PredictorAltPorts_DecilesVW.zip` 等）连续两次触发 Google Drive "Quota exceeded"（虚拟病毒扫描确认后的下载配额超限，不是请求写法的问题），已在 manifest.json 中如实记录为失败项，未替换为二手数据源；OSAP 的 212 路多空 predictor 宽表和 SignalDoc 说明文件（均小于 25MB，不触发该配额门槛）下载和解析都成功。`openassetpricing` PyPI 包因依赖 polars、在本机（无 AVX2）上连裸 `import polars` 都会 SIGILL 崩溃（即便设置了 `POLARS_SKIP_CPU_CHECK=1`），故改为直接对接 OSAP 官网 `/data/` 页面上公开的 Google Drive 直链，这是任务说明里允许的备选路径。

## 多头组合 Top 25（按 W_select CAGR；无 W_select 的库回退 W_common —— 本表中实际全部有 W_select）

| 组合 | 窗口 | CAGR | 年化波动 | Sharpe(超额) | 最大回撤 |
|---|---|---:|---:|---:|---:|
| 49 Industries: Gold（french, ew） | W_select | 99.3% | 46.3% | 1.64 | -24.6% |
| Net Share Issues 十分位 5（french, vw） | W_select | 75.0% | 24.0% | 2.30 | -8.0% |
| Market Beta 十分位 9（french, vw） | W_select | 71.9% | 26.5% | 2.03 | -12.2% |
| 49 Industries: Guns（french, ew） | W_select | 68.1% | 48.2% | 1.21 | -28.2% |
| 49 Industries: Aero（french, ew） | W_select | 67.3% | 46.9% | 1.19 | -19.7% |
| 49 Industries: Gold（french, vw） | W_select | 66.2% | 36.2% | 1.47 | -28.8% |
| Short-Term Reversal 十分位 10/Hi（french, vw） | W_select | 47.1% | 22.3% | 1.65 | -10.9% |
| 49 Industries: Steel（french, ew） | W_select | 46.8% | 22.1% | 1.66 | -8.3% |
| Variance 十分位 9（french, vw） | W_select | 46.8% | 32.3% | 1.21 | -12.8% |
| 49 Industries: Chips（french, vw） | W_select | 45.9% | 20.9% | 1.71 | -16.0% |
| Net Share Issues 十分位 9（french, vw） | W_select | 42.7% | 24.7% | 1.38 | -13.2% |
| 49 Industries: FabPr（french, ew） | W_select | 42.1% | 29.6% | 1.18 | -19.5% |
| Investment 十分位 10/Hi（french, vw） | W_select | 40.4% | 21.9% | 1.46 | -14.4% |
| Long-Term Reversal 十分位 10/Hi（french, vw） | W_select | 40.1% | 21.2% | 1.49 | -18.1% |
| D/P 十分位 1/Lo（french, vw） | W_select | 40.0% | 16.8% | 1.83 | -11.4% |
| Variance 十分位 8（french, vw） | W_select | 37.9% | 22.0% | 1.37 | -12.6% |
| Accruals 十分位 7（french, vw） | W_select | 37.7% | 19.8% | 1.50 | -10.3% |
| 49 Industries: Banks（french, vw） | W_select | 36.5% | 18.3% | 1.55 | -10.1% |
| Book-to-Market 十分位 10/Hi（french, vw） | W_select | 36.0% | 20.9% | 1.36 | -13.9% |
| 49 Industries: Aero（french, vw） | W_select | 35.7% | 14.2% | 1.91 | -3.8% |
| HXZ 测试组合：R11 动量十分位 10/Hi（hxz, vw） | W_select | 35.4% | 21.4% | 1.31 | -17.6% |
| Residual Variance 十分位 10/Hi（french, vw） | W_select | 34.6% | 32.7% | 0.93 | -21.9% |
| Residual Variance 十分位 5（french, vw） | W_select | 34.3% | 14.9% | 1.76 | -10.1% |
| Market Beta 十分位 8（french, vw） | W_select | 33.2% | 21.0% | 1.25 | -16.5% |
| CF/P 十分位 7（french, vw） | W_select | 32.8% | 16.9% | 1.50 | -10.7% |

注：本表按"该组合自身的绝对收益"排序，不代表"该异象的多头方向"。例如 Short-Term Reversal 十分位 10（Hi = 上月涨幅最高）排名靠前，但 French 官方 ST_Rev 因子的定义是"低减高"（多头是 Lo，见下表 long_side 列），十分位 10 只是"上月的赢家"这个原始组合近期绝对收益高，和"反转异象"本身方向相反；十分位排序的经济学多头方向要看下一张长短表和 stats.csv 的 `long_side` 列。

## 多空因子 Top 25（按 W_select Sharpe；OSAP 无 W_select，不进入本表，其 198 个多空 predictor 的 W_common 结果见 stats.csv）

| 因子 | 多头方向 | CAGR | 年化波动 | Sharpe | 最大回撤 |
|---|---|---:|---:|---:|---:|
| JKP: Change sales minus change Inventory (dsale_dinv) | direction=1 | 9.6% | 3.9% | 2.40 | -1.1% |
| JKP: Change in net operating assets (noa_gr1a) | direction=-1 | 5.9% | 2.4% | 2.39 | -1.0% |
| JKP: Change in net noncurrent operating assets (nncoa_gr1a) | direction=-1 | 5.9% | 2.5% | 2.32 | -1.4% |
| JKP: Change in operating cash flow to assets (ocf_at_chg1) | direction=1 | 9.9% | 4.2% | 2.27 | -2.0% |
| JKP 主题：Profit Growth Theme | 主题内因子合成 | 7.2% | 3.2% | 2.18 | -1.4% |
| JKP: Change in quarterly ROA (niq_at_chg1) | direction=1 | 10.5% | 5.2% | 1.95 | -3.5% |
| JKP: Change in quarterly ROE (niq_be_chg1) | direction=1 | 9.6% | 4.9% | 1.90 | -2.8% |
| JKP: Tax expense surprise (tax_gr1a) | direction=1 | 8.2% | 4.4% | 1.82 | -1.9% |
| JKP: Change sales minus change SG&A (dsale_dsga) | direction=1 | 12.6% | 6.7% | 1.80 | -2.7% |
| JKP: Change in long-term net operating assets (lnoa_gr1a) | direction=-1 | 5.1% | 3.0% | 1.64 | -2.4% |
| JKP: Change in long-term investments (lti_gr1a) | direction=-1 | 4.1% | 2.6% | 1.54 | -1.3% |
| JKP: Year 1-lagged return, nonannual (seas_1_1na) | direction=1 | 14.8% | 9.6% | 1.49 | -3.3% |
| JKP: Standardized earnings surprise (niq_su) | direction=1 | 6.1% | 4.1% | 1.47 | -2.5% |
| JKP: Net operating assets (noa_at) | direction=-1 | 9.5% | 7.1% | 1.31 | -4.9% |
| JKP: CAPEX growth 2y (capx_gr2) | direction=-1 | 5.0% | 4.2% | 1.20 | -2.6% |
| JKP: Labor force efficiency (sale_emp_gr1) | direction=1 | 8.3% | 6.9% | 1.19 | -4.1% |
| French Momentum 十分位价差（top-bottom, ew） | high（Mom=High-Low，官方定义） | 19.3% | 16.4% | 1.16 | -15.4% |
| JKP: Change in noncurrent operating assets (ncoa_gr1a) | direction=-1 | 3.3% | 2.9% | 1.14 | -3.8% |
| JKP: Abnormal corporate investment (capex_abn) | direction=-1 | 7.3% | 6.5% | 1.12 | -5.6% |
| JKP: Standardized Revenue surprise (saleq_su) | direction=1 | 4.6% | 4.2% | 1.09 | -2.1% |
| French Net Share Issues 十分位价差（top-bottom, ew） | low（任务简报给定方向） | 20.0% | 18.3% | 1.09 | -21.3% |
| JKP: Residual momentum t-12 to t-1 (resff3_12_1) | direction=1 | 6.6% | 6.7% | 1.00 | -6.2% |
| JKP: R&D capital-to-book assets (rd5_at) | direction=1 | 11.4% | 12.5% | 0.92 | -8.6% |
| JKP: Asset tangibility (tangibility) | direction=1 | 5.3% | 5.9% | 0.91 | -6.3% |
| JKP: Price momentum t-12 to t-7 (ret_12_7) | direction=1 | 7.0% | 7.9% | 0.90 | -4.9% |

## 49 个行业组合（按 W_select CAGR 排序，VW；EW 见 stats.csv）

| 排名 | 行业 | CAGR | 年化波动 | Sharpe | 最大回撤 |
|---:|---|---:|---:|---:|---:|
| 1 | Gold | 66.2% | 36.2% | 1.47 | -28.8% |
| 2 | Chips | 45.9% | 20.9% | 1.71 | -16.0% |
| 3 | Banks | 36.5% | 18.3% | 1.55 | -10.1% |
| 4 | Aero | 35.7% | 14.2% | 1.91 | -3.8% |
| 5 | Fun | 32.4% | 23.7% | 1.11 | -20.3% |
| 6 | Fin | 32.1% | 20.7% | 1.23 | -13.3% |
| 7 | Cnstr | 31.3% | 29.1% | 0.92 | -26.4% |
| 8 | Smoke | 30.6% | 20.4% | 1.19 | -15.3% |
| 9 | Ships | 30.0% | 17.5% | 1.33 | -11.5% |
| 10 | Softw | 29.1% | 17.5% | 1.29 | -14.8% |
| 11 | Hardw | 28.7% | 18.1% | 1.24 | -14.9% |
| 12 | Mines | 27.5% | 22.0% | 1.00 | -17.2% |
| 13 | Guns | 27.3% | 24.7% | 0.92 | -17.1% |
| 14 | Autos | 27.2% | 45.0% | 0.65 | -31.3% |
| 15 | RlEst | 25.7% | 27.7% | 0.79 | -17.5% |
| 16 | Rtail | 25.7% | 15.5% | 1.26 | -13.3% |
| 17 | Steel | 24.9% | 24.4% | 0.85 | -19.6% |
| 18 | Mach | 23.5% | 19.9% | 0.92 | -15.3% |
| 19 | Util | 23.0% | 13.0% | 1.31 | -7.8% |
| 20 | Other | 21.4% | 14.1% | 1.13 | -6.3% |
| 21 | Hlth | 20.1% | 22.4% | 0.72 | -17.0% |
| 22 | BldMt | 20.0% | 24.2% | 0.68 | -19.3% |
| 23 | ElcEq | 19.0% | 30.7% | 0.56 | -24.4% |
| 24 | Drugs | 18.0% | 16.4% | 0.80 | -15.9% |
| 25 | FabPr | 17.7% | 44.3% | 0.47 | -25.9% |
| 26 | Agric | 15.9% | 23.1% | 0.55 | -17.3% |
| 27 | Whlsl | 14.4% | 14.6% | 0.68 | -8.6% |
| 28 | Telcm | 14.2% | 15.7% | 0.62 | -8.3% |
| 29 | Soda | 14.1% | 12.9% | 0.72 | -10.5% |
| 30 | Trans | 13.7% | 17.9% | 0.55 | -15.8% |
| 31 | Books | 13.6% | 16.3% | 0.57 | -10.2% |
| 32 | PerSv | 13.5% | 20.5% | 0.49 | -19.1% |
| 33 | LabEq | 13.4% | 21.0% | 0.48 | -22.2% |
| 34 | MedEq | 11.4% | 16.4% | 0.45 | -9.5% |
| 35 | BusSv | 10.6% | 17.2% | 0.40 | -12.9% |
| 36 | Meals | 9.3% | 14.0% | 0.37 | -13.7% |
| 37 | Boxes | 7.1% | 17.6% | 0.21 | -18.9% |
| 38 | Txtls | 6.8% | 36.4% | 0.22 | -31.7% |
| 39 | Toys | 6.5% | 20.1% | 0.18 | -15.9% |
| 40 | Coal | 5.2% | 32.4% | 0.17 | -43.3% |
| 41 | Insur | 4.2% | 18.2% | 0.05 | -23.0% |
| 42 | Rubbr | 2.1% | 19.2% | -0.04 | -25.9% |
| 43 | Hshld | 1.7% | 12.4% | -0.18 | -15.2% |
| 44 | Paper | 1.6% | 16.2% | -0.12 | -20.9% |
| 45 | Oil | 0.6% | 16.8% | -0.16 | -16.5% |
| 46 | Chems | -2.4% | 18.4% | -0.30 | -20.9% |
| 47 | Clths | -3.1% | 24.6% | -0.20 | -33.3% |
| 48 | Food | -5.1% | 11.2% | -0.83 | -19.5% |
| 49 | Beer | -8.5% | 11.7% | -1.11 | -23.9% |

## 有什么突出的地方（只列事实，不给建议）

- **顶部聚类**：多头组合 Top25 里 24/25 来自 French（9 席行业、15 席十分位），1 席是 HXZ 的 R11 动量十分位；行业单独排名榜首四名是 Gold、Chips（半导体）、Banks、Aero，垫底两名是 Food、Beer——消费必需品行业在这个窗口跑输。
- **多空 Top25 几乎被 JKP 的"变化量"类因子占满**：25 席里 16 席是 JKP 因子/主题，且集中在会计科目环比变化（`dsale_dinv`、`noa_gr1a`、`nncoa_gr1a`、`ocf_at_chg1`、`niq_at_chg1`、`niq_be_chg1`、`tax_gr1a`、`dsale_dsga` 等），这些因子的年化波动普遍只有 2.4%~9.6%（远低于传统十分位价差 15%~30% 的波动），Sharpe 靠"低波动"而非"高收益"推高；同一批因子的 W_common 排名普遍更靠后（例如 `factors_tangibility` 从 W_common 第 133 名跳到 W_select 第 24 名），说明这批高 Sharpe 更多是近 27 个月的窗口特征，不是长期稳定的排名。
- **经典多空因子普遍为负或转负**：VW 口径下，除 Accruals(+0.18)、Momentum(+0.29)、Book-to-Market(+0.32)、HXZ R11 动量(+0.43) 外，本文算过的全部 French 十分位价差在 W_select 都是负 Sharpe——Long-Term Reversal(-1.31)、Investment/CMA(-1.06)、E/P(-0.97)、Short-Term Reversal(-0.93)、D/P(-0.93)、Residual Variance(-0.68)、Variance(-0.59)、CF/P(-0.50)、Size/ME(-0.49)、Net Share Issues(-0.43)、Beta(-0.29)、Operating Profitability(-0.06)。AQR 官方 Quality Minus Junk（USA）同期 Sharpe -1.17、CAGR -11.5%，AQR Value and Momentum Everywhere 的 US Value 分支 Sharpe -0.48。JKP 的 low_risk 主题（-0.60）、quality 主题（-0.73）、short_term_reversal 主题（-0.76）、value 主题（-0.24）同期也都是负 Sharpe，与 French/AQR 的方向一致。
- **同名因子跨库不一致**：JKP 的 `be_me`（账面市值比因子）W_select CAGR -0.6%，French 的 BEME 十分位价差（多头=Hi，按官方 HML 定义）同期 +4.3%（vw）/+3.6%（ew）；JKP 的 value 主题整体也是负的。两边都源自公开数据，方向不同，反映构造方法（JKP 全市场 capped-VW 连续截面 vs. French NYSE 断点十分位）造成的差异，不是任一方算错。
- **窗口排名剧烈翻转的例子**：行业 Gold 的 CAGR 排名从 W_common 第 370 名（全部 409 个 class-a 序列里）跳到 W_select 第 6 名；行业 Coal 从第 395 名到第 61 名；French Accruals 十分位价差的 Sharpe 排名从 W_common 第 4 名（全部 213 个 class-b 序列里）掉到 W_select 第 121 名，且 Sharpe 由 +2.12 转为 -0.29；JKP 的 `ni_ivol`、`iskew_ff3_21d`、`kz_index` 等因子也出现 rank_diff 超过 100 位的排名翻转。

## 未能获取的来源

OSAP 的另类权重十分位/五分位压缩包（`PredictorAltPorts_DecilesVW.zip`、`PredictorAltPorts_DecilesEW.zip`，均约 33MB）：两次下载都在 Google Drive 的大文件病毒扫描确认环节返回 "Quota exceeded"（配额超限，非登录墙也非 403），已如实记录在 `manifest.json` 的失败条目里，未替换为二手镜像。OSAP 的核心多空 predictor 宽表（`PredictorPortsFull` 等价文件）和 SignalDoc 说明文件均下载成功。
