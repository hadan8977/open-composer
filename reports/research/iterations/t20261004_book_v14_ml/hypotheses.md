# Hypotheses: t20261004_book_v14_ml

## Hypothesis

An out-of-sample ML composite of the same slow theme inputs captures nonlinear and interaction effects (size-conditional value, quality and low-risk premia) that the equal-weight composite misses, so under the unchanged v1.2 construction and costs it, or its equal blend with M0, raises the offset-median net Sharpe by at least 0.10 in both the recent and the stress-ML window.

## Failure mode

With 23 inputs and 1-8 years of weekly training the models learn noise or the 2017-2023 style history (value crash, junk rallies) and do not beat the equal-weight composite out of sample (BSW 2022, our M1 < M0 in v1.2); or nonlinear scores turn over faster and the extra cost eats the gross gain.

## Measurement

Stage A: simplified weekly gross long-short Sharpe (all 5 offsets) and book-aligned rank IC versus M0, weekly score rank autocorrelation, label-permutation check. Stage B: offset-median and blended net Sharpe per candidate and window, delta vs B0r per offset, vol-matched paired NW t, turnover, cost, beta, 2x cost. Stage C (selected candidate only, separate brief): account layer, 20-seed placebo, family-19 tier.

## Stop/Pivot criterion

No candidate beats M0's simplified gross Sharpe in both windows (Stage A) or none meets E1/E2/E4/E5 (Stage B): keep M0, record ml_contribution_pass from the design-doc comparison, close ML composites for the v1.2 construction until new inputs (Lazy Prices, prediction-market features) exist; the bottleneck is then signals, not models.

## 预注册全文（2026-10-04T07:31Z 写，2026-10-04 07:07 主审轮 Opus；早于任何 ML 合成器在 v1.2 构造下的任何训练或数字）

### 0. 为什么做，写之前看过什么

- 设计文档第 5 节为组合线预注册了 M2（GBDT 集成）和 M3（随机傅里叶特征），由 ml_contribution_pass 判定。Stage 2b 在 10-01 取消，理由只是 v1 的构造失败（"换合成器解决不了构造问题"，纲领原文："在 v1.1 的构造下再测"）。v1.1 已取消，接替它的 v1.2 简单构造已有变体到 P1（M0_U3000，family DSR 0.912）。所以前置条件已经满足，这是主线 1 原定的下一步，不是新格子。
- 机主 10-01 的批评之一是"没有建模、模型训练"。ML 合成器是组合层面回应这一点的正路：同数据、同成本、同构造，和等权基线比。
- **看过的数据**（本合同之前）：
  - v1.2：M0_U3000 近期净夏普 1.506，M1_U3000 1.389（按残差 IC 学到的权重输给等权）；收益归因近期风格 9.0%/年（残差波动风格 12.7%）、个股特质 −1.2%/年、SPY 对冲腿 9.4%/年，即这本书赚的主要是风格溢价，不是风格内选股。
  - T-17（09-30）：纯量价 ML 只在压力期测，RankIC 0.020–0.059，集成比单个 LightGBM 高 0.006–0.012。
  - T-24：ml_pv 残差 IC 近期 t 0.5–1.8，未入库。
  - v1.3：信号周度秩自相关 0.93–1.00，M0 合成 0.983；成本来自目标变化和 VIX 翻转。
  - 任何 ML 合成器都没有在 v1.x 的构造里跑过（RF1 的 M0X 因数据约束未跑）。
- **外部证据**（原文已读，快照 `reports/research/intel/sources/book-v14-ml-2026-10-04/`）：
  - 支持：DKKM 2024（NBER w33012）随机傅里叶特征岭 SDF，样本外毛夏普约 3.7，主要来自微盘股；只用超大盘、大盘仍约 1.6、1.8（FF6 0.74）。AQR 2024 Q4：复杂模型在有经济含义的信号上把毛夏普提高 50–100%（流动性好的大盘股 65%），且和简单模型"高度可加"；但加入 2 个噪声变量会让表现降约一半。都没扣成本。
  - 反对：Barroso–Saxena–Wang 2022，500 只最大的股票，扣成本后 ML 预测不比线性 Fama-MacBeth 预测好；最好的净夏普 1.10–1.20 来自线性预测加换手惩罚。我们自己的 M1 < M0 方向一致。
