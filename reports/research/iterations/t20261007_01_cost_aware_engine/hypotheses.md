# Hypotheses: t20261007_01_cost_aware_engine

## Hypothesis

A fast composite that cannot carry its own leg (P1 stage 0: blending a separate fast leg with M0 lowers the recent Sharpe from 0.80 to 0.75) can still add net Sharpe inside the slow book, by entering the score (I1), by choosing the day on which each slow trade is made (I2), or through a decay-discounted aim book with partial adjustment (I3), and the machine-learning slow score m0m2 adds on top; the gain is at least 0.10 in recent-window net Sharpe over B0.

## Failure mode

The fast composite's lag-2 information is about a quarter of its lag-1 information and the slow score is already strong, so the score blend adds noise, trade timing costs more in drift than it saves, and the Garleanu-Pedersen aim gives the fast signal only 3-8% weight so I3 is just a damped slow book (which v1.3 already refuted); the 2.7-year recent window cannot resolve a 0.1-0.3 Sharpe difference (power 4-33%).

## Measurement

Per point: offset-median and blended net Sharpe per window, delta vs B0 per offset, vol-matched paired Newey-West t, turnover, cost, beta, 2x cost; selected point (median of the top three of the 21 points with a fast element): five vetoes, family DSR, 100-seed net placebo, fast-composite-only placebo (G3), six robustness items, tier; diagnostics U1000, MOO, theme ablation, capital ladder.

## Stop/Pivot criterion

All I1/I2/I3 points of the S0 route are <= 0 versus B0 and all S2-route points are <= 0 versus S2_I0 in the recent window: close the 'fast and slow in one book at close-to-close speed' line; the fast composite then belongs to intraday execution only.

## 预注册全文（2026-10-07T14:35Z 写，T-20261007-01 执行代理 Sonnet 5.5；早于本合同任何一个点的任何结果；此前只做了恒等检验和计时）

### 0. 为什么做，写之前看过什么

- 机主要高夏普，要深挖因子体系和模型训练，所有东西两周内上模拟盘。v1.2 今天在 quant1 首单，近期净夏普约 1.5。
- 三样已有增量，各自单独测过，从没进同一本书：
  1. 慢分数：v1.4 第 A 阶段 m0m2、m0m3 的简化周度毛夏普 2.008、2.247，M0 为 1.735（毛口径，没走组合层）。
  2. 快合成 FC_EW（P1 阶段 0，60 个快输入等权）：近期 IC t 3.12；单独做、κ = 0.1 时近期净夏普 0.446；和 v1.2 日收益相关 −0.05。
  3. 按成本控制交易速度：v1.3 的 N50 近期净夏普 +0.158，没过当时的 E3，冻结为唯一挑战者。
- 阶段 0 的混合结果（`t20261005_p1_s0_decay/results.json` `composites.FC_EW.blend_with_m0`）：快腿单独成腿、与 M0 按波动倒数混合，近期夏普从 0.795（M0 同波动）降到 0.748，因为平均 79% 的资金落在较弱的快腿。所以快信号不能单独成腿，要在同一本书里合。
- 外部做法（`external-brief.md`，来源快照在 `reports/research/intel/sources/cost-aware-engine-2026-10-07/`）：
  - Garleanu–Pedersen 2013：最优做法是向 aim portfolio 部分调仓，aim 是当前与未来预期 Markowitz 组合的指数平均，衰减快的信号在 aim 里权重小（命题 2、3）。v1.3 只测了静态的固定速度（P2/P3/P2V），命题 3 的"按衰减倾斜"当时没有快主题可用，记在 v1.3 决策里。
  - Novy-Marx–Velikov 2016：买入/持有价差（缓冲带）是最有效的降成本办法（v1.3 的 N50 即此）。
  - Frazzini–Israel–Moskowitz：价格冲击随成交占比开方，成本感知的优化把价值动量组合的换手压低约 2/3、冲击降约一半，且组合比单个信号降得更多（多信号在同一本书里交易互相抵消）。DeMiguel–Martín-Utrera–Nogales–Uppal 2020 同一机制（只读了摘要，不作为约束引用）。
  - Jensen–Kelly–Malamud–Pedersen：用成本感知的目标直接学权重；没找到公开代码。
  - 用快信号安排慢目标的成交时机：只找到 Supit 2020（Robeco 订单，执行层、单笔交易、一天内），结论是增益取决于预测器，简单预测器反而每笔亏约 9 bp。组合层面的同类做法没找到。
