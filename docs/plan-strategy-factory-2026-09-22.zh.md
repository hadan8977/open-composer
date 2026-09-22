# 计划：策略迭代工厂 — 2026-09-22（按用户当日要求重写）

> 读者：Fable 5.1 / Opus（迭代执行者）、Sonnet（小活）、Codex（工程）。没有上下文也能执行。先读 `docs/research-mission.zh.md` 和 `docs/current-view.zh.md` 最新章节。
> 用户 2026-09-22 原话要点：**尽快、直接地优化迭代出策略和模型并接入模拟盘；要"回测很爆炸"的策略；站在巨人肩膀上；这件事占 80% 精力和 token；迭代交给 Fable/Opus，小活交给 Sonnet；节省 token。** 电话会文本源不买；JEPA-like 模型先不做；四个现役 sleeve 由 Fable 决定。
> 一句话：不再从零发明策略。每周从"别人已发表、已实盘跟踪"的策略里挑 5 个，用冻结的近期窗口协议在本地复制、迭代两轮，活下来的立即接模拟盘；同时把大模型读文本这条只有我们能便宜做的线做成前向验证。

## 1. 什么叫"足够优秀"（上模拟盘的门槛，提议值，只有用户能改）

窗口沿用 H-20260918-05：warmup 2022-06→2023-09-15；**选择窗 2023-09-18→2025-12-31**（唯一用来排名）；**留出窗 2026-01-02→今天**（从不参与排名）；对标窗 2024-01-08→今天（与 SPMO 同窗）。成本 10 bp/边主口径、20 bp/边压力口径，信号日收盘出信号、次日开盘成交。

| 门槛 | 数值 | 为什么 |
|---|---|---|
| G1 对标窗年化 | ≥ 50%，且最大回撤 ≤ 35% | "爆炸"的可操作定义；SPMO 同窗 35.8% / −20.3% 必须两边都赢 |
| G1' 替代 | 夏普 ≥ 2.0 且年化 ≥ 30% | 允许低回撤高夏普型 |
| G2 留出窗 | 夏普 ≥ 1.0 且收益为正 | 没碰过的 2026 必须站得住 |
| G3 安慰剂 | 随机同构对照打赢真值的比例 ≤ 10% | 排除"菜单/杠杆/牛市"冒充信号 |
| G4 成本压力 | 20 bp/边下 G1 或 G1' 仍成立 | 换手高的策略在这里死 |
| G5 可执行 | 只用 Alpaca 现货多头（可做空的另标）、日线或分钟线、现有 cron 通道能下单 | 上不了模拟盘的不算 |

过 G1–G5 的候选：写卡、冻结规则、$15k 一个 sleeve、30 天彩排授权、带回撤清仓线（从最高点回撤 ≥ 1.5 × 对标窗最大回撤 × 0.5，取 12%–30%），同时上线的新 sleeve ≤ 3 个。**新 sleeve 的授权按用户 09-22 "尽快接入模拟盘" 的委托执行，范围仅限 Alpaca Paper、每 sleeve ≤ $15k、总额 ≤ $45k；超出范围另问。**

## 2. 分工与 token 纪律（硬规则）

| 角色 | 做什么 | 不做什么 |
|---|---|---|
| Fable 5.1 主会话 | 每周一次裁定：选候选、审结果、更新 current-view；写 brief | 不跑网格、不读大文件、不做采集 |
| Opus / Fable 迭代执行者 | 按 brief 复制一个候选：预注册网格 → 跑 → 安慰剂 → 复盘卡。一个候选一个会话 | 不自行扩网格、不改门槛、不搜索已在 brief 里的东西 |
| Sonnet | 采集清单、来源快照、周报、cron、截图、格式化 | 不做判断、不写策略逻辑 |
| Codex | 工程：采集器、打分器、评估器、cron、修 bug | 不做研究裁定 |

- 每个任务 = 一个 brief 文件（`reports/research/briefs/<id>.md`，≤ 60 行）+ 一个结果文件；下一个会话只读这两个，不重放历史。
- 同时最多 2 个执行者；子代理 ≤ 15 次工具调用；不跑全量 pytest；长任务走 `scripts/run_capped.sh --mem 1.8G` 并可断点续跑。
- 批量文本打分只用用户给的端点（第 7 节），不用 Claude 订阅额度。
- 一个候选最多迭代 **2 轮**；第 2 轮只允许 brief 里预注册的变化（参数区间、风险覆盖、波动率目标、股票池）。两轮不过就否定并写教训，不恋战。

## 3. 三条轨道

### 轨道 B（40%）复制工厂：别人已发表 / 已实盘跟踪的高近期收益策略

