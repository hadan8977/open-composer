# Step 10 机制补充执行计划（2026-09-03）

日期：`2026-09-03`
计划版本：`1.1`（1.0 = Sonnet 原稿；1.1 = 追加 §11 Fable 5.1 审阅修订）
基线提交：`70220dd`（goal-first W0-W9 全部完成后的状态）
执行者：无上下文执行者
状态：已审阅（Fable 5.1，2026-09-03）。执行前必须先落实 §11.3 的必改项；§11 与正文冲突时以 §11 为准
截止：`2026-09-11`（下周五）前必须有一个候选连接到新模拟盘账号（观察模式或下单模式，取决于晋级证据）

---

## 0. 给执行者的前置说明

本文件自包含，但建议先读三份文档建立语境（不要重新调研，直接读结论）：
`docs/conclusion-goal-first-2026-09-03.zh.md`（上周结论）、
`docs/capability-gap-analysis-2026-09-02.zh.md`（能力差距分析）、
`reports/research/control/goal-first-2026-09-02-progress.md`（逐 Wave 证据）。

**环境准备**（每条 shell 命令都要）：
```bash
export PATH="$HOME/.local/bin:$PATH"
export UV_CACHE_DIR=/tmp/open-composer-uv-cache
```
**每次代码改动后必须跑**：
```bash
uv run ruff format . && uv run ruff check . && uv run pytest -q
```
产品面改动还要 `uv run oc repo check --strict` 和 `make verify`。

**机器**：6 核 / 3.8GB 内存。分钟线抓取（2016-2022，`data/sip-hist/`）预计本周末前完成，完成后不再有后台重负载进程，本计划的内存预算可以按"独占"计算，但仍不要用 `pytest -n auto`（上限 `-n 2`）。

**既有失败基线**：`tests/test_mom_breadth_qd_r1.py` 11 个失败，其余为零。回归判断标准不变。

**2026-09-03 用户决策，已执行，不要重做**：
- 冠军路由 `nasdaq_tqqq_post_drawdown_reentry_router_delayed30_offensive_paper_auto_candidate` 已通过 `oc strategy disable` 正式退役（`strategy_specs/retired/`，`lifecycle: retired`）。
- 每日 paper cycle 的 cron 已移除（原来指向已退役的 spec）；SIP 新鲜度检查 cron 保留。
- 滞留的 10,235 股 TQQQ 与 kill switch **不处理**——旧模拟盘账号本身会被放弃，新候选就绪后连接一个新账号。
- OPG 限价单已由用户确认在新账号上可用，不需要再验证。
- `ALPACA_DATA_FEED` 从 `iex` 改为 `sip`：**待办，`.env` 受权限保护，执行者需要用户或有权限的会话手动改这一行**。
- `strategy_specs/active/nasdaq_tqqq_fixed_etf_router_daily_iter11_exposure_search_paper_auto_candidate.yaml`：**本轮未评估、未决定**，仍是 `lifecycle: active` + `paper_auto`。不在本计划范围内，但执行者应该知道它的存在——如果第 4 节的产品修复完成后有余力，值得用同样的方法论重新验证一遍（不在本计划的 Done 定义里）。

---

## 1. 目标与判定标准

用户原话："下周要完成目标"，且把"往哪个方向投入精力"的判断权交给执行者（"你认为可以实现目标就可以做"）。

**目标的可操作定义**：在 `2026-09-11` 前，至少有一个策略候选：
1. 在本周已验证的方法论下（SIP 干净数据、预注册门槛、有效 N 聚类、无调参）拿到 `promotion_eligible=True` 的裁定，或者拿到一个诚实的、有具体后续动作的"未达标但值得继续"判断（不是含糊的"再试试"）；
2. 走完产品主路径（`oc strategy evidence`/`promotion-report`/`harness plan`/`paper readiness`）到只剩用户决策类 blocker；
3. 接入新模拟盘账号，进入 `observation_only` 或更高的执行状态。

**如果三个机制方向都是干净负结果**：诚实报告，不强行包装。但本计划的 Wave 0（产品修复）和方法论基础设施在任何结果下都是有价值的交付物，不因为机制本身失败而"白做"。

---

## 2. 为什么选这三个方向（不是随便选的）

延续本项目"广度优先、经济上独立的机制"原则（`AGENTS.md`），三个方向彼此的收益来源完全不同：

