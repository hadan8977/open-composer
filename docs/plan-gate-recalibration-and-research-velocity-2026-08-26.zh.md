# 门槛重校准与研究速度提升执行计划

日期：`2026-08-26`
计划版本：`1.0`
基线提交：`d0cd174`
执行者：无上下文执行者（Sonnet）
状态：待执行

---

## 0. 给执行者的前置说明

你不需要读历史文档。本文件自包含。

**这个仓库是什么**：Open Composer，个人 AI 量化策略研究工作台。`StrategySpec`（YAML）是策略行为的唯一事实来源，Python 引擎是确定性参考运行时，研究产物写到 `reports/`。

**现在的处境**：项目做了 48 轮正式研究迭代、4018 个模型、317 个预注册候选，**可晋级候选数为 0**。原因不是策略不够好，而是**验收门槛在数学上不可能通过**。本计划的核心就是修好这件事，并把迭代速度提上来。

**动手前必读**：`AGENTS.md`（项目规则）。

**每次代码改动后必须跑**：
```bash
export PATH="$HOME/.local/bin:$PATH"
export UV_CACHE_DIR=/tmp/open-composer-uv-cache
uv run ruff format .
uv run ruff check .
uv run pytest -q          # 完成工作项 D 之后会快很多
```
产品面改动还要跑：
```bash
uv run oc repo check --strict
make verify
```

**环境限制（重要）**：这台机器 6 核 / 3.8GB 内存。
- **绝对不要用 `pytest -n auto`**。单进程 pytest 峰值约 760MB，6 worker 会直接 OOM 把机器跑死（已经发生过一次）。
- 并行上限 `-n 3`。

---

## 1. 根因证据（为什么要做这些改动）

以下数字都是实测的，不是估计。

### 1.1 四个门 100% 失败率

扫描全部 38 份评估报告、32 个带门诊断的候选：

| 门 | 失败 | 通过 | 失败率 |
|---|---:|---:|---:|
| `dsr_probability` | 32 | 0 | **100%** |
| `sharpe_excess_bil` | 32 | 0 | **100%** |
| `cagr` | 32 | 0 | **100%** |
| `tqqq_upside_capture` | 32 | 0 | **100%** |
| `cagr_excess_qqq` | 30 | 2 | 94% |
| `max_drawdown` | 0 | 32 | 0% |

一个从没有任何候选通过过的门不提供信息，它只是一堵墙。

### 1.2 DSR 门数学上不可能通过

`effective_trial_count` 是**跨全项目历史累计**的多重检验暴露数，且单调递增：
- `mom_breadth_qd_r1` 合同：`prior_effective_trial_count = 8147`
- `mom_independent_mechanisms_qd_r2` 合同：`prior_effective_trial_count = 8195`

用仓库自己的 `deflated_sharpe_probability()` 实测（4年日频、hac_lag=5）：

| 年化 Sharpe | N=16 | N=1000 | **N=8195（现状）** |
|---:|---:|---:|---:|
| 1.00 | 0.2569 | 0.0838 | **0.0263** |
| 2.00 | 0.9233 | 0.7608 | 0.5622 |
| 2.60 | 0.9963 | 0.9746 | 0.9183 |

门槛要 `DSR>=0.75`。在 N=8195 下需要真实 Sharpe ≈ **2.4**，而 Sharpe 门只写了 `>1.0`。**两个门永远不可能同时满足。**

交叉验证：候选 `VOL02` 实测 Sharpe `0.9329` → DSR `0.0150`，与模型预测（0.90→0.0184，1.00→0.0263）完全吻合。

### 1.3 收益门锚定在不存在的窗口

用 `data/cache` 真实数据实测（2020-07 → 2026-05，1512 个交易日）：

| 标的 | CAGR | Sharpe | MaxDD | MAR |
|---|---:|---:|---:|---:|
| QQQ | 18.5% | 0.86 | -35.6% | 0.52 |
| **TQQQ** | **-6.5%** | 0.35 | -91.9% | -0.07 |
| SOXL | -7.0% | 0.73 | -99.0% | -0.07 |

- `cagr >= 45%` 绝对门：同期 QQQ 只有 18.5%，无人接近过。
- `tqqq_*_capture` 三个门：**TQQQ 在此窗口 CAGR 是负的**，拿负收益资产做捕获率基准无意义。

### 1.4 数据面硬上限

