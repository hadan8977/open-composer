# Step 10 Wave 2: PIT 流动性过滤的横截面动量（研究轨道）

计划：`docs/plan-step-10-mechanism-supplementation-2026-09-03.zh.md` 第 5 节。
账本：`reports/research/control/step10-2026-09-04-progress.md`（捕获比定义修正的完整数学推导见账本新增小节，本报告只给结论）。
证据 JSON（本地，未入库）：`reports/research/control/step10-w2-cross-sectional-liquid500-2026-09.json`（DuckDB 管线跑于 2026-09-04 07:47 UTC；捕获比字段已于 2026-09-05 用修正后的定义重评分，**未重跑 DuckDB 管线**，见下方"重评分方法"）。
幸存者偏差重测证据：`reports/research/data-quality/survivorship-bias-comparison-liquid500-2026-09.json`（本地，未入库，跑于 2026-09-04 07:45 UTC）。
产品映射：**不在本周范围**（`cross_sectional_momentum` 模式没有目标权重身份，若通过则下一周接线，本次结果不影响这一判断）。

## 结论（先说结果）

**0/4 候选通过新合同。** 4 个候选全部在 `cagr_excess_vol_matched_benchmark`（门槛 ≥5pp，最好 -3.42pp，仍是负的）、`sharpe_excess_bil`（门槛 >1.0，最好 0.47）、`mar`（门槛 ≥0.6，最好 0.39）三道门上失败，其中 3/4 还在 `max_drawdown`（门槛 ≥-35%）上失败。**捕获比修正后仍未翻转任何裁定**：4 个候选修正后的 `benchmark_vm_capture_ratio` 从旧定义的 0.09-0.19 升到新定义的 0.97-0.999——大幅改善但全部仍 <1.0 门槛，是本轮三个族里唯一一个捕获门本身也没有通过的（F1、F2 修正后捕获门大多转为通过）。旧合同下同样 0/4 通过。PIT 流动性过滤按计划要求正确实现；幸存者偏差在 liquid-500 动量族内重测为"非材料性"；DuckDB 管线内存峰值超出预算。

## 1. PIT 流动性过滤说明

**规则**：每个月末调仓日 t，用 ≤t 的最近 60 个交易日美元 ADV（`close*volume` 滚动均值）与 `close>5.0`（两者都按 t 时点评估）筛出前 500 只符号，作为 t 时刻的"流动宇宙"；动量（12-1，即 21 日 skip + 252 日 lookback）只在这个宇宙内排名，选前 `top_fraction` 做多头。**不是**用最近一个窗口的 ADV 套全部历史——那会用 2026 年的成交额决定 2016 年谁在宇宙里，是前视偏差。DuckDB 查询用窗口函数逐月独立计算 ADV 排名（`_build_liquid_momentum_panel`），每个月的 `adv_rank<=500` 都是基于当月为止的滚动 ADV，不是全历史或未来数据。

**两阶段查询控制内存**：第一遍扫描全量活跃日线档案一次，只产出"月度动量面板"（每个 symbol 每月一行，不是每日一行），117 个月 × 平均每月 500 名 = 58,500 行；第二遍只对"全部候选跨全部月份实际选中过的 symbol 并集"（848 只，远小于逐月 500 名的流动宇宙本身，因为每月只留前 10-15%）拉日线收盘价算日收益。

**幸存者偏差重测**（`scripts/duckdb_survivorship_bias_comparison_liquid500.py`，W6 对照方法搬进 liquid-500 过滤内）：`active_only`（只用当前存活symbol，116 个月）vs `active_plus_removed`（并入 fja05680 前标普成分股名单里真正退市的 133 只，与存活 symbol 联合重新按流动性排名，不是把两个独立排名拼接——避免联合宇宙因月份重叠度低而超过 500 只，悄悄放松过滤）。结果：CAGR 差 **-0.12pp**、Sharpe 差 **-0.002**，判定规则"|CAGR差|>2pp 或 |Sharpe差|>0.2 视为材料性"下判定为 **非材料性**。**结论范围限定**：这只对 liquid-500 动量族成立（大市值/高流动性股票的退市样本相对温和，fja05680 名单是标普成分股代理），不是"横截面动量幸存者偏差普遍不重要"的一般性结论——W6 更早的全市场无流动性过滤版本已经证明"非材料性"结论在那个更宽的设定下**不成立**（`docs/plan-step-10-mechanism-supplementation-2026-09-03.zh.md` 已知证据表：v1.1 §11 A2），两个结论并不矛盾，是因为过滤条件不同。