| 方向 | 收益来源 | 与本周已测试机制的关系 |
|---|---|---|
| Wave 2：日内出场规则变体 | 同一入场信号，不同的持仓管理 | 复用 W4 的入场规则和全部基础设施，**出场逻辑是全新机制**，不是同一噪声带的更多参数 |
| Wave 3：横截面动量（流动性过滤版） | 跨标的相对强弱，与择时无关 | 复用 W6 的管线，修复内存问题后作为正式候选而不只是可行性探针 |
| Wave 4（备选，视时间而定）：波动率管理暴露 | 风险溢价的波动率择时（Moreira & Muir 2017），与前两者都不相关 | 全新机制，用现有日线数据即可，不需要分钟线或横截面面板 |

三者中至少两个必须真正跑完评估（Wave 2 + Wave 3 是硬性要求，Wave 4 是时间允许时的第三个机会）。

---

## 3. Wave 0：轻量迭代路径（最高优先级，其他一切的前提）

### 3.1 为什么这是第一优先级

W5 发现：任何新迭代（2026-08-15 后创建）想跑 `factor_lab`/`promotion-report`/ML 训练，`iteration_dossier.py` 的 `_campaign_requirement_blockers` 都强制要求绑定一份完整的 campaign 合同（参考 `reports/research/campaigns/mom_independent_mechanisms_qd_r2/`，约 388 行：假设树、分支配额、候选蓝图、可见性分区、暴露预算、探索策略、QD 归档策略、统计族策略）。**不做这个修复，Wave 2/3/4 的每一个候选都要重复付出这个前置成本，本周的截止日期基本不可能达成。**

### 3.2 设计原则（不能削弱真正的 breadth campaign 治理）

新增豁免必须满足**全部**以下结构性条件才生效，任何一个条件不满足就退回原有的强制要求；不是自我声明就能免检：

1. 显式声明字段 `search_space.json` 新增 `"single_mechanism_no_campaign_attestation": true`（默认不存在/false，必须显式打开）。
2. `paths` 数组长度恰好为 1（一个机制族，不是多分支）。
3. `total_candidate_budget <= 24`（复用已有的单路径候选数上限，不新增一个自由裁量的数字）。
4. `campaign_contract_path`、`campaign_id`、`campaign_contract_sha256` 三个字段均为空/未声明（不能同时又声明属于某个 campaign 又要走轻量豁免）。
5. `iter_id` 不在 `LEGACY_UNBOUND_ITERATION_IDS` 里（那是另一套迁移历史机制，不要混用）。

### 3.3 要改的代码

`open_composer/research/iteration_dossier.py`：

- 在 `_campaign_requirement_blockers` 函数签名里新增参数 `single_mechanism_attestation: bool`、`path_count: int`、`total_candidate_budget: int | None`、`campaign_fields_declared: bool`（调用点 `_search_space_blockers` 已经解析出这些值，原样传入即可，不要在函数内部重新解析 payload）。
- 新增判定：
  ```python
  lightweight_exempt = (
      single_mechanism_attestation
      and path_count == 1
      and total_candidate_budget is not None
      and total_candidate_budget <= 24
      and not campaign_fields_declared
  )
  if not legacy_unbound and not campaign_bound and not lightweight_exempt:
      blocked.append("campaign_contract_required_for_new_iteration")
  ```
- 在返回的校验结果里新增一个**不阻断**的 `warnings` 条目 `f"lightweight_single_mechanism_exemption_used"`，当 `lightweight_exempt` 为真时写入——这样即使不阻断,后续审计仍然看得出这条迭代走的是豁免路径,不是普通 campaign 路径。
- `IterationDossierValidation`（或其等价的结果对象）需要能携带这个 warning；如果现有结构没有 warnings 通道用于此类非阻断记录，检查 `validate_iteration_dossier` 现有的 `warnings` 列表字段是否已支持（W5 的校验结果里出现过 `"warnings": []`，说明已有该字段，直接复用）。

### 3.4 必须写的测试（对抗性，不是只测"能通过"）

新增或扩展 `tests/test_iteration_dossier.py`：

1. **正例**：单路径、`total_candidate_budget=18`、attestation=true、无 campaign 字段 → `pre-backtest` 校验通过（不再出现 `campaign_contract_required_for_new_iteration`），且 warnings 里出现豁免记录。
2. **反例 1**：attestation=true 但 `paths` 有 2 个 → 仍然要求 campaign 合同（多分支不能豁免）。
3. **反例 2**：attestation=true 但 `total_candidate_budget=30` → 仍然要求 campaign 合同（超过 24 上限不能豁免）。
4. **反例 3**：attestation=true 但同时声明了 `campaign_contract_path` → 仍然要求 campaign 合同（不能既豁免又挂靠 campaign）。
5. **反例 4**（防止"改小 budget 数字但实际候选更多"的作弊）：`total_candidate_budget=10` 但 `candidate_manifest_path` 指向的实际候选清单有 15 条 → 仍然阻断（复用已有的 `_candidate_manifest_blockers` 里 `expected_total` 一致性检查，确认它在豁免路径下依然生效，不要因为加了豁免分支就意外跳过这个检查）。
6. **回归**：`tests/test_iteration_dossier.py` 现有全部约 3024 行测试必须保持通过，不改动任何既有测试的期望值。

