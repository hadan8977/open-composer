# Codex Signal Desk MVP

Date: 2026-05-08

## 1. 一句话结论

新版本不应继续沿着 EvoQ 当前的 Dashboard-first 产品形态走。

更合适的 MVP 是一个 **repo-native Codex workbench**：

```text
你用自然语言和 Codex 对话
  -> Codex 在受约束的项目仓库里生成策略 spec、代码、测试、回测和报告
  -> deterministic runner 定时扫描 5m/15m/1h/daily 信号
  -> 只在候选信号出现后调用轻量 LLM 做事件/文本/风险审查
  -> 生成可读的 signal card
  -> 你手动交易并写入 journal
  -> Codex 周期性复盘、改进策略和测试
```

这更接近 Composer 的自然语言策略体验，但不复制它的封闭券商产品路径。产品第一版不是一个网页，也不是一个自动交易 bot，而是一个个人策略工作台。

## 2. 为什么不是继续做 EvoQ

EvoQ 当前的主要问题不是某个模块坏了，而是产品形态错位：

- 你想要的是“对话式生成、优化、解释策略”，而不是手动操作每个研究/运行环节。
- 你目前主要希望手动交易，系统先生成信号和决策卡，不需要一开始就打通自动下单。
- Dashboard-first 会提前把复杂性压到 UI、配置、后端状态机、部署和权限系统上。
- 对个人使用来说，最重要的资产是策略代码、数据快照、回测报告、信号日志和交易复盘，而不是大型 Web 产品。

因此新 MVP 应该把 EvoQ 当成参考库和教训，而不是在原 Dashboard 架构上继续加功能。

## 3. 三种 Codex 集成形态的判断

### 3.1 只做项目文件夹和规则

结论：必要，但不够。

优点：

- 最轻量。
- 策略、报告、日志都天然可审计。
- Codex 很适合在一个清晰仓库里读写代码、跑测试、改文档。
- `AGENTS.md` 可以给 Codex 提供项目级约束。OpenAI 文档说明 Codex 会在工作前读取 `AGENTS.md`，并按全局、项目、子目录层级合并指导。

缺点：

- 规则是软约束，不是产品。
- 不能保证策略 spec 合法。
- 不能保证回测没有运行。
- 不能保证 LLM 输出可解析。
- 不能自动形成信号、journal 和复盘闭环。

判断：

项目文件夹是底座，但必须叠加 schema、runner、测试和日志。

### 3.2 只做 skills 和 MCP

结论：适合增强 Codex，但不能代替产品架构。

Skills 的价值：

- 把反复出现的工作流变成可复用能力，例如：
  - strategy-designer
  - backtest-reviewer
  - event-analyst
  - risk-reviewer
  - weekly-strategy-reviewer
- OpenAI 文档把 skill 定义为带 `SKILL.md`、可选脚本和资源的目录，适合包装任务流程。

MCP 的价值：

- 给 Codex 或 Claude Code 接入外部工具和数据。
- Codex 官方支持 CLI 和 IDE extension 连接 MCP。
- OpenBB MCP 可暴露金融数据工具。
- Alpaca MCP 已经能暴露行情、持仓、订单相关动作。

风险：

- MCP 是工具层，不是治理层。
- 金融 MCP 尤其危险，因为 Alpaca MCP 包含 order actions。
- 不能让模型直接拥有 live broker 写权限。
- MCP 的工具调用必须做 allowlist、只读优先、paper-only、日志审计。

判断：

Skills 用来让 Codex 更懂工作流。MCP 用来给 Codex 查数据和上下文。二者都不能替代 deterministic runner 和审计状态。

### 3.3 直接封装成完整 App

结论：最终可能需要，但 MVP 不应从这里开始。

优点：

- 配置 API key、看信号、看报告更友好。
- 更像 Composer。
- 可以给非工程用户使用。

缺点：

- 会重新掉进 EvoQ 的坑：先花大量成本做 UI、账号、配置、状态机、部署、权限。
- 早期最不确定的是策略流程和信号质量，不是 UI。
- 一旦 App 先行，Codex 的优势反而被削弱，变成维护一个复杂产品。

