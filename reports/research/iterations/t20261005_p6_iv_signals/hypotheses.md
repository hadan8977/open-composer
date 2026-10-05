# Hypotheses: t20261005_p6_iv_signals

## Hypothesis

Option-implied volatility carries stock-level information missing from the price/fundamental library: high implied relative to realized volatility predicts higher returns, implied-volatility changes carry informed-trading information, and moves large relative to the implied move reverse; measurable on L12 in 2024-2026 with DoltHub data.

## Failure mode

Published effects are mostly borrow-fee proxies and spanned by equity characteristics, so the L12 IC is below the window's detectable effect; the vendor's blended IV mixes opposite-signed call and put changes; IVZ3 is just the reversal already measured by P1 Stage 0.

## Measurement

IC decay lags 1..22, decision CIC with Newey-West t, BH over four, marginal IC vs m0_composite and themes, persistence, diagnostics by year, bucket and window.

## Stop/Pivot criterion

Promotion only: failing signals are 'not yet at depth' with the reason; the full-smile features wait for the T-20261005-33 recorder.

## 预注册全文（2026-10-05 13:28 UTC 写定，13:07 主审轮 Opus；早于任何期权信号的 IC、衰减或收益数字）

### 0. 为什么做，写之前看过什么

- **为什么做**：机主 09-11 的数据分层把期权隐含信息排在价量之上。第二版计划第 3.6 节用途 2 把它定为 P1 阶段 2a 的信号来源。T-36c（`reports/research/intel/I-20261005-03-options-implied-stock-signals.md`）算过：只靠自存的前向快照，200 只、60 天能检出的最小 21 日 IC 是 0.117，而发表效应只有 0.007–0.033，要等好几年。更快的路是 DoltHub 的 `volatility_history`，但 2024-09 以后的覆盖率和时点一直没测（T-20260929-60 的整段验收按冻结标准"不通过"，那是期权定价用途的标准，本合同是另一个用途，不放宽它）。
- **本轮自己测的**（只是数据可得性，不含任何信号与收益的关系；证据在 `reports/research/intel/sources/p6-iv-signals-2026-10-05/`）：
  - 覆盖：近期窗 2024-01-08..2026-09-15 共 674 个交易日，有数据 594 个（88.1%）；2024-10-01 起 490 个交易日有 485 个（99.0%）；每个有数据的日期中位 1,535 只标的。2024-01 到 2024-08 只有周一、三、五（每月 9–13 天）。节假日也有行（27 个非交易日）。
  - 时点：`dolt_log` 最近 60 条提交显示，日期 d 的数据在 d 之后那个日历日约 06:35 UTC（美东 02:35）提交，早于下一个交易日开盘。
  - 幸存者：2021-03 的行里有 TWTR、SIVB、FRC、ATVI、XLNX、CTXS、DISCA、VIAC、CERN、KSU、PXD、SBNY，而且用的是当时的代码（FB，不是 META）。DoltHub 的标的集合是时点的。我们的 panel 混用两种口径（2021 年用 META，但 VIAC 不改 PARA），所以连接率要按年报告。
  - 表结构：iv_current、iv_week_ago、iv_month_ago、hv_current、hv_week_ago、hv_month_ago 等，主键 (date, act_symbol)。iv_current 的供应商定义（期限、看涨看跌如何合成）没有文档。
- **更正 I-03 的符号**：I-03 和 T-20260929-61 的计划写的是"HV 高于 IV 者做多"。Bali–Hovakimian 2009 摘要（快照 `options-signals-2026-10-08/abstracts-fetched-2026-10-05.md`）和 OSAP 的 RIVolSpread（`osap-signaldoc-optionmetrics-rows.json`，Sign −1，"Realized Vol (past 30 days) minus ATM Implied Vol"，t 2.9）都是"已实现减隐含与未来收益负相关"，即做多隐含高于已实现的股票。"HV 高于 IV 者做多"是 Goyal–Saretto 买期权的方向，不是股票的方向。本合同按 Bali–Hovakimian 定号。
- **本轮新读的反面证据**（`web-sources-2026-10-05.md`）：Neuhierl–Tang–Varneskov–Zhou（Management Science 2026，只读摘要）：控制大量公司特征后，只有少数期权特征有增量；Walter–Zimmer–Ulrich（arXiv 2609.31263，2026-09-25，样本内）：股票因子解释期权因子约 91% 的方差，Bonferroni 后留下的四个是跳跃尾部、峰度和隐含波动率凸性，IV−RV、IV 变化、看涨看跌价差都不在其中。所以本合同把"对 M0 的边际 IC"列为必报诊断，先验下调。