### 3.5 验收标准

- 上述 6 类测试全部通过。
- `uv run oc research iteration validate goal_first_w5_qqq_momentum --stage pre-backtest`（W5 留下的真实迭代档案，6 组合、单路径、无 campaign）重新跑一遍：**必须从 `campaign_contract_required_for_new_iteration` 变为 `status=ok`**（补充 `single_mechanism_no_campaign_attestation: true` 到它的 `search-space.json` 后）——这是用真实产物验证修复有效，不是只看单元测试。
- `oc repo check --strict` 通过；全量测试仍然是"11 个失败，全部且仅来自 `test_mom_breadth_qd_r1.py`"。

---

## 4. Wave 2：日内出场规则变体

### 4.1 机制设计

复用 `open_composer/research/kernel/mechanisms/intraday_momentum_etf.py` 的入场规则（波动率缩放噪声带突破），**替换出场逻辑**为 Maróy（SSRN 5095349）讨论的几种出场方式的一个有界子集：

- 固定盈利目标（noise_band 的 N 倍，N∈{1.0, 1.5, 2.0}）。
- 时间止损（持仓超过 M 个 5 分钟 bar 后无论盈亏平仓，M∈{6, 12}，对应 30/60 分钟）。
- 两者组合（先到者退出）。

新建 `open_composer/research/kernel/mechanisms/intraday_momentum_etf_exit_variants.py`（不要改动已有的 `intraday_momentum_etf.py`，那是 W4 已有证据的机制，新出场规则是新机制，用新文件），复用同一个 `daily_intraday_momentum_returns` 里的入场/噪声带计算逻辑（提取成共享的 `_entry_signal`/`_noise_band` 辅助函数供两个机制模块 import，不要复制粘贴入场逻辑）。

参数网格：`profit_target_multiplier {1.0,1.5,2.0} × time_stop_bars {6,12,None}` = 9 组合（不含 W4 已测的"止损/持有到收盘"两种，那两种已有证据，不重复计入这轮的候选数）。

### 4.2 评估

新建 `scripts/search_intraday_momentum_exit_variants.py`，模板照抄 `scripts/search_intraday_momentum_etf.py`（数据加载、按年分块、`daily_returns_on_naive_dates` 共享基准函数、两遍有效 N 聚类、内存/时间预算记录），只换机制模块和参数空间。SPY + QQQ 各跑一遍，`fold_count=3`（同样受限于 3.5 年分钟数据）。

### 4.3 验收标准

- 峰值 RSS 记录，预期与 W4 同量级（<700MB），如果明显更高需要排查原因再继续。
- 产出 `reports/research/control/step10-w2-intraday-exit-variants-2026-09.{json,md}`，格式仿照 `goal-first-w4-intraday-momentum-2026-09.md`。
- **无论结果正负都要如实记录**，不因为要赶截止日期就放宽解读。

---

## 5. Wave 3：横截面动量（流动性过滤版，正式候选）

### 5.1 修复内存问题

W6 诊断：`data/sip/daily/*/*.parquet` 全市场窗口函数扫描是内存主因。修复思路：**先按流动性缩小宇宙，再做窗口函数**，而不是先扫全市场再筛选。

`scripts/duckdb_cross_sectional_feasibility.py` 里 `query_c_twelve_one_momentum` 的 SQL 改为两阶段：

1. 先算一份"最近 60 个交易日平均美元成交量"排名表（`AVG(close*volume) OVER (PARTITION BY symbol ORDER BY timestamp ROWS BETWEEN 59 PRECEDING AND CURRENT ROW)`，只在最近的窗口算一次，不需要对全部历史都算），取 ADV 排名前 500 的 symbol 集合。
2. 用这 500 个 symbol 的集合过滤 `raw` CTE（`WHERE symbol IN (SELECT symbol FROM top_500_by_adv)`），再做 `LAG() OVER (PARTITION BY symbol ...)` 窗口函数——这一步的输入行数从全市场降到约 500 个标的的历史,窗口函数状态大幅缩小。

这不是本计划新写的探索脚本,是 W6 已有脚本的一个修复,复用其余全部逻辑（月度分组用 `to_period("M")`,已经在 W6 修好）。