判断：

第一版只做 CLI/TUI + 文件报告。等策略生命周期稳定后，再做薄 UI。UI 只包装已有 runner，不重新发明业务逻辑。

## 4. 推荐形态：混合式 repo-native 产品

最终选择：

```text
项目仓库 = 产品本体
AGENTS.md / CLAUDE.md = 代理约束
skills = 可复用工作流
schemas = 硬格式约束
runners = 确定性执行
SQLite = 信号和 journal 状态
MCP = 可选只读数据/工具层
轻量 LLM API = 运行期结构化审查
Codex = 策略工程师和复盘工程师
```

这个形态的核心优势：

- 高效：不用先建大型 App。
- 可控：策略和信号都落在文件、schema、测试和日志里。
- 能发挥 Codex：Codex 最擅长的是在仓库里持续改代码、跑测试、写报告。
- 能保留自然语言体验：用户主要和 Codex 对话，不手动点流程。
- 能支持 5m/15m：运行期不依赖 Codex 响应，而是 deterministic scanner 先筛选，LLM 只审查候选信号。

## 5. Codex、LLM、MCP、脚本的职责边界

### 5.1 Codex

Codex 负责慢任务、深任务、工程任务：

- 把自然语言交易想法改写成 strategy spec。
- 写策略代码、scanner、backtest、测试。
- 运行验证命令并修复失败。
- 对比策略版本。
- 生成回测报告和复盘报告。
- 做周复盘、月复盘、策略失效分析。
- 重构策略库和 runner。

Codex 不负责：

- 每 5 分钟扫描全市场。
- 运行期直接决定买卖。
- 自动下单。
- 在没有测试和审计的情况下修改 active strategy。

### 5.2 直接 LLM API

直接 LLM API 负责快任务、结构化文本任务：

- 新闻/财报/SEC filing 摘要。
- 事件分类。
- 候选信号的上下文审查。
- 风险卡片生成。
- 把非结构化文本转为 JSON feature。

直接 LLM API 不负责：

- 改策略代码。
- 扫描全市场。
- 直接给 position sizing。
- 绕过 deterministic risk gate。

运行期 LLM 必须使用结构化输出，例如 OpenAI Structured Outputs 的 `json_schema` / `text.format`，保证返回内容能被 schema 校验。

### 5.3 MCP

MCP 负责给 Codex 或 Claude Code 接工具：

- OpenBB MCP：行情、基本面、经济数据、新闻等研究工具。
- Alpaca MCP：paper account、行情、持仓、watchlist 等。
- Financial Datasets MCP：SEC filings、财务数据、新闻。
- Browser/Search MCP：只在研究阶段使用。

MCP 权限原则：

- MVP 默认只读。
- 禁止 live order tool。
- Alpaca 只允许 paper key。
- 对含 order action 的 MCP server 使用 `enabled_tools` / `disabled_tools` allowlist。
- 所有 MCP 结果进入本地 cache，不作为不可追溯的隐式上下文。

### 5.4 Deterministic runners

Runner 是真正的运行期骨架：

- 拉取和缓存市场数据。
- 计算指标。
- 执行 scanner。
- 跑回测。
- 生成候选信号。
- 调用 LLM review。
- 写入 SQLite 和 Markdown/JSON 报告。
- 发本地通知、Telegram/Discord/邮件或 TradingView webhook。

Runner 不允许自动 live trading。paper trading 也必须单独开关。

## 6. MVP 目录结构

建议新开一个干净项目，不在 EvoQ 当前后端里继续堆：

