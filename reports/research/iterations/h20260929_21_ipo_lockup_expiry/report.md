# Report: h20260929_21_ipo_lockup_expiry

Queue: T-20260929-21. Direction: `dir:ipo_lockup_expiration_drift`.
Hypothesis: 做空/回避美股近期 IPO 普通股在 ~180 天股权解禁到期日附近，能在扣除
实际交易成本后获利（Field & Hanka 2001 JF：解禁日附近 3 日 CAR 约
-1.5%～-1.8%）。

## 1. 事件列表构建（PIT）与 20 样本人工核查

事件由 `scripts/build_h20260929_21_lockups.py` 两条口径合成：
`424b4_confirmed`（SEC EDGAR 424B4 招股说明书，通过当前 `company_tickers.json`
把 CIK 映射到 ticker，再与该 ticker 在 `data/features/daily_broad` 里的首个
交易日做 -3..+5 日窗口交叉核对）和 `first_trade_fallback`（该 ticker 在面板里
的首个交易日，要求晚于面板起点至少 180 天，并通过 SPAC 单位/认股权证后缀
与最低股价过滤）。过滤非普通股名称（优先股/次级债/存托股/权证等关键词，复
用 `data/features/universe/_asset_metadata.parquet` 的 `name` 字段）后，最终
事件数 `total_events=3577`（`424b4_confirmed`=1157，`first_trade_fallback`=2420；
来源：`reports/research/iterations/h20260929_21_ipo_lockup_expiry/build_summary.json`）。

20 样本随机人工核查（seed 20260929，在名称过滤器加入前抽样）发现 **6/20
（30%）不是真正带员工/VC 解禁动态的普通股 IPO 事件**：EIC（封闭式基金）、
BPYPO（Brookfield Property Partners 优先股系列）、RZC（RGA 次级债券）、CCRD
（同周 ticker 改名，不是新股）、BSLK（首个交易日与真实借壳上市日期对不
上，未解决的数据异常）、DCX（本轮搜索未能独立确认对应 2022 年纳斯达克
IPO，按错误处理）。**6 个错误全部出在 `first_trade_fallback` 口径**
（该口径抽样 17 个中 6 个错=35%；`424b4_confirmed` 口径抽样 3 个全部正确）。
详见 `decision-record.md`。

处理方式：加入非普通股名称过滤器（结构性排除了 BPYPO、RZC 两类，占已知 6
个错误的 2/6），移除了过滤前 3897 个候选事件中的 339 个（8.7%）。**没有**
在过滤后的事件集上重新做第二轮独立抽样核查（时间预算限制）；因此本报告
如实把 30%（6/20）当作过滤前的**上限**口径报告，而不是当作已解决。
`first_trade_fallback` 口径的结果置信度应相应下调；`424b4_confirmed` 口径
样本量小（n=3）也未在更大规模上独立复核。

## 2. 数据卫生（price hygiene）

对事件股票面板和 BIL 面板都用了
`open_composer.research.features.price_hygiene.sanitize_price_matrices`
（默认阈值：单日价格比>10x 或 >5 个交易日缺口叠加大对数跳变则整段价格打
码）。结果（来源：`results.json.price_hygiene`）：

- 事件股票面板：`breaks_detected=6663`，`symbols_masked=259`（占 3577 个事件
  标的的 7.2%，其中因单日跳变 79 个、因缺口 180 个），`price_cells_masked
  =124532`。这证实近期 IPO/小盘股确实比一般股票更容易出现价格断层，值得
  在这类回测里单独处理。
- BIL 面板：`breaks_detected=0`，未被打码（符合预期，BIL 是稳定的短债 ETF）。
- 检查了净值最大的 5 笔交易（symbol/entry/exit，见下表）是否落在被打码的
  259 个标的名单里：**都不在**（RYDE/AXG/BUUU/MENS/YDDL 均未被 hygiene 标
  记），即这些大额亏损/盈利交易目前判定为真实的小盘股剧烈波动，不是已知
  的价格断层伪影；但不能排除该口径未覆盖到的其它数据问题。
- Ghost-bar 检测未在这一层运行（`data/features/daily_broad` 没有
  `volume`/`trade_count` 列），假定已经在上游特征构建阶段处理，本轮未独立
  复核。

## 3. 13 个预注册候选：全量结果表（TEST 窗口 2024-01-08..2026-09-17）

方向：`pos`=只做空解禁后走势偏弱一侧候选；`neg`=只做空解禁后走势偏强一侧
候选（动量过滤反向分组，非"做多"）；`all`=不做动量过滤；`avoid_long_info`
=仅供参考、不计入决策规则的对照行。窗口 `L5L1`=解禁前 5 日进场/解禁后 1
日出场，`L1L5`=解禁前 1 日进场/解禁后 5 日出场。