### 1. 机制和要回答的问题

1. 隐含高于已实现（波动率风险补偿或知情需求）的股票，在 2024–2026 年的流动股里是否仍有正的日度信息（扣掉行业和 β 之后）？
2. 隐含波动率的月度、周度变化是否带信息（An 等：看涨隐含上升 +，看跌隐含上升 −；供应商的 iv_current 是合成值，方向先验不明）？
3. 用隐含波动率去缩放 3 日涨跌（"跌幅超过期权给的预期幅度"）是否比用已实现波动率缩放更有信息？
4. 这些信息有多少是 v1.2 合成分数 M0 和九个主题里没有的？

### 2. 对象（预先写定，全部计入）

在信号日 t 计算（t 的定义见第 4 节 F2），只用 t 收盘及以前的信息：

| 编号 | 定义 | 方向 | 决策统计量 |
|---|---|---|---|
| IVRV | iv_current(t) − RV21(t)；RV21 = √252 × 最近 21 个交易日（截至 t 收盘）日对数收益的标准差，用 `data/research/equity_book/prices` 的复权收盘价 | +（Bali–Hovakimian；OSAP RIVolSpread 的 −1 取反） | CIC(2..22) |
| DIV21 | iv_current(t) − iv_month_ago(t)（同一行的供应商字段） | 取压力窗 L12 的 CIC(2..22) 均值的符号 | CIC(2..22) |
| DIV5 | iv_current(t) − iv_week_ago(t) | 取压力窗 L12 的 CIC(2..6) 均值的符号 | CIC(2..6) |
| IVZ3 | ln(close_t / close_(t−3)) ÷ (iv_current(t) × √(3/252)) | −（反转） | CIC(2..6)；另要求 IVZ3 − HVZ3 的 CIC(2..6) 点估计 > 0 |

- DIV21、DIV5 的符号：脚本先只算压力窗，把符号、均值、t 和时间戳写进 `cache/signs.json`，之后才能算近期窗的任何数字（P1 阶段 0 对 ON5、ID5 的做法）。
- 对照（不计入候选，不参与 BH）：HVZ3 = 同样的 3 日收益 ÷ (RV21 × √(3/252))；IVRV_V = iv_current − hv_current（供应商 HV）；每个信号滞后 63 个交易日的旧值。
- 候选 4 个，DSR 族 N = 4。项目披露：P1 阶段 0 之后是 193，本阶段加 4；跨项目总数以 T-20261005-34 的台账为准。

### 3. 共同口径（与 P1 阶段 0 相同，除非另写）

- **宇宙**：信号日 t 的 panel adv_rank ≤ 1000（L12，决策档）且当天 DoltHub 有该代码的行（精确代码匹配）。另报 L1（≤ 500）、L2（501–1000）。
- **目标收益**：e(t, j) = 收盘 t+j−1 到收盘 t+j 的个股收益减 β × SPY 同期收益（β = panel beta_252_spy，缺失记 1，截断到 −0.5..3），再在（日期，ind_code）内去均值；滞后 1 另拆成隔夜和日内。没有收益的股票当天剔除，不补退市收益，每天计数。
- **IC**：信号在（L12 ∩ 有数据）内转成秩正态，与 e(t, j) 求 Spearman；每个日期至少 200 只，否则该日期该滞后记缺失。对每个滞后得到日序列。CIC(a..b) = 滞后 a..b 的 IC 均值之和；t 值用每个日期的滞后和序列的 Newey–West t：CIC(2..6) 用 10 阶，CIC(2..22) 用 25 阶。稀疏段（周一三五）按有数据的日期排成序列计算，报告里写明。
- **成交约定**：t 收盘决策、t+1 收盘成交（v1.2 修正案 A1），所以可实现的是滞后 ≥ 2。本阶段不算交易速度和净夏普（留给 P1 阶段 2a），只报持续性（t 对 t−1、t−5、t−21 的截面 Spearman）以便估换手。
- **窗口**：近期 2024-01-08..2026-09-15 决定晋级；压力窗 2019-02-11..2023-08-31 只诊断并给 DIV21、DIV5 定号；机主 B 窗 2026-07-01..2026-09-15 只报告。每个滞后只用 t+j ≤ 2026-09-17 的日期。2026-09-18 以后的数据（DoltHub 和价格）一律不读，那是新的留出段。

