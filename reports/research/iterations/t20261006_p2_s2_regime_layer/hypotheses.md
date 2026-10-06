# Hypotheses: t20261006_p2_s2_regime_layer

## Hypothesis

A persistence-penalised online jump model on market risk features identifies equity bear regimes early enough that removing S3's levered exposure in them raises S3's stress-period Sharpe by at least 0.10 over an exposure-matched volatility target, without costing more than 0.10 of recent Sharpe.

## Failure mode

S3's monthly momentum rotation and its 0.40 volatility target already shrink exposure in the same episodes, so the jump model adds only what a tighter volatility target adds; or the one-day delay and V-shaped rebounds (2020-04, 2025-04) make the gate re-enter late; or the paper does not reproduce on CRSP value-weighted data.

## Measurement

Index level: Sharpe, return, volatility, MDD, Calmar, ES 5%, turnover, average exposure and changes per year for buy-and-hold, each spec and its exposure-matched volatility target (1990-2023; 2010-01..2026-07). Sleeves: per object, spec, offset and window the same metrics plus ES97.5, differences to the volatility target and to the ungated sleeve with paired stationary-bootstrap intervals, placebo percentiles, 20 bp, zero delay and a crash-episode table.

## Stop/Pivot criterion

Mechanical status for S3: shadow_candidate_selected, increment_not_robust or no_increment_all_depth_points. The last reads 'no increment at any depth point; underpowered to refute' unless the reproduction passed and power is adequate (plan v2 P-1). Shadow = 8-12 weeks log-only before any allocation change.

## 预注册全文（2026-10-06T07:33Z 写定，07:07 主审轮 Opus；早于任何状态、乘数或加门后收益在我们数据上的计算）

### 0. 为什么做，写之前看过什么

- **计划**：第二版计划第 3.2 节 P2 阶段 2"状态层"（10-08 至 10-13）。机主 10-04 说压力期夏普低；S3 占试点风险约 90%，压力期夏普约 0.59（T-75），T-31 之后试点只剩 S3。
- **看过的**：
  - 论文 Shu–Yu–Mulvey 2024（JAM 25(5):493–507）表 4 和表 3：标普 1990–2023，B&H 夏普 0.48 → JM 0.68，回撤 −55.2% → −26.6%，换手 44%，平均仓位 80%；HMM 0.54，换手 141%；λ = 50–100 时每年切换不到 1 次。
  - 作者的代码 jumpmodels：损失 0.5 × 平方欧氏距离，前向 DP，k-means++ 起点，按累计收益排状态（快照 `reports/research/intel/sources/p2-s2-regime-layer-2026-10-06/`）。
  - I-20261004-06 第 1、7、9 节。
  - 登记簿：`dir:jump_model_regime`（parked，"只是回撤控制"）、`dir:s3_bear_regime_guard`（refuted）、`dir:levered_single_asset_sma_trend_gate`（refuted）、H-20260928-31（refuted）。
  - T-75 的分状态表、T-41 的成交时点结果。
  - **没看过**：任何状态序列、乘数，或加门后收益在我们数据上的数字。
- **和旧否定的区别**：
  - 旧的都是单规格、只在 2016–2023 上拟合的滞后价格闸门。
  - 这次是带持续性惩罚的在线聚类（下行风险和风险调整收益特征），用 30 多年免费长历史拟合，按三条深度轴扫。
  - 对照是登记簿重开条件要求的"同敞口波动率目标"。
  - 按机主 10-04 的深度规则，旧的单规格测试不能否定这一类。

### 1. 机制和要回答的问题

- **机制**：熊市状态有持续性（波动聚集，回撤期漂移为负）。用带跳跃惩罚的聚类识别下行风险特征，可以在较短延迟内在线识别熊市。
- **为什么 S3 可能比指数受益更多**：
  - 三倍杠杆 ETF 每日重置，在高波动、来回震荡的阶段复利损耗最大（arXiv 2504.20116：趋势市增强，均值回复和波动聚集拖累）；
  - 动量轮动在熊市后的恐慌状态最容易崩溃（Daniel–Moskowitz 2016）。
  - 在这些状态里离场，去掉的正是负凸性最强的一段。这个作用不同于把仓位整体缩小，所以对照必须是同敞口的波动率目标。
- **谁在付钱，什么时候失效**：
  - 收益来自躲开杠杆损耗和动量崩溃，不是额外的风险溢价。
  - 失效情形：V 形反弹（2020-04、2025-04）时，一天延迟让重新入场太晚；S3 自己的月度轮动和 0.40 波动率目标已经在同一段时间降了仓。
- **问题**：日度状态乘数能否在压力窗提高 S3 的同敞口夏普至少 0.10，同时近期窗代价不超过 0.10？指数层面，它是不是比同敞口波动率目标多出东西，也就是不只是回撤控制？

