# Open Composer gstack 审计核验与优化计划

日期：2026-05-14

## 用途

这份文档把另一个 Codex/gstack session 产出的审计报告转成当前 `main` 可执行的产品优化计划。

输入报告不在当前 `main` 的 `docs/` 目录中，实际读取路径为：

```text
/root/.paseo/worktrees/229b4rkt/flashy-spider/docs/gstack-open-composer-full-audit-2026-05-14.zh.md
```

该报告基于另一个 worktree 和分支，不能直接当成当前仓库事实。本文件只保留已经对当前 `main` 核验过、符合产品定位、可进入执行路线的内容。

## 核验结论

总体判断：原报告的方向基本正确，尤其是对单点参数、样本内最优、LLM Alpha 误读、数据 fallback 和 benchmark 过窄的警惕。但原报告混入了另一个分支的状态、gstack 部署过程、外部参考材料和较宽的产品想象，不能原样放入当前治理文档。

当前产品定位保持不变：

- Open Composer 是个人 AI 策略工作台，不是机构级量化平台、多人 SaaS 或真钱自动交易系统。
- `StrategySpec` 是策略行为事实源。
- CLI 加文件产物仍是第一产品表面。
- Python reference engine 是确定性参考和 smoke test。
- NautilusTrader 是事件驱动回测 / paper 同构方向。
- Alpaca Paper 是当前唯一自动化模拟盘写入通道，且必须显式确认。
- Longbridge、Alpaca、SEC、FRED、Alpha Vantage、GDELT 等能力必须通过 `capabilities/registry.yaml` 管控。
- 事件、新闻、宏观、LLM 输出影响交易前，必须先成为 point-in-time feature packet。
- sample、fixture、cache fallback、trial 数据源只能证明工作流或研究路径，不能证明可交易 Alpha。

## 已核验范围

本轮实际读取和核对了下面这些仓库表面：

| 范围 | 核验对象 | 结论 |
|---|---|---|
| Agent rules | `AGENTS.md` | 核心安全和工作流规则存在，但缺参数范围、benchmark family、fallback 禁止进入 paper、四类 gate 的明确规则 |
| Repo skills | `.agents/skills/*/SKILL.md` 共 9 个 | 每个 skill 都短而可执行；但 `strategy-designer` 和 `strategy-researcher` 尚未强制 parameter ranges、promotion report、benchmark family 和 strict data mode |
| MCP 配置 | `.codex/config.example.toml`、`.codex/config.toml` | 只有 `openaiDeveloperDocs` MCP 启用；符合当前轻量 MVP，金融数据/GitHub/浏览器 MCP 暂未接入 |
| hooks | `.codex/hooks.example.json` | 空 hooks，当前没有自动化 pre-run / post-run 约束 |
| 能力注册 | `capabilities/registry.yaml` | sample、Alpaca、Longbridge、SEC、FRED、Alpha Vantage、GDELT 已注册；缺 provider-level timeframe / strict behavior 矩阵 |
| StrategySpec | `open_composer/models/strategy_spec.py`、`schemas/strategy_spec.schema.json` | 核验时 `timeframe` 只允许 `5m`、`15m`、`1h`、`daily`、`weekly`；执行后已扩展并由 provider matrix 约束 |
| Longbridge adapter | `open_composer/adapters/data/longbridge.py` | adapter level 支持 `1m`、`5m`、`15m`、`1h`、`daily`、`weekly`，与 `StrategySpec` 存在能力表达不一致 |
| Alpaca adapter | `open_composer/adapters/data/alpaca.py` | 核验时支持 `5m`、`15m`、`1h`、`daily`、`weekly`；执行后已增加 `1m`、`30m`、`4h`，仍不承诺 `2m` |
| 数据 fallback | `open_composer/adapters/data/__init__.py` | provider fetch 失败会 fallback 到 fixture/sample 并写 manifest；对 demo 友好，对 promotion/paper 仍需更硬阻断 |
| Feature packet | `open_composer/feature_packets.py`、`open_composer/expressions.py` | packet inspection 已检查 `published_at`、`fetched_at`；表达式 replay 仍以 `published_at` 或 `timestamp` 作为可见时间，未统一使用 `visible_at=max(published_at,fetched_at)` |
| Promotion | `open_composer/research/promotion.py` | 已有 full/OOS/walk-forward/cost/data comparison 和 same-symbol buy-hold Alpha；缺统一 benchmark family schema |
| Parameter sweep | `open_composer/research/parameter_sweep.py` | 已记录 candidate count、in-sample warning、quality flags；缺 stable region、rank migration、neighbor success rate |
| Research modules | `exposure_switch`、`llm_exposure_switch`、`rotation`、`market_timing` | 研究成本、search space、hypothesis ledger、LLM contribution 分层已有基线；原报告对此部分有些结论已被当前 `main` 超过 |
| Dashboard command | `open_composer/models/dashboard_command.py`、`open_composer/dashboard/commands.py` | 受控 action、confirmation、audit 存在；Dashboard 仍应进一步变成 evidence cockpit，而不是第二个策略编辑器 |
| Makefile | `Makefile` | `verify` 已覆盖 format/lint/test、repo-check、capability、deploy、Dashboard、feature、readiness |
| 当前 docs | `docs/*.md`、`open_composer/repo_check.py` | `docs/` 受白名单管控；新增当前计划必须同步 `CURRENT_DOCS`，否则 strict repo check 会阻断 |