### 5.2 正式候选评估

新建 `scripts/evaluate_cross_sectional_momentum_liquid500.py`：用上述流动性过滤后的面板,构造月度调仓的 12-1 动量组合日收益序列（不是月度收益,要转成日收益才能喂进 `open_composer.research.kernel.mechanism_eval` 的 `Mechanism`/`rolling_origin_folds` 管线——在调仓日之间用等权持仓的每日盯市收益,不是只有月末一个点）。

**这一步是本计划技术难度最高的部分**：需要把"月度选股、日度盯市"的组合构造转成一个逐日收益序列，供现有 P1b 管线的 `fold_count` 按日历年分折。参数网格：`top_decile_fraction {0.1, 0.15} × rebalance_frequency {monthly, bimonthly}` = 4 组合（bounded,不是新的自由搜索）。

用**同一份** `config/promotion/kernel-paper-tier-gates.json` 门槛评估（不新建一份门槛合同——如果这份月度调仓的策略在"QQQ/TQQQ 相对捕获率"这类日频路由设计的门槛上表现奇怪,如实记录这个不匹配,不要为了让它通过就换一套更宽松的门槛）。

### 5.3 验收标准

- 峰值内存 < 1GB（这是本 Wave 存在的理由，如果修复后还是超预算，如实记录"流动性过滤后仍然超预算"这个结果，不要继续加大过滤力度直到勉强达标）。
- 产出 `reports/research/control/step10-w3-cross-sectional-momentum-liquid500-2026-09.{json,md}`。

---

## 6. Wave 4（备选，时间允许时做）：波动率管理暴露

仅在 Wave 2 与 Wave 3 都在计划时间过半（约 `2026-09-09`）之前完成且都是负结果时启动，作为第三次机会,而不是无论如何都要做的固定任务。

机制：QQQ 暴露按已实现波动率的倒数缩放（Moreira & Muir 2017 风格),月度或周度重新计算目标暴露,现金腿放 BIL。用日线数据即可,不需要分钟线,复用 `router_common.py` 里已有的 `volatility_scale`/`target_volatility_annual_pct` 相关逻辑（**先检查这些是否已经是可直接复用的函数,不要重新实现波动率目标计算**——W3 的教训是"另起炉灶前先查仓库已有实现"）。

---

## 7. Wave 5：晋级与接入（仅对通过门槛的候选执行）

对 Wave 2/3/4 中任何一个拿到 `promotion_eligible=True` 的候选：

1. 用 Wave 0 的轻量路径写一份真实的迭代档案（外部简报可以复用本周 W5/W7 已经写好的 8+4 张 source card,加上该机制专属的 1-2 篇补充文献）。
2. 手工构造对应的 `StrategySpec`（参考 `strategy_specs/drafts/sip_smoke_qqq_daily.yaml` 的写法,`data.path` 指向 `data/sip/daily`,`lifecycle: draft`）。
3. 依次跑 `oc strategy evidence` → `oc strategy promotion-report` → `oc harness plan` → `oc harness verify` → `oc paper readiness`,记录每一步的 blocker,像 W5 一样不绕过。
4. 走到只剩"需要用户批准 lifecycle/连接新账号"这一类 blocker 为止。**不在本计划范围内自行把 lifecycle 改成 active 或提交任何模拟盘订单**——这是用户决策,按本项目一贯规则,晋级到 paper 需要用户批准。

对全部候选都未通过的情况：在 `reports/research/control/strategy-iteration-progress-2026-07-01.md` 追加一节诚实记录三个机制的负结果,给出下一步方向的建议,不强行包装。

---

## 8. 时间线（供执行者自行把握节奏,不是强制的逐日检查点）

| 日期 | 内容 |
|---|---|
| 09-03/04 | Wave 0（轻量路径修复 + 对抗性测试） |
| 09-05/06 | Wave 2（出场规则变体）与 Wave 3（横截面流动性修复）并行推进 |
| 09-07/08 | Wave 2/3 评估结果出炉；视进度决定是否启动 Wave 4 |
| 09-09/10 | 对通过门槛的候选执行 Wave 5；对全负结果的情况写诚实总结 |
| 09-11 | 截止：至少一个候选连接新模拟盘账号,或一份诚实的"三个机制都不通过"总结 + 下一步建议 |

---

## 9. 禁止事项