### 2. 对象（预先写定，全部计入试验数）

九个规格，按轴扫，不做全因子组合。参数全文见 `candidate-manifest.json`：

| 规格 | 模型 | 输入 | 持续性 | 轴 |
|---|---|---|---|---|
| J3_CV | 跳跃模型 | F3 | λ 按交叉验证选，{0,5,15,35,50,70,100,150} | 论文基准 |
| J3_L15、J3_L50、J3_L150 | 跳跃模型 | F3 | λ 固定 15、50、150 | 持续性 |
| J4_CV | 跳跃模型 | F3 + log VIX | 交叉验证 | 输入 |
| J6_CV | 跳跃模型 | F4 + VRP 差 + BAA10Y 21 日变化 | 交叉验证 | 输入 |
| H2_CV | 2 状态对角高斯 HMM | F3 | 平滑 k ∈ {0,2,4,8,20}，交叉验证 | 模型 |
| G2 | 2 成分对角高斯混合 | F3 | 无 | 模型 |
| TV | 现有"200 日线 × VIX 三档" | — | — | 模型（项目现有划分） |

- **决策对象**：S3（偏移 0、4、8、12、16 的五偏移混合，冻结的 0.40 波动率目标和回落加仓）。试验数 9，计入项目总数，用于 DSR。
- **只报告**：S1、S2、C2；指数层全部结果；J3_CV 熊市乘数取 0.5 的诊断；零延迟敏感性；危机片段表；选中规格的 S3 21 偏移分布。

### 3. 共同口径

- **市场序列**（超额收益）：
  - 1970-01-02..2015-12-31 用 French 日度 Mkt-RF（CRSP 市值加权，文件 F-F_Research_Data_Factors_daily）；
  - 2016-01-04 起用 SPY 的 SIP 复权收盘收益减 RF；
  - RF 用 French 日度 RF 到其最后一天，之后用最后一个月的日均值。
- **特征**：
  - F3：下行偏差 EWM（半衰期 10），Sortino 比率 EWM（半衰期 20、60），都在市场超额收益上算（论文第 3.3 节）。
  - F4 = F3 加 log VIX 的 EWM（半衰期 10，FRED VIXCLS）。
  - F6 = F4 加 log(VIX/100) − log(RV21)，再加 BAA10Y 的 21 日变化（百分点，FRED）。
  - VIX、BAA10Y 缺一天时最多沿用 3 个交易日，超过就让该日特征缺失、沿用前一天的状态。
- **拟合**：
  - 每年 1 月、7 月第一个交易日，在最近 3000 个交易日上重拟合。
  - 特征先截到训练均值 ± 3 个标准差，再用训练均值和标准差标准化（jumpmodels 示例的流程）。
  - 跳跃模型：损失 0.5 × 平方欧氏距离，每次换状态罚 λ；k-means++ 起点 10 个，固定种子，max_iter 1000，tol 1e-8。
  - 状态按训练窗内市场累计超额收益排序（sort_by cumret），高的为牛市。
- **在线推断**：
  - 前向 DP：values[t] = loss[t] + min_j(values[t−1][j] + λ·1{j≠k})，从每次重拟合日往前 3000 个交易日开始，用那次的参数一直算到下一次重拟合。
  - 状态_t = argmin_k values[t]。只用 t 及以前的数据。
- **交叉验证**（CV 规格）：
  - 每月第一个交易日，对每个候选值，用它自己的在线序列算指数 0/1 策略最近 2016 个交易日（8 年）的夏普（一天延迟、10 bp），取最高的。
  - 选中值从 t+2 起生效。超参数只按指数层选，**从不按子策略选**。
  - 第一个检验月：J3、H2、G2 是 1990-01（数据从 1970 起，12 年拟合加 8 年验证，同论文）；J4、J6 是 2010-01（VIX 从 1990 起）。
- **乘数和时点**：
  - 牛市 m = 1，熊市 m = 0；TV 是 0、0.5、1。
  - 收盘 d 推断的状态从第 d+2 个交易日起生效（一天延迟，同论文主口径）。
  - 零延迟（d+1）只报告。
- **指数层**：在场的日子拿超额加 rf，离场拿 rf；m 每变化一个单位收 10 bp。
- **子策略层**：
  - 冻结引擎用 `reports/research/program/etf-open-close-2026-10-07/compute.py` 的 simulate_effective（T-41 已证明和冻结引擎一致）；
  - 风险权重乘 m，剩余放该子策略自己的现金 ETF；
  - 每边 10 bp 按成交名义计，m 变化带来的交易也算在内；
  - 恒等检查：m ≡ 1 时与 T-41 的 O 口径逐位一致（≤ 1e-12），不过就停。