### 4. 数据门（T-20261005-44 执行；不过就停，结论写"未到深度：数据"）

- **F1 覆盖**：拉取后重算。近期窗有数据的交易日 ≥ 550 个；2024-10-01..2026-09-15 的交易日覆盖率 ≥ 0.95；有数据日期的标的数中位 ≥ 1,200。
- **F1b 连接**：近期窗各日期 |L12 ∩ DoltHub| / |L12| 的中位数 ≥ 0.60。报告逐年连接率，以及从未匹配上的 L12 前 20 名（按 ADV）。不建改名映射，改名造成的损失写进局限。
- **F2 时点**（只测量，不设通过线，但必须在任何 IC 之前写进 `data-feasibility-measured.json`）：
  - 只用交易日的行，丢弃非交易日的行（报告节假日行与前一交易日完全相同的比例）。
  - 两个假设：H_same（d 行反映 d 收盘）和 H_prev（反映 d 之前那个交易日的收盘）。在 2024-10-01..2026-09-15 的每个日期，算 hv_current 与自算历史波动率（窗口 w ∈ {10, 20, 21, 22, 30}，截至 d 或截至前一交易日）的截面 Spearman，取各日期中位数。H_prev 的最佳中位数比 H_same 的最佳中位数高 ≥ 0.01 时，信号日 t = d 的前一交易日；否则 t = d（保守口径：信息只会被假设得更晚）。
  - 公布时点：用 `dolt_log` 最近 100 条提交，核对日期 d 的提交是否早于下一交易日美东 15:50。≥ 95% 是：成交在 t+1 收盘；否则把 t 再往后挪 k 个交易日（k 为公布延迟的 95 分位，至少 1），写明。
- **F3 数值**：近期窗非空 iv_current 有 ≥ 99% 在 [0.02, 5]；2024-10 起每只标的相邻交易日 iv_current 的一阶自相关中位数 ≥ 0.90；交易日上与前一交易日完全相同的行（陈旧）≤ 5%。
- **F4 时点标的**（只报告）：2019 年出现、2026 年不再出现的代码数；本轮探针的 12 个退市代码在拉取结果里的首末日期。

### 5. 晋级规则（机械判定，写在结果之前）

- **晋级为 P1 阶段 2a 的输入**：近期窗 L12 的决策 CIC 按冻结方向 > 0，Newey–West t ≥ 2.0，并在 4 个候选上做 Benjamini–Hochberg（单侧 p，正态近似），q ≤ 0.10。IVZ3 还要 IVZ3 − HVZ3 的近期 CIC(2..6) 点估计 > 0。
- **否则**记"未到深度"，并写原因：功效（MDE 大于下面第 6 节的参考效应）、数据、或估计值小。本阶段不能关闭任何方向（机主 10-04，计划 P-1）。
- **mechanical_status** 只能是三个值之一：`promote_some`、`none_promoted_not_at_depth`、`data_gate_failed`。
- **诊断（只报告，不作门槛）**：对 M0 的边际 IC（每个日期在同一集合内把信号对 m0_composite 和 9 个 theme_* 做截面 OLS，取残差再算 IC）；L1、L2 分档；逐年；压力窗同号与否（压力窗 t ≤ −2 的标"状态翻转"）；机主 B 窗；IVRV_V；滞后 63 日旧信号的 IC；滞后 1 的隔夜、日内拆分；衰减曲线和半衰期（P1 阶段 0 的 h_np）。