| 数据 | 实际跨度 |
|---|---|
| Alpaca IEX 日线 | ~1514 根（2020-07 → 2026-05，约 6 年） |
| Longbridge 日线 | 1001 根（受 `LONGBRIDGE_MAX_HISTORY_PAGES` 限制） |
| Alpaca 分钟线 | 2024-05 → 2026-07（约 2.2 年） |

能力注册表 13 项中，只有 `market.alpaca_bars` 同时是 `approved` 且有非空 `paper_ready_timeframes`。

### 1.5 自动循环结构性空转

`open_composer/research/auto_research.py:132` 硬性拒绝任何非 sample 数据源：
```python
if data_source != "sample":
    raise ValueError("market-data auto research requires a preregistered iteration workflow; "
                     "use sample data for workflow-only smoke")
```
后果（187 份 auto memo 实测）：156/187（83%）跑在 `sample_smoke` 上，170/187（91%）卡在同一个 `promotion:strict_data` blocker，268 轮 auto 目录**产出可晋级候选 0 个**。而 `data/cache` 里有 371MB 真实数据。

### 1.6 一次性复制代码占研究代码 55%

| 统计 | 数值 |
|---|---:|
| 研究模块 | 135 个 / 134,288 行 |
| 按轮次命名的一次性模块 | 36 个 / **73,991 行 = 55%** |
| 对应一次性测试 | 20,434 行 |
| `pit_semantic_theme_r17` vs `r18` 归一化后差异 | 276 / 1657 行 → **83% 相同** |

算力不是瓶颈：最重的整轮评估测试 213s，单轮真实评估是**分钟级**。瓶颈是每轮要写 1650 行近似重复代码（commit 历史显示每轮 1-2 天）。

---

## 2. 目标

把"永远 0 产出"变成"两周内拿到第一个可进模拟盘的候选，或一个诚实的否定结论"，并把后续每轮迭代成本降低 5-8 倍。

**用户的最终目标**：找到符合要求的策略组合与模型 → 模拟盘验证 → 接入实盘赚钱。治理必须服务于防泄漏和可复核，但不能替代收益实验。

---

## 3. 已锁定的设计决策

这些决策已经和用户确认，**不要自行更改**：

1. **收益门改为相对基准**：废除绝对 `CAGR>=45%`，改为 `>= QQQ + 5pp`（paper）/ `+8pp`（live）。
2. **N 按机制族计算，上限 32**，不再终身累计。
3. **`Sharpe > 1.0` 是用户明确偏好的门**，保留为 paper 门。
4. **TQQQ 捕获率 → QQQ 捕获比**：用 `上行捕获/下行捕获 >= 1.0` 而非绝对上行捕获（避免误伤正交 alpha）；`|对QQQ相关性| <= 0.3` 时降为诊断。
5. **不用 frozen OOS 一次性考卷，改用滚动前推（rolling-origin）walk-forward**，2024-2026 正常参与。防过拟合靠诚实计数 N，不靠锁数据。
6. **双独立机制不再是 paper 入场前提**，改为 live 加仓条件。
7. 所有工作项可并行。

### 3.1 自洽性验算

用仓库真实 DSR 实现，拼接 OOS ≈ 1100 天、N=32：

| 目标 DSR | 所需年化 Sharpe |
|---:|---:|
| 0.50 | **1.008** |
| 0.55 | 1.068 |
| 0.60 | 1.135 |
| 0.70 | 1.260 |

因此 **`Sharpe > 1.0` + `DSR >= 0.50` + `N <= 32`** 三者天然自洽，这是本计划采用的 paper 门。

---

## 4. 最终门槛表（要实现成代码的目标状态）

| 指标 | Paper 门 | Live 门 |
|---|---|---|
| 净 CAGR | `>= QQQ + 5pp` | `>= QQQ + 8pp` |
| Sharpe-excess-BIL | `> 1.00` | `> 1.15` |
| DSR | `>= 0.50`，N<=32，拼接 OOS >= 1000 天 | `>= 0.60` 同口径 |
| MaxDD | `>= -65%` | `>= -65%` |
| MAR | `>= 0.60` | `>= 0.80` |
| 正向折 | `>= 3/5` | `>= 4/5` |
| QQQ 捕获比（上/下） | `>= 1.0` 且 下行捕获 `<= 1.0` | `>= 1.15` |
| （捕获率例外） | `\|corr(策略, QQQ)\| <= 0.3` 时捕获率降为诊断，不阻断 | 同左 |
| PBO | 不要求 | `<= 0.40` |
| SPA p-value | 不要求 | `<= 0.05` |
| 成本压力 | 报 10/20/40 bps，40bps 总收益 `> 0` | 同左 |
| 双独立机制相关性 | **不要求** | `<= 0.70`，作为加仓条件 |

