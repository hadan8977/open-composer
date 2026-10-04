# Hypotheses: t20261004_book_v15_fm

## Hypothesis

The 22 slow inputs of the equal-weight composite M0 are factors whose industry- and beta-neutral long-short returns are positively autocorrelated at the one-year horizon (Ehsani-Linnainmaa 2022), so holding only the inputs (or themes) with a positive trailing 12-month long-short return, under the unchanged v1.2 construction and costs, raises the offset-median net Sharpe by at least 0.10 in both the recent and the stress-ML window.

## Failure mode

Factor momentum is weak at the individual-factor level and does not beat buy-and-hold of the same factors (Fan-Li-Liao-Liu 2022); our own rolling-IC weighting M1 lost to M0 in v1.2; with only 22 correlated inputs the signal-level gain is diluted by rank-normalization, industry demeaning and the hedge, or eaten by the turnover of inputs switching in and out.

## Measurement

Stage A: simplified weekly gross long-short Sharpe (all 5 offsets) versus M0, rank IC on y21, score autocorrelation, included share and switches per year, and a 20-seed Markov timing placebo per candidate. Stage B: v1.2 strategy layer, offset-median net Sharpe and delta versus B0r per window, offsets improved, OLS and Dimson beta, vol-matched paired NW t, 2x cost, turnover and cost, phase split (report only). Stage C (selected candidate only, separate brief): account layer, 20-seed within-date placebo, evaluation-standard v2.0.2 tier with family N = 22.

## Stop/Pivot criterion

No candidate beats M0's simplified gross Sharpe in both windows with its timing placebo passed (Stage A), or none meets E1/E2/E4/E5 (Stage B): keep M0 and close recency (factor-momentum) timing of the inputs for the v1.2 construction; the timing layer then has only the volatility-state variant left (design section 12, data-constrained), and the signal layer moves to new inputs (T-20261002-04 Lazy Prices).

## 预注册全文（2026-10-04 16:44 UTC 写定，16:20 主审轮 Opus；早于任何主题择时在 v1.2 构造下的组合层或简化毛收益数字）

### 0. 为什么做，写之前看过什么

- **纲领位置**：设计文档第 12 节的择时层，研究纲领"候选清单 v2"最后一条（动量择时：因子动量）。不是新格子。
- **为什么以前没做**：10-01 RF1 的方向评审考虑过因子择时，引用 Fan 等 2022（因子动量打不赢同一组因子的买入持有），选了 VIX 状态变体 M0V（因数据约束未跑），没有测近期收益择时。那是按文献摘要做的取舍，没有用本仓库数据检验过。
- **相关的负面结果**：v1.2 的 M1（按滚动残差 IC 加权）近期净夏普 1.389，低于 M0 的 1.506。区别：M1 用残差 IC，剥掉了这本书实际赚的风格溢价；本合同用行业和 beta 中性、但不剥风格的多空总收益，并且用 Ehsani–Linnainmaa 的符号规则（只留过去一年为正的因子）。M1 的失败仍下调先验。
- **看过的数据**（本合同之前，全部披露）：
  1. 信号层便宜测试（本轮 16:32 UTC 首次运行，`signal-level-check.py` 和 `signal-level-check.txt`）：22 个输入的日多空收益（`regimes/signal_ls_daily.parquet`）按标签月合成，过去 12 个月为正的输入下个月比为负的多 53.7 bp/月（96 个月，NW t 2.74；压力期 2018-10..2023-08 32.5 bp、t 1.25；近期 82.8 bp、t 2.95）。"只留赢家"的等权夏普：压力期 0.68 对全等权 0.49，近期 1.99 对 1.81。1 个月回看没有效果（WML t 0.94 / 0.27，夏普低于等权），不进本合同。这个测试的月度对齐在月初有 1 天重叠（上月最后一个标签在本月第 2 个交易日开盘才实现），本合同按 p−2 严格处理。
  2. v1.4 第 A 阶段的 M0 数字（简化毛夏普近期 1.735、压力期-ML 0.521）和 M3 暴露诊断；v1.2、v1.3 的全部结果。