- 和已关闭路线的区别（写进 `direction-review.json`）：v1.3 的 N50 重开需要新信息，这里的新信息是快合成与机器学习慢分数；v1.3 对 GP 命题 3 的后续要以快主题主导换手为前提，现在有了快合成；阶段 0 说明快信号不能单独成腿。

### 1. 问题

把慢分数（S）、快合成 FC_EW 和按成本控制交易速度合进同一本书（v1.2 构造不变），同波动下的近期净夏普能不能比 B0 明显提高？合的方式三种，各取三个点，不在预注册之外调参。

### 2. 数据、窗口和基线

- 数据截止 2026-09-17，之后的数据不读。近期窗口 2024-01-08..2026-09-15（约 674 个标签日）决定结论；压力期 2017-10-02..2023-08-31 只作诊断；全期只报告。使用 S2/S3 的候选从 2019-01-02 起（v1.4 第一个样本外预测日），压力期诊断相应取 2019-01-02..2023-08-31。
- B0 = v1.2 R6 主变体 M0_U3000（U3000、行业去均值、只做空易借券名字、EWMA β 的 SPY 对冲、VIX > 20.60 减半、每周 5 个 tranche、t 日收盘决策、t+1 收盘成交、`costfn.make_cost_fn("close")`、借券 25 bp/年）。所有比较用同一次运行里重算的 B0。
- 引擎：`open_composer/research/equity_book/engine_v2.py`（新文件，纯函数）和 `scripts/t0701_engine.py`；不改 `equity_book/` 下已有文件，不改生产程序。
- 恒等检验（冻结前做）：新引擎关掉新功能（S0、I0；I1 的 w_f = 0；I2 的 c = None）与旧的 B0 路径（`book_v13_trading_rules.rules_pass(B0)`；S2 的 I0 与 `book_v14_ml_eval.strategy_pass_with_source`）在同一进程、同一份数据上逐位比较，最大绝对差 ≤ 1e-9；与 10-02 保存的 R6 序列只报告差多少。结果写进 `identity.json`。
- 快合成：`data/research/t0701_store/fc_ew.parquet`，由 `scripts/t0701_fast_store.py` 重跑 P1 阶段 0 的 build 阶段（代码、符号规则不变）得到，ON5、ID5 的符号与阶段 0 `results.json` 的 `signs` 一致（均为 −1）。FC_EW = 60 个快输入各自在当日信号库行内做 rank-normal（缺失记 0）后的平均。进书前再在当日 U3000 成员内做一次 rank-normal（缺失记 0）。

### 3. 三种合成方式的精确定义（冻结）

记 z_s = 慢分数在 U3000 成员内的 rank-normal（M0 为 `AlphaSource`，S2/S3 为 `predictions.parquet` 的 m0m2、m0m3 列经 `PredictionSource`），z_f = FC_EW 的成员内 rank-normal。