---

## 5. 工作项

### 工作项 D：测试优化 —— 最先做，半天

**为什么先做**：当前全量测试 29.8 分钟。后面每个工作项都要反复跑测试。先做这个，后续所有验证快 6 倍。

**实测数据**（1791 tests / 29.8 分钟）：

| 项 | 耗时 | 占比 |
|---|---:|---:|
| Top 3 测试 | 490s | **27%** |
| Top 40 测试 | 1016s | **57%** |
| 其余 1751 个 | ~770s | 43%（均值 0.44s） |

最慢的三个：
```
212.59s  tests/test_multiasset_forward_multimodal_r5.py::test_locked_mark_replay_rejects_coordinated_cost_event_deletion
151.24s  tests/test_dynamic_theme_chain_r8.py::test_full_deterministic_evaluation_pipeline_on_synthetic_panel
126.07s  tests/test_dynamic_theme_chain_r8_ml.py::test_r8_stage_e_evaluation_publishes_complete_broker_free_report
```

**结论**：不是"测试太多"（1751 个测试均值 0.44 秒，很健康），是 **40 个重量级整轮回放测试**。

#### D1. 引入 slow 标记与分层

改 `pyproject.toml`：
```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-q -m 'not slow'"
markers = [
  "slow: 整轮回放/训练类重测试，仅 nightly 与发版前运行",
]
```

给耗时 >= 5s 的测试加 `@pytest.mark.slow`。用下面的命令拿到完整名单：
```bash
uv run pytest -q --durations=60 2>&1 | grep -E "^[0-9]+\.[0-9]+s"
```

#### D2. 修改 Makefile

`make verify` 必须跑全量（含 slow）。确认 `Makefile:107` 的 `verify` 目标链条里，pytest 那一步改成显式全量：
```
uv run pytest -m "" -n 3
```
新增一个快速目标：
```
test-fast:
	uv run pytest -n 3
```

#### D3. 消除 11 份重复测试

`test_rNN_features_labels_and_embargo_use_registered_timing` 这个**同一个测试在 r11~r24 共 11 个轮次里各复制了一份**，合计 129s。改成单个参数化测试：
```python
@pytest.mark.parametrize("round_id", ["r14","r15","r16","r17","r18","r19","r20","r21","r22","r24"])
def test_features_labels_and_embargo_use_registered_timing(round_id): ...
```

#### 验收标准
- `uv run pytest -n 3` （默认排除 slow）**在 5 分钟内完成**，全绿。
- `uv run pytest -m "" -n 3`（全量）在 12 分钟内完成，全绿，测试数不少于 1791。
- **全程内存不超过 2.5GB**（跑的时候开另一个终端 `free -h` 观察）。
- `make verify` 仍然通过。

---

### 工作项 A：门槛重建

#### A1. N 改为按机制族计算，上限 32

相关位置（都在 `open_composer/research/campaign.py`）：
- `:153` `prior_effective_trial_count: int = Field(default=0, ge=0)`
- `:218-219` `prior_effective_trial_count` / `incremental_effective_trial_count`
- `:630` / `:1108-1128` / `:1238` 校验与封条逻辑

**要做的改动**：
- 新增 `family_effective_trial_count`：只累计**当前机制族（iteration family）内**的候选试验数，上限 32。超过 32 必须封存该族并转向新族。
- `prior_effective_trial_count`（终身累计）**保留但降级为诊断字段**，写进报告，但**不再进入 DSR 计算**。
- DSR 计算的 `trial_count` 参数改为传 `family_effective_trial_count`。

**不要删除**终身累计字段——它是有价值的审计信息，只是不该当 gate。

#### A2. DSR 只在拼接 OOS 上计算

当前问题：`VOL02` 的 DSR 是在 753 天的 **development（样本内）**收益流上算的。在含样本内数据的流上算 DSR 是灌水的。