- **同敞口波动率目标**（对照）：
  - m_VT = min(1, τ/σ̂)，σ̂ 是未加门对象日净收益的 EWM（半衰期 21）年化波动，收盘 d 已知，同样延迟生效；
  - τ 在每个窗口内用二分法定，使 m_VT 的均值等于该规格 m 的均值（子策略按每个偏移分别定）。
  - 匹配用的是窗口内的波动路径，对照因此略占信息优势，对检验偏严。
- **安慰剂**：在 2017-10-02..2026-09-17 上，把该规格的日度乘数循环平移 k 个交易日，k 从 {−756..−63} ∪ {63..756} 里抽，50 个固定种子；报告真实夏普在安慰剂里的分位。
- **窗口**：
  - 指数层：复现 1990-01-02..2023-12-29；全部规格 2010-01-04..2026-07-31。
  - 子策略层：压力窗 2017-10-02..2023-08-31（判定，即标准 config 的 stress_window）；近期 2024-01-08..2026-09-17（不劣）；机主 B 窗 2026-07-01..2026-09-17（只报告）；全期 2017-10-02..2026-09-17。
  - **2026-09-18 及以后的数据一律不读**。
- **夏普**：超额（指数用 rf，子策略减 BIL），日度年化；配对平稳块自助（平均块长 21，2000 次，固定种子）给差值区间，只报告。

### 4. 阶段 2a：复现关口和指数层（T-20261006-03）

- **复现**（P-1 第 1 条，免费数据下按相对结论判）：J3_CV 在 1990–2023 上要同时满足：
  - R1：夏普减 B&H ≥ +0.10（论文 +0.20）；
  - R2：最大回撤改善 ≥ 15 个百分点（论文 28.6）；
  - R3：每年切换 ≤ 2 次。
  - 三条都过记 `reproduced`。
  - 不过：先对照 jumpmodels 包，在隔离环境里用同一段数据和 λ 比拟合中心和状态。两边一致仍不过，记 `not_reproduced_on_crsp`；这时 J、H、G 类规格都不能到 PASS_SHADOW，阶段 2b 照跑，只作诊断。
- **指数层输出**（只报告，也是死因诊断的依据）：每个规格、它的同敞口波动率目标和 B&H 的夏普、年化、波动、最大回撤、Calmar、ES5%、换手、平均仓位、每年切换次数；窗口 1990–2023（J3、H2、G2）和 2010-01..2026-07（全部）。
- 关键诊断是"规格夏普减同敞口波动率目标夏普"。它回答登记簿的结论"只是回撤控制"对不对。
- **产出**：`index_results.json`，加上每个规格的日度乘数文件 `cache/multipliers.parquet`。冻结后交给阶段 2b，**2b 不许重算或修改**。

### 5. 阶段 2b：子策略判定（T-20261006-04；机械，写在结果之前）

对 S3 的每个规格（五偏移混合，10 bp，一天延迟）：

- **PASS_SHADOW** 要求以下全部成立：
  - (a) 压力窗夏普减同敞口波动率目标版 S3 ≥ +0.10，且近期窗 ≥ −0.10；
  - (b) 压力窗夏普减未加门 S3 ≥ +0.10；
  - (c) 全期循环平移安慰剂分位 ≥ 0.80；
  - (d) 五个偏移里至少 4 个的压力窗"减波动率目标"差 > 0；
  - (e) 每边 20 bp 时 (a) 仍成立；
  - (f) 全期平均每年乘数变化 ≤ 3 次；
  - J、H、G 类规格还要阶段 2a 是 `reproduced`。
- **INCREMENT_NOT_ROBUST**：压力窗"减波动率目标"差 > 0、近期窗 ≥ −0.10，但 (a)–(f) 有不满足的。
- **NO_INCREMENT**：其余。
- **选规格的规则**（事先写定）：PASS_SHADOW 里压力窗"减波动率目标"差最大的；相差 0.02 以内选每年变化少的。
  - J3 族只在 {L15, L50, L150, CV} 中的一个点通过时标 `fragile_persistence`，仍可入选，但影子期加倍到 12 周。
- **阶段机械状态**：
  - `shadow_candidate_selected`：至少一个 PASS_SHADOW；
  - `increment_not_robust`：没有 PASS_SHADOW，但至少一个 INCREMENT_NOT_ROBUST；
  - `no_increment_all_depth_points`：全部 NO_INCREMENT。
- S1、S2、C2 同样打标签，只报告，不作决定。

### 6. 功效（写在结果之前；用 √((2−2ρ)/T) 估计配对夏普差的标准误，ρ 为两条序列的相关，脚本按实际序列报告）