- **I0**：不加快信号。S0 的 I0 就是 B0（不计试验）。S2 的 I0 和 S3 的 I0 各一个点，是 v1.4 第 B 阶段要测的点；另外按 `t20261004_book_v14_ml/hypotheses.md` 冻结的 E1–E5 再报一遍（恒等容差：冻结时 1e-12，本合同在同一平台 1e-9）。
- **I1 分数合成**：分数 = z_s + w_f·z_f（z_f 缺失记 0，z_s 缺失名字不入选），w_f ∈ {0.25, 0.5, 1.0}，之后完全按 v1.2：分 tranche、每次调到目标。
- **I2 交易时机**：目标完全不变（只用慢分数）。每个 tranche 调仓日 p，名字 i 的交易为 Δ_i = 目标 − 漂移后的持仓；成交日 d = 0 对应 v1.2 的 t+1 收盘。d 日成交前用 d 日之前最后一个收盘的 z_f（第 d 天用 p+d 日收盘的 z_f）：若 sign(Δ_i)·z_f,i < −c 就推迟一个会话再查；最多推迟 4 个会话，到期必须成交（同一 tranche 的块长为 5，所以 d ≤ 4）；c ∈ {0, 0.5, 1.0}；成交后该名字按预定目标权重（决策日定下的目标，不重算）持有。没有 z_f（不在 U3000 成员内）的名字不推迟。SPY 对冲在每个有股票成交的日子按当日持仓重设（−Σ 持仓·β），其余日子保持股数。成本用成交日的属性（`ctx.panel.at(成交日决策日)`）按 `costfn` 计，不增加换手。
- **I3 GP 目标组合加部分调仓**：每个会话（不分 tranche、不分偏移）：aim_t = `book_v12.tranche_target` 对分数 Σ_k b_k·z_k/(1 + φ_k/κ) 的结果（含行业去均值、易借券限制、VIX 缩放、成交价缺失记零），w_t = (1−κ)·w_(t−1) + κ·aim_t；没有次日成交价的名字置零；非易借券名字不做空；|w| < 1e-6 视为 0（尘埃）；不在目标里的名字按同一公式几何衰减。κ ∈ {0.05, 0.1, 0.2}。
  - φ_k = ln 2 / 半衰期，b_k = 压力期（2017-10-02..2023-08-31）阶段 0 的数据（`results.json`，L12 桶，规则固定，不用近期窗口）：b_k = 该信号的滞后 2 日均 IC（第一个可成交滞后）；半衰期 = `h_exp`，上限 252。慢分数（M0 的数；S2 也沿用 M0 的 b、φ，因为阶段 0 没测 m0m2）：b_slow = 0.014996，半衰期 252（M0 的 h_exp 约 5518，取上限）→ φ_slow = 0.002751。快合成：b_fast = 0.003421，半衰期 1.8786 → φ_fast = 0.368961。
  - 这样 aim 里快合成的相对权重只有约 2.8%（κ = 0.05）、4.8%（0.1）、7.5%（0.2）：GP 的逻辑本身就让衰减快的信号在 aim 里权重小。所以 I3 很可能主要是对慢分数做日度部分调仓；事先写明，避免把它当快信号主导换手的检验。
  - I3 没有调仓偏移：日度一本书。G2 里 I3 点与 B0 的 5 个偏移逐一比较（见 §5）。
- **F 轴**：S0、I3 下 3 个 κ 点，快合成换成 FCX = (60·FC_EW + Σ_k s_k·z_k)/67，k 为 `data/features/intraday_daily/` 的 7 个日内日频特征（overnight_return、intraday_return、intraday_amplitude、open_30min_volume_share、close_30min_volume_share、vwap_deviation、intraday_skew），z_k 为当日 FC_EW 同一行集内的 rank-normal（缺失记 0），符号 s_k 为压力期内 z_k 与滞后 2 标签（行业去均值的简单收益）的日均秩相关的符号，在近期窗口之前定下；b_fast、φ_fast 沿用 FC_EW 的数。2026-09-05..09-17 的日内日频特征已用 `scripts/t0701_build_intraday_sep.py` 建出（只读到 09-17 的分钟线，现有 2026 文件只到 09-04）；FCX 存于 `data/research/t0701_store/fcx.parquet`（`scripts/t0701_fcx_store.py`，符号只用压力期：overnight −、intraday_return −、amplitude −、open 占比 −、close 占比 +、vwap 偏离 +、skew +，见 `fcx_meta.json`）。F 轴计入试验。

### 4. 候选（试验）

- 主网格 20 个点：S0 下 I1×3、I2×3、I3×3 = 9；S2 下同样 9；I0 的 S2 和 m0m3 各 1 = 2；F 轴 3 个（S0、I3、FCX，κ 三个点）。共 23 个，以 `candidate-manifest.json` 为准。全部登记进全局试验台账，一个不删。
- 其余全部和 v1.2 B0 相同：U3000、行业去均值、只做空易借券、F1 构造（对 BIL）和 β 对冲、vix_scale、借券 25 bp/年、`costfn` 收盘快照、t 收盘决策 t+1 收盘成交。
- 诊断（只对选出的规格做，只报告，不计试验，不用来选）：U1000 与 U3000；MOO（t+1 开盘成交）与 MOC；2 倍成本；数据类别消融（S0 路线：逐个去掉 9 个慢主题之一，和去掉快合成，其余等权重，报告近期净夏普变化；S2 路线：`model-meta` 里有特征组重要性就用）；资金阶梯（30 万、100 万美元，整股、100 美元最小订单，V2 三个量化指标、被跳过订单占比、每天订单数；I1 用 v1.2 账户层，I2/I3 用对候选自己的目标权重序列做整股取整的简化版，写明）；换手和成本前沿；VIX 翻转占成本比例；与 v1.2 的日收益相关和跟踪误差。