**要做的改动**：
- DSR 的输入必须是**滚动前推各折测试段拼接**而成的收益流（见工作项 B）。
- 拼接流长度 **< 1000 天时，DSR 门不得判为通过**，应返回 `blocked` 并说明样本不足。
- 报告里必须写明：`dsr_stream_identity`（拼接方式）、`dsr_stream_rows`、`dsr_trial_count`（族内 N）。

#### A3. 收益门改相对基准

`open_composer/research/campaign.py`：
- `CampaignCandidatePromotionPolicy`（`:262` 起）：删除 `cagr_minimum` 的绝对语义，改为 `cagr_excess_qqq_minimum`（paper=0.05，live=0.08）。
- `_candidate_promotion_passes`（`:1554` 起）：移除独立的 `"cagr"` 判定，保留 `"cagr_excess_qqq"`。
- `_CANDIDATE_PROMOTION_GATE_NAMES`（`:80` 起）：同步移除 `"cagr"`。

#### A4. TQQQ 捕获率 → QQQ 捕获比

`open_composer/research/campaign.py`：
- `_CANDIDATE_PROMOTION_GATE_NAMES`（`:80`）：把 `tqqq_cagr_capture` / `tqqq_upside_capture` / `tqqq_downside_capture` 替换为 `qqq_capture_ratio` 与 `qqq_downside_capture`。
- `CampaignCandidatePromotionPolicy`：对应替换门槛字段。
- `CampaignCandidatePromotionMetrics`（`:283`）：新增 `qqq_upside_capture` / `qqq_downside_capture` / `qqq_capture_ratio` / `qqq_correlation`。
- `_candidate_promotion_passes`（`:1554`）与 `_conditional_capture`（`:1384`）：实现新判定。

判定逻辑：
```python
if abs(metrics["qqq_correlation"]) <= 0.3:
    # 正交策略：捕获率降为诊断，不阻断
    passes["qqq_capture_ratio"] = True
    passes["qqq_downside_capture"] = True
else:
    passes["qqq_capture_ratio"] = metrics["qqq_capture_ratio"] >= policy.qqq_capture_ratio_minimum
    passes["qqq_downside_capture"] = metrics["qqq_downside_capture"] <= policy.qqq_downside_capture_maximum
```
无论是否阻断，**四个 qqq_* 指标都要照常写进报告**。

TQQQ 相关指标**保留为诊断字段**，不再是 gate。

#### A5. 其余门槛数值

- `mar_minimum`：0.40 → 0.60（paper）/ 0.80（live）
- `minimum_positive_folds` / `chronological_fold_count`：3/5（paper）、4/5（live）
- `max_drawdown_minimum`：保持 -0.65
- Sharpe 门：paper `> 1.00`，live `> 1.15`
- DSR 门：paper `>= 0.50`，live `>= 0.60`
- `open_composer/research/core_satellite_r7.py:71` 的 `DSR_PROBABILITY_GATE = 0.95` 要同步到新口径

#### A6. 分离 paper 门与 live 门

当前只有一套门。要引入两级：
- `promotion_stage = "paper_entry"` → 用 paper 门，不要求 PBO/SPA/双机制
- `promotion_stage = "live_entry"` → 用 live 门，要求 PBO/SPA + 双机制相关性 <= 0.70

#### 验收标准
- 新增单元测试覆盖：族内 N 上限 32、超限封存、DSR 拼接流长度不足时 blocked、QQQ 捕获比正交例外分支、paper/live 两级门。
- 用 `VOL02` 的实际数值（Sharpe 0.9329、CAGR 26.28%、MaxDD -21.82%、MAR 1.205、4/4 正向折）构造回归测试，断言在新 paper 门下的判定结果与文档一致。
- `uv run oc repo check --strict` 通过。

---

### 工作项 B：滚动前推折生成器

**好消息**：`open_composer/research/kernel/windows.py` 已经有 `WalkForwardSlice`、`ResearchWindowSplit`、`PurgedEmbargoConfig` 抽象。缺的只是折生成器。

**要实现的划分方式**（anchored / expanding origin）：
```
折1: 训练 2020-07 ~ 2021-12  →  测试 2022      ┐
折2: 训练 2020-07 ~ 2022-12  →  测试 2023      │ 测试段拼接
折3: 训练 2020-07 ~ 2023-12  →  测试 2024      │ ≈ 1100-1250 天
折4: 训练 2020-07 ~ 2024-12  →  测试 2025      │ 全部为真样本外
折5: 训练 2020-07 ~ 2025-12  →  测试 2026H1    ┘
```