1. 不为了赶截止日期而放松 `config/promotion/kernel-paper-tier-gates.json` 的任何门槛,不新建一份更宽松的门槛合同来替代它。
2. 不在 Wave 0 的豁免机制里引入任何"自我声明就能绕过"的逻辑——必须有结构性校验（路径数、候选数上限、campaign 字段互斥）配合声明字段,且要有对抗性测试证明绕不过去。
3. 不改动 `tests/test_mom_breadth_qd_r1.py`,不碰 `mom_breadth_*` 目录,不碰 §0 提到的其他历史禁改文件（`capabilities/registry.yaml`、`market_calendar.py`、`strategy_spec.py`、`campaign_statistics.py`、`quality_diversity.py`、`storage.py`、`pyproject.toml`、`uv.lock`）。
4. 不自行把任何候选的 `lifecycle` 改成 `active`,不提交任何模拟盘订单——这两者都是用户决策。
5. 不删除或修改 `strategy_specs/retired/nasdaq_tqqq_post_drawdown_reentry_router_delayed30_offensive_paper_auto_candidate.yaml`（已正确退役,保留作为历史证据）。
6. 不重新评估 `nasdaq_tqqq_fixed_etf_router_daily_iter11_exposure_search_paper_auto_candidate`（超出本计划范围,除非用户另行要求）。
7. `pytest` 并行度上限 `-n 2`,不用 `-n auto`。

---

## 10. 完成的定义

1. Wave 0 的 6 类测试全部通过,`goal_first_w5_qqq_momentum` 真实迭代档案从阻断变为 `status=ok`。
2. Wave 2 与 Wave 3 都有完整的评估产物（无论结果正负）。
3. 如果有候选 `promotion_eligible=True`：走完 Wave 5 到只剩用户决策类 blocker,新模拟盘账号已连接（观察模式）。
4. 如果没有候选通过：`strategy-iteration-progress-2026-07-01.md` 有诚实的负结果记录和下一步建议。
5. `uv run pytest -q` 失败数仍为 11 且全部来自 `test_mom_breadth_qd_r1.py`；`oc repo check --strict` 为 `status=ok`；`ruff format .`/`ruff check .` 全绿。
6. 每个 Wave 独立 commit。

---

## 11. Fable 5.1 审阅修订（2026-09-03）

本节是 Fable 5.1 对上周工作（W0-W9）与本计划的审阅结论。**与正文冲突时以本节为准**；正文保留 Sonnet 原文以便对照。审阅中核实过的事实列在 11.6，执行者直接引用，不要重做。

### 11.1 一句话结论

运营闭环、SIP 接入、重采样器、机制评估管线这些基础设施是真实且经过测试的，冠军路由退役的判断成立。但三项研究结论被高估（11.2），计划本身有两个结构性问题会让 Wave 2/3 在开跑之前就注定失败（11.3 的 R1、R4），执行前必须先改。

### 11.2 对 W0-W9 的核查

**可信、可直接复用的部分**：SIP 三条数据路径接入（`oc backtest` 全链路验证）；`resample.py`（10 个测试）；`daily_returns_on_naive_dates`；`capture_returns` 打通；`check_sip_freshness.py --notify-on-stale`；`run_daily_paper_cycle.py` 的 400 天回看修复；W5 对产品阻断点的定位——`_campaign_requirement_blockers` 是唯一卡点，调用链 `require_iteration_execution_gate → validate_iteration_dossier(stage="pre-backtest") → _search_space_blockers → _campaign_contract_blockers → _campaign_requirement_blockers` 已核实，`promotion-report`/`factor_lab` 走的就是这条链。

**三项被高估的结论**：

**A1. W4 "单 ETF 日内动量干净负结果"测的不是论文的规则。** 机制的噪声带 = 倍数 × 前 14 个交易日**全日**高低价差的均值；论文（Zarattini/Aziz/Barbon）的噪声带是**分时**的：σ_t = 前 14 日在同一时刻 |close_t/open − 1| 的均值，早盘窄、尾盘宽，且上界锚定在 max(开盘价, 前收盘价)。审阅探针（QQQ，2024-12 至 2025-12，5 分钟 RTH bar）：

| 噪声带 | 中位宽度（占开盘价） | 2025 年触发入场的交易日占比 |
|---|---:|---:|
| 机制 ×0.5 | 0.65% | 35.2% |
| 机制 ×1.0 | 1.30% | 7.8% |
| 机制 ×1.5 | 1.95% | 2.3% |
| 论文 σ_t，10:00 | 0.30% | — |
| 论文 σ_t，11:30 | 0.48% | — |
| 论文 σ_t，15:30 | 0.67% | — |
| 论文口径入场（30 分钟检查，只做多） | — | 29.4% |