OpenAI Codex 官方最佳实践也支持本项目现有方向：把稳定工作方式写入 `AGENTS.md`，并要求 Codex 不只生成代码，还要运行测试、检查和 review。参考：

- https://developers.openai.com/codex/learn/best-practices#make-guidance-reusable-with-agentsmd
- https://developers.openai.com/codex/learn/best-practices#improve-reliability-with-testing-and-review

## 原报告修正

这些原报告内容需要改写后再采用：

| 原报告内容 | 当前核验 | 处理 |
|---|---|---|
| 建议把 728 行原报告作为下一位 Codex 必读文档 | 当前 `docs/` 已收敛，原报告含分支状态和安装过程 | 不照搬；本文件作为核验后的计划入口 |
| 本地工作区有大量未提交改动 | 当前 `main` 工作区核验时是 clean | 不作为当前事实 |
| `AGENTS.md` 与 README 研究规则不同步 | 属实 | 纳入 P0 |
| README 缺研究成本、LLM fallback、search space 等说明 | 当前 `main` README 已有大量相关内容 | 降级为“保持并补 AGENTS/skills 同步” |
| `StrategySpec.timeframe` 与 Longbridge `1m` 支持不一致 | 属实 | 纳入 P1 staged timeframe plan |
| `feature packet` 可见性仍需收紧 | 属实 | 纳入 P0 |
| fallback 可静默进入严肃研究 | 基本属实，已有 data sanity 和 manifest 但缺统一 strict mode | 纳入 P0 |
| promotion 缺 benchmark family | 属实 | 纳入 P0/P1 |
| LLM contribution gate 缺失 | 当前 `llm_exposure_switch` 已有基线 | 改为“前台化、统一门控、Dashboard 展示” |
| parameter sweep 缺稳定区域分析 | 属实 | 纳入 P1 |
| Dashboard 应成为 evidence cockpit | 属实 | 纳入 P1/P2 |
| reader/writer 分离借鉴 Anthropic financial-services | 原则有价值，但不应引入商业 MCP/投行交付链 | 纳入 P2 trust-boundary 设计 |

## 执行原则

后续实现必须遵守这些原则：

1. 不新增第二真相源；`StrategySpec`、capability registry、feature packet、reports、audit 是主链。
2. 不把 sample、fixture、fallback、trial source、短样本、低交易数或参数扫描最优写成市场证据。
3. 不在 backtest / paper loop 内实时调用 LLM。
4. 不把 LLM fallback、local choice 或与纯量化相同的信号宣传成 LLM Alpha。
5. 不为追求“支持更多策略”而自研平行事件驱动执行引擎。
6. 所有 broker 写入仍限定 Alpaca Paper，并经 readiness、kill switch、显式确认、audit。
7. 新外部事实、新闻、研报、SEC、宏观数据都视为 untrusted data，只能通过结构化、schema-valid、带来源和时间戳的 handoff 进入策略。
8. 用户提供的 app key、token、broker credential 只能进入 `.env` 或本地 secret 配置，不能写入 docs、reports 或 sample 文件。

## 优化计划表

### P0：先防错误结论