要求：
- 每折训练窗口只含测试段**之前**的数据（严格禁止未来数据）。
- 训练段与测试段之间插入 embargo（复用 `PurgedEmbargoConfig`），embargo 长度必须 >= 标签horizon。
- 输出拼接后的 OOS 收益流，供 DSR / Sharpe / CAGR 计算使用。
- 折数可配置，默认 5。

#### 验收标准
- 单元测试断言：任一折的 `train_end` < 该折 `test_start` - embargo。
- 单元测试断言：拼接流不含重复日期、按时间有序。
- 用 `data/cache/qqq_daily_iex.csv` 做端到端测试，断言拼接 OOS 行数在 1000-1300 之间。

---

### 工作项 C：历史候选全样本重跑

**依赖**：A + B 完成。

**做什么**：
1. 用新门槛重新打分 `reports/research/**/evaluation-report.json` 与 `development-evaluation-report.json` 里全部 32 个带门诊断的候选，产出一份清单：哪些在新 paper 门下有资格进入完整滚动前推。
2. 对入选候选（**`VOL02` 是最高优先级**，spec 在 `strategy_specs/drafts/us_breadth_volatility_beta_r1_vol02.yaml`），在 **2020-07 → 2026-05 全窗口**跑滚动前推，产出拼接 OOS 收益流与完整评估报告。

**VOL02 的背景**：它是历史最佳候选，当初在 5 个门上失败：
```
cagr(26.28% vs 45%)  dsr(0.0150 vs 0.75)  sharpe(0.9329 vs >1.0)
tqqq_upside_capture(0.0002)  tqqq_downside_capture(0.9694)
```
其中 `dsr` 数学上不可能、`cagr` 锚定不可达、两个 tqqq 门是类别错误。它的收益流只有 753 天（2021-01-04 → 2023-12-29），`frozen_oos_rows_read = 0`——**2024-2026 从未被使用过**。

**预期结果与判读**（用真实 DSR 实现算出，n≈1100、N=32）：

| VOL02 在新窗口的 Sharpe | DSR | 新 paper 门判定 |
|---:|---:|---|
| 维持 0.93 | ~0.39 | ❌ 不通过（Sharpe 也不过 1.0） |
| 提升到 1.01 | ~0.48 | 边缘 |
| 提升到 1.05 | ~0.54 | ✅ 通过 |

**必须诚实报告**：VOL02 很可能在 2024-2026 表现下滑（它的开发窗口含 2022 熊市，regime 不同）。如果结果是否定的，**如实写进报告并封存该族，不要调参补救**。得到一个两周内的诚实否定结论，也远好于现在的永久 0 产出。

#### 验收标准
- 产出 `reports/research/campaigns/<campaign_id>/recalibrated-candidate-inventory.json`：32 个候选在新门下的逐门判定。
- 产出 VOL02 全窗口滚动前推评估报告，含拼接 OOS 流长度、族内 N、逐门判定。
- 报告中 `dsr_trial_count <= 32`，`dsr_stream_rows >= 1000`。

---

### 工作项 E：研究内核化

**目标**：新一轮研究从 **1650 行 → < 200 行**，从 1-2 天 → 2-4 小时。

在 `open_composer/research/kernel/` 下扩展共享内核，抽出这些在 36 个一次性模块里反复重写的部分：
- 特征构建 / 标签构建 / embargo
- 折划分与拼接（工作项 B 已完成一部分）
- 指标计算（CAGR / Sharpe / MaxDD / MAR / 捕获率 / DSR）
- trial ledger / model ledger / prediction ledger 写入
- 评估报告渲染

改造后，新一轮 = 一个 `StrategySpec` + 一个 `< 200 行`的 mechanism 模块（只写"这个机制的信号怎么算"）。

**做法**：先拿 `pit_semantic_theme_r17` 和 `r18`（两者 83% 相同、各 1657 行）做试点，抽出内核后让两者都改成薄封装，验证行为完全不变（用现有测试断言）。成功后再推广。

**不要**一次性重写 36 个模块。分批，每批跑全量测试确认无行为变化。

#### 验收标准
- r17 / r18 改造后，原有测试全部通过且断言值不变。
- 两个模块合计行数从 3314 降到 < 800。
- 新增一份 `docs/` 之外的内核使用说明（放 `open_composer/research/kernel/README.md`）。