| 候选 candidate_id | TEST事件数 | TEST 年化Sharpe | TEST CAGR | STRESS Sharpe | 胜率(净收益>0扣成本后,%) | 平均每笔净收益 | 中位每笔净收益 | 1%/99%截尾均值 | 每年交易笔数(TEST) | 最差单笔净收益 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| L5L1_adv1500_all | 411 | -0.309 | -11.03% | -0.192 | 47.95% | -0.325% | -0.189% | 0.240% | 152.7 | -513.9% |
| L5L1_adv1500_pos | 191 | -0.315 | -5.48% | -0.032 | 47.95% | -0.061% | -0.189% | 0.354% | 71.0 | -201.7% |
| L5L1_adv1500_neg | 205 | 0.093 | -0.36% | -0.247 | 48.44% | -0.356% | -0.187% | 0.285% | 76.2 | -513.9% |
| L5L1_unrestricted_all | 698 | -1.402 | -42.04% | -0.110 | 45.77% | -0.384% | -0.336% | 0.100% | 259.4 | -513.9% |
| L5L1_unrestricted_pos | 277 | -1.011 | -16.93% | -0.095 | 45.07% | -0.300% | -0.290% | 0.099% | 102.9 | -201.7% |
| L5L1_unrestricted_neg | 370 | -0.690 | -23.33% | -0.058 | 48.30% | -0.293% | -0.189% | 0.293% | 137.5 | -513.9% |
| L1L5_adv1500_all | 409 | 0.022 | -3.67% | -0.486 | 47.15% | -0.870% | -0.212% | -0.351% | 152.0 | -224.2% |
| **L1L5_adv1500_pos**（TEST内最佳） | 190 | **0.419** | 5.63% | -0.460 | 45.58% | -0.481% | -0.290% | -0.150% | 70.6 | -200.6% |
| L1L5_adv1500_neg | 204 | -0.055 | -4.26% | -0.243 | 48.83% | -1.067% | -0.110% | -0.317% | 75.8 | -248.4% |
| L1L5_unrestricted_all | 695 | -0.958 | -40.41% | -0.362 | 45.99% | -0.998% | -0.365% | -0.312% | 258.2 | -267.5% |
| L1L5_unrestricted_pos | 275 | -0.308 | -8.35% | -0.537 | 43.69% | -0.796% | -0.391% | -0.266% | 102.2 | -267.5% |
| L1L5_unrestricted_neg | 369 | -0.753 | -32.20% | -0.166 | 48.93% | -1.132% | -0.110% | -0.355% | 137.1 | -234.9% |
| avoid_long_info（信息参考，不计入决策） | 698 | 0.819 | 25.09% | -0.409 | 44.28% | -0.122% | -0.320% | -0.604% | 259.4 | -79.1% |

来源：`reports/research/iterations/h20260929_21_ipo_lockup_expiry/results.json`
的 `cells.*`（每个候选的 `test_metrics`/`stress_metrics`/`trade_stats`/
`trades_per_year_test`）。胜率、平均/中位/截尾均值、最差单笔均为净值（已扣
ADV 分层价差成本与借券成本），n_trades（含 TEST+STRESS 全部窗口的单腿事件
交易）作为分母。

TEST 内最佳候选 `L1L5_adv1500_pos` 的 5 笔 |毛收益| 最大交易
（来源同上 `cells.L1L5_adv1500_pos.trade_stats.largest_abs_gross_return_trades`）：

| symbol | entry | exit | 毛收益 | 净收益 |
|---|---|---|---:|---:|
| RYDE | 2024-09-03 | 2024-09-11 | -200.4% | -200.6% |
| AXG | 2024-03-05 | 2024-03-13 | -119.2% | -119.4% |
| BUUU | 2026-02-10 | 2026-02-19 | -79.4% | -79.7% |
| MENS | 2025-12-15 | 2025-12-23 | +79.4% | +79.3% |
| YDDL | 2026-04-07 | 2026-04-15 | +71.4% | +71.1% |

（负号=做空该标的期间股价上涨、组合亏损；均未被 price hygiene 标记为需要
打码，判定为真实的小盘股尾部波动，是这个策略结构性的一部分而非数据错误。）

## 4. 容量约束下被跳过的事件数

同一交易日在场持仓上限 15、单腿权重上限 10% 下，各候选因容量满员被跳过的
事件数（来源：`results.json.capacity_skipped`）：`L5L1_adv1500_all`=352、
`L5L1_adv1500_pos`=33、`L5L1_adv1500_neg`=79、`L5L1_unrestricted_all`=753、
`L5L1_unrestricted_pos`=36、`L5L1_unrestricted_neg`=182、
`L1L5_adv1500_all`=352、`L1L5_adv1500_pos`=33、`L1L5_adv1500_neg`=79、
`L1L5_unrestricted_all`=753、`L1L5_unrestricted_pos`=36、
`L1L5_unrestricted_neg`=182、`avoid_long_info`=753。

## 5. 安慰剂检验（TEST 内最佳候选 L1L5_adv1500_pos）

事件日期聚类 t 统计量（同一解禁日的多个事件先在组内取真实-安慰剂差值均
值，再跨组做 t 检验）。来源：`results.json.placebos`：