18 个网格点里 12 个（×1.0、×1.5）一年只交易 6-20 天，这些格子的"没有信号"实际上是"没有交易"；W4 报告里最优候选的 QQQ 上行捕获 0.001-0.012 正是这个现象。×0.5 的 6 个格子接近论文尾盘带宽，但仍是论文早盘带宽的 2 倍，而论文的收益集中在早盘突破。此外机制只做多（论文多空双向）、无波动率目标（论文有），W4 的 JSON 也没有记录每个候选的交易次数，所以"无信号"和"无交易"无法区分。**结论**：W4 是对"一个比论文严格得多的规则"的负结果，不是对论文机制的负结果；Wave 2 若沿用这个入场规则，会再得到一个无信息量的负结果（见 R2）。探针里论文口径入场 + 持有到收盘在 2025 年的粗算（无止损、无波动率目标、单年）Sharpe 0.40——这不是信号证据，只说明入场规则的差异在结果上是实质性的。

**A2. W6 "幸存者偏差对动量不构成材料性影响"不是这次试验能证明的。** 对照组是全市场 ACTIVE 宇宙（每月约 12,479 只）加 133 只真正退市的前标普 500 成分股——补进去的名字只占宇宙的 1%，前十分位本身约 1,250 只，133 只无论有没有偏差都不可能撼动汇总数字。而这个 ACTIVE 宇宙是按**今天的**活跃列表抓的，2016 年以来所有退市（每年数百只：破产、SPAC 清算、被收购）全部缺失，远不止 133 只。"多头动量结构性回避输家"这个经济学论证本身成立且有文献支持，但它是论证不是测量。Wave 3 正文把它当成已定论（"幸存者偏差已确认非材料性"）是不对的，见 R4 的补救。

**A3. W3 "8 门过 7"读起来比实际强。** 2022-2026 的拼接窗口相对于原始选择是**样本内**（参数是在 IEX 数据上从 961 个候选里选出来的，数据截至 2026-05），`raw_candidate_count=1` 意味着前推重选是空操作，真正的样本外只有 2026-07-09 之后的 37 个交易日（年化 -58.6%）。DSR 0.5006 是用 32 这个替代试验数算的，用诚实的试验数会再挂一门。退役结论正确，只是"7/8"这个表述不要再被引用为"差一点就行"。

### 11.3 执行前必改项

**R1. 门槛合同的基准族错配（用户决策；执行者不得在看到结果后再选）。**

`config/promotion/kernel-paper-tier-gates.json` 是为 TQQQ 杠杆路由族校准的（它自己的 `rationale` 写明替换的是 TQQQ 捕获门槛）。其中 `cagr_excess_qqq ≥ 5pp` 意味着候选 CAGR 必须超过 QQQ 5 个百分点：

| 基准 | 2016-01..2026-08 CAGR / Sharpe-ex-BIL | 2024-01..2026-08 CAGR / Sharpe-ex-BIL |
|---|---:|---:|
| QQQ | 20.2% / 0.84 | 24.2% / 0.93 |
| SPY | 15.2% / 0.77 | 21.3% / 1.03 |

一个不加杠杆、只做多的横截面股票组合（Wave 3）或隔夜空仓的日内规则（Wave 2）不可能做到 25-29% CAGR；`sharpe_excess_bil > 1.0` 也高于 QQQ 自己十年的 0.84。正文 5.2 "用同一份门槛、如实记录不匹配"等于预先宣布 Wave 2/3 全部失败，这周就白跑了。`AGENTS.md` 要求"晋级必须检查基准族"，`gate_contract.py` 的预注册机制就是为此设计的——正确做法不是放松现有合同，而是**在 Wave 0 里、任何 Wave 2/3 结果出现之前**，为非杠杆机制族预注册一份基准族对应的合同。两个选项：

- **选项 A（推荐）**：新建 `config/promotion/unlevered-family-paper-tier-gates.json`（独立 commit，先于任何评估运行，遵守现有合同自己写的"改数字必须单独 commit 且先于运行"规则）。保留 `sharpe_excess_bil > 1.0`、`dsr ≥ 0.5`、`max_drawdown ≥ -0.65`、`mar ≥ 0.6`、`positive_fold_fraction ≥ 0.6` 不变；把 `cagr_excess_qqq` 换成"相对本族基准的超额 CAGR ≥ 5pp"，捕获率门槛也换成相对本族基准。族基准：单 ETF 日内族 = 同标的买入持有；横截面 liquid-500 族 = SPY 买入持有（或等权 liquid-500 宇宙，二选一并写死）。`mechanism_eval.evaluate_candidate` 目前把 QQQ/TQQQ/BIL 写死为基准，需要加一个 `benchmark_returns` 参数（默认 QQQ，保证既有测试全绿）。
- **选项 B**：所有机制都保留 QQQ 相对门槛，但每个机制都必须预注册一个波动率目标叠加层（目标 = QQQ 滚动已实现波动率，杠杆上限 2x，融资成本按 BIL + 利差），这样超额 QQQ 才是同类比较——日内动量论文自己就是这么做的（目标日波动 2%，杠杆上限 4x）。工作量更大，而且把机制变成了杠杆产品。