- **据此定下的设计选择**（都在看到任何 ML 结果之前）：
  1. 输入只用 22 个主题输入加对数市值，排除快信号、alpha101/191、新闻（AQR 噪声变量证据和 T-24）。
  2. 标签对齐这本书实际赚的收益：行业去均值、按 EWMA beta 对冲 SPY 后的远期收益，不用因子中性残差（残差目标会丢掉这本书的主要收益来源，M1 的教训）。
  3. 加两个"M0 + ML"等权混合候选，直接检验"复杂模型和简单模型可加"。
  4. 配对检验用同波动的差（v1.3 的教训：原始收益差不是规模无关的），并在冻结前写出功效。

### 1. 问题

在 v1.2 构造完全不变（得分 → 秩正态 → 行业去均值、多空各 1 的线性权重；易借空头；按持仓的 EWMA beta 对冲 SPY；VIX > 20.60 减半；5 档周频；D 收盘决策、D+1 收盘成交、全量调仓；成本模型 v1 收盘口径，$1M 规模，借券 25 bp/年）的前提下，把等权主题合成 M0 换成样本外 ML 合成器，或和 M0 等权混合，能不能让偏移中位净夏普在近期和压力期都至少高 0.10？

### 2. 数据、窗口和基线

- **数据**：研究快照（A1 哈希绑定，截至 2026-09-17），只读：`data/research/equity_book/signals/<年>.parquet`、`panel/<年>.parquet`、`T25.Context`（`scripts/realism_ladder_book_ls.py`）里的价格、EWMA beta、主题分。不用 live 目录。
- **窗口**（标签日）：近期 2024-01-08..2026-09-15（与 v1.2 相同）；压力期-ML 2019-01-02..2023-08-31（第一次重训要两年数据，2017-10..2018-12 没有样本外预测）；全期-ML 2019-01-02..2026-09-15；A、B 只报告。M0 在 v1.2 原压力期 2017-10-02..2023-08-31 的数字另报，作对照。
- **基线 B0r**：M0_U3000 走同一代码路径，从 2019-01-02 起重新开始。全量调仓下每块的目标权重与历史持仓无关，所以 B0r 的 gross、borrow、hedge_size、vix_scale 必须和 `data/research/equity_book/realism_ladder/R6_M0_U3000_o<k>.parquet` 在 2019-01-02 以后逐位一致（≤ 1e-12），cost 只在每个偏移的第一次刷新不同。B0r 不是试验。

### 3. 特征和标签

- **特征**（K = 23，按日在 U3000 成员内做截面秩标准化到 [−0.5, 0.5]，即百分位秩 − 0.5；缺失保留为 NaN）：bm、ep、sp、cfp、gp_at、roe、op_at、neg_accruals、neg_asset_growth、neg_nsi_12m、mom_12_1、ind_mom_12_1、resid_mom_12_1、neg_beta_252、neg_idio_vol_63、sue_eps、sue_rev、cmp_opp_buy_60d、nonplan_buy_mcap_60d、neg_short_vol_ratio_21、neg_si_shares、seas_5y（信号库同名标准化列），加 log(mcap)（`panel` 的 mcap > 0）。
- **决策日 p 的标签**（价格口径同 `px.returns("close", ·)`：标签 p 赚 C[p+2]/C[p+1] − 1）：
  - y21 = (C[p+22]/C[p+1] − 1) − β_i·(S[p+22]/S[p+1] − 1)，β_i 取 `ctx.ewma.at(t)`（缺失 1.0，截断 [−1, 4]），S 是 SPY 收盘；然后在 `ind_code` 行业内去均值，再取当日百分位秩。
  - r5 = (C[p+6]/C[p+1] − 1) − β_i·(S[p+6]/S[p+1] − 1)，截断到 [−0.5, 0.5]（M3 用）。
  - 远期价格缺失（期间退市等）的样本不进训练（局限见第 9 节）。

### 4. 训练和预测（全部样本外）