| 窗口 | 年数 | ρ = 0.85 时 SE | ρ = 0.95 时 SE | 80% 功效的 MDE（ρ 0.85 / 0.95） |
|---|---|---|---|---|
| 指数 1990–2023 | 34 | 0.094 | 0.054 | 0.23 / 0.14 |
| 指数 2010-01..2026-07 | 16.6 | 0.135 | 0.078 | 0.34 / 0.19 |
| 压力窗 2017-10..2023-08 | 5.9 | 0.225 | 0.130 | 0.56 / 0.32 |
| 近期 2024-01..2026-09-17 | 2.7 | 0.333 | 0.192 | 0.83 / 0.48 |

- 指数层能看到论文量级的效应（+0.20 约为 1.5–2 个标准误）。
- 子策略层的 +0.10 只是政策门槛，不是显著性检验。
- 所以 `no_increment_all_depth_points` 写成"所有深度点都未见增量，功效不足以否定"（P-1 第 5 条不满足），**不能写"否定"**。CBS 2025 的论文也是同样情形：方向一致，但不显著。

### 7. 先验（结果之前，用于校准，不作门槛）

- 复现 R1–R3 全过：约 65%（CRSP 和标普总收益、1 月期和 3 月期国库券的差别，加上实现细节）。
- J3_CV 在指数层比同敞口波动率目标高 ≥ 0.05（1990–2023）：约 45%。
- S3 至少一个规格 PASS_SHADOW：约 20%。理由：S3 已有 0.40 波动率目标，09-23 的均线闸门没赢过同敞口对照；但杠杆损耗和动量崩溃的机制支持状态信息有增量。
- `no_increment_all_depth_points`：约 45%。

### 8. 之后做什么

- **shadow_candidate_selected**：
  - 选中的规格从审核后的下一个会话起只记日志、影子运行 8 周（fragile 的 12 周）：每天写状态、乘数和加门后的 S3 目标。
  - 失效信号：一个季度变化超过 3 次，或 6 个月滚动夏普低于同敞口波动率目标。
  - 影子通过后，按配置第二版（T-58）的口径在账户层复核，再提给机主。试点在这期间用冻结的 S3 规则。
  - 实盘用到 French 数据重拟合的问题要先解决：SPY 的 SIP 历史到约 2027-11 才满 3000 个交易日；先登记 French 日度数据能力，或冻结 2016 年以前的拼接。
- **increment_not_robust**：不进影子。把增量最大的那个规格写进阶段 3（周期条件器，10-21 起）的输入设计。
- **no_increment_all_depth_points**：按第 6 节写"功效不足以否定"，S3 上的状态层停在这一步。指数层如果显示规格胜过同敞口波动率目标，状态读数只作 T-58 账户层的风险监控；P2 转阶段 3。登记簿 `dir:jump_model_regime` 按指数层结果改写结论。
- **复现不过**：指数层和子策略层都只作诊断。先查数据差异（CRSP 对标普总收益），不追加规格。

### 9. 本阶段不做的

- 拓扑变体（Gidea–Katz 持续同调景观范数）：要先装拓扑库，归阶段 2c，在本阶段审核之后另写合同。
- 稀疏跳跃模型（约 20 个特征自动选择）、3 状态模型、主题层（SMH 上的状态）。
- 熊市乘数 0.5 只作 J3_CV 的诊断。
- 不改 S3 规则、不改模拟盘、不碰 2026-09-18 以后的数据。

### 10. 已知局限

- French CRSP 市值加权代替标普总收益，1 个月期国库券代替 3 个月期。2016 年在 SPY 处拼接。
- TV 的 VIX 三档阈值取自 1990–2015，指数层 2010–2015 段对 TV 是样本内。
- 子策略开盘成交，论文用收盘到收盘。
- 同敞口波动率目标在窗口内匹配，对照略占信息优势，对检验偏严。
- H2 用 F3 特征，不是论文那个只用收益的 HMM；和论文的 0.54 比较只作参考。
- I-20261004-06 里"稀疏跳跃模型"的快照（arXiv 2106.09535）抓错了文章，是一篇物理论文，本合同不引用。

### 11. 执行

- **T-20261006-03（阶段 2a）**：数据、模块、测试、交叉核对、复现、指数层九个规格。本机，`run_capped --mem 1.5G`，上限 3 小时。
- **T-20261006-04（阶段 2b）**：子策略层。等 T-03 done，并且 `cache/multipliers.parquet` 的 sha256 已写进 `index_results.json`。上限 2 小时。
- 都排在关键路径任务之后（priority 2）。目标：10-09 前交 2a，10-11 前交 2b；10-12 07:07 主审轮（P2）审核。