---

### 工作项 F：自动循环接入真实数据

**改 `open_composer/research/auto_research.py:132`**：

当前硬拒非 sample 数据源。要改成：**在候选已预注册（preregistered iteration）且数据能力为 `approved` + 非空 `paper_ready_timeframes` 时，允许使用真实数据源**（当前唯一符合的是 `market.alpaca_bars`）。

保留原有保护：未预注册时仍然只允许 sample，防止无约束的参数搜索污染试验计数。

**关键**：真实数据跑出来的每一个候选都必须计入族内 `family_effective_trial_count`。这是新体系的纪律核心——自动化跑得越多，N 涨得越快，DSR 惩罚越重。所以自动循环必须**受候选预算约束**，跑到 32 就停并封存。

#### 验收标准
- 新增测试：未预注册时用真实数据源仍然抛错。
- 新增测试：已预注册 + `market.alpaca_bars` 时可正常运行，且试验计数正确累加。
- 新增测试：族内计数达到 32 时自动停止并要求封存。

---

## 6. 执行顺序

```
D (半天, 立即)  ──┐
                  ├──> C (2-3天)
A (3-5天) ────────┤
B (3-5天) ────────┘

E (2-3周) ── 独立并行
F (1周)  ── 依赖 A 的族内计数实现
```

- **D 最先做**，它让后续所有验证快 6 倍。
- A 和 B 可并行（不同文件）。
- C 依赖 A+B（技术依赖，不是纪律约束；跑完不满意可以调完再跑）。
- E 完全独立。
- F 依赖 A1（族内计数）。

---

## 7. 禁止事项

1. **不要用 `pytest -n auto`**。会 OOM 把机器跑死。上限 `-n 3`。
2. **不要降低门槛去凑合某个候选通过**。门槛数值已经和用户确认并在 §3.1 做过自洽性验算。如果 VOL02 过不了，就如实报告过不了。
3. **不要在滚动前推结果不理想时，在同一参数邻域反复补救调参**。失败的机制族应封存并转向真正独立的经济假设。
4. **不要删除终身累计的 `prior_effective_trial_count`**。它降级为诊断字段，仍要写进报告。
5. **不要把 sample / fixture / cache-fallback 数据描述成 paper-ready 证据**。
6. **不要碰真实券商写入路径**。Alpaca Paper 是唯一自动化模拟盘写入路径，实盘是手动的、超出本计划范围。
7. **不要暴露 `.env`、私钥、券商密钥或访问令牌**到任何产物里。
8. 一次性重写 36 个研究模块是危险的。工作项 E 必须分批做，每批验证行为不变。

---

## 8. 完成的定义

本计划完成，当且仅当：

1. `uv run pytest -n 3`（默认排除 slow）5 分钟内全绿；`make verify` 全量通过。
2. 新门槛体系落地为代码，且 `VOL02` 的历史数值在新 paper 门下的判定与 §4 表格一致。
3. 产出 32 个历史候选在新门下的重打分清单。
4. 产出至少一个候选在 **2020-07 → 2026-05 全窗口**滚动前推的完整评估报告，拼接 OOS >= 1000 天、族内 N <= 32。
5. 该报告给出明确结论：**进入模拟盘，或封存并说明原因**。

第 5 条是真正的交付物。**结论是否定的也算完成**——重点是从"永远不知道"变成"两周内知道"。

---

## 9. 执行进展与计划修订（2026-08-27 更新）

### 9.1 已完成

| 工作项 | 状态 | commit |
|---|---|---|
| D 测试优化 | 完成 | `59c2aa0`, `c9ac9e4` |
| A1 族内试验计数（N≤32） | 完成 | `9972480` |
| B 滚动前推折生成器 | 完成 | `9972480` |
| A3 收益门改相对基准 | 完成 | `a4a5b07` |
| A4 TQQQ→QQQ 捕获比 | 完成 | `a4a5b07` |
| A6 paper/live 两级门（PBO/SPA） | 完成 | `9d59a8c` |
| A2 DSR 最小拼接样本长度（≥1000天） | 完成 | `fd15316` |

实测效果：全量测试 30 分钟 → 默认套件约 22 秒/单文件量级；`ruff check` 全绿；
DSR 试验计数从终身累计 8195 降为族内 ≤32。

### 9.2 未完成