**B0 协议（冻结，复用引擎 `scripts/run_h20260918_05_recent_menu.py` 的窗口、成本、安慰剂实现）**：每个候选 ≤ 100 个预注册 cell；安慰剂三件套：同菜单随机挑选 60 种子、门控信号随机日历平移 1–20 日、随机方向（日内类）；杠杆与做空波动率产品只按招募说明书类别排除；复盘必报 SPY / MTUM / SPMO / 同波动超额 / 安慰剂五个数。

**B1 每周采集（Sonnet，≤ 15 次调用，产出 ≤ 800 字表格）**，来源固定：
1. Composer 公开 symphony：按 OOS（"out-of-sample start"）≥ 12 个月、年化 ≥ 50% 排序，记录规则描述、资产、OOS 起始日、年化、回撤、夏普。09-22 已核实一例：`v6 Symphony Sorter` OOS 自 2023-09-22，年化 144.8%，回撤 −48.4%，夏普 1.81，逻辑 = 20/200 日均线趋势 + RSI 过热 + 波动率/债券压力三门控，风险开时 TQQQ/SOXL/TECL/UPRO，风险关时 UVXY/VIXY/SQQQ/SOXS 或 BIL/SHY/TLT/XLP/XLV。阈值不公开，需本地预注册重建。
2. Quantpedia 2025–2026 新增策略页（免费描述 + 论文链接）。
3. SSRN / arXiv 2025–2026：关键词 "ETF rotation", "leveraged ETF", "intraday momentum", "earnings call LLM", "news LLM returns", "short-term reversal", "overnight returns"。
4. Concretum、Allocate Smartly 公开文章；QuantConnect 社区带 live 结果的策略；GitHub 带 OOS 起始日的仓库。
每条记：规则是否完整公开、资产、报告的 2024 年后表现、是否有实盘/OOS 跟踪、代码与许可。已在本地否定过的家族（见 current-view "已被否定的"）直接标 refuted 不再报。

**B2 每周挑选（Fable）**：≤ 5 个候选，每个必须满足：规则可复现、2024 年后有报告结果或 OOS 记录、本地数据能跑、Alpaca 能执行。每个写一张 H 卡（含情报节、最便宜的决定性测试、否定条件）、`direction-review.json`，过 `oc research direction-check`。

**B3 复制 + 迭代（Opus/Fable 执行者，一个候选一个会话）**：第 1 轮原样复制（作者规则 + 我们的窗口/成本/安慰剂）；第 2 轮预注册变体。产出 iteration 目录 + 复盘卡。

**B4 上线（Fable）**：过 G1–G5 → 冻结规则 → `oc paper` 彩排授权 → cron。

**第 1 周种子候选（09-22 裁定，不必再采集）**：
| # | 候选 | 巨人 | 本地要验什么 |
|---|---|---|---|
| B-1 | 杠杆科技轮动 + 三门控（趋势 / RSI 过热 / 压力）+ 对冲腿 | Composer `v6 Symphony Sorter` 家族，OOS 3 年 | 本地 L-20260918-05 已证明单一均线门控在牛市窗口不过安慰剂；新元素是 **RSI 过热减仓** 与 **VIX/反向 ETF 对冲腿**。预注册：RSI 窗口 {10,14} × 过热阈值 {75,80,85} × 压力门 {VIX 期限结构倒挂, TLT 20 日趋势} × 风险关资产 {BIL, SQQQ 25%} ≤ 48 cell |
| B-2 | S3 加波动率目标与回撤刹车 | Moreira-Muir 2017 波动率管理（顶刊，多次复现）；S3 本地 145% / −56% | 目标年化波动 {40%, 60%}、21 日实现波动率、杠杆上限 1；回撤 −25% 减半仓。问：能否把 −56% 压到 −35% 内而年化 ≥ 50% |
| B-3 | 行业轮动短回看 | Moskowitz-Grinblatt 行业动量；S1 本地安慰剂 2% | 回看 {21, 42, 63} × 持有 {1, 2} × 周频；当前是轮动剧烈市场，短回看是否更好 |
| B-4 | 财报新闻稿语气 → 次日（轨道 A 主线） | Yu et al. 2026-06 | 见轨道 A |
| B-5 | 新闻标题 LLM 打分 → 次日（本地已有 68.5 万条带 visible_at 的 Benzinga 标题） | Lopez-Lira & Tang 2023/2025，Chen-Kelly-Xiu | 见轨道 A T6；只测成交额前 1,500 的流动池 |

### 轨道 A（40%）大模型读文本 → 次日（H-20260922-01；只有我们能便宜做的线）

