# Hypotheses: t20261005_p1_s0_decay

## Hypothesis

Fast price-volume signals on liquid US stocks carry daily information whose IC decays over several sessions (the DLSA Sharpe half-life is about seven sessions), so trading them partially (kappa < 1) at the close with measured spreads keeps a positive net Sharpe that full daily rebalancing at the open with a flat 8 bp loses; a multi-signal composite has more information per unit of turnover than any single signal.

## Failure mode

The library signals' daily information is too short-lived (most IC at lag 1, which a close t+1 fill cannot capture) or too small relative to the measured close spread even at slow speeds, or it is already contained in m0_composite.

## Measurement

IC decay lags 1..22 (lag 1 split overnight/intraday), persistence, half-life, net Sharpe for 7 speeds at MOC with the close-snapshot cost model, MOO variant, by bucket and window; composites with placebo, blend with M0 and DSR. Results in results.json, report.md, trial-ledger.json.

## Stop/Pivot criterion

Measurement only: nothing here closes P1 (owner rule 2026-10-04: cheap tests only promote). Objects meeting the preregistered information rule enter the Stage 2 contract; if none does, the record says 'not yet at depth' and P1 proceeds to Stage 1 (learned residual signal with costs in the objective) as planned in I-20261004-05.

## 预注册全文（2026-10-05 01:30 UTC 写定，01:07 主审轮 Opus；早于任何快信号的衰减曲线、滞后 2 以后的 IC、收盘成交成本和部分调仓数字）

### 0. 为什么做，写之前看过什么

- **纲领位置**：第二版计划草稿的 P1 中频股票引擎（`docs/plan-v2-2026-10-05.zh.md` 第 3 节）；第一版计划 C2"10-05 主审轮写预注册，10-09 前出第一批结果"；T-80 调研 `reports/research/intel/I-20261004-05-mid-frequency-depth.md` 第 7 节"阶段 0"（交互会话 10-04 18:57 接受）。不是新格子。
- **看过的数据**（全部披露）：
  1. `reports/research/program/regimes-2026-10-01/results.json` 的日多空表。口径是开盘 t+1 到开盘 t+2、每天全量调仓、固定 8 bp/边、全 U3000。快因子库近期毛夏普最高 2.64（g191_gtja190，年换手 71 倍，净 0.61）；a101_alpha016 毛 1.56、净 −4.15（换手 171 倍）；多数 Alpha101/191 净 −4 到 −8；m0_composite 毛 1.81、净 1.53。
  2. T-24 信号筛选（月末形成、21 日远期）：Alpha158 FDR 合成两窗都约等于 0。
  3. v1.2、v1.3、v1.4 第 A 阶段的全部结果。
  - **没算过**：任何快信号的衰减曲线、滞后 2 以后的 IC、收盘成交成本下的净值、部分调仓、按流动性分档的结果。
- **为什么旧的否定不算数**（第二版计划 P-1）：T-24 用 21 日视野测快特征，看不到日频信息；regimes 表是"开盘成交 + 每天全量调仓 + 固定成本"，正是 T-80 第 5 节列的三种浅做法；外部的行业残差反转否定（sector_residual_reversal_statarb_decay）是单信号、含低价股、约 7 bp 成本、没有空头腿。
- **机主规则**（10-04 晚）：便宜测试只能提速、不能否定。本阶段是测量，只决定哪些输入、什么速度进入第 2 阶段，不能关闭 P1。

### 1. 机制和要回答的问题

- **机制**：
  - 短期反转：流动性提供者为非基本面的价格压力收费。Da–Liu–Schaumburg 2014 发现只有"行业内、扣除现金流新闻后"的残差部分显著，约为常规反转的 3 倍；Blitz 等 2013 的残差反转约 2 倍，扣成本后在 1990 年以后的大盘股里仍显著。
  - 成交量冲击：关注度和可见度溢价（Gervais–Kaniel–Mingelgrin 2001）。
  - 隔夜和日内成分：不同投资者群体（Lou–Polk–Skouras 2019）。
  - Alpha101/191 类短周期量价公式，混合了以上机制。