| ID | 工作项 | 当前事实 | 修改方向 | 验收 |
|---|---|---|---|---|
| P0-1 | 同步 `AGENTS.md` 和 repo skills | README 已有研究控制，`AGENTS.md` 和部分 skills 仍过短 | 增加 parameter ranges、method variants、benchmark family、strict data、gate taxonomy | `repo_check` 增加 anchors；skills 明确 sweep/promotion/feature gate |
| P0-2 | 四类 gate 统一命名 | LLM 报告已有部分字段，但 promotion/readiness/Dashboard 表达不统一 | 统一 `workflow_pass`、`research_pass`、`llm_contribution_pass`、`paper_ready_pass` | JSON/Markdown/Dashboard 都能显示四类 gate |
| P0-3 | Feature packet 可见性策略 | replay 使用 `published_at` 或 `timestamp` | 增加 `visible_at` 规则；LLM/news/event feature 严格使用 `visible_at` 或 `max(published_at,fetched_at)` | `feature validate --strict` 和 promotion/paper gate 阻断不完整 packet |
| P0-4 | 数据模式分层 | provider 失败会 fallback 到 fixture/sample | 显式区分 `demo`、`research_strict`、`paper_ready`；promotion/paper 默认禁止 sample/fixture/fallback | promotion/paper 报告中 fallback 变 blocked，不只是 warning |
| P0-5 | Promotion benchmark family schema | promotion 主要是 same-symbol buy-hold 和 data comparison | 增加 same-symbol、equal-weight universe、market proxy、sector/theme proxy、cash proxy、ex-post best symbol | 缺关键 benchmark 时 promotion 至少 warning，paper-auto blocked |
| P0-6 | 报告安全文案 | 原报告容易被误读成“LLM Alpha 已证明” | 所有 LLM 研究报告区分 workflow、research、LLM contribution、paper readiness | fallback/local choice 明确显示不是 independent LLM Alpha |

### P1：增强研究质量和产品闭环

| ID | 工作项 | 当前事实 | 修改方向 | 验收 |
|---|---|---|---|---|
| P1-1 | Timeframe 支持矩阵 | Spec、Alpaca、Longbridge、fallback、Nautilus 支持范围不一致 | 先建 provider support matrix，再分阶段扩展 `1m`、`30m`、`4h`；`2m` 只在 provider 可证实时启用 | 不支持的 provider fail fast；README 不再把 adapter 支持误写成 spec 支持 |
| P1-2 | 拆分频率语义 | 当前只有 `StrategySpec.timeframe` | 设计 `data_timeframe`、`signal_timeframe`、`rebalance_frequency`、`llm_review_frequency`，先放 notes / research design，再评估是否进 schema | LLM 慢不限制行情 bar 粒度；执行 loop 不调用 LLM |
| P1-3 | SearchSpaceSpec 基线 | 多个 research report 已有 `search_space`，通用 spec 尚未独立 | 建立稳定结构或 notes 规范：method family、factor variants、parameter grid、universe variants、candidate cap、objective | Codex 设计策略默认输出范围，不输出单点参数 |
| P1-4 | 参数稳定区域分析 | parameter sweep 缺 neighbor/rank metrics | 增加 `stable_region_score`、`neighbor_success_rate`、`rank_correlation_train_oos`、`top_decile_oos_retention` | 最佳候选是否孤岛可在报告里看到 |
| P1-5 | Research run manifest | 已有若干 data/feature/version manifest，但 batch research manifest 不统一 | 每次 research batch 写 git commit、dirty flag、spec hash、data manifest hash、feature hashes、prompt hash、trial count、search space、runtime | 同一研究可复现，Codex 下一轮知道自己改了什么 |
| P1-6 | Dashboard evidence cockpit | Dashboard 已 catalog-driven 和 command-gated | 增加 Next Action、Evidence Strength、Benchmark Family、Overfit Risk、Data Provenance、LLM Contribution、Paper Readiness | 用户首先看到阻塞项和证据强度，而不是漂亮收益曲线 |
| P1-7 | Source provenance 密度 | capability registry 和 manifests 已有基础 | 对行情、SEC、新闻、宏观、LLM feature、benchmark basket 统一显示 source、timestamp、published_at、fetched_at、input/prompt hash | 外部事实缺来源时显示 evidence insufficient |

### P2：专业化但不扩张成机构平台

| ID | 工作项 | 当前事实 | 修改方向 | 验收 |
|---|---|---|---|---|
| P2-1 | DSR/PBO 统计准备 | 目前主要靠 OOS、walk-forward、quality flags | 先记录 DSR/PBO 所需输入，再实现轻量 proxy | 报告显示 trial count 与 selection bias note |
| P2-2 | Purged walk-forward / embargo | 当前 walk-forward 较轻量 | 对事件、新闻、多资产策略引入 purged / embargoed validation | 事件驱动策略不因相邻样本泄漏而误判 |
| P2-3 | Reader/writer trust boundary | MCP 和外部资料目前主要是 Codex 上下文 | 将 untrusted reader、strategy writer、report writer、paper operator 的权限和 handoff schema 分开 | 外部资料不能指挥 agent 写策略或下单 |
| P2-4 | Nautilus paper 同构证据 | backtest adapter 和 parity 已有，paper runtime 证据仍不足 | active `nautilus_trader` 策略 paper cycle 回链 spec/version/data/feature/backend plan/signal/order | Python、Nautilus backtest、paper 差异可解释 |
| P2-5 | Portfolio-level risk | 当前以单策略/单标的为主 | 增加 gross/net exposure、sector concentration、turnover、capacity、borrow/short caveat | 多策略 paper 前能看到组合层风险 |