```text
codex-signal-desk/
  AGENTS.md
  CLAUDE.md
  README.md
  pyproject.toml
  .env.example
  Makefile

  .codex/
    config.example.toml
    hooks.example.json

  skills/
    strategy-designer/SKILL.md
    backtest-reviewer/SKILL.md
    event-analyst/SKILL.md
    risk-reviewer/SKILL.md
    weekly-reviewer/SKILL.md

  schemas/
    strategy_spec.schema.json
    signal.schema.json
    event_feature.schema.json
    review_card.schema.json
    trade_journal.schema.json

  strategy_specs/
    drafts/
    approved/
    active/
    retired/

  strategies/
    indicators/
    rules/
    exits/
    sizing/

  data/
    raw/
    cache/
    sample/

  engines/
    data_loader.py
    indicator_engine.py
    backtest_engine.py
    scan_engine.py
    risk_engine.py
    report_engine.py

  event_intel/
    collectors/
    extractors/
    prompts/
    cache/

  runners/
    desk.py
    init_config.py
    doctor.py
    validate_strategy.py
    backtest.py
    scan.py
    review_signal.py
    journal_trade.py
    weekly_review.py
    export_pine.py

  db/
    schema.sql
    migrations/

  reports/
    backtests/
    scans/
    reviews/
    weekly/

  journal/
    trades/
    decisions/
    mistakes/

  tests/
    fixtures/
    test_strategy_schema.py
    test_backtest_no_lookahead.py
    test_scan_engine.py
    test_review_card_schema.py
```

## 7. MVP 功能清单

### 7.1 必须有

1. `desk init`
   - 创建 `.env`。
   - 创建 SQLite。
   - 下载或生成 sample data。
   - 检查 Python 版本和依赖。

2. `desk doctor`
   - 检查 OpenAI key、Alpaca paper key、数据源 key。
   - 明确显示哪些功能可用，哪些降级。
   - 解决 EvoQ 里“打开网页不知道怎么配置 key”的问题。

3. Strategy spec schema
   - 所有策略先是 YAML/JSON spec。
   - 字段包括 universe、timeframe、entry、exit、risk、data assumptions、forbidden behavior。

4. Codex strategy workflow
   - 用户用自然语言要求 Codex 生成策略。
   - Codex 必须先写 draft spec，再写代码和测试。
   - 不能直接写 active strategy。

5. Backtest runner
   - 支持至少 daily、1h、15m。
   - 输出 metrics、equity curve、trades、drawdown、assumption warning。
   - 明确标记数据源和时间范围。

6. Scan runner
   - 支持 watchlist。
   - 支持 5m/15m/1h/daily。
   - 只输出候选信号，不下单。

7. Review card
   - 只有 deterministic scanner 先触发候选信号后，才调用 LLM。
   - LLM 输出必须符合 `review_card.schema.json`。
   - 字段包括 action_label、evidence、risk、invalidation、time_horizon、manual_action。

8. Journal
   - 手动记录是否交易、价格、理由、情绪、结果。
   - 每个 trade 关联 signal id、strategy version、review card、数据快照。

9. Weekly review
   - Codex 读取 reports 和 journal。
   - 输出策略问题、误判模式、改进建议。
   - 只生成 draft proposal，不自动改 active strategy。

### 7.2 可以延后

- Web Dashboard。
- 自动下单。
- Qlib 深度集成。
- QuantConnect/LEAN 集成。
- 复杂多 agent debate。
- 自训练模型。
- 全市场实时新闻扫描。

## 8. 交互逻辑

### 8.1 创建策略

用户对 Codex 说：

```text
帮我设计一个 15m QQQ pullback 策略。
要求只做多，趋势过滤用 200 EMA，回撤后 RSI 修复进场，最多持仓 2 小时。
先不要自动交易，只生成策略、回测和扫描器。
```

Codex 必须执行：

1. 写 `strategy_specs/drafts/qqq_pullback_15m.yaml`。
2. 运行 `desk validate strategy_specs/drafts/qqq_pullback_15m.yaml`。
3. 写 `strategies/rules/qqq_pullback_15m.py`。
4. 写测试。
5. 跑 backtest。
6. 写 `reports/backtests/qqq_pullback_15m.md`。
7. 给出是否值得继续优化的结论。

### 8.2 批准策略

用户说：

```text
如果回测和风险检查过关，把它提升为 approved，但不要 active。
```

系统要求：

- schema valid。
- tests pass。
- backtest report 存在。
- no-lookahead test pass。
- risk section 完整。

Codex 只能把 spec 从 `drafts/` 移到 `approved/`，不能直接 active。