两个选项都合规；**唯一不可接受的是维持正文原样**。审阅建议：A 必做；B 只在 Wave 2 有余力时作为附加视图；两者都必须在开跑前 commit。

**R2. Wave 2 先把入场规则对齐论文，再变出场规则，并记录交易频率。**

- 在新模块里实现论文口径的噪声带：σ_t(d) = 前 `lookback_sessions` 个交易日在同一 bar 时刻 |close/open_d' − 1| 的均值；上界 = max(open_d, close_{d−1}) × (1 + σ_t)；每个 5 分钟 bar 收盘检查（或论文的 30 分钟节奏，二选一并预注册）。只做多沿用项目惯例，但要在报告里写明"论文的空头腿未测试"是局限而不是证据。
- 出场变体网格改为：{持有到收盘, 边界回落止损（论文原版止损）, 盈利目标 ×{1.0,1.5,2.0}, 时间止损 {6,12} bar}，总数 ≤ 24 并预注册；另外保留 W4 带宽定义的 ×0.5 格子作为对照，让与 W4 的比较是显式的。
- 每个候选必须输出：在场交易日数与占比、年均交易次数、平均持仓 bar 数、单笔平均收益。W4 的 JSON 没有这些，所以才无法区分"无信号"和"无交易"。

**R3. Wave 2 用全部 10.5 年分钟线。** `data/sip-hist/minute`（2016-2022）按当前速率（约 4.3 个分片/分钟，2019 年 225/1118 于 09-03 08:00 UTC）预计 **2026-09-04 约 00:30 UTC** 抓完，不是"周末"。`load_sip_bars` 接受任意 `root`，读取不依赖 `_LAYOUT.json`（那只是抓取端的续写守卫），脚本里对同一标的分别从两个 root 读再拼接即可；**不要合并目录**。检查 2022-12-30 / 2023-01-03 边界无重复会话。`fold_count` 用 5，并像 W3 一样报告 `CRISIS_WINDOWS`（2018Q4、2020 疫情、2022 全年）。正文 4.2 的"fold_count=3、3.5 年"作废。

**R4. Wave 3 的流动性过滤必须按时点计算；幸存者偏差在 liquid-500 内重测。**

- 正文 5.1 第 1 步"只在最近的窗口算一次"是前视偏差：用 2026 年的成交额挑 2016 年的宇宙，等于按"后来的赢家"选股，比 W6 想测的幸存者偏差更严重。改为：对每个月末调仓日 t，用 ≤ t 的最近 60 个交易日算 ADV，取前 500（`close > 5` 的价格过滤也按 t 时点）；动量面板只对 ∪_t universe(t) 这个并集里的标的算 LAG（并集通常一两千只，内存收益仍在），选股时只在 universe(t) 内取前十分位。
- 在 liquid-500 宇宙内重跑 `scripts/duckdb_survivorship_bias_comparison.py` 的对照（fja05680 的前标普成分股名单对大市值宇宙是合理代理，对全市场不是），结论只能写成"对 liquid-500 动量族"。

**R5. Wave 0 的四个设计缺口。**

