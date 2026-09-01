# SIP 数据迁移与宽搜索执行计划

日期：`2026-09-01`
计划版本：`1.0`
基线提交：`3034ef2`
执行者：无上下文执行者（Sonnet）
状态：待执行
前置计划：
- `docs/plan-gate-recalibration-and-research-velocity-2026-08-26.zh.md`（门槛重校准，D/A/B/C 已完成）
- `docs/plan-kernel-extraction-and-auto-research-real-data-2026-08-28.zh.md`（**其中工作项 E 已作废**，见 §1.2）

---

## 0. 给执行者的前置说明

本文件自包含。你不需要读历史文档，但 §1 的禁改清单必须先读。

**环境准备**（每条 shell 命令都要）：
```bash
export PATH="$HOME/.local/bin:$PATH"
export UV_CACHE_DIR=/tmp/open-composer-uv-cache
```

**每次代码改动后必须跑**：
```bash
uv run ruff format . && uv run ruff check . && uv run pytest -q
```
产品面改动还要 `uv run oc repo check --strict`。

**机器约束**：6 核 / 3.8GB 内存 / 磁盘 217GB（约 146GB 可用）。
- **绝对不要用 `pytest -n auto`**，会 OOM。并行上限 `-n 2`。
- 默认测试套件已自动跳过 slow 测试，约 7 分钟。全量用 `make test-full`。

**已知既有失败**：`tests/test_mom_breadth_qd_r1.py` 有 **11 个失败**，全仓其他文件零失败。
这是已记录的遗留问题，**与本计划无关，不要修，也不要碰 `reports/research/iterations/mom_breadth_*/`**。
回归判断标准：**失败数仍为 11 且全部来自该文件**。

---

## 1. 硬约束

### 1.1 全局禁改文件清单

7 个已封存 campaign 的 `phase-one-preregistration-lock.json` 用 SHA-256 硬绑定了下列文件，
**改动任何一个都会打挂 `test_mom_breadth_qd_r1.py`**：

```
capabilities/registry.yaml
open_composer/market_calendar.py
open_composer/models/strategy_spec.py
open_composer/research/campaign_statistics.py
open_composer/research/iteration_dossier.py
open_composer/research/quality_diversity.py
open_composer/storage.py
pyproject.toml
uv.lock
open_composer/research/mom_breadth_qd_r1.py
tests/test_mom_breadth_qd_r1.py
scripts/prepare_mom_breadth_qd_r1.py
strategy_specs/drafts/us_breadth_*.yaml   （全部 16 个）
```

这些文件**只能 import / 读取**。`open_composer/research/campaign.py` 也在锁里，
但已有 `GATE_RECALIBRATION_DRIFT_BLOCKERS` 授权条目，改它不会产生新失败。

> **注意 `quality_diversity.py` 在禁改清单里。** 本计划的 QD 搜索必须写成
> `open_composer/research/kernel/` 下的**新模块**，import 现有 QD 类型，不要修改原文件。

### 1.2 已作废的工作项

前置计划的**工作项 E（内核化 r17/r18）已被用户明确取消**，不要做。
`pit_semantic_theme_r11..r24` 全家族已封存，重构它们没有价值。

---

## 2. 背景：为什么做这些

### 2.1 数据面（已由本计划的 §3 部分完成）

旧的 IEX 数据只有 **2.2 年分钟线**，而用户的核心诉求是"很多策略必须用分钟级或比日线更细的数据"。
实测确认 IEX 的 2 年是**账户档位的滚动窗口**，不是代码限制。

改用 SIP（合并全美交易所行情，IEX 的严格超集，实测同一周 QQQ：SIP 4121 根 vs IEX 1795 根，
差异来自盘前盘后覆盖）后，历史深度可达 10 年。

**用户决定：SIP 全面取代 IEX，旧 IEX 数据和相关研究产物全部弃用（知识库保留）。**

### 2.2 宽搜索与多重检验的矛盾（本计划的核心）