### 8.3 激活扫描

用户说：

```text
把 QQQ pullback 策略设为 active，15 分钟收盘后扫描，只提醒我，不自动下单。
```

runner 做：

```text
desk scan --active --timeframe 15m --bar-close-only
```

如果有候选信号：

1. 写 `reports/scans/YYYY-MM-DD/signal_*.json`。
2. 调用 `desk review-signal signal_*.json`。
3. 生成 `reports/reviews/review_*.md`。
4. 发通知。

### 8.4 手动交易和 journal

用户收到卡片：

```text
QQQ long candidate
rating: watch
entry zone: 431.20-431.80
invalid if: 15m close below VWAP and RSI < 42
risk: FOMC in 90 minutes
manual action: wait for next 15m close
```

用户交易后：

```text
desk journal trade --signal <id> --action "skipped" --reason "FOMC too close"
```

或者：

```text
desk journal trade --signal <id> --action "manual-long" --entry 431.55 --exit 433.10
```

### 8.5 周复盘

用户说：

```text
复盘这周的 15m 策略信号，找出我跳过的机会和误交易，提出下周改进。
```

Codex 读取：

- `reports/scans/`
- `reports/reviews/`
- `journal/trades/`
- `strategy_specs/active/`

输出：

- 哪些信号有效。
- 哪些信号被 LLM review 误导。
- 哪些手动决策有情绪偏差。
- 哪些策略规则需要改。
- 只写 draft proposal。

## 9. 策略引擎选择

不应该一开始绑定 Qlib。

更稳的路径：

```text
MVP:
  pandas/polars + pandas-ta/custom indicators + vectorbt/backtesting.py

Later:
  Qlib adapter for ML/factor research
  TradingView Pine export for chart alerts
  Alpaca paper adapter for simulated tracking
  QuantConnect/LEAN adapter for mature systematic strategies
```

原因：

- Qlib 适合因子研究、ML pipeline 和较正式的量化研究。
- 你的第一需求是自然语言策略生成、15m/1h/manual signal、event review。
- 早期绑定 Qlib 会让数据格式、calendar、instrument universe、workflow 都变重。
- 最好的抽象是定义统一 `SignalFrame` 和 `StrategySpec`，让 Qlib 只是一个后端 adapter。

## 10. Alpaca 的位置

Alpaca 不应该是 MVP 的运行容器。

Alpaca 的正确位置：

- market data source；
- paper account tracking；
- optional paper order adapter；
- portfolio state reader；
- news source；
- later broker integration。

你不能把 Qlib 策略“上传到 Alpaca 让 Alpaca 托管运行”。通常做法是：

```text
本地电脑 / VPS / GitHub Actions / 云服务器
  -> 运行 scanner 或 trading script
  -> 读取 Alpaca market data
  -> 可选提交 paper order
  -> Alpaca 只负责账户、订单、成交模拟和 dashboard
```

对你的当前目标，MVP 只需要读取行情和生成 manual signal。paper order adapter 可以第二阶段做。

## 11. 频率设计

### Daily / weekly

最适合 LLM 深度参与：

- 财报。
- SEC filing。
- 宏观事件。
- sector rotation。
- strategy review。

### 1h

适合结合：

- 趋势和均值回归策略。
- 宏观日内环境。
- 新闻摘要。
- LLM 风险卡。

### 15m

适合 MVP 的主动交易扫描：

- deterministic scanner 负责技术信号。
- LLM 只在候选信号出现后审查上下文。
- 不做全市场 LLM 扫描。

### 5m

可以支持，但要强约束：

- bar close only。
- watchlist 小。
- 只做 deterministic candidate filtering。
- LLM review 必须使用缓存新闻和短上下文。
- 输出可以是 watch/avoid，不一定要求立即 trade。

### 1m/tick

不做。LLM、Codex、手动交易都不适合这个频率。

## 12. Guardrails

### 12.1 策略生命周期

```text
draft -> tested -> approved -> active -> paused -> retired
```

硬规则：