- **为什么关键在速度**：这类信息的寿命是几天（DLSA 的夏普半衰期约 7 个会话，持有 22 日仍 >1）。赚不赚钱取决于三件事：衰减速度、交易速度、成交成本（Gârleanu–Pedersen 2013；Turnover-Adjusted IR 2021）。
- **问题**：
  - Q1 每个信号的 IC 从滞后 1 到 22 怎么衰减；收盘 t+1 成交损失多少（整个滞后 1），开盘 t+1 成交损失多少（滞后 1 的隔夜部分）。
  - Q2 持续性（秩自相关）和由此决定的换手。
  - Q3 净夏普随交易速度怎么变，最优速度在哪里。
  - Q4 合成能不能提高单位换手的信息量。
  - Q5 和 M0 的相关，以及信号层的组合增量。

### 2. 对象（预先写定，全部计入）

| 组 | 对象 | 角色 |
|---|---|---|
| A 快因子库（53） | 19 个 a101_*、32 个 g191_*、rev_21_ind、on252，用信号库存的处理后分数和符号 | 合成的输入；单独只报告，不单独晋级 |
| B 新信号（7） | REV5、IREV5、RREV5、RREV21、ON5、ID5、VSHK（定义见 lightweight-config.json） | 候选；也是合成的输入 |
| C 合成（3） | FC_EW、FC_WF252、FC_WF63 | 候选 |
| D 背景（10） | m0_composite、9 个 theme_* | 只回答"v1.2 自己要不要日频"，不是试验 |

- 候选 10 个（B 7 + C 3），每个 7 种速度，共 70 个配置：本阶段的 DSR 试验族。项目累计披露 123 + 70 = 193。
- **新信号的符号**：
  - REV5、IREV5、RREV5、RREV21 取过去收益的负号（反转）；VSHK 取正号（成交量溢价）。
  - ON5、ID5 的文献没有给出 5 日成分对收盘到收盘总收益的明确方向，取它们压力期 L12 档 CIC(2..6) 均值的符号。脚本必须先只算压力期，把符号和时间戳写进缓存（`signs.json`），再读近期窗。

### 3. 共同口径

- **宇宙和分档**：
  - 信号库每天的行（U3000 成员）。
  - 用 panel 在 t 日的 adv_rank 分档：L1 ≤ 500，L2 501–1000，L3 1001–3000，L12 ≤ 1000。L12 是决策档。
  - 脚本先核对：dollar_adv_21 的中位数随档单调下降，否则停。
- **目标收益**：
  - 单日个股收益减 β × SPY 同口径收益。β 取 panel 在 t 日的 beta_252_spy，缺失记 1，截断到 −0.5..3。
  - 再在（日期，ind_code）内去均值。
  - 滞后 j 的收益是 close(t+j−1) 到 close(t+j)。滞后 1 另拆成隔夜（close t 到 open t+1）和日内（open t+1 到 close t+1）。
  - 当天没有收益的股票当天剔除，不补退市收益（与 regimes 研究相同的简化），每天计数。
- **IC**：
  - 档内 Spearman 秩相关，≥ 50 只。对每个滞后得到一条日序列，报告均值和 Newey–West t（10 阶）。
  - 缺失按中性秩处理（标准化后为 0），在报告里写明。
  - CIC(a..b) 是滞后 a 到 b 的 IC 均值之和。可实现部分：收盘 t+1 成交是滞后 ≥ 2；开盘 t+1 成交是滞后 1 的日内部分加滞后 ≥ 2。
- **半衰期**（两种，都报告，第一种为主）：
  - h_np：最小的 m，使滞后 2 到 1+m 的 IC 均值之和 ≥ 0.5 × CIC(2..22)。CIC(2..22) ≤ 0 时记 NaN。
  - h_exp：对滞后 2..22 拟合 IC_j = A·exp(−λ(j−2))，h = ln2/λ。λ ≤ 0 或拟合失败记 NaN。
- **滞后损失**：F_MOC = 1 − CIC(2..22)/CIC(1..22)，F_MOO = 1 − (日内 IC(1) + CIC(2..22))/CIC(1..22)。CIC(1..22) ≤ 0 时记 NaN。
- **持续性**：同档共同股票上，t 日分数与 t−L 日分数的截面 Spearman，L = 1、5、21，取窗内均值。
- **速度曲线**：
  - 目标权重：档内分数转成秩正态 → `book_v12.target_weights(score, ind_code)`（行业去均值，多空各 1）→ `book_v12.restrict_shorts(w, SE_t)`。SE_t 用 `borrow.short_eligible`，输入和 `scripts/realism_ladder_book_ls.py` 一样：adv_rank、panel 收盘价、252 日内的反向拆股。
  - 部分调仓：w_t = (1−κ)·w_(t−1) + κ·w*_t，κ ∈ {1, 0.5, 0.25, 0.1, 0.05}，不再缩放，报告平均总敞口。
  - 全量调仓：每 5 个、每 21 个会话一次，报告所有偏移的中位数（不挑调仓日）。