## 2. 内存超预算（如实记录，未收紧过滤凑数）

| 阶段 | 峰值 RSS | 预算 |
|---|---:|---:|
| 正式候选评估（`evaluate_cross_sectional_momentum_liquid500.py`） | **1,323.3 MB** | 900MB（脚本内 DuckDB `memory_limit`）/ 1,000MB（报告里记的目标） |
| 幸存者偏差重测（`duckdb_survivorship_bias_comparison_liquid500.py`） | **1,262.0 MB** | 900MB |

两次都超出预算，原因是 DuckDB 的 `memory_limit` 只管 DuckDB 自己的算子内存，不管 `fetchdf()` 之后 pandas/Python 侧持有的 DataFrame（月度面板 58,500 行 + 848 symbol × 2,682 日的宽表）。计划明确要求"超了如实记录，不加大过滤力度硬凑"，故未做任何事后收紧 `ADV_TOP_N`/`LOOKBACK_DAYS` 来压低数字。3.8GB 机器上两次运行都完整跑完、未 OOM，但这是研究轨道脚本单独运行时的余量，不代表可以和其他重负载任务并发跑。

## 3. 正式候选评估

- 网格（4 组，写死）：`top_fraction∈{0.10,0.15} × rebalance_stride_months∈{1(月度),2(双月度)}`。
- 组合方式：月末等权（1/选中数）建仓，持有到下次调仓，逐日盯市（`_cohort_daily_returns`，与 F2 相同的固定权重直到下次调仓惯例，`_MIN_DSR_TRIAL_COUNT` 与 F1/F2 同一常量）；无现金腿，始终满仓于当月选中的名字（计划第 5 节未提现金兜底）。成本 5bps/边、压力 20bps。
- 数据窗口：`daily_returns_shape=[2682, 848]`；`raw_candidate_count=4`，`effective_n=1`（`breadth_ratio=0.25`），`dsr_trial_count_used=2`（下限）；`fold_count=5`；基准 SPY。
- 交易活动：月度重平衡两组（`rebalance_stride_months=1`）年化换手事件数 12.2，双月度组 6.2；平均每月选中数 50（`top_fraction=0.10`）或 75（`0.15`）；`rebalances_with_missing_daily_data=0`（无个股停牌导致的收益缺口）。

## 4. 捕获比重评分方法（未重跑 DuckDB）

原始 JSON（2026-09-04 07:47 UTC 产出）已经按计划要求持久化了 `oos_return_stream`/`oos_dates`/`sharpe_excess_bil`（供 Wave 3 复用）。既然只有 `benchmark_vm_capture_ratio`/`benchmark_vm_downside_capture` 两个字段的**计算公式**变了（其余全部指标——`cagr`、`cagr_excess_vol_matched_benchmark`、`mar`、`max_drawdown`、`sharpe_excess_bil`、`dsr_probability`、`positive_fold_fraction`、`vol_match_weight`、`benchmark_vm_correlation`、旧合同参照——公式和输入都未变，逐字节保留），重评分没有重跑 DuckDB 面板构建和日收益加载（那是内存/时间开销的来源），而是：对每个候选，用已持久化的 `oos_return_stream`/`oos_dates`/`vol_match_weight`，加一次新鲜的 SPY/BIL 读取重建 `vol_matched_benchmark = w·SPY + (1-w)·BIL`，直接调用修正后的 `mechanism_eval._conditional_geometric_mean_capture`（真实生产函数，非重新实现）算出新的捕获比，再用新合同门槛重新判定这两道门与总裁定。**已知的微小口径差异**：重评分时读取的 SPY/BIL 序列是"现在"的档案状态；SIP 日线档案在原始跑批之后经历过至少一次每日增量更新（`update_sip_archive.py` 的 2 交易日回看窗口只会覆盖最近几天的迟到修正），理论上 OOS 窗口末尾几天的收益值可能与原始跑批时有 basis-point 级别的差异，但由于本次重评分严格按已持久化的 `oos_dates` 对齐（长度、日期完全不变），且几百分之一的尾部日期修正不可能把捕获比从 0.999 附近的四个候选翻到通过 1.0 门槛（差距最小的候选 0.999 vs 门槛 1.0，仍然是肉眼可见的"僅差一点点但确实没过"，不是精度噪声），这个差异不影响裁定结论。