- Codex 可以创建 draft。
- Codex 可以提出 approved。
- active 必须用户明确确认。
- active strategy 修改必须先 fork 新版本。
- retired strategy 不再扫描，但报告保留。

### 12.2 交易权限

MVP：

- no live trading。
- no automatic order。
- paper order disabled by default。
- all broker write operations require explicit command and separate config flag。

### 12.3 LLM 输出约束

所有 LLM 输出必须：

- JSON schema valid。
- 带 evidence。
- 带 timestamp。
- 带 model name。
- 带 prompt version。
- 带 source list。
- 不允许输出“保证收益”类语言。
- 不允许直接输出 “buy now with X shares”。

### 12.4 MCP 权限

对 MCP：

- 默认只启用 read-only tools。
- 禁用 Alpaca order create/replace/cancel。
- remote MCP 必须 HTTPS/TLS + token auth。
- 不把 live brokerage key 放入 Codex MCP。
- 对所有 MCP tool output 写 cache 和 source metadata。

### 12.5 Hooks

可以用 Codex/Claude Code hooks 做额外防线：

- 阻止 live order 相关命令。
- 阻止修改 `strategy_specs/active/` 而不改版本号。
- 修改 strategy 后自动提示运行 tests/backtest。
- session start 自动加载当前 active strategy 和风险规则摘要。

注意：

Hooks 是 guardrail，不是完整安全边界。OpenAI Codex hooks 文档明确说明当前 `PreToolUse` 不能拦截所有 shell 路径。因此关键安全必须依赖 runner 权限、API key 隔离、broker write disabled 和人工确认。

## 13. 数据和审计模型

SQLite 最适合保存状态：

```sql
strategies(id, name, version, status, spec_path, code_path, created_at)
backtests(id, strategy_id, data_snapshot_id, metrics_json, report_path, created_at)
signals(id, strategy_id, timeframe, symbol, signal_json, created_at)
review_cards(id, signal_id, model, prompt_version, review_json, report_path, created_at)
manual_trades(id, signal_id, action, entry_price, exit_price, notes, created_at)
events(id, symbol, event_type, source_url, event_json, created_at)
data_snapshots(id, source, universe, timeframe, start_at, end_at, checksum)
```

文件系统保存人类可读内容：

- specs。
- reports。
- review cards。
- weekly reviews。
- journal notes。

结论：

这里的 SQLite 不是用来替代 Skill，也不是用 SQL 来约束 Codex。它只是本地状态和审计层，用来保存 journal、signals、review cards、strategy lifecycle 和数据快照。

针对你原本问的 “几个 Skill 和 MCP 能不能约束住产品”：

- Skill 负责约束 Codex 的工作流，例如策略设计、回测审查、事件分析、风险复盘。
- MCP 负责给 Codex/Claude Code 提供外部工具和数据。
- SQLite 负责保存运行期状态和审计记录。
- 真正的硬约束来自 schema、runner、测试、权限隔离和人工确认。

因此最佳组合是 Skill + MCP + schemas + deterministic runners + SQLite audit + Git，而不是单靠 Skill/MCP，也不是单靠 SQLite。

## 14. MVP 第一版验收标准

第一版只算成功，如果可以完成这条链路：

```text
自然语言提出策略
  -> Codex 生成 draft spec/code/test
  -> 本地 backtest 通过
  -> 用户批准为 active scanner
  -> 15m 扫描 watchlist
  -> 有候选信号时生成 review card
  -> 用户手动交易或跳过
  -> journal 记录
  -> 周复盘生成改进提案
```

量化验收：

- 新用户 30 分钟内能跑 sample strategy。
- 不配置 broker key 也能跑 sample data 回测。
- 不配置 OpenAI key 也能跑 deterministic scanner。
- 配置 OpenAI key 后能生成 review card。
- 配置 Alpaca paper key 后能读 paper account 和 IEX data。
- 没有任何 live broker write path 默认开启。
- 每个 signal 都能追溯到 strategy version、data snapshot、review prompt 和 journal。

## 15. 分阶段计划

### Phase 0: 产品骨架