用户要求"先撒网再选优和优化"（遗传算法/树状搜索）。但天真地这么做会让 DSR 的试验数 N 爆炸——
前置计划正是因为 N=8195 导致 DSR 门数学上不可能通过（Sharpe=1.0 时 DSR 仅 0.026，门槛 0.75）。

**关键研究发现（这是解开矛盾的钥匙）**：

> DSR 里的 N 是**"有效独立试验数"，不是回测的字面次数**。高度相关的变体
> （MA50 vs MA51）不构成独立试验。López de Prado (2018) 提出用聚类算法
> （ONC / 层次聚类 / 相关矩阵特征值谱）对**候选的收益序列**聚类，**聚类数即有效 N**。
>
> 来源：https://www.ml4trading.io/docs/diagnostic/methods/deflated-sharpe-ratio/
> 　　　https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2460551

**这同时给了用户自己那条规则一个可测量的定义。** 用户的研究规则写着
"不用遗传变异或大量相近参数制造虚假探索宽度"，此前无法执行，因为"虚假宽度"没有定义。现在有了：

| | 候选数 | 聚类数 | 判定 |
|---|---:|---:|---|
| **假宽度** | 500 | 3 | 只测了 3 个想法，各换了 167 种参数 |
| **真宽度** | 500 | 80 | 真的探索了 80 种不同行为 |

**所以 `MAX_FAMILY_EFFECTIVE_TRIAL_COUNT = 32` 必须改为约束"聚类数"，不是"候选数"。**
这样撒网就合法了：生成 500 个候选，只要聚成 ≤32 类，门槛完全不变。

### 2.3 项目现状：QD 是个空壳

| 组件 | 状态 |
|---|---|
| QD 归档/细胞/精英（`quality_diversity.py` 790行）| ✅ 存在，但**在禁改清单里** |
| `generation_mode` | ⚠️ 只支持 `enumerated_candidates`（手工枚举）|
| `mutation_mode` | ❌ **`bounded_parameter_mutation` 只是枚举值，零实现** |
| 描述维度 | ⚠️ 只有 1 个（`mechanism_family`），MAP-Elites 退化成一维 |
| 有效 N 聚类 | ❌ **完全不存在** |

现有的是"手写 19 个候选挑最好的 1 个"，不是搜索。

---

## 3. 数据迁移现状（部分已完成，你需要接手剩余部分）

### 3.1 已完成

- `scripts/fetch_sip_universe.py`：可断点续传的全市场 SIP 抓取器，按 `年/shard` 写 parquet。
- **全市场 10 年日线（2016-2025）已抓完**：`data/sip/daily/`，3360 个 shard。
- 全市场 3.5 年分钟线（2023-2026）**正在后台抓取**，约 30 小时，进度见 `/tmp/fetch_minute.log`。
- 2026 日线补齐**正在后台跑**，进度见 `/tmp/fetch_daily_2026.log`。
- 旧 IEX 缓存已归档到 Drive `datasets/legacy-iex-cache`（149 文件 / 181MB）。
- `data/sip/` 已加入 `.gitignore`。

**实测体量**（60 只随机抽样，非估算；全市场平均流动性系数 0.16）：

| | Parquet | 抓取耗时 |
|---|---:|---:|
| 全市场 13,405 只 × 3.5年分钟 | ~38 GB | ~31 小时 |
| 全市场 × 10年分钟 | ~108 GB | ~87 小时 |
| 全市场 × 10年日线 | ~0.8 GB | ~35 分钟 |

### 3.2 工作项 D1：等待并验证抓取完成

先确认两个后台任务都结束（`pgrep -f fetch_sip_universe` 为空），然后验证：
- `data/sip/daily/` 覆盖 2016-2026，每年 336 shard；
- `data/sip/minute/` 覆盖 2023-2026；
- 抽查 QQQ/TQQQ/SPY 在日线和分钟线里都有连续数据。

若有缺失，重跑同一条命令即可（脚本会跳过已存在的 shard）。

### 3.3 工作项 D2：把 SIP 注册为数据能力

`capabilities/registry.yaml` **在禁改清单里，不能改**。因此：
- 在 `open_composer/adapters/data/` 下新增一个读 `data/sip/` parquet 的加载器
  （建议 `sip_parquet.py`），提供按 symbol + 时间范围 + 频率取数的接口；