- 训练样本只用偏移 0 的周度决策日（`decision_positions(..., WEEK, 0)`，从 2017-10-02 起）。
- 每年第一个交易日重训，2019–2026 共 8 次，扩张窗口。训练样本要满足 p ≤ p_refit − 43（21 日标签 + 1 + 21 个会话的隔离期），用断言检查。
- 每个模型对 [本次重训日, 下次重训日) 的每个交易日、每个 U3000 成员给出预测。
- **M2**：`scripts/run_t20260930_17_model_family_sweep.py` 的 `FamilyModel`，"LGBM"、"XGB"、"CAT" 三个，参数原样（T-17 冻结），目标 y21 的百分位秩，NaN 交给模型原生处理。每日把三个预测各自转成截面百分位秩后取均值，记为 M2。
- **M3**（DKKM 2024 第 2.3 节、式 (6)(9)）：
  - Z = 23 个特征，NaN 记 0。ω_p ~ N(0, I_23)，p = 1..2000，每个 ω_p 的 γ_p 从 {0.5, 0.6, 0.7, 0.8, 0.9, 1.0} 均匀抽；种子 20261004，8 次重训共用同一组 (ω, γ)。
  - S = [sin(γ Z ω), cos(γ Z ω)]，P = 4000 列；每个日期内每列按 `ind_code` 行业去均值，得 S̃。
  - 因子 F_t = N_t^(−1/2) · S̃_t′ r5_t（P 维），t 取训练周。
  - λ(z) = (z·s̄·I + Ê[F F′])⁻¹ Ê[F]，s̄ = tr(Ê[F F′])/P，z ∈ {1e−3, 1e−2, 1e−1, 1, 10, 100, 1000}。
  - 选 z：训练周数 ≥ 104 时，用前面的周（留 1 周间隔）拟合，在最后 52 周上算 SDF 组合 λ′F 的周夏普，取最大的 z，再用全部训练周按这个 z 重拟合；少于 104 周（2019、2020 两次）固定 z = 1。
  - 得分 = S̃_{i,t} · λ。
- **混合**：M0M2 = rank_normal(rank_normal(M0) + rank_normal(M2))；M0M3 同理。M0 = `AlphaSource(ctx.themes, ctx.fic, "M0", "u3000")` 的输出（主题等权 → 秩正态）。
- **标签打乱检查**（不是试验）：LightGBM 和 M3 各再训练一份，训练标签在每个训练日期内随机打乱（种子 1），其余完全相同，同样预测。

### 5. 候选（试验）和判定

4 个候选：V14_M2、V14_M3、V14_M0M2、V14_M0M3。B0r 是基线。定档族 N = 19（v1.2 的 10 个 + v1.3 的 5 个 + 本合同 4 个），全项目 N = 120。

**第 A 阶段（最便宜的否定测试，简报 T-20261004-02）**：
- 简化周度毛收益：每个偏移 o 的决策日 p，w = `book_v12.target_weights(rank_normal(score), ind)`（U3000 成员，不做易借、VIX、对冲），周收益 = Σ w_i·r5_i（r5 不截断，缺失记 0）；年化夏普 ×√52；对 5 个偏移取中位。另报 y21 的秩 IC（均值、NW t 滞后 4）、相邻周得分秩自相关中位数、与 M0 简化收益的相关。
- **打乱检查通过**：两个打乱模型的简化毛夏普（偏移中位）绝对值在近期 ≤ 1.22、压力期-ML ≤ 0.93（2/√年数）。不过 → `permutation_check_failed`，停，查泄漏。
- **闸门**：候选的简化毛夏普在近期和压力期-ML 都高于 M0 才进第 B 阶段。都不高 → `no_candidate_beats_m0_gross_stage_a`，停，ml_contribution_pass = false。

**第 B 阶段（简报 T-20261004-03，只对第 A 阶段留下的候选）**：v1.2 策略层 × 5 个偏移，对比 B0r。
- E1：偏移中位净夏普 − B0r ≥ +0.10，近期和压力期-ML **都**满足（runbook 第 5 节优化规则，原样）；
- E2：两窗各自至少 4/5 个偏移的净夏普高于 B0r 同偏移；
- E4：5 档混合净收益的 OLS beta 和 Dimson beta 绝对值两窗都 ≤ 0.15；
- E5：第 A 阶段打乱检查通过。
- **选择**：满足 E1、E2、E4、E5 的候选里，近期偏移中位净夏普最高的记为 R*；差距 ≤ 0.01 时取压力期-ML 高的。
- **报告但不作资格**：同波动配对 NW t（滞后 5，候选的混合日净收益乘以 σ(B0r)/σ(候选)，σ 取同一窗口，减去 B0r）在全期-ML 和两窗；与 B0r 的日收益相关；2 倍成本净夏普；换手、成本、平均总敞口。
- **ml_contribution_pass**（设计文档定义，原样）：M2 或 M3（纯 ML）的偏移中位净夏普在近期和压力期-ML 都高于 B0r。另报 ml_additive（M0M2 或 M0M3 两窗都高于 B0r），两者分开写，不合并。
- mechanical_status 只能是：`stage_a_stopped`、`no_candidate_eligible_keep_m0`、`eligible_candidate_selected`。