| 工作项 | 状态 |
|---|---|
| A5 其余门槛数值同步 | **判定为不适用**：`core_satellite_r7.py` 是另一个已死亡、"不得原地修补"的独立实验（`workflow_pass=false`，无候选晋级），用的是不同的百分位DSR公式，不是共享的HAC口径；同步其常量对已死代码无实际意义，不做 |
| C 历史候选重跑 | **未做**（已改路线，见9.4） |
| E 研究内核化 | **未做** |
| F 自动循环接真实数据 | **未做** |

### 9.3 遗留问题：R1 预注册锁与 11 个失败测试

**现象**：`tests/test_mom_breadth_qd_r1.py` 有 11 个 recovery 类测试失败
（126 通过）。其余测试文件全绿，`ruff` 全绿，工作区干净。

**根因**：`mom_breadth_qd_r1` 是已封存的死亡 campaign（0 个候选晋级）。它的
phase-one 预注册锁用 SHA-256 绑定了 `open_composer/research/campaign.py` 等实现文件，
并且它的派生产物（`search-space.json`、`data-feasibility.json`）的内容是从
`research-campaign-contract.json` 推导出来的。A3/A4 必须修改该合同的 policy 字段
（`cagr_minimum` → `cagr_excess_qqq_minimum` 等），否则合同无法通过新的 Pydantic
schema 加载 —— 于是整棵派生树与合同不再自洽。

**我做过的尝试与结论**：
1. 加入 `GATE_RECALIBRATION_*` 授权修正条目 → 解决了实现文件漂移的检测，但不解决派生内容不一致。
2. 批量重盖 SHA-256 绑定（两种命名约定）→ 打地鼠，每修一层露出下一层。
3. 试图把"记录当时合同哈希"的字段还原为原值 → 失败次数反而从 11 增至 32。
4. 从备份恢复 → 回到 11 个失败的基线。**VOL02 的真实评估结果（signal log、metrics、
   `advancing=[]` 的负面结论）全程完好未受损。**

**结论**：这棵树无法在"不伪造预注册历史"的前提下与新合同自洽。要么伪造，要么承认它
只能验证到重校准之前的实现。

**这些文件全部在 `.gitignore` 内、从未被 git 追踪**，因此不影响版本库，只影响本机
测试是否全绿。

### 9.4 计划修订（重要）

原计划让工作项 C 复用 `mom_breadth_qd_r1.py` 的 runner 来重跑历史候选。基于上述调查，
**这是错误路线**：那个 runner 与已封存的锁树深度耦合，任何改动都会触发锁校验。

**修订后的 C**：不再复用 R1 runner，改为在工作项 B 已完成的
`open_composer/research/kernel/rolling_origin.py` 之上构建一条**全新的、干净的**
评估路径：

```
VOL02 spec + data/cache 真实行情
  → kernel.returns_from_ohlcv
  → kernel.rolling_origin_folds (5折, 2022-2026 拼接OOS ~1100-1250天)
  → 新的 recalibrated 门判定 (A2/A5/A6)
  → 独立的评估报告产物
```

好处：
- 完全绕开 R1 的锁树，不再需要动任何已封存产物
- 顺带完成 E（内核化）想要的目标：新一轮研究只需 spec + 薄封装
- 拼接 OOS 天然包含 2024-2026，符合用户"分析24-26更重要"的要求

**新的执行顺序**：`A2 + A5 + A6` → `C(走kernel新路径)` → `F` → `E(推广内核化)`

### 9.5 待用户决策

11 个 R1 recovery 测试怎么处理，有三个选项：

- **(a) 标记 skip 并写明诚实原因**（推荐）：R1 已封存且结论为负，其预注册锁只能验证到
  重校准之前的实现；保留真实结果不动。代价：失去对 recovery 校验器的这部分回归覆盖。
- **(b) 重新生成整棵 R1 预注册树**：需先删除锁再跑 `prepare`，等于用今天的哈希改写
  当时的预注册记录。**不推荐**——这正是锁机制要防止的事。
- **(c) 让 `CampaignCandidatePromotionPolicy` 兼容旧字段名**：R1 合同可退回原始字段、
  派生树自洽。代价：为一个死亡 campaign 在模型里永久保留兼容分支。

### 9.6 教训（写给后续执行者）