- **不要**试图把 SIP 塞进现有 registry。新加载器直接被下面的评估工具链使用。
- 加载器必须在返回的 DataFrame 上标注 `data_source_mode="sip_parquet"` 和
  `acquisition_tier="research_strict"`，保持与现有 provenance 约定一致。

**必须写测试**：加载器能正确按时间范围切片、缺失 symbol 报错清晰、不同频率不混用。

### 3.4 工作项 D3：清理旧 IEX 资产（**已完成，且计划原文的判断是错的**）

执行于 2026-09-01。**实测推翻了本节原来的两条假设**，记录如下以免重蹈：

**假设 1（错）**：「归档 `data/research/`（326MB，多为 IEX 时代快照）→ 再删本地」。
实测 `data/research/` 的 1962 个文件里 **688 个是 SIP、只有 119 个是 IEX**，
其余 1144 个是 manifest / 回执 / 交易日历等衍生物。它**不是** IEX 时代快照。

**假设 2（错）**：「删掉后只有 1 个测试失败」。实测**删掉 `data/research/` 会打挂 24 个测试、
跨 13 个文件**（`test_pit_semantic_theme_r12..r24`、`test_paper_audit_contracts`），
因为它是这些测试的实时依赖数据，不是快照。

**最终结论**：
- `data/cache/*iex*`（149 CSV + 151 manifest = 300 文件，约 180MB）→ **已删除，零新增失败**。
- `data/research/`（1962 文件）→ **保留**。不是 IEX 资产，且是测试依赖。

**归档（删除前完成，可逆）**：
- `datasets/legacy-iex-cache`（149 CSV）
- `datasets/legacy-iex-cache-manifests`（151 JSON）——**原归档遗漏了这 151 个文件，已补传**
- `datasets/legacy-iex-research`（1962 文件，逐文件 md5 校验一致）

**方法论**：删除前先 `mv` 到 `/tmp` 再跑全量测试，确认失败数不变才真删。
本次正是靠这一步避免了不可逆的数据丢失。

> 这次清理还意外挖出一个**远比清理本身重要的缺陷**：旧 IEX 缓存是以 `adjustment=raw`
> 抓的，杠杆 ETF 里混入了 6 处幻影拆股暴跌，现金腿收益记成 0。
> 详见 `docs/finding-iex-cache-price-adjustment-defect-2026-09-01.zh.md`。

---

## 4. 工作项 P1a：有效 N 聚类（最高优先级）

**这是解开宽搜索矛盾的钥匙，必须在 P2 之前完成。**
如果先开搜索后做聚类，第一轮就会把 N 推到几百，门槛重新锁死——重蹈 8195 的覆辙。

### 4.1 要做什么

新增模块（建议 `open_composer/research/kernel/effective_trials.py`）：

```python
def effective_independent_trials(
    candidate_returns: Mapping[str, Sequence[float]],
    *,
    method: Literal["hierarchical"] = "hierarchical",
    correlation_threshold: float = 0.7,
) -> EffectiveTrialsReport
```

- 输入：候选 ID → 收益序列（所有候选必须在**同一时间轴**上，与 PBO/CSCV 用的收益矩阵一致）。
- 做法：算候选间相关矩阵 → 层次聚类（用 `1 - |corr|` 作距离）→ 在
  `correlation_threshold` 处切树 → **聚类数即有效 N**。
- 输出必须包含：`effective_n`、`raw_candidate_count`、每个聚类的成员列表、
  以及 `breadth_ratio = effective_n / raw_candidate_count`（诊断"真宽度 vs 假宽度"）。

**实现约束**：
- 只用 `numpy` / `scipy`（已在依赖里），不要引入新依赖（`pyproject.toml` 在禁改清单里，改不了）。
- 层次聚类给的是保守下界，这正是我们要的——**宁可高估 N，不可低估**。
- 相关性用 Pearson，与 `campaign.py` 里 `_pearson_correlation` 保持一致口径。

### 4.2 接进门槛

