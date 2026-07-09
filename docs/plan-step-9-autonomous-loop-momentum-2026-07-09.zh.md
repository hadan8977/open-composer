# Step 9 自主迭代循环 + 分钟线动量第 1 轮 + Paper 验证修复（2026-07-09）

> 执行者注意：本文档自包含，不依赖会话上下文。所有路径相对仓库根
> `/root/codex-test/open-composer`，在当前部署分支上继续（Step 8 已完成）。
> 先执行 Wave 9.P 修正并注册本文档，再按 Wave 顺序执行；每个 Wave 一个
> 独立提交；红灯即停，停时必须落盘 blocked 说明工件，不得静默绕过。

## 0. 背景与本轮定位（必要事实）

用户在 2026-07-09 确立了项目长期目标：**自主自动化的策略研发循环**。四条硬规则：

1. **先搜索后开发（硬门）**：每轮新策略生成或优化迭代，必须先完成外部检索
   学习（论文/文章/帖子/他人策略）并反思，产出简报工件后才能开始写策略。
2. **接入机器学习**：ML 肯定要接，但怎么接、怎么训由证据决定；既有纪律
   （`ml_beats_linear_baseline`、purged/embargo、受限搜索、trial ledger）不变。
3. **工具与架构整合**：充分复用既有资产（因子库、research kernel、
   capabilities registry、auto_research、成本敏感性、universe 审计）。
4. **实盘过渡**：策略 → paper 验证 → 用户批准 → 实盘（人工 review card）。
   paper 之后允许基于表现继续迭代，但**不允许每天改**。

本阶段具体策略目标：**美股分钟线动量策略**——面向**近期市场形势**（因子有
半衰期，不追求超长历史证据），频率上 1m/5m/15m/30m/1h 都允许探索，不预设；
多路并行、及时反思换路，不死磕一条路。长期补充方向：**AI 获取新闻/情绪等
非常规信息并转成信号**（本计划只做入口设计，见 §9，不在本轮实施交易影响）。

用户 2026-07-09 的三个决定（写死，Codex 不得更改）：

- **跨源重验（Step 8 Wave 8.5）的数据深度问题由用户自行解决，本计划不碰。**
  `route_cross_source_pass` 目前 blocked 的状态保留原样；实盘启动前置条件
  中该项标记为「用户延后处理」，实盘无论如何都需要用户逐项批准。
- **Paper 验证 Day-1 fail（state_drift_warning）必须修复**，并且把「失败必须
  有修复动作」固化成产品行为（见 Wave 9.0）。
- 实盘不着急：先把 paper 验证窗真正跑起来。

## 1. 目标与 Done 定义

| # | 目标 | Done 定义 |
|---|---|---|
| G1 | Paper 验证修复 | state drift 根因修复；paper 真实下单（仅 Alpaca Paper）后账户与引擎状态对齐；修复后首个交易日验证判定 pass；「失败日必须有 remediation 记录」进代码并有单测 |
| G2 | 迭代循环契约 | iteration dossier 目录契约 + 校验命令落地；外部简报硬门可校验；每轮必须产出 decision record；paper 阶段改动频率约束写死 |
| G3 | 分钟线可行性 | 逐 symbol×timeframe 的历史深度/质量探测报告 + 各频率带 go/no-go + 成本压力参数表 |
| G4 | 外部研究简报 | 动量第 1 轮简报按 schema 产出并通过校验（无简报则后续 Wave 阻塞） |
| G5 | 动量第 1 轮 | 3–4 条路径在统一门槛下完成受限搜索与评估，每条路径有 continue/pivot/stop 决策记录；阴性结果照常入档 |
| G6 | 后续入口设计 | ML 接入与 AI 信息接入的入口条件、门槛、受限范围写成设计说明（不实施） |

## 2. 执行纪律（历史教训，全程有效）

以下都是本项目此前真实发生过的问题，逐条为强约束：

1. **失败不修不算完成**：任何验证/循环/测试红灯，要么修复、要么落盘
   blocked 说明（原因 + 建议动作）并停止；禁止交付「第一天就 fail 且无
   处置」的状态。
2. 阴性结果必须追加进 tracked 迭代日志
   `reports/research/control/strategy-iteration-progress-2026-07-01.md`。
3. 测试不得把工件写进真实 `reports/research/control/`（用 tmp_path）。
4. 计划文档注册进 `open_composer/repo_check.py` 的 `CURRENT_DOCS` 与
   `tests/test_repo_check.py` 两处；**不得把 docs/plan-\* 移入 archive 来让
   检查变绿**。
5. 验证命令保留真实退出码：`uv run pytest -q 2>&1 | tail -3; echo
   "pytest_exit=${PIPESTATUS[0]}"`；禁止用管道吞掉非零退出。