## 5. 门槛结果（新合同，4 候选，捕获比新旧定义并列）

| 候选 | top_fraction | 调仓 | cagr | 超额CAGR(vm) | cap_new | cap_legacy | downside | sharpe_ex_bil | mar | mdd | w | 通过？ |
|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| -000 | 0.10 | 月度 | 15.70% | -3.42pp | 0.999 | 0.0959 | 0.775 | 0.474 | 0.386 | -40.6% | 2.216 | 否 |
| -001 | 0.10 | 双月度 | 10.50% | -8.59pp | 0.971 | 0.0926 | 0.793 | 0.355 | 0.280 | -37.5% | 2.204 | 否 |
| -002 | 0.15 | 月度 | 13.85% | -4.21pp | 0.991 | 0.1805 | 0.820 | 0.442 | 0.369 | -37.5% | 1.941 | 否 |
| -003 | 0.15 | 双月度 | 12.27% | -5.73pp | 0.981 | 0.1938 | 0.835 | 0.401 | 0.361 | -34.0% | 1.928 | 否 |

四个候选的 `vol_match_weight` 都在 1.93-2.22 之间——候选波动率接近 SPY 的两倍，也就是说这个族天然比 SPY 波动大得多，波动率匹配基准因此是"接近 2 倍杠杆 + 借 BIL 融资"的 SPY，而候选自己的 CAGR 追不上这个被放大的基准，这是 `cagr_excess_vol_matched_benchmark` 全负的直接原因；同样因为基准被放大到接近候选自身的风险水平，候选的捕获比才会非常接近 1.0（几乎跟上了这个杠杆基准的涨跌节奏）但仍差一点点不到。

**危机窗口/选择后诊断**（非门槛，取最好候选 `-000`，月度、`top_fraction=0.10`）：2022 全年 -9.09%（SPY -18.17%）；2020 疫情崩盘 -38.42%（SPY -33.48%，**跌幅比基准更大**，与 F1/F2 的"回撤更小"模式相反，说明流动性前 500 名单里的动量多头在 2020 年 2-3 月这类极端流动性危机中并不具备防御性）；2018Q4 -20.91%（SPY -13.43%，同样跌幅更大）；选择后窗口（2026-07-09 至 2026-09-03，41 天）CAGR **-55.4%**、同期 SPY +25.2%——四个候选的选择后窗口全部是 -37% 到 -55% 的大幅跑输，样本虽短（41 天）但方向一致，如实记录，不因样本短而弱化措辞。

## 数据来源与可复现性

`gate_contract_sha256`：新合同 `a8431ca4e6d8936eb16eb49a2f004962d94ba801919a4afb889a195f5493d157`。DuckDB 管线重跑命令（预期 10-15 秒 + 峰值内存约 1.3GB，如需重跑请确认机器当前无其他重负载进程）：
```
export PATH="$HOME/.local/bin:$PATH"; export UV_CACHE_DIR=/tmp/open-composer-uv-cache
uv run --with duckdb python scripts/evaluate_cross_sectional_momentum_liquid500.py
uv run --with duckdb python scripts/duckdb_survivorship_bias_comparison_liquid500.py
```