- **外部证据**（原文已读，快照 `reports/research/intel/sources/book-v15-fm-2026-10-04/`）：
  - 支持：Ehsani–Linnainmaa 2022（JF 77(3)；NBER w25551 表 3，1964–2015，最多 20 个因子，月度）：平均因子在正收益年之后每月 53 bp、负收益年之后 1 bp；等权夏普 1.06，时间序列赢家组合 1.33，输家 0.04；多空版因子动量 0.98，低于等权。
  - 反对：Fan–Li–Liao–Liu 2022（Financial Review 57(3)，只读到摘要）：22 个和 187 个因子的样本里只有 22–27% 的因子有明显延续，因子动量策略打不赢对应的只做多组合。
  - 所以本合同只测"只留赢家/向赢家倾斜"（E–L 表 3 里打赢等权的那一种），不测多空因子动量（E–L 和 Fan 都显示它不如等权）。
- **回看期只用 12 个月**：这是 E–L 的主设定，也是便宜测试里两个看过的回看期中较好的那个（轻度选择，已披露）。本合同不再试 6、24、36 个月。

### 1. 问题

在 v1.2 构造完全不变（得分 → 秩正态 → 行业去均值、多空各 1 的线性权重；易借空头；按持仓的 EWMA beta 对冲 SPY；VIX > 20.60 减半；5 档周频；D 收盘决策、D+1 收盘成交、全量调仓；成本模型 v1 收盘口径，$1M，借券 25 bp/年）的前提下，把 M0 的输入（或主题）按过去 12 个月多空收益的符号取舍，能不能让偏移中位净夏普在近期和压力期-ML 都至少高 0.10？

### 2. 数据、窗口和基线

- **数据**：研究快照（A1 哈希绑定，截至 2026-09-17），只读：`data/research/equity_book/signals/<年>.parquet`（22 个处理后的输入列、`theme_*`、`m0_composite`）、`data/research/equity_book/regimes/signal_ls_daily.parquet`（22 个输入的日多空收益，10-01 由 `scripts/analyze_equity_book_regimes.py` 建，本合同之前已存在）、`T25.Context`。不用 live 目录。
- **窗口**与 v1.4 相同（标签日 / 决策日口径同 v1.4）：近期 2024-01-08..2026-09-15；压力期-ML 2019-01-02..2023-08-31；全期-ML 2019-01-02..2026-09-15。2019 起的原因：择时要 252 个标签，最早 2018-10 才有；与 v1.4 共用窗口和基线。
- **基线 B0r**：与 v1.4 完全相同（M0_U3000 从 2019-01-02 重新起跑，与 R6 逐位核对）。v1.4 第 B 阶段的 `identity.json` 通过时，直接读 `data/research/book_v14/S_B0r_o<k>.parquet`；否则按 v1.4 简报跑 identity。B0r 不是试验。

### 3. 择时信号（严格时点）

- LS_k(t)：`signal_ls_daily` 的第 k 列。标签 t 的收益是"t 收盘的分数，t+1 开盘持有到 t+2 开盘"，beta 对冲（面板 252 日 beta）、行业去均值、多空各 1 美元、无退市收益。
- 决策日 p（收盘）能用的标签是 t ≤ p−2（标签 t 在 t+2 开盘实现）。按快照交易日历的位置计。
- R_k(p) = ∏(1 + LS_k(t)) − 1，t 取位置 p−253 到 p−2 的 252 个标签；缺失按 0；有限值少于 200 个时 g_k(p) = 1（中性）。
- 输入层：g_k(p) = 1 当 R_k(p) > 0，否则 0。
- 主题层：R_θ(p) = 主题内各输入 R_k(p) 的均值；g_θ(p) = 1 当 R_θ(p) > 0，否则 0。

### 4. 候选（3 个试验）

M0 的输入权重 a_k = 1 / (9 · n_θ(k))（主题分 = 主题内处理后分数的均值，缺失为 0；M0 = 9 个主题等权；value、quality 各 4 个输入，momentum 3 个，investment、low_risk、earnings、insider、short_info 各 2 个，seasonality 1 个）。s_k 是信号库第 k 个处理后的输入列。