| 安慰剂 | 配对数 n | 真实-安慰剂均值差 | t 统计量 |
|---|---:|---:|---:|
| date_shift_plus60（事件日+60 个交易日） | 960 | -0.395% | -0.588 |
| date_shift_minus60（事件日-60 个交易日） | 974 | +1.834% | 2.220 |
| random_date（同数量随机日期，seed=20260929） | 482 | +0.745% | 0.657 |

判据要求安慰剂对比 |t| >= 2（`placebo_pass`）。三个安慰剂中只有
`date_shift_minus60` 一个方向单独达到 |t|>=2，`date_shift_plus60` 与
`random_date` 都不显著；`decision_rule.placebo_pass=false`（来源：
`results.json.decision_rule`）——即没有稳健地在两个安慰剂族里都通过，判
定为未通过安慰剂检验。

（本次重跑修复了此前 `shift_events()` 的一个代数错误：修复前该函数在移位
后才重新计算窗口宽度，导致位移被代数抵消，安慰剂交易与真实交易逐笔相同
——`date_shift_plus60`/`date_shift_minus60` 均显示 `mean_diff=0.0` 整、
`t_stat=NaN`。已加回归测试
`test_shift_events_actually_moves_entry_and_exit_indices` 锁定修复；本报告
中的安慰剂数字来自修复后的重跑。）

## 6. 2倍成本稳健性、S3 相关性/增量边际、DSR

- 2倍成本重跑（`results.json.best_candidate_2x_costs`）：TEST Sharpe
  从 0.419 降到 0.326（`decision_rule.survives_2x_costs=true`，因为判据只要
  求 2 倍成本下策略方向不反转/仍为正，非要求仍达标阈值——具体阈值判定见
  第 7 节）。
- 与 S3（既有基线组合）的相关性：`correlation_with_s3_test = -0.119`；
  增量边际 `diversifier_edge_vs_s3_test = -0.274`（负值，即加入这个候选反而
  拉低组合而非贡献增量收益）。
- DSR（Deflated Sharpe Ratio，用全部 13 个预注册候选作为 trial_count，
  HAC lag=21）：`dsr_probability = 0.159`，`dsr_trial_count = 13`（来源：
  `results.json.dsr_probability`/`dsr_trial_count`）。0.159 远低于常见的
  0.95 显著性门槛，即使不看其它判据，多重检验校正后的把握也很低。

## 7. 冻结判决规则与最终结论

判决规则（冻结于 `search-space.json`/`candidate-manifest.json` 预注册，
`TEST` 有 >=40 个事件时以 TEST 窗口为准）：TEST Sharpe >= 1.19 **或**
`diversifier_edge_vs_s3_test >= +0.05`；安慰剂对比 |t| >= 2；2倍成本下不反
转；TEST 事件数 >= 40。

逐条核对（来源：`results.json.decision_rule`，判决窗口
`verdict_window=TEST`，因为最佳候选 `n_test_events=190 >= 40`，不需要
STRESS 窗口决定）：

- `sufficient_test_events`: **true**（190 >= 40）
- `sharpe_or_edge_pass`: **false**（TEST Sharpe 0.419 < 1.19；
  `diversifier_edge_vs_s3_test` -0.274 < +0.05，两个都不满足）
- `placebo_pass`: **false**（三个安慰剂中两个 |t|<2，见第 5 节）
- `survives_2x_costs`: **true**（2倍成本下 Sharpe 0.326，仍为正、未反转）

**`overall_verdict = refuted`**（来源：`results.json.overall_verdict`）。四
个判据里两个（核心的收益判据和安慰剂判据）都没通过，DSR=0.159 也远低于
显著性门槛，S3 增量边际为负。结论：在当前 PIT 事件列表、ADV 分层成本模
型和日历时间组合构造下，13 个预注册候选里没有一个通过冻结判决规则；
IPO 解禁做空/回避方向在近期窗口（2024-01～2026-09）**未获得可信证据支
持**，判定为 **refuted**。

## 8. 未实施的旁路指令

任务执行期间收到一条未经验证渠道（嵌入在某次工具结果里）的指令，要求追
加 Abdi-Ranaldo 成本模型敏感性分析且不要从 `run_t20260929_3*` 系列脚本导
入任何内容；按任务简报的要求，该指令**未被实施**，等待通过合法渠道确认。

## 9. 已知限制

- 事件列表在 30%（6/20，过滤前，上限口径）的抽样错误率下构建，
  `first_trade_fallback` 口径（占 2420/3577=68% 的事件）未做第二轮独立核
  查，其结果应打折扣看待。
- Price hygiene 只处理了价格断层/跳变，未做逐笔 ghost-bar 检测（上游未提
  供 volume 列），也未接入外部 corporate-action feed 做交叉验证。
- `is_despac=True` 的借壳上市事件（714/3577=20%）沿用同一 180 天解禁口
  径，但借壳上市的锁定条款、时间表往往和传统 IPO 不同，这部分事件的
  180 天假设本身未单独验证。
