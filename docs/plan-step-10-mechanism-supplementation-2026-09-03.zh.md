# Step 10 机制补充执行计划（2026-09-03）

日期：`2026-09-03`
计划版本：`1.0`
基线提交：`70220dd`（goal-first W0-W9 全部完成后的状态）
执行者：无上下文执行者
状态：待 Fable 5.1 审阅
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