- **V15_FM12**（输入层只留赢家）：c = Σ a_k g_k s_k / Σ a_k g_k；全部 g = 0 时 c = m0_composite（记次数）。
- **V15_FM12T**（主题层只留赢家）：c = Σ g_θ · theme_θ / Σ g_θ；全部为 0 时用 m0_composite。
- **V15_FM12H**（输入层半倾斜）：w_k = a_k · (1.5 若 g_k = 1，否则 0.5)；c = Σ w_k s_k / Σ w_k。
- 得分 = 当日 U3000 成员内 rank_normal(c)，进入不变的 v1.2 构造（与 v1.4 的 `PredictionSource` 同一路径）。
- **建表恒等检验**：g 全取 1 时，FM12 和 FM12T 的公式在每个日期都还原 `m0_composite`（最大绝对差 ≤ 1e-6，float32）。不过就停，查实现。

定档族 N = 22（v1.2 的 10 个 + v1.3 的 5 个 + v1.4 的 4 个 + 本合同 3 个），全项目 N = 123。

### 5. 阶段和判定

**第 A 阶段（最便宜的否定测试，简报 T-20261004-04）**：
- 简化周度毛收益，口径与 v1.4 第 5 节第 A 阶段逐字相同（每个偏移 o 的决策日 p，w = `book_v12.target_weights(rank_normal(score), ind)`，周收益 = Σ w_i·r5_i，r5 不截断、缺失记 0；夏普 ×√52；5 个偏移取中位）。对象：M0、FM12、FM12T、FM12H。另报 y21 秩 IC（均值、NW t 滞后 4）、相邻周得分秩自相关中位数、与 M0 简化收益的相关、平均保留比例、每年切换次数。
- **择时安慰剂（E5）**：每个候选 20 个种子。每个输入（FM12T 为每个主题）的 g 序列换成独立的两状态马尔可夫链：转移概率 p01、p10 用真实 g 序列在 2019-01-02..2026-09-15 的日序列估计，从平稳分布起步，`default_rng(20261004 + seed)`，seed = 1..20；其余公式不变。安慰剂保留真实规则的切换频率和保留比例，去掉它与过去收益的关系。**通过**：候选在全期-ML 的偏移中位简化毛夏普高于 20 个安慰剂中第 18 高的值（即分位 ≥ 0.90）。两窗的分位只报告。
- **闸门**：候选的偏移中位简化毛夏普在近期和压力期-ML 都高于 M0，并且安慰剂通过，才进第 B 阶段。都不满足 → `stage_a_stopped`，停。

**第 B 阶段（同一简报的后半段，只对第 A 阶段留下的候选）**：v1.2 策略层 × 5 个偏移，从 2019-01-02 起，对比 B0r。规则与 v1.4 第 5 节第 B 阶段逐字相同：
- E1：偏移中位净夏普 − B0r ≥ +0.10，近期和压力期-ML **都**满足；
- E2：两窗各自至少 4/5 个偏移的净夏普高于 B0r 同偏移；
- E4：5 档混合净收益的 OLS beta 和 Dimson beta 绝对值两窗都 ≤ 0.15；
- E5：本候选的第 A 阶段择时安慰剂通过。
- **选择**：满足 E1、E2、E4、E5 的候选里近期偏移中位净夏普最高的记为 R*；差距 ≤ 0.01 时取压力期-ML 高的。
- **只报告**：同波动配对 NW t（滞后 5，口径同 v1.4）在全期-ML 和两窗；与 B0r 的日收益相关；2 倍成本净夏普；换手、成本、平均总敞口；按 `regimes/phases.json` 分阶段的净收益差。
- mechanical_status 只能是：`stage_a_stopped`、`no_candidate_eligible_keep_m0`、`eligible_candidate_selected`。

**第 C 阶段（只对 R*，下一主审轮看过第 B 阶段后另写简报）**：账户层（整股、$100 最小单、保证金、F1 叠加层、F2）、20 种子同日打乱安慰剂（净、毛分位 ≥ 0.95）、评判标准 v2.0.2 记分（族 N = 22、全项目 N = 123），R* 档位 ≥ P1。