6. 同数据纪律：任何对比都在同一数据 vintage 上重算基线，禁止跨工件比数字。
7. 受限搜索：每轮组合数上限写死后不得中途扩大；超出即停并记录。

## 3. Wave 9.P 计划修正与注册

1. 校验本文档引用的 CLI 命令形态与模块路径（`oc paper readiness` 为位置
   参数等），有出入先修正本文档并单独提交。
2. 注册本文档进 `CURRENT_DOCS` 与 `tests/test_repo_check.py`。
3. 本 Wave 不改任何产品行为。

## 4. Wave 9.0 Paper 验证修复（把 Day-1 fail 修掉并防复发）

现状事实：2026-07-09 每日循环 status=ok，但 `paper_order_authorization=false`
（router 处于 observation_only，信号 `decision=paper_orders_not_allowed`，
paper 账户实际未下单），账户持仓仍是旧状态 ⇒ `state_drift_warning` ⇒ 验证
日判 fail。不下单则漂移永不自愈，20 日验证窗永远过不去。

1. **补齐缺失的 readiness 工件**（`oc paper readiness <strategy> --strict`
   当前 warning 列出：`execution_policy`、`execution_reality_report`、
   `gap_stress_report`、`leveraged_etf_risk_note`、`paper_safety_review`、
   `source_cards`）。优先寻找并运行既有生成器（在 `open_composer/research/`
   与 CLI 中检索，如 execution_policy、短仓/杠杆风险、gap stress 相关命令）；
   确无生成器的按既有工件契约实现最小生成器。禁止手填数字。
2. **完成 router 下单授权**：使用 `open_composer/router_authorization.py`
   既有语义生成授权工件（缺 CLI 则加薄命令）。授权范围仅 Alpaca Paper；
   不得弱化 kill-switch、readiness、信号先落日志等任何既有控制。
3. **一次受监督对齐**：授权完成后跑一次每日循环并显式传递既有 allow 下单
   标志，让 paper 账户按当日 target weights 调仓到位；保存订单/对账工件。
4. **验证自愈**：对齐后的下一个交易日循环应无 `state_drift_warning`，验证
   日判定 pass；把该日判定表贴进提交信息。
5. **失败必须有处置（产品化，本 Wave 核心交付之一）**：
   - 扩展验证/循环机制：任何 counted-but-failed 验证日，必须在
     `reports/paper/validation/remediations/YYYYMMDD.md` 留 remediation 记录
     （原因、动作、状态）；
   - 次日循环开始时检查前一交易日：若 fail 且无 remediation 记录 ⇒ 产生
     error 级告警并计入当日循环日志与通知；
   - 单测覆盖：fail+有记录、fail+无记录（告警）、pass 三条路径。
6. 每日循环默认行为更新：授权工件存在且 kill-switch 清空时，循环携带 allow
   标志正常下单；授权缺失时保持 observation_only（现行为）。语义写进
   `docs/runbook-live-manual-execution.zh.md` 的前置检查清单。

## 5. Wave 9.1 迭代循环契约（自主研发循环的骨架）

目的：把「先搜索→受限搜索→评估→反思决策」固化成任何执行者（Claude/Codex）
都必须走的产品流程，而不是口头纪律。

1. **iteration dossier 目录契约**：`reports/research/iterations/<iter_id>/`
   （`iter_id` 形如 `mom_minute_r1`），包含：
   - `external-brief.md/.json`（外部研究简报，schema 见 Wave 9.3）；
   - `hypotheses.md`（可证伪假设清单，每条含预期失败模式）；
   - `search-space.md/.json`（路径×参数×组合数上限，引用既有
     research_brief 机制）；
   - trial ledger / 评估报告的路径引用；
   - `decision-record.md`（轮末反思：每条路径 continue/pivot/stop + 理由 +
     下一轮建议）。
2. **薄 CLI**：`oc research iteration init <iter_id>`（生成骨架）、
   `oc research iteration validate <iter_id>`（校验完整性；外部简报缺失或
   不合 schema ⇒ 非零退出）。核心逻辑进模块并带单测。
3. **硬门（流程绑定）**：本计划 Wave 9.4 开始前必须 `iteration validate`
   通过；后续所有策略轮次同样适用（写进 AGENTS.md 的研究流程段，一句话
   即可，不重写文件）。
4. **节奏约束**：已进入 paper 的策略，spec 变更需满足（a）有 decision
   record、（b）距上次变更 ≥10 个交易日（kill 规则触发的降风险除外）。在
   lifecycle/promotion 检查中加最小校验或至少在验证报告中显式检查并告警。

## 6. Wave 9.2 分钟线可行性探测（数据、成本、执行假设）

只测量、不做策略结论。全部结果进
`reports/research/control/minute-momentum-feasibility-<date>.md/.json`。