沿用 `docs/plan-earnings-text-forward-test-2026-09-22.zh.md` 的 T1–T5，改动：打分模型 = 用户端点（第 7 节）；不买电话会文本，只用 8-K Item 2.02 新闻稿；新增 **T6 新闻标题**：
- T6（Codex 工程 + Opus 评估）：`data/features/news_packets/`（68.5 万条，字段 symbols/headline/summary/visible_at）→ 只取成交额前 1,500 的股票、2024-01 起 → 先 2 万条试点打分（估 300 万 token）→ 每股每日聚合分 → 次日开盘进、收盘出与 +1/+5 日；同样的五分位、成本、安慰剂（标题随机错配）；价格基线 = 当日收益与相对成交量。试点通过（Q5−Q1 ≥ 30 bp/日且占位 ≤ 50%）再扩到全量。
- 历史段结论一律标"可能含模型记忆，量级参考"；真正裁定靠 10-13 起的前向影子。

### 轨道 C（20%）现役 sleeve 运营（用户 09-22 委托 Fable 决定）

- C1（Codex，10-01 前）：S1、S2、S3、top50 彩排各续 30 天，同额度；加回撤清仓线 S1 12%、S2 15%、S3 25%、top50 15%（从各自 sleeve 权益最高点算，日检，触发即 `oc paper revoke-rehearsal` 该 sleeve 并写 control_history）。S2 明确标注为"科技篮子 beta 对照"，不算研究成果。
- C2（Sonnet，每周五）：四个 sleeve 前向周报：净值、vs SPMO、vs 同菜单等权、成交偏差；写进 `reports/paper/rehearsal/weekly-<date>.md`，cockpit 自动可见。
- 淘汰：任一 sleeve 触发清仓线，或前向 60 日夏普 < 0 而 SPMO > 0.5，停，不复活。

## 4. 日历

| 周 | 轨道 B | 轨道 A | 轨道 C |
|---|---|---|---|
| W1 09-22→09-28 | B-1、B-2、B-3 三张卡 + direction-review；Opus 跑 B-2、B-3（各 ≤ 100 cell，几分钟）；Sonnet 采集 #1 | Codex T1 事件表、T2 打分器（含 429 退避与断点）、T4 采集器；T6 试点 2 万条 | C1 写好清仓逻辑与测试 |
| W2 09-29→10-05 | Opus 跑 B-1（需 VIX/期限结构数据，先查本地 Cboe 指数能力）；第 2 轮迭代；过 G1–G5 的写 sleeve 申请 | T3 历史段（2024-01→今）跑完；T6 若通过扩全量夜跑 | 10-01 续期 + 清仓线上线 |
| W3 10-06→10-12 | 上线 ≤ 3 个新 sleeve；采集 #2 → 挑 5 个 | T4 前向 dry-run 一周对账 | 周报 |
| W4 10-13→ | 第 2 批复制 | Q3 财报季前向影子正式记录；每周五周报 | 周报 |
| 11-14 | 第 3 批 | 财报文本裁定；通过 → sleeve | 30 天续期决定 |

每周日 Fable 更新 `docs/current-view.zh.md`：本周否定了什么、活下来什么、下周 5 个候选。

## 5. 不做

Stocks in Play / ORB；Alpha158 全年重建；H-20260917-02 网格；Qlib 六单元；期权；电话会文本采购；JEPA-like 模型接入；任何没有 2024 年后公开结果的"自创"变体；第 3 轮迭代。

## 6. 记录与闸门

每个候选 = 一张 H 卡（含情报节）+ `reports/research/iterations/<id>/`（candidate-manifest、direction-review.json、cells、placebo、summary、report）+ 教训卡。新 iteration 必过 `oc research direction-check` 与 `oc research iteration validate`。门槛数字只有用户能改；执行者发现门槛不合理只能写在复盘里。

## 7. 打分端点与限流

- 凭据文件：`/root/.config/open-composer/text-scorer.env`（mode 600，仓库外），变量 `OC_TEXT_SCORER_BASE_URL` / `OC_TEXT_SCORER_API_KEY` / `OC_TEXT_SCORER_MODEL`。脚本用 `set -a; . 该文件` 或 python-dotenv 读取；**任何日志、报告、manifest 只记模型名和提示词哈希，不记 URL 之外的东西，绝不记 key**。
- 端点是 OpenAI 兼容的 chat/completions；09-22 探测一次成功（见本轮记录）。
- **5 小时滚动限额**：每次调用记录 usage；收到 429 或限额错误即停止本批，写 `next_try_at`，由 cron 在下一个 10 分钟 tick 重试；每 100 个事件落一次 checkpoint；夜间 00:00–06:00 UTC 跑大批量，白天只跑前向增量；试点 200 个事件先测出每小时可用吞吐再定批量。
- 提示词与实体中性化见 `docs/plan-earnings-text-forward-test-2026-09-22.zh.md` 第 3 节；`temperature=0`，`response_format` 若端点支持则用 JSON 模式，否则正则抽取并对失败样本重试一次。