- (a) 豁免条件必须加上 `candidate_manifest_path` 已声明且文件存在。现在的代码里候选清单对未绑定 campaign 的迭代是可选的（只在 campaign 绑定时强制，`campaign_contract_child_candidate_manifest_missing`），轻量豁免如果不要求它，就违反了 `CLAUDE.md` "每个参数化候选都要在回测前预注册到机器可读清单"。注意耦合：`_search_space_blockers` 一旦看到 `candidate_manifest_path`，就同时要求 `cost_table_path` 和 `data_feasibility_path`（后者要有 `q2_diagnostic_execution_authorized`、`workflow_passed`、sha256 等字段）。执行者必须在 Wave 0 里显式决定轻量路径是否也要这两个文件、要的话怎么产出（W5 的档案里两者都是空串），不要到周中才发现。
- (b) 哈希锁：`iteration_dossier.py` 当前 SHA-256（`e37b3125…`）与 `reports/research/campaigns/mom_breadth_qd_r1/development-evaluation-attempt.json` 里锁定的值**相同**，改它会让这个已封存活动记录到实现漂移。审阅核实：这把锁已经被 `open_composer/research/campaign.py` 和 `tests/test_mom_breadth_qd_r1.py` 两个文件的漂移破坏；唯一拿真实仓库与记录值比对的测试（`test_recovery_preregistration_state_accepts_exact_repository_evidence_without_market_reads`）已经在 11 个基线失败里；另一个用真实仓库根的测试（`test_recovery_revalidates_mutable_preregistration_semantics`）自己构造 attempt，不含实现哈希。所以改动**预期不会新增失败**——但审阅未能实证（临时改文件的探针被拒），执行者改完必须跑 `tests/test_mom_breadth_qd_r1.py`，失败数超过 11 就停下来汇报，不要去动锁文件或测试。
- (c) 正文 3.3 的调用链描述不准：`_campaign_requirement_blockers` 是经 `_campaign_contract_blockers(payload, root, stage)` 调用的，拿到的是整个 payload，不是解析后的值。最小改动是在 `_campaign_requirement_blockers` 内部从 payload 读 `paths`、`total_candidate_budget`、三个 campaign 字段和 attestation 字段；要不要穿透传参是执行者的选择，不是正确性问题。
- (d) 正例测试要覆盖 Wave 5 真正用到的入口：`require_iteration_execution_gate(spec, root, enforce_unbound_design=True, require_registered_iteration=True)`（`promotion.py` 与 `factor_lab.py` 的调用方式），不只是 `oc research iteration validate --stage pre-backtest`。今天两者是同一个 stage，但测试要钉住实际入口。

### 11.4 建议改（不阻断执行）

- **iter11 的处置**（用户决策）：`strategy_specs/active/nasdaq_tqqq_fixed_etf_router_daily_iter11_exposure_search_paper_auto_candidate.yaml` 仍是 `lifecycle: active` + `paper_auto` + `alpaca_paper`，它的证据和冠军路由建在同一份有缺陷的 IEX 缓存上（commit `51ebc77` 已追踪到两条活跃策略），现在也没有任何 cron 在跑它。而且 `strategy_specs/retired/` 里已经有一份同名的旧 schema 副本——同一个策略名同时存在于两个生命周期目录。建议直接 `oc strategy disable` 退役；执行前先确认该命令遇到目标文件已存在时是覆盖还是报错。这两个目录都不在 git 里，属于本机运行时状态。
- W3 报告的表述：把"7 of 8 gates pass"补一句"2022-2026 窗口相对原始选择是样本内"。
- 时间线：R1/R5 让 Wave 0 多约半天，R2/R3 让 Wave 2 多约半天到一天；Wave 4 基本不会有时间，按备选处理即可。09-11 截止对 Wave 0/2/3/5 仍可行，前提是 09-04 开工。

### 11.5 仍未解决、需要用户的事项

1. R1 选 A 还是 B（或都要）。
2. iter11 退役还是重验。
3. `.env` 里 `ALPACA_DATA_FEED=iex` → `sip`（权限保护，执行者改不了）。
4. SIP 日线增量续抓的布局冲突：日线档案已经比分钟线档案晚一个交易日，新鲜度 cron 会持续告警；Wave 5 接入模拟盘前必须有一份当前的日线档案，约 35 分钟重抓。
5. Telegram bot token（告警送达）。
6. 预期管理：如果 R1 维持 QQQ 相对门槛且不做波动率目标，09-11 的诚实结果大概率是"三个有据可查的负结果 + 基础设施"，不是接入模拟盘的候选。这一点现在决定，不要等到 09-10。

### 11.6 审阅核实过的事实（执行者直接引用）

- 分钟线抓取：进程在跑（watchdog + fetcher），`data/sip-hist/minute/` 2016-2018 各 13,416 分片完成，2019 进行中；Drive 推送任务 `sip-daily-push`（每日）、`sip-minute-push`、`sip-hist-minute-push`（每小时）最近一次均 success。
- QQQ/SPY 基准数字见 R1 表，来源 `daily_returns_on_naive_dates` 于 SIP 日线档案。
- A1 的探针是审阅时的临时脚本（`/tmp/w4_probe.py`，未入库）；Wave 2 按 R2 输出交易频率后即可复现同类数字，不需要恢复这个脚本。
- 冠军路由退役、每日 cron 移除、OPG 结论更新：已核实生效（`strategy_specs/retired/` 存在该文件；`crontab -l` 只剩 22:30 UTC 的新鲜度检查）。