1. **探测宇宙（写死上限）**：
   - ETF 组（优先，规避个股幸存者偏差）：QQQ、SPY、IWM、DIA、11 只 SPDR
     行业 ETF、TQQQ、SQQQ、GLD、TLT、BIL ≈ 20 只；
   - 个股组：≤30 只当前高流动性大盘股（按成交额取前 30，声明为静态清单，
     **幸存者偏差 caveat 必须写进报告**）。
2. **深度/质量探测**：对每 symbol × {1m,5m,15m,30m,1h} 用
   `market.alpaca_bars` 探测可得历史首日、缺口率、零成交 bar 占比、
   盘前盘后数据是否混入。1m/5m 只取 5 只代表性 symbol 近 1 年做质量抽样，
   避免全量拉取。
3. **物化与隔离**：拉取的数据落 `data/research/alpaca_minute/`（或既有缓存
   结构的对应位置）+ manifest（symbol、timeframe、行数、首末日期、sha256），
   不得覆盖既有日线研究缓存；注意 API 限速，分批可续传。
4. **成本压力参数表**：按 timeframe 给出回测用滑点/点差预设（basis：IEX 非
   合并盘口的 caveat），并定义压力档 ×2、×4。此表是 Wave 9.4 所有回测的
   强制输入。
5. **执行假设**：第 1 轮统一 RTH-only（不含盘前盘后）；隔夜持仓是否允许由
   各路径显式声明。写进报告。
6. **产出 go/no-go**：按频率带（1m/5m 中高频、15m/30m 中频、1h 中低频）
   给出「数据可支撑回测」的结论与最大可用窗口。若某频率带历史 <18 个月
   ⇒ 该带本轮 no-go（样本不足），记录并跳过。

## 7. Wave 9.3 外部研究简报（先搜索后开发，硬门）

1. **schema**（`external-brief.md` + 结构化 `.json`）：
   - ≥8 个来源（其中 ≥3 篇论文级），每个来源一张 source card：URL、发表/
     更新时间、类型、可信度评级、核心主张、对本项目适用性、反思（该结论
     可能过拟合/过时/成本敏感的理由）；
   - 主题覆盖（检索清单）：日内/分钟级时序动量与反转、横截面动量的调仓
     频率与成本、隔夜 vs 日内收益分解、波动率管理动量与 momentum crash、
     市场日内动量（开盘前半小时效应类）、分钟级动量的交易成本实证；
   - 结论段：对 Wave 9.4 预设候选矩阵的**修订建议**（增/删/改路径，附理由）；
   - 与 `hypotheses.md` 联动：每条假设标注来源支撑与可证伪判据。
2. **执行方式**：若执行环境具备联网检索能力，按检索清单完成并写简报；
   若不具备，本 Wave 落盘 `blocked`（缺联网能力）并交回规划者补简报，
   **不得跳过此门直接进 Wave 9.4**。
3. 简报完成后运行 `oc research iteration validate mom_minute_r1` 必须通过。

## 8. Wave 9.4 动量候选矩阵第 1 轮（非 ML，受限搜索）

前置：Wave 9.2 的 go 频率带 + Wave 9.3 简报通过校验。以下预设矩阵可被简报
修订（修订须写进 decision record），但**总预算不得突破**。

1. **预设路径（3–4 条，命名前缀 `us_mom_minute_`）**：
   - P1 时序动量/趋势跟随：单 ETF（QQQ/SPY）15m–1h 突破/移动动量 + 波动率
     目标仓位；隔夜规则显式声明；
   - P2 横截面相对强度：ETF 宇宙（行业 SPDR + 风格）分钟数据日内 1–2 个
     固定决策点轮动，持有 top-k；
   - P3 隔夜/日内分解动量：隔夜收益与日内收益分别作为条件/信号（近年
     文献主题），RTH 执行；
   - P4 波动率调节动量：P1/P2 的信号叠加已实现波动率调节与 regime 过滤
     （复用 factor_library 中现有 regime/波动率因子）。
2. **预算（写死）**：每条路径 ≤24 个参数组合，全轮总计 ≤80；全部进 trial
   ledger（每条 trial 记 params、窗口、结果、数据 manifest 哈希）。
3. **统一评估门（全部满足才 continue）**：
   - 成本后为正：用 Wave 9.2 成本表基准档计算净收益；压力 ×2 档不翻负
     为加分项，写进报告；
   - purged walk-forward ≥4 折（embargo ≥ 信号视界），**近期权重**：最后
     两折（≈ 最近 6–12 个月）净收益必须为正且不输各自基准；
   - 基准族：QQQ B&H、BIL、该路径的 naive 动量基线（如无过滤的同频率
     动量）；
   - 每次回测产出报告（项目规则）；样本/回退 caveat 与幸存者偏差 caveat
     显式写明。