### 5. 选规格和判定（结果出来之前写定）

- **选规格**（标准 5b 第 6 条）：在含快信号的 21 个点（I1、I2、I3，S0 和 S2 两条路线共 18 个，加 F 轴 3 个；I0 的两个点不参加，它们属于 v1.4 第 B 阶段）里，取近期同波动净夏普（5 个偏移的中位数；I3 无偏移，取其本身）最高的三个点，用其中位（第 2 名）的规格。同波动净夏普就是净夏普本身（夏普与缩放无关）；同波动只用在日收益差：d_t = cand_t·sd(B0)/sd(cand) − B0_t。
- **候选本身**：按标准 v2.1 走一遍：五条否决（V4 压力期崩溃照常；S2 路线压力期取 2019 起，并注明）；DSR（标准 §3：N_eff = 1 + (N − 1)(1 − ρ̄)）：两种口径都报：试验数用本合同实际跑的个数（23），和再加组合族已登记的 19 个（v1.2 10、v1.3 5、v1.4 4）；ρ̄ 取本合同各点与 B0 近期日净收益的平均两两相关，方差用本合同各点近期夏普的方差；定档用组合族口径。净口径安慰剂 100 个种子：每个日历季度按（种子、季度、股票代码）的哈希给股票一个随机名次，每个决策日把真实分数的排序值按这个名次分配，构造和成本不变；稳健性 6 项；得出档位。
- **相对 B0 的增量**（标准 5a 第 4 条）：
  - **G1**：近期同波动净夏普（5 个偏移的中位数）比 B0 高至少 0.10；
  - **G2**：5 个偏移里至少 4 个比 B0 高（I3 无偏移：与 B0 的 5 个偏移逐一比较，至少 4 个 B0 偏移低于它）；
  - **G3**：只打乱快合成的安慰剂，100 个种子，慢分数不动，快合成按上面的净口径哈希名次分配；候选的增量（近期 5 偏移混合夏普 − B0，同样从 2023-11-01 起暖机的版本）要高于 90% 的种子；I0 的点不适用；
  - **G4**：压力期只作诊断：同波动净夏普不能比 B0 低 0.20 以上；V4 崩溃否决照常。
  - 配对检验：同波动日收益差的 Newey–West（lag 5）t 值，近期和全期都只报告。
- **结论三选一**：
  - **成立**：候选至少是 P1，并且 G1 到 G4 都过。写模拟盘方案（`paper-sleeve-cost-aware-engine.md`，作为 quant1 的第二个子策略和 v1.2 并行，子账本隔离之后上，做前向对比）。
  - **不成立**：S0 路线 9 个点相对 B0 的近期同波动净夏普增量都 ≤ 0，并且 S2 路线 9 个点相对各自的 I0（S2_I0）也都 ≤ 0（快信号在更好的慢分数上也没增量）。
  - **未到深度**：其他情况。写清缺哪一条、怎么补。
- 另外报告（不进判定）：S2 路线相对 S2_I0 的增量，用来区分"快信号带来的"和"慢分数本身带来的"。

### 6. 功效和误报（冻结前算好，`python3` 正态近似）

- 近期约 674 个标签日（2.675 年）。配对 t ≈ ΔSR·√年数 / √(2(1 − ρ))，t = 2 时能检出的最小 ΔSR = 2·√(2(1 − ρ)/2.675)：

| 候选与 B0 的相关 ρ | 0.80 | 0.90 | 0.95 | 0.98 |
|---|---|---|---|---|
| ΔSR 的标准差 | 0.387 | 0.273 | 0.193 | 0.122 |
| t = 2 能检出的最小 ΔSR | 0.77 | 0.55 | 0.39 | 0.25 |
| 零假设下偶然 ΔSR ≥ 0.10 的概率 | 0.40 | 0.36 | 0.30 | 0.21 |
| 真 ΔSR = 0.10 时 t ≥ 2 的功效 | 0.04 | 0.05 | 0.07 | 0.12 |
| 真 ΔSR = 0.30 时 t ≥ 2 的功效 | 0.11 | 0.18 | 0.33 | 0.67 |