`open_composer/research/campaign.py`（可改，有授权条目）：
- 把 `MAX_FAMILY_EFFECTIVE_TRIAL_COUNT = 32` 的语义从"候选数上限"改为"**聚类数上限**"。
- DSR 计算传入的 `trial_count` 改为 `effective_independent_trials(...)` 的结果。
- 报告里必须**同时**写出 `raw_candidate_count` 和 `effective_n`——
  两者的比值是审计"是否在制造虚假宽度"的直接证据。

### 4.3 验收标准

必须写这些测试：
1. 完全相同的 N 个候选（收益序列一致）→ `effective_n == 1`；
2. 完全正交的 N 个候选（随机独立序列）→ `effective_n ≈ N`；
3. 3 组各 100 个高度相关候选 → `effective_n ≈ 3`（这是"假宽度"的判定用例）；
4. 聚类数超过 32 → 门槛拒绝并给出清晰错误；
5. 端到端：用 `data/sip/` 真实数据构造若干候选，验证报告字段完整。

---

## 5. 工作项 P1b：机制评估工具链

### 5.1 为什么

`scripts/evaluate_vol02_recalibrated.py` 已经证明了快路径可行：342 行给出一个可信裁定，
对比旧路径每轮 37-41 个治理产物、耗时 1-2 天。其中 **170 行是完全通用的**
（读真实数据 → 滚动前推 → 新门槛 → 裁定 JSON），只有 90 行是机制专属的。

**把那 170 行提炼成工具链。** 这直击用户"治理吃掉 alpha 时间"的核心抱怨。

### 5.2 接口设计（关键）

搜索单元定义为**机制模板 + 参数向量**：

```
Mechanism  = 声明了参数空间的信号函数模板
Candidate  = 该模板 + 一组具体参数值
```

- **手写单个机制** = 参数空间只有 1 个点的退化情形；
- **网格/遗传搜索** = 同一模板下采样多个点；
- **树状探索** = 多个模板并列各自展开。

**两种模式统计地位必须完全相同**——都要交出收益序列，都进同一个聚类、同一套门槛。
不允许"手写的"享受比"搜出来的"更宽松的待遇。

每个候选必须携带：
```
candidate_id, mechanism_family, param_vector,
oos_return_stream      # 聚类 + DSR/PBO/SPA 的输入
generation, parent_id  # 谱系，用于审计
```

### 5.3 复用已有组件（不要重造）

- 滚动前推折：`open_composer/research/kernel/rolling_origin.py`（已实现，含 purge+embargo）
- 门槛判定：`campaign.py` 的 `_candidate_promotion_passes` / `_qqq_capture_gate_passes`
- DSR/PBO/SPA：`campaign_statistics.py`（**禁改，只能调用**）
- 有效 N：P1a 的新模块

### 5.4 验收标准

- 用 VOL02 跑通，结果与 `reports/research/recalibrated/vol02-recalibrated-evaluation.json`
  **数值一致**（这是回归基线，证明提炼没有改变行为）；
- 能用同一接口跑一个 2 候选的小型参数搜索，产出含 `effective_n` 的裁定报告；
- 新机制接入只需写信号函数 + 参数空间声明，**不超过 100 行**。

---

## 6. 工作项 P2：QD 搜索 + 表达式树/遗传编程

**依赖 P1a 完成。** 用户明确要求做表达式树/遗传编程，但要求"注意避免过拟合和未来函数的问题"。

### 6.1 分两步，先易后难

**P2a：同机制内参数搜索**（先做，风险可控）
- 在 `kernel/` 下实现 `bounded_parameter_mutation`（原枚举值无实现）；
- 网格 + 有界变异，父代从 QD 精英里选；
- 多维描述子（不要只用 `mechanism_family` 一维）——建议加入如"持仓天数中位数"、
  "对 QQQ 相关性"、"换手率"等**行为**维度，这才是 MAP-Elites 的本意。

**P2b：表达式树 / 遗传编程**（后做）
- 候选是可组合的公式树（因子 → 信号）。

### 6.2 防过拟合（外部研究结论，必须落实）