4. **纪律**：draft-first；`oc spec validate` 通过后才跑回测；不做 promotion、
   不碰 paper、不改活跃 spec；短历史（分钟数据首日决定）如实标注证据等级
   ——本轮定位是「近期形势动量」，前向 paper 验证权重更高，回测不冒充
   长历史证据。
5. **轮末产出**：`reports/research/iterations/mom_minute_r1/decision-record.md`
   ——每条路径 continue/pivot/stop + 理由 + 下一轮建议（含是否进入 ML 轮的
   判断依据）；阴性结果追加进 tracked 迭代日志。

## 9. 后续轮次入口条件（设计说明，本计划不实施）

1. **ML 轮（mom_minute_r2 候选）**：入口条件 = 至少一条路径过 Wave 9.4 全部
   门 + 该路径 OOS 决策样本 ≥800。范围：factor_library 特征在分钟 bar 上
   物化 + LightGBM vs 线性基线，`ml_beats_linear_baseline`（成本后、DSR
   校正）为硬门；purged/embargo（embargo ≥ label 视界）；组合数上限 12；
   复用 `open_composer/research/ml_backend/`，不重建。
2. **AI 信息接入轮**：入口条件 = 动量线有存活候选后。范围：对
   `news.alpha_vantage` / `news.gdelt`（均 trial）先跑 capability 评估；
   任何新闻/情绪要素必须先变成点时（PIT）feature packet（`visible_at`、
   `published_at`、`fetched_at`、`source`、`input_hash`、`prompt_hash`）；
   首轮仅 **advisory-only**（进 review card 与日志，不影响交易），
   `llm_contribution_pass` 需边际提升 + 缺模态鲁棒性报告后才允许影响行为。
   复用 `feature_packets.py`、`hybrid_news_evidence.py`、
   `alternative_data_evidence.py`、`llm_materialize.py`。

## 10. 边界与安全（全程有效）

- 不改 PDR 活跃 spec；paper 行为变更仅限 Wave 9.0 的授权与对齐路径。
- 实盘零自动化；实盘启动仍需用户逐项批准（跨源门由用户延后处理，此状态
  记录进 runbook 前置清单，不得删除该前置项）。
- 不触碰 `.env`/密钥；Alpaca/Longbridge 凭据只经既有配置面。
- 不新增第三方依赖；分钟数据拉取带 manifest、限速、可续传，不覆盖既有缓存。
- 研究缓存与黄金对照不重抓；同数据纪律全程适用。
- push 不在本计划范围（用户单独决策）。
- 每个 Wave 独立提交：9.P → 9.0 → 9.1 → 9.2 → 9.3 → 9.4。

## 11. 验收命令

每个 Wave 提交前：

```bash
uv run ruff format . && uv run ruff check .
uv run pytest -q 2>&1 | tail -3; echo "pytest_exit=${PIPESTATUS[0]}"
uv run oc repo check --strict
make verify
```

额外冒烟：

```bash
uv run oc paper readiness nasdaq_tqqq_post_drawdown_reentry_router_delayed30_offensive_paper_auto_candidate --strict   # 9.0 后 warning 项应消失或有书面豁免
uv run python scripts/run_daily_paper_cycle.py --dry-run                     # 9.0
uv run oc research iteration validate mom_minute_r1                          # 9.1/9.3
uv run oc data verify-research-cache                                         # 9.2 前后各一次（主缓存未动）
```

## 12. 交付清单

- [ ] 9.P：本文档修正 + CURRENT_DOCS/测试注册。
- [ ] 9.0：readiness 缺失工件补齐 + router 下单授权 + 受监督对齐 + 修复后
      首个验证日 pass + remediation 强制机制（含单测）。
- [ ] 9.1：iteration dossier 契约 + `oc research iteration init/validate` +
      节奏约束检查（含单测）。
- [ ] 9.2：分钟线可行性报告（深度/质量/成本表/执行假设/频率带 go-no-go）
      + 数据 manifest。
- [ ] 9.3：`mom_minute_r1` 外部研究简报（过校验）或 blocked 说明。
- [ ] 9.4：候选矩阵受限搜索 + 统一门评估 + trial ledger + decision record +
      迭代日志追加。
- [ ] §9 两个后续入口的设计说明随 decision record 一并落盘。

## 13. 用户操作清单（Codex 不得代做）

- 确认每日 cron 已安装且在跑（`crontab -l`；未装则
  `bash scripts/install_daily_cron.sh`）。
- 知悉并认可：Wave 9.0 后 paper 账户开始**真实提交 Alpaca Paper 订单**
  （仍仅模拟盘，实盘规则不变）。
- 第二数据源历史深度问题（跨源门）由用户自行解决，解决后通知重跑 8.5。
- 阅读 `mom_minute_r1` 的 decision record 并确认下一轮方向（ML 轮 / AI 信息
  轮 / 继续非 ML 迭代）。
- push 时机单独决策。