- **成交和成本**：
  - 主口径：t 日收盘决策，t+1 收盘成交（收盘竞价，与 v1.2 修正案 A1 相同），持仓收益从 close(t+1) 起算（即滞后 ≥ 2）。
  - 成本：Σ_i |Δw_i| × (半价差 + 冲击 + 0.5 bp 费用) / 1e4。半价差用 `costs.half_spread_bp(t 日收盘价, dollar_adv_21, vol_21, 年份, "close")`，输入都取 panel 在 t 日的值，缺失按 40 bp；冲击用 `costs.impact_bp(|Δw_i| × 100 万美元, adv, vol)`。
  - 借券：空头名义 × 25 bp/年，按日计。
  - 变体 MOO：开盘 t+1 成交，用 "open" 快照，持仓收益从 open(t+1) 起算。只算 κ = 1 和该对象 MOC 口径的最优速度。
  - 2 倍成本：同一条权重路径重放，每个配置都报。
- **窗口**：
  - 近期 2024-01-08..2026-09-15，决定晋级；
  - 压力期 2017-10-02..2023-08-31，诊断，并给 ON5、ID5 定符号；
  - 机主 B 窗 2026-07-01..2026-09-15，只报告。
  - 每个滞后用所有 t+j ≤ 2026-09-17 的日期。不读 2026-09-18 以后的任何数据：那是新的留出段。
- **每个速度配置的指标**：毛夏普、净夏普、2 倍成本净夏普、年化换手（Σ|Δw| 均值 × 252 / 2）、平均总敞口、成本（bp/年）、与 m0_composite 日净收益的相关（M0 用同一引擎、L12、κ = 0.2、MOC）。

### 4. 合成

- 60 个快输入（A 53 + B 7）各自在 t 日的 U3000 内转成秩正态分数，缺失记 0。
- **FC_EW**：60 个分数等权平均。
- **FC_WF252**：
  - 每个输入 k 取信号日 s ≤ t−2 的 L12 滞后 2 日 IC 最近 252 个观测，算 IR_k = 均值 / 标准差。少于 200 个有限值时 IR_k = 0。
  - 合成：c_t = Σ IR_k·z_k / Σ|IR_k|（符号可以翻转）。
- **FC_WF63**：同上，取 63 个观测，至少 50 个。
- 热身期之前的日期记 NaN，不进窗口统计；报告有效起始日。
- 合成之后和其他对象一样测 IC、持续性和速度曲线。
- **安慰剂**（只对 3 个合成，在各自 MOC 最优速度上）：20 个种子，每个日期内在 L12 打乱合成分数（`evaluate.permute_within_date`），同 κ、同成本重算近期净夏普。报告真实值的分位；要求高于全部 20 个种子。
- **与 M0 的信号层组合**：
  - M0 用同一引擎在 L12、κ = 0.2（近似周频五档）、MOC 下的日净收益；合成用它最优速度的日净收益。
  - 两者按 63 日波动倒数月度定权，和"同波动的 M0"比近期、压力期夏普。
  - 只报告，用于第 2 阶段排序。
- **DSR**：合成在最优速度上的近期日净收益，试验数取 21（3 个合成 × 7 种速度）和 193，用 `evaluate.deflated_sharpe`。

### 5. 晋级规则（机械判定，写在结果之前）

- **单个新信号（B 组）**：
  - 条件：近期窗 L12 的 CIC(2..6) > 0，NW t ≥ 2.0；并在 7 个新信号上做 Benjamini–Hochberg（单侧 p 值），q ≤ 0.10。
  - 过了的作为第 2 阶段合成的输入，不单独做成策略。