| 陷阱 | 文献结论 | 必须实现的防护 |
|---|---|---|
| **GP 膨胀** | GP 倾向加深/加长公式提升样本内表现，样本外崩坏 | **硬限制表达式深度 ≤4、节点数 ≤12**；限定算子集合 |
| **Alpha 快速衰减** | 传统 GP 挖出的 alpha 衰减极快，根源是过拟合 | 要求跨 regime 的折都为正（≥3/5）|
| **有效 alpha 极稀疏** | 搜索空间里有效 alpha 密度极低 | 预期低命中率，**不许因为"跑了500个没结果"就放松门槛** |
| **数据窥探** | 公认问题 | P1a 的诚实聚类 N + 已有 PBO/SPA |

来源：https://arxiv.org/abs/2412.00896 · https://arxiv.org/html/2502.16789v2 · https://arxiv.org/pdf/2505.11122

### 6.3 防未来函数（硬性）

- **所有特征必须只用 `t-1` 及更早的数据**，信号在 `t` 收盘确认、`t+1` 开盘执行；
- 复用 `rolling_origin.py` 的 purge + embargo，**不要另写一套**；
- 表达式树的算子集合**禁止包含任何前视算子**（如 `future_return`、居中移动平均、
  全样本 z-score / 全样本分位数）——所有滚动统计必须是**因果的**（只回看）；
- **必须写测试**：构造一个已知含未来信息的表达式，断言被拒绝。

### 6.4 分层结构（让宽搜索合法的关键）

```
第1层 撒网(discovery)  : 训练分区上跑几百个候选,不碰评估流
                         ↓ 按质量+多样性筛
第2层 精英(QD archive) : 每个描述细胞留少数精英
                         ↓ 收益序列聚类 -> 有效N (P1a)
第3层 门(gate)         : 有效N ≤32 才允许进,DSR/Sharpe/CAGR 全套
```

---

### 6.5 机器吞吐预算（实测，不是估算）

在 2026-09-01 于本机实测 `load_sip_bars`，搜索循环必须按这些数字设计，
否则会重蹈 `pytest -n auto` 把机器 OOM 的覆辙。

| 场景 | 耗时 | 峰值 RSS |
|---|---:|---:|
| 日线 1 只 × 11 年（冷，首次建分片索引） | 15.2s | 0.14 GB |
| 日线 5 只 × 11 年（热） | 1.0s | 0.16 GB |
| 分钟 1 只 × 1 季度（冷，扫 3672 个分片页脚） | 47.1s | 0.26 GB |
| 分钟 1 只 × 1 季度（热） | 1.0s | 0.38 GB |
| 分钟 10 只 × 1 季度（热，43 万行） | 5.7s | **0.97 GB** |

三条由此得出的硬约束：

1. **分片索引缓存只在进程内**（`_SYMBOL_RANGE_CACHE`）。每个新进程都要重付冷启动代价——
   日线 15s，分钟 47s。搜索循环必须**跑在一个长驻进程里**，不要每个候选起一个子进程。
2. **分钟线内存是真正的天花板**：10 只 × 1 季度就吃掉 1GB。本机可用内存约 1.8GB，
   且后台还有抓取进程。**10 只 × 1 年（约 170 万行）会 OOM。**
   分钟级搜索必须按时间分块流式处理，或把标的池压到 ≤10 只。
3. **日线几乎免费**（全市场 11 年才 543MB）。**P2a 的参数搜索先全部在日线上做**，
   只有已经过门槛的候选才值得付分钟线的代价。

## 7. 工作项 F：自动循环接入真实数据

沿用前置计划 `plan-kernel-extraction-and-auto-research-real-data-2026-08-28.zh.md` 的 §3，
但有两处**修订**：

1. 数据源不再走 `capabilities/registry.yaml`（禁改），改用 D2 的 SIP parquet 加载器；
2. 族内预算约束的是 **P1a 的聚类数**，不是候选数。

`open_composer/research/auto_research.py:132` 目前硬拒非 sample 数据源。改为：
已预注册迭代 + 使用 SIP 加载器 + 聚类后有效 N ≤32 时放行；否则保持现有行为。