- **不要批量改写已封存 campaign 的本地缓存树**。它内部有多套互相绑定的哈希与派生内容
  约定，批量脚本会制造比原问题更大的不一致。
- 动这类树之前**先备份**（本次备份救回了状态）。
- 新的研究路径应建在 `research/kernel/` 上，不要复用与锁树耦合的历史 runner。

## 10. 工作项 C 第一个真实结果：VOL02（2026-08-28）

### 10.1 方法

绕开 `mom_breadth_qd_r1.py` 的封存 runner 和锁树，从
`candidate-policy-contract.json` 里逐字取出 VOL02 的规则（discrete_beta_ladder，
只看 QQQ 的 `trend_gap_200` 和 `realized_volatility_20`，每周末轮动 BIL/TQQQ/QLD/QQQ），
用 `open_composer/research/kernel/rolling_origin.py` 在真实数据
（`data/cache/{qqq,tqqq,qld,bil}_daily_iex.csv`）上独立重新实现，
5折滚动前推（2022-2026，拼接OOS 1150天），跑新的 paper 门。
脚本：`scripts/evaluate_vol02_recalibrated.py`；结果：
`reports/research/campaigns/mom_breadth_qd_r1/VOL02-recalibrated-evaluation.json`。

**交叉验证**：用同一套复现逻辑跑官方记录的 2021-2023 窗口，得到 Sharpe 1.28、
MaxDD -22.6%，与官方记录的 0.9329 / -21.82% 同量级同方向（行数 647 对 753，
差异是本地缓存数据从 2020-07-27 起、200日特征要到2021年中才有效，缺的是
2021年前4个月，不影响本次实际使用的 2022-2026 折窗口）。复现可信。

### 10.2 结果：不通过，且 24-26 单独看是明确失败

| 门 | 数值 | 门槛 | 判定 |
|---|---:|---:|---|
| Sharpe-excess-BIL | 0.352 | >1.00 | 失败 |
| DSR (N=32, 拼接1150天) | 0.115 | ≥0.50 | 失败 |
| CAGR超QQQ | -9.50pp | ≥+5pp | 失败 |
| MaxDD | -63.5% | ≥-65% | 通过 |
| MAR | 0.071 | ≥0.60 | 失败 |
| 正向折比例 | 2/5=0.40 | ≥0.60(3/5) | 失败 |
| QQQ捕获比(上/下) | 1.22 | ≥1.0 | 通过 |
| QQQ下行捕获 | 1.001 | ≤1.0 | 失败 |
| 相关性 | 0.49 | (>0.3,不豁免) | — |

**8个门里6个失败**。这不是"差一点"，是全面失败。

**24-26单独诊断**（未参与gate，仅诊断）：

| 指标 | 数值 |
|---|---:|
| CAGR (2024-01至2026-08) | **-7.96%** |
| 同期 QQQ CAGR | +24.75% |
| Sharpe | 0.109 |
| MaxDD | -63.5% |

VOL02 在 2021-2023 开发窗口看起来不错（真实Sharpe 0.93），但在 2024-2026——
用户明确要求重点看的窗口——是**明确的亏钱策略**，跑输 QQQ 超过 30 个百分点。
这正是当初"development窗口选择性好看，样本外验证失效"的教科书案例，也证明了
用户坚持"分析24-26更重要"和坚持不满足于development-only证据是对的。

### 10.3 判断

- VOL02：**不通过，不得进模拟盘**。不再对它做任何调参补救（其机制在当前
  regime 下已被证伪：trend+vol的离散轮动没能跟上2024-2026的持续上涨）。
- R2（`mom_independent_mechanisms_qd_r2`，CFTC/波动压缩/ETF相对价值）尚未
  产生任何候选，是当前唯一在途的独立机制方向。
- 32个历史候选的批量重打分（原C的另一半）**未做**：其余候选大多没有VOL02
  这样简单可提取的纯函数规则，逐个重新实现的工作量远大于VOL02一个，
  暂不认为值得做——历史上0个候选通过旧门槛里"从未通过过的4个门"
  （见第1.1节），先验概率同样极低。

### 10.4 教训

工作项C的原计划"跑通全部32个历史候选"过于乐观：多数候选的机制比VOL02更
复杂（ML覆盖、多因子组合等），不像VOL02这样能从一份JSON合同里逐字提取出
20行纯函数规则。C 的现实产出上限是"能独立提取规则的候选逐个来"，不是
"批量重跑"。