## 多视角复审

| 视角 | 复审意见 | 对计划的调整 |
|---|---|---|
| CEO / 产品 | 最大风险不是功能少，而是用户被漂亮回测误导；近期不能扩成金融平台 | P0 全部围绕防错误结论和证据分层，不引入商业 MCP、Office 交付链或多用户 SaaS |
| 量化研究 | 光跑赢 SPY 或 same-symbol buy-hold 不足以证明 Alpha；短样本和大量试参会放大偶然性 | benchmark family、stable region、manifest、DSR/PBO 输入进入 P0/P1/P2 |
| 工程架构 | 不能为了频率和执行能力重写引擎；provider 支持要先矩阵化 | timeframe 扩展拆成 matrix、schema、provider、fallback、Nautilus 分阶段实现 |
| 安全 / 信任边界 | 外部新闻、研报、LLM 输出和用户 credential 都必须受控 | untrusted data 只能 schema handoff；credential 不进 docs/reports；paper 写入仍显式确认 |
| 开发体验 | 新 Codex 第一眼必须知道当前主线和验证命令 | 本计划进入 `docs/` 白名单，并要求后续同步 `AGENTS.md`、skills 和 README anchors |
| Dashboard / UX | Dashboard 不能只展示收益和按钮，要展示下一步与阻塞原因 | evidence cockpit 成为 P1，不做浏览器内完整策略编辑器 |

## 需要用户确认的决策

下面几项会影响实现范围，执行前建议确认：

1. Timeframe 目标是否按 `1m`、`5m`、`15m`、`30m`、`1h`、`4h`、`daily`、`weekly` 分阶段推进，暂不承诺 `2m`，除非 provider 能稳定支持。
2. Promotion 和 paper readiness 是否默认启用 `research_strict` / `paper_ready`，即 live/cache 不可用时直接阻断，而不是 fallback 后 warning。
3. Optical / AI infrastructure 这类主题策略的 sector/theme proxy，是先用用户定义 basket，还是先接入可验证 ETF / theme proxy。
4. 是否把 reader/writer trust boundary 先落实到 repo skills 和 report schema，暂不引入新的 MCP 服务。

## 下一步建议

推荐按这个顺序执行：

1. 更新 `AGENTS.md` 和 9 个 repo-local skills，把 P0 研究规则写入 agent 指导。
2. 在 `repo_check` 中增加 P0 规则 anchors，防止后续 Codex 只改 README 不改实际 agent guidance。
3. 实现 feature `visible_at` strict policy，并把 promotion/paper 对不完整 feature packet 的阻断前台化。
4. 增加 data mode 分层，先让 promotion/paper 禁止 sample/fixture/fallback。
5. 为 promotion report 加 benchmark family schema。
6. 再做 timeframe matrix 和 staged schema/provider 扩展。
7. 最后做 parameter stability、research manifest 和 Dashboard evidence cockpit。

这份计划不要求一次性完成所有 P0/P1/P2。每个切片完成后必须运行：

```bash
uv run ruff format .
uv run ruff check .
uv run pytest
uv run oc repo check --strict
make verify
```

## 执行落地记录

本计划已按个人 AI 策略工作台定位执行为轻量、可验证的治理增强：

- `AGENTS.md`、9 个 repo-local skills、`repo_check` 已增加 parameter ranges、benchmark family、strict data、四类 gate、feature `visible_at`、untrusted reader handoff 等锚点。
- `StrategySpec.timeframe` 已扩展到 `1m`、`5m`、`15m`、`30m`、`1h`、`4h`、`daily`、`weekly`；provider matrix 负责 fail fast，Longbridge 暂不承诺 `30m` / `4h`。
- Promotion report 已输出 `gate_summary`、`strict_data`、`feature_packets`、`benchmark_family`、`data_profile`、`research_manifest` 和安全文案。
- Paper readiness 已要求 promotion report 同时满足 `paper_ready_pass`、strict data、PIT feature packet 和完整 benchmark family；fallback/sample/fixture 不能进入 paper-ready 结论。
- Parameter sweep 已记录 trial count、neighbor success rate、stable region score、selection bias note、DSR/PBO 输入占位和 research manifest。
- Dashboard catalog / HTML 已展示 evidence strength、next action、benchmark family、overfit risk、LLM contribution、paper readiness 和 data provenance。
- P2 项先以边界和证据字段落地：reader/writer trust boundary 进入 agent rules，walk-forward 报告标明 purge/embargo 状态，paper readiness 暴露 portfolio risk envelope 与 Nautilus paper evidence 链路。