---

## 8. 执行顺序

**分钟线抓取正在后台跑（约 25 小时），但绝大部分工作不依赖它。不要空等。**

```
P1a(有效N聚类)   <- 最先做:纯数学,零数据依赖,且阻塞 P2
   |
   +-- D2(SIP加载器)   <- 10年日线已全部就绪,现在就能做
   +-- D3(清理IEX)     <- 无依赖
   +-- P1b(评估工具链) <- 用日线即可验证
          |
          v
       P2a(参数搜索) -> P2b(表达式树/GP)
          |
          v
        F(自动循环)
          |
          v
       D1(验证分钟线抓取完成)  <- 放到最后
```

各工作项对分钟线的依赖：

| 工作项 | 依赖分钟线 | 现在可否开工 |
|---|---|---|
| P1a 有效N聚类 | 否（纯数学） | ✅ 立刻 |
| D2 SIP 加载器 | 否（日线已就绪） | ✅ 立刻 |
| D3 清理 IEX | 否 | ✅ 立刻 |
| P1b 评估工具链 | 否（日线可验证） | ✅ 立刻 |
| P2 搜索 | 否（但依赖 P1a） | P1a 完成后 |
| F 自动循环 | 否（但依赖 P1a） | P1a 完成后 |
| D1 验证抓取 | 是 | 最后做 |

### 8.1 抓取任务的监督与完成判定

后台有一个看门狗 `scripts/fetch_watchdog.sh` 在跑，它会：
进程死了自动重启；15 分钟没写出新 shard 判定卡死并重启；空闲内存 <250MB 时先等；
看到完成标记后自行退出。**重启永远安全**，抓取器会跳过已存在的 shard。

**判断是否完成，只需检查标记文件**（不要去翻日志）：
```bash
ls data/sip/minute/_COMPLETE_2023_2026.json    # 存在即代表 3.5 年分钟线抓完
cat data/sip/minute/_COMPLETE_2023_2026.json   # 含行数、耗时、标的数
```

**不要同时启动第二个抓取进程。** 实测单个抓取已经让这台 3.8GB 机器进入 swap
（曾因此卡死 30 分钟）。10 年分钟线（→Drive）必须等 3.5 年的完成标记出现后再启动。

每完成一项：跑验收标准 → `ruff` → `pytest` → 独立 commit。不要把多个工作项混在一个 commit。

## 9. 禁止事项

1. **不要用 `pytest -n auto`**（会 OOM）。上限 `-n 2`。
2. **不要修改 §1.1 禁改清单里的任何文件**（含 `quality_diversity.py`、`pyproject.toml`）。
3. **不要修复 `test_mom_breadth_qd_r1.py` 的 11 个既有失败**，不要碰 `mom_breadth_*` 目录。
4. **不要把 SIP 和 IEX 数据混用**——bar 数差 2.3 倍，混用是 PIT 灾难。
5. **不要把 `data/sip/` 提交进 git**（已 gitignore，不要绕过）。
6. **不要为了让候选通过而放松门槛**。宽搜索的正确代价是诚实的有效 N，不是更松的门。
7. 表达式树算子集合**不许包含前视算子**。
8. 不要碰 `.env`、券商密钥。不要动 paper/实盘写入路径。
9. 下载 Drive 数据前先 `drive_df` 看空间；不要碰 `gdrive:vps-backup`。

## 10. 完成的定义

1. `uv run pytest -q` 失败数**仍为 11 且全部来自 `test_mom_breadth_qd_r1.py`**；
   `ruff check .` 全绿；`oc repo check --strict` 为 `status=ok`。
2. `data/sip/` 有完整的 10 年日线 + 3.5 年分钟线，且有可用的加载器和测试。
3. 旧 IEX 数据已归档到 Drive 并从本地删除；知识库保留。
4. `effective_independent_trials()` 通过全部 5 条验收测试，并已接进门槛。
5. 评估工具链能复现 VOL02 的裁定数值，且新机制接入 <100 行。
6. 参数搜索可用；表达式树有深度/节点上限和前视算子拒绝测试。