**结果**：
- 第 C 阶段全过：R* 进**影子跟踪**。要先建 live 的输入多空收益模块（与 `signal_ls_daily` 同口径，逐日核对快照重叠段），再从 live 目录离线算 R* 的每日目标，与 M0 并列记录（不改生产端、不下单）。
- **替换 M0** 还要：E3 同波动配对 NW t（全期-ML）≥ 2.0，账户层 F1 叠加层近期净夏普(R*) − F1(B0) ≥ +0.05、压力期 ≥ 0，F2 近期 IR(R*) ≥ B0，保证金违规 0。替换不早于 v1.2 两周执行验证之后的第一次月度复评，另立生产任务。
- 否则保留 M0，写明哪一条没过、差多少。
- 与 v1.4 的关系：本合同只和 M0/B0r 比。v1.4 和本合同都有 R* 时，二者合用要另立合同。

### 6. 功效和误报（冻结前用 `python3` 正态近似算好）

- 同波动配对 t ≈ ΔSR·√年数 / √(2(1 − ρ))。择时只改输入权重，FM 与 M0 的书级日收益相关预计 0.9 上下。全期-ML 7.7 年、真实 ΔSR = 0.2 时：ρ = 0.8 → 期望 t 0.88，t ≥ 2 的功效 13%；ρ = 0.9 → 1.24、22%；ρ = 0.95 → 1.75、40%。替换门槛 E3 在样本内很难过，这是有意的。
- 零假设（ΔSR = 0）下单窗偶然 ≥ +0.10 的概率：ρ = 0.9 时近期 0.36、压力期-ML 0.31，两窗独立约 0.11；ρ = 0.95 时约 0.07。再要求 4/5 偏移和择时安慰剂，每个候选粗估 0.05–0.08，3 个相关候选里至少一个偶然过 E1+E2+E5 约 0.10–0.15。所以 E1/E2/E5 只配影子跟踪，不配替换。

### 7. 先验

- 第 A 阶段至少一个候选通过：约 40%（E–L 表 3 和本仓库信号层测试两窗同向支持；Fan 2022、M1 < M0、只有 22 个相关输入反对）。
- 第 B 阶段有合格候选：约 18%。最终替换：约 5%。
- 即使不过，也能回答"择时层能不能帮这本书"，并关掉近期收益择时这条路。

### 8. 适用状态、有效期、失效信号、退出规则

与 v1.2 第 7 节相同。若 R* 进入影子：规则不变，每天按第 3 节更新 g；前向 63 个会话里影子净夏普比 M0 低 0.5 以上，或输入层"赢家减输家"的月度价差在滚动 24 个月里为负（E–L：因子自相关断掉时动量崩溃），就停止影子并记录。

### 9. 局限（事先写明）

- 信号层便宜测试在预注册之前看过（第 0 节已披露）；回看期有轻度选择，本合同不再试其他回看期。
- `signal_ls_daily` 是开盘到开盘、缺收益的股票直接剔除（无退市收益），书在收盘成交。择时只用 252 个标签累计收益的符号，口径差异影响小；进生产前 live 端必须按同一口径重建。
- 只有 22 个输入、9 个主题，主题内输入彼此相关，独立的择时下注很少。
- 所有窗口都已被 M0/M1/v1.3/v1.4 看过；本合同的新信息只是择时规则本身。
- T-20261004-54（sue_series 时点泄漏审计）可能修订 earnings 主题。若 T-54 发现实质泄漏，在任何影子之前用修正后的快照重跑第 A、B 阶段。

### 10. 过了之后做什么 / 不过做什么

- 过第 B 阶段：下一主审轮写第 C 阶段简报。
- 第 A 或第 B 阶段停止：保留 M0；输入的近期收益（因子动量）择时在 v1.2 构造下关闭，写死因（哪一阶段、差多少）。择时层只剩波动状态变体（设计第 12 节，受数据约束）；信号层下一步是 T-20261002-04 Lazy Prices。