### 6. 功效（写在结果之前；脚本按实际 N 和序列报告 SE 与 MDE）

- 近期窗约 594 个有数据的日期；L12 ∩ DoltHub 预计约 650–750 只（F1b 测）。单个滞后的截面 IC 抽样标准差约 1/√700 ≈ 0.038。
- CIC(2..22)：每个日期 21 个滞后之和的标准差约 √21 × 0.038 ≈ 0.17；月度信号持续、窗口重叠，有效独立期约 594/21 ≈ 28，所以 SE ≈ 0.032，MDE = 2.8 × SE ≈ 0.09。
- CIC(2..6)：每个日期约 √5 × 0.038 ≈ 0.085，NW 放大约 1.75，SE ≈ 0.0061，MDE ≈ 0.017。
- 参考效应（量级换算，IC21 ≈ CIC(1..21)/√21）：IVRV 发表值 IC21 0.018–0.026 → CIC(2..22) 0.082–0.119；DIV21 用 An 等的 0.021–0.033 → 0.096–0.151（合成 IV 的效应未知，只作参考）；DIV5、IVZ3 没有发表值，参考用 P1 阶段 0 的 0.010。发表后普遍打折（McLean–Pontiff 约 −58%），打折后的 IVRV 约 0.035–0.050，本窗口检不出。
- 结论：本检验只能检出接近原文、未打折的效应；MDE 大于参考效应的对象，结果不显著时写"功效不足"，不算否定。真实 IC 随时间波动会让 SE 再大 1.2–1.5 倍，脚本按实际序列算。

### 7. 先验（结果之前，用于校准，不作门槛）

- IVRV 晋级约 20%；DIV21 约 12%；DIV5 约 12%；IVZ3 自身过约 40%，加上 HVZ3 条件约 20%。至少一个晋级约 45%。
- 晋级的信号对 M0 的边际 IC 仍为正约 30%（Neuhierl 等、Walter 等的证据）。

### 8. 之后做什么

- **有晋级**：
  1. 进 P1 阶段 2a 的信号族（10-06 01:07 起的 P1 主审轮写合同，约 10-12），方向和时点按本合同冻结；在组合层按边际净夏普判，计入 2a 的试验总数。
  2. 在 2a 依赖它之前：跑能力评估，在 `capabilities/registry.yaml` 登记 `options.dolthub_volatility_history`（trial、research_only）；写每日增量拉取（每天 06:40 UTC 之后拉新日期），cron 由交互会话安装。
  3. 2026-09-18 以后的留出段只在 2a 冻结之后打开一次。
- **无晋级**：写"未到深度"和原因。DoltHub 上这四个信号不再加工作，除非有新信息（例如能拿到同一行权价的看涨、看跌 IV，构造 Cremers–Weinbaum 价差）。期权信息这条线转到 T-20261005-33 自存的整条链：凸性、峰度、跳跃尾部（Walter 等留下的维度）和看涨看跌价差都要从那里算，第一次数据质量检查在 12 月下旬。

### 9. 本阶段不做的

交易速度和净夏普（P1 阶段 2a 做）；DoltHub option_chain 的个股整链（按 API 每次 1,000 行，约 1,000 只 × 500 天 × 150 行，拉不动）；看涨看跌价差、微笑斜率、风险中性偏度和峰度（数据不够）；改名映射；2026-09-18 以后的数据；Modal。

### 10. 已知局限

- iv_current 的期限和合成方式没有文档；DIV21、DIV5 是合成 IV 的变化，不是 An 等的看涨、看跌分开的变化。
- 稀疏段只有周一三五；节假日行丢弃；改名的标的在连接时丢失（2021 年的 FB 等）。
- 不补退市收益（与 P1 阶段 0 相同）。
- DoltHub 是第三方免费库，供应商和快照时刻没有文档；2024-10 以后时点由提交记录支持，此前的回填段只能假设同样的口径。