- **合成（C 组）**：
  - "信息成立"：近期 L12 的 CIC(2..6) > 0，NW t ≥ 2.0。
  - "净值成立"：信息成立，而且最优速度的近期净夏普 > 0、高于全部 20 个安慰剂种子。
  - 净值成立 → 第 2 阶段 A 路：v1.2 构造里的快腿。
  - 只有信息成立 → 第 2 阶段 B 路：成本进目标函数的优化器，和 v1.2 慢信号一起净额成交。不关线（先改进、后否定）。
- **都不成立**：记"未到深度"，P1 先做阶段 1（学习式残差信号，成本进目标函数）。
- **压力期**：同号与否只报告，不作门槛（近期决定，旧数据看崩溃风险）。压力期 CIC(2..6) 的 t ≤ −2 的对象，在报告里单独标"状态翻转"，第 2 阶段设计时要加状态条件。
- **`mechanical_status`**：
  - `identity_failed`：恒等检验没过，停；
  - `measured_promotions`：至少一个对象晋级；
  - `measured_no_promotion`：没有对象晋级，即"未到深度"。

### 6. 功效（写在结果之前；数字是估计，脚本按窗口报告实际值）

- 近期窗约 670 个会话，L12 约 1000 只。
  - 零假设下单日截面秩相关的标准误约 1/√1000 ≈ 0.032，5 个滞后之和约 0.07。
  - 信号持续带来的序列相关，按 Newey–West 放大约 1.5–2 倍。
  - 均值标准误约 0.07 × 1.75 / √670 ≈ 0.005，所以 t ≥ 2 要求 CIC(2..6) 约 ≥ 0.01，即每个滞后约 0.002。
- 脚本对每个对象报告实际 IC 标准差和 80% 功效下的最小可检测效应 MDE = 2.8 × SE。MDE > 0.01 的对象写"功效不足"，不算否定。
- 净夏普：近期 2.7 年，年化夏普的标准误约 0.6，单独判有效太粗。
  - 晋级以信息量（IC）为主，净夏普只看符号和速度曲线的形状。
  - 同一数据上不同 κ 之间高度相关，相对比较的误差小得多。

### 7. 先验（结果之前，用于校准，不作门槛）

- 至少一个合成"信息成立"：约 60%。快因子库滞后 1 的毛夏普 1–2.6，问题在滞后 ≥ 2 还剩多少：一日反转类的信息多集中在滞后 1。
- 合成"净值成立"：约 30%。
- 新信号至少两个过 BH：约 50%。残差反转和行业内反转有两篇独立文献；ON5、ID5 不确定。
- m0_composite 的最优速度在 κ ≤ 0.25，即周频五档已接近最优、v1.2 自己不必日频：约 70%。v1.3 已知主题周度秩自相关 0.93–1.00。

### 8. 之后做什么

- **净值成立**：10-06 01:07 主审轮写第 2 阶段合同。最好的合成作为 v1.2 构造里的快腿（或第 10 个主题），按账户层边际净夏普判；部分调仓速度用本阶段的 κ*，Novy-Marx–Velikov 的买/持缓冲作为构造变体。目标是 10-09 前出第一批结果（第一版计划 C2 的时限）。
- **只有信息成立**：第 2 阶段 B 路，即 `optimize.py`（cvxpy）成本进目标函数，或 Gârleanu–Pedersen 瞄准组合（按各信号衰减速度加权）。
- **都不成立**：P1 阶段 1 先做。T-80 第 7 节的两项前置（1998–2016 日数据的免费来源、DLSA 许可证）由下一个 E1 主审轮查。
- **无论结果**：衰减曲线和成本–速度表进入 P1 项目笔记（第二版计划 P-3 落地后迁入），F_MOO、F_MOC 给阶段 3（收盘时点、15:45 快照）用。

### 9. 本阶段不做的

学习式模型（阶段 1、2）、分钟线特征（阶段 3）、跨信号的 GP 瞄准组合、买/持缓冲带、财报窗口信号（要先有预期公告日模型）、2026-09-18 以后的数据、Modal。

### 10. 已知局限

- 不补退市收益：L12 档影响小，报告每天剔除的只数。
- VSHK 是 21 日对 63 日成交额的粗代理，比原文的"一天到一周"粗。
- 成本模型的 close 快照是 15:45 前的最后报价，不是收盘竞价价格。收盘竞价的实际成本待核对：T-80 说 Alpaca 的 CLS 单标 Yes*，要联系销售。
- 借券 25 bp 是一般费率，难借名字已经由 SE_t 排除；冲击按 100 万美元规模。