- 含义：G1 的 0.10 是效应量门槛，不是显著性检验；近期窗口分辨不出 0.1–0.3 的真实增量，G1 单独过不说明什么，所以判定还要 G2（偏移一致）、G3（打乱快合成的安慰剂）、DSR 与档位。ρ 的实际值结果出来后按选出的规格再报，并补上 t = 2 的最小可检 ΔSR。
- 23 个点高度相关，取近期最好三个点的中位规格，只是降低而不是消除选择偏差；定档用组合族 DSR。

### 7. 先验

- I1 里有真增量（G1–G4 全过且 ≥ P1）：约 20%（快合成近期 IC t 3.12 但滞后 2 起效应只有滞后 1 的 1/4，慢分数已经强；v1.3 的静态降速都没过）。I2：约 10%（Supit 的增益依赖预测器）。I3：约 5%（aim 里快合成只占 3–8%，本质是对慢分数日度部分调仓）。最后至少有一条"成立"：约 20%。
- 即使不成立，也回答机主的问题"快信号能不能和慢信号合进同一本书"，并给出下一步（快信号只剩滞后 1 的信息，需要日内成交或更短持有）。

### 8. 适用状态、有效期、失效信号、退出规则

与 v1.2 第 7 节相同：美股 U3000，周度 5 个 tranche（I3 为日度），有效期至 2026-12-31。若成立并上模拟盘：授权有效期不超过 60 个交易日；前向 63 个会话里与 v1.2 的同波动净夏普差低于 −0.5，或净成本超出模型 1.5 倍，或 G3 在新数据上被推翻（打乱快合成的版本不再更差），就停止子策略并记录；仓位上限和账本隔离写在 `paper-sleeve-cost-aware-engine.md`。

### 9. 局限（事先写明）

- 所有窗口都被 M0、阶段 0 看过，本合同的新信息只是三者的组合。
- FC_EW 滞后 2 的 IC 只有滞后 1 的约 1/4，MOC 次日成交本身已经丢了最强的一天；日内成交可能更适合快信号，不在本合同内。
- 模拟盘成交偏乐观：Alpaca 模拟盘不含冲击和借券费；成本模型 v1 是 NBBO 抽样校准，所有比较用同一成本。
- I3 的 b_k、φ_k 来自阶段 0 的压力期，S2 沿用 M0 的 b、φ；FCX 沿用 FC_EW 的 b、φ。
- 2 倍成本、U1000、MOO 等诊断不用于选择。
- 试验数偏多，ρ 高，近期窗口功效低（§6）。

### 10. 过了之后做什么 / 不过做什么

- 成立：主审轮 10-12 审核；子账本隔离（T-20261006-07）后约 10-14 上模拟盘，作为 quant1 的第二个子策略，和 v1.2 前向对比。
- 不成立：关闭"快慢合并进同一本书"这条线，快合成只保留给日内成交的方向。
- 未到深度：写缺哪一条（例如功效、F 轴数据、I2 的推迟规则太简单）和补法，下一主审轮决定。

### 11. 计算估算和恒等结果（冻结时写）

- 恒等检验（全长，偏移 0 和 3，Modal 2 核）：新引擎 S0/I0、I1（w_f = 0）、I2（c = None）与旧 B0 路径（v1.3 `rules_pass`）最大绝对差 4.4e-16；S2/I0 与 v1.4 的 `strategy_pass_with_source` 最大绝对差 4.4e-16（容差 1e-9，通过）。与 10-02 保存的 R6 序列：偏移 0 差 4e-16，偏移 3 差 1.6e-6（换手列；同 T-70 测到的数据漂移量级），只报告。结果在 `identity.json`。
- 计时：一个偏移的 B0 全长约 15–20 秒（Modal 2 核）。主网格估计合计约 20 分钟（2–4 核，约 0.1 美元）；两个安慰剂各 100 个种子（暖机从 2023-11-01 起），分 8 片并行约 20 分钟（约 0.5 美元）；诊断和消融估计约 0.3 美元。本任务 Modal 总预算上限 3 美元（含已花的 0.3 美元左右的调试和恒等运行），超过就停并报告。
- 本机不跑重任务（只写文件、读 parquet、跑评估脚本）。