**第 C 阶段（只对 R*，下一主审轮看过第 B 阶段后另写简报）**：账户层（整股、$100 最小单、保证金、F1 叠加层、F2）、20 种子同日打乱安慰剂（净、毛分位 ≥ 0.95）、评判标准 v2.0.2 记分（族 N = 19、全项目 N = 120），R* 档位 ≥ P1。

**结果**：
- 第 C 阶段全过：R* 进入**影子跟踪**：从 live 目录离线算 R* 的每日目标，和 M0 并列记录（不改生产端、不下单）。
- **替换 M0**（改模拟盘的主变体）还要：E3 同波动配对 NW t（全期-ML）≥ 2.0，并且账户层 F1 叠加层近期净夏普(R*) − F1 叠加层(B0) ≥ +0.05、压力期 ≥ 0，F2 近期 IR(R*) ≥ B0，保证金违规 0。替换不早于 v1.2 两周执行验证之后的第一次月度复评，另立生产任务。
- 否则保留 M0，写明哪一条没过、差多少。

### 6. 功效和误报（冻结前算好，`python3` 正态近似）

- 同波动配对 t ≈ ΔSR·√年数 / √(2(1 − ρ))。全期-ML 7.7 年、真实 ΔSR = 0.2 时：ρ = 0.6 → 期望 t 0.62，t ≥ 2 的功效 8%；ρ = 0.8 → 0.88、13%；ρ = 0.9 → 1.24、22%。所以替换门槛（E3）在样本内很难过，即使 ML 真的好 0.2；这是有意的：替换要强证据。
- 反过来，零假设（ΔSR = 0、ρ = 0.8）下单窗偶然达到 +0.10 的概率：近期约 0.40，压力期-ML 约 0.37，两窗独立约 0.15；再要求 4/5 偏移，粗估每个候选约 0.10，4 个相关候选里至少一个偶然过 E1+E2 约 0.25–0.30。所以 E1/E2 只配得上"影子跟踪"这一档，不配替换。

### 7. 先验

- 第 A 阶段至少一个候选通过：约 45%（AQR/DKKM 支持；BSW、M1 < M0、T-24 反对）。
- ml_contribution_pass：约 25%。第 B 阶段有合格候选：约 15%。最终替换：约 4%。
- 即使全不过，也能回答机主的问题"模型训练能不能帮这本书"，并把下一步明确指向新输入（文本、预测市场），而不是换模型。

### 8. 适用状态、有效期、失效信号、退出规则

与 v1.2 第 7 节相同。若 R* 进入影子：每年第一个交易日按本合同第 4 节重训一次，不改设置；前向 63 个会话里影子净夏普比 M0 低 0.5 以上，或打乱检查在新数据上失败，就停止影子并记录。

### 9. 局限（事先写明）

- 训练样本短：2019 年那次只有约 60 个训练周；M3 的 P/T 远大于 DKKM（130 个特征、360 个月）。
- 远期价格缺失的样本不进训练，模型学不到"困境股退市"的损失；策略层沿用 v1.2 的处理（缺失收益记 0），对所有候选和 B0r 相同；第 C 阶段账户层用 −30% 退市下限复核。
- 压力期-ML 比 v1.2 的压力期短（2019 起），压力期的 2017-10..2018-12 只报告 M0。
- 成本模型是 NBBO 抽样校准的 v1 模型；所有比较用同一成本。
- 所有窗口都已被 M0/M1 看过；本合同的新信息只是 ML 合成器本身。

### 10. 过了之后做什么 / 不过做什么

- 过第 B 阶段：下一主审轮写第 C 阶段简报。
- 第 A 或第 B 阶段停止：保留 M0；ML 合成器在 v1.2 构造下关闭，写死因（哪一阶段、差多少）。组合线信号层的下一步是新输入（T-04 Lazy Prices、预测市场特征），不是换模型或调超参数。