- 新建 `codex-signal-desk` 仓库。
- 写 `AGENTS.md`、`CLAUDE.md`、README。
- 建 `pyproject.toml`、Makefile、ruff/pytest。
- 建 schemas。
- 建 SQLite schema。
- 建 sample data。
- 实现 `desk init` 和 `desk doctor`。

### Phase 1: 纯量化策略链路

- 实现 strategy spec。
- 实现 backtest runner。
- 实现 scan runner。
- 实现 2-3 个样例策略：
  - daily momentum rotation。
  - 1h trend pullback。
  - 15m QQQ/SPY pullback。
- Codex skill: strategy-designer。
- Codex skill: backtest-reviewer。

### Phase 2: 手动信号工作流

- 实现 review-free signal card。
- 实现 journal。
- 实现 scheduler。
- 实现 notification。
- 实现 weekly review。

### Phase 3: LLM event/review layer

- 实现 structured review card。
- 接 OpenAI Structured Outputs。
- 接新闻/SEC/macro collector。
- 增加 event_feature schema。
- LLM 只对 candidate signal 做审查。

### Phase 4: MCP/data extensions

- OpenBB MCP read-only。
- Alpaca MCP read-only。
- Financial Datasets MCP read-only。
- `.codex/config.example.toml` 提供 allowlist。
- hooks 示例阻止 broker write。

### Phase 5: 可选 paper tracking

- Alpaca paper portfolio reader。
- 可选 paper order adapter。
- 默认关闭。
- 每次 paper order 需要显式命令和确认。

### Phase 6: 薄 UI

只在前面流程稳定后做：

- config status。
- active strategies。
- latest signals。
- review cards。
- journal。
- reports browser。

UI 不实现策略逻辑，只调用 runner 和读取 SQLite。

## 16. 最小技术栈

建议：

- Python 3.11+。
- `pydantic` / `jsonschema` for schemas。
- `typer` for CLI。
- `sqlite-utils` or SQLAlchemy Core for state。
- `pandas` / `polars`。
- `pandas-ta` or in-house indicators。
- `vectorbt` or `backtesting.py` for early backtests。
- `pytest`。
- `ruff`。
- OpenAI API for structured review。
- Alpaca SDK only for market data/paper reader in early phase。

暂不建议：

- FastAPI + Next.js。
- full event-sourcing backend。
- multi-agent orchestration framework。
- Qlib-first architecture。
- automatic broker execution。

## 17. 与 Composer 的关系

目标上对标 Composer：

- 自然语言生成策略。
- 策略可回测。
- 策略可运行。
- 用户不需要手写每一步。

但实现上不同：

- Composer 是封闭产品和券商体验。
- Codex Signal Desk 是个人可审计代码仓库。
- Composer 更偏低频组合/条件编排。
- Codex Signal Desk 可以支持 15m/1h/manual signal，并把 LLM 事件分析作为上下文层。
- Composer 替用户封装策略结构；这里让 Codex 生成可测试代码和可读 spec。

## 18. Sources

- OpenAI Codex CLI: https://developers.openai.com/codex/cli
- OpenAI AGENTS.md: https://developers.openai.com/codex/guides/agents-md
- OpenAI Codex skills: https://developers.openai.com/codex/skills
- OpenAI Codex MCP: https://developers.openai.com/codex/mcp
- OpenAI Codex hooks: https://developers.openai.com/codex/hooks
- OpenAI Structured Outputs: https://developers.openai.com/api/docs/guides/structured-outputs
- MCP tools specification: https://modelcontextprotocol.io/specification/2025-06-18/server/tools
- OpenBB MCP docs: https://docs.openbb.co/odp/python/extensions/interface/openbb-mcp
- Alpaca MCP server: https://docs.alpaca.markets/docs/alpaca-mcp-server
- Alpaca paper trading: https://docs.alpaca.markets/docs/paper-trading
- Alpaca real-time news: https://docs.alpaca.markets/docs/streaming-real-time-news
- LLM + Quant research notes: [LLM-QUANT-ARCHITECTURE-RESEARCH.md](LLM-QUANT-ARCHITECTURE-RESEARCH.md)
