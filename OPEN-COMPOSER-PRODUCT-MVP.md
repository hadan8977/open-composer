# Open Composer 产品 MVP

Date: 2026-05-08

## 1. 产品定义

Open Composer 是一个面向个人使用的、对话式的 AI 策略工作台。

它的核心不是自动交易，而是让用户通过自然语言和 Codex 共同完成策略研究、策略实现、回测、扫描、信号审查、手动交易记录和复盘。

第一版要解决的问题是：

- 用户说出一个交易想法；
- Codex 在受约束的项目仓库里把想法变成策略 spec、代码、测试和回测；
- 系统用确定性 runner 扫描 15m、1h、daily 等周期的候选信号；
- LLM 只在候选信号出现后做事件和上下文审查；
- 用户最终手动决定是否交易；
- 系统记录结果，并让 Codex 周期性复盘和改进。

## 2. 用户问题

目标用户不是专业量化团队，而是想借助 AI 学习和交易的个人用户。

这个用户面临的问题是：

- no-code 策略产品接近需求，但闭源、受地区/券商限制；
- 传统量化框架很强，但对个人用户太重；
- 纯 LLM 交易代理不稳定，也不可审计；
- dashboard-first 产品会先陷入 UI、状态、部署和配置复杂度；
- 手动交易缺少纪律、复盘和可重复流程。

Open Composer 的解决方式是：

```text
Codex 负责策略工程
确定性脚本负责回测和扫描
LLM 负责文本/事件/上下文审查
用户保留最终交易决定权
```

## 3. MVP 目标

MVP 要证明一条完整闭环：

```text
自然语言策略想法
  -> Codex 生成策略 spec
  -> 策略代码 + 测试
  -> 回测报告
  -> 用户批准为可扫描策略
  -> 15m / 1h / daily 候选信号
  -> 可选 LLM review card
  -> 用户手动决策
  -> journal 记录
  -> Codex 周复盘和改进提案
```

只要这条闭环跑通，即使没有 Web dashboard，产品也已经有价值。

## 4. 目标用户

第一版只服务单个个人用户：

- 关注美股或 ETF；
- 希望用 AI 辅助生成和优化策略；
- 能接受用 Codex / Claude Code 打开一个项目文件夹；
- 希望先手动交易，而不是自动下单；
- 关注 15m、1h、daily、weekly 等频率；
- 不希望被大型后端或复杂 dashboard 拖住。

## 5. 产品原则

1. 对话优先，但不是 LLM-only。
2. Codex 生成和改进策略资产，runtime runner 执行确定性逻辑。
3. 所有策略先变成结构化 spec，再变成代码。
4. 回测、扫描和复盘必须可复现。
5. LLM 只在候选信号出现后审查上下文。
6. broker 写权限默认关闭。
7. MVP 以手动交易为第一执行模式。
8. 每个信号、审查和交易记录都必须可追溯。

## 6. 产品形态

MVP 不是大型 Web App。

第一版产品形态是：

- 一个 Git 仓库；
- Codex 项目规则；
- repo-scoped skills；
- CLI 命令；
- YAML / JSON 策略 spec；
- Python 量化后端；
- 本地数据缓存；
- Markdown / JSON 报告；
- SQLite 审计状态；
- 可选 MCP 连接；
- 可选 Alpaca paper account reader。

这样做的原因是：当前最不确定的不是 UI，而是策略生成、验证、扫描、审查和复盘这条链路是否真的顺畅。

## 7. 技术框架摘要

Open Composer 需要量化运行能力，但第一版不应该 Qlib-first，也不应该 Lumibot-first。

推荐 MVP 架构是：

```text
Codex / Claude Code
  -> AGENTS.md + repo skills
  -> strategy spec
  -> Python backtest / scanner
  -> Pine Script export
  -> signal parity report
  -> LLM review service
  -> SQLite + Parquet/CSV + Markdown audit trail
  -> optional Alpaca / Lumibot / vectorbt / Qlib adapters
```

核心技术决策：

- Open Composer 自己做产品层、策略 spec、Codex workflow、审计和报告；
- 第一版主线是 StrategySpec -> Python backtest/scanner -> Pine export；
- Python 和 Pine 的信号一致性是第一版关键验证；
- TradingView/Pine 是第一版手动交易提醒出口，但不是策略真源；
- Alpaca 是后续真实行情和 paper account adapter；
- Lumibot 用于后续 Alpaca paper execution，不作为第一版核心；
- vectorbt 用于后续参数扫描和批量研究；
- Qlib 作为后续 ML/factor research adapter，不作为第一版底座；
- MCP 是 Codex 工具接入层，不是安全边界；
- OpenAI API 或兼容 LLM 只负责结构化 review 和事件提取。

详细技术方案见 [OPEN-COMPOSER-TECHNICAL-FRAMEWORK.md](OPEN-COMPOSER-TECHNICAL-FRAMEWORK.md)。

## 8. 核心用户流程

### 8.1 创建策略

用户输入：

```text
帮我做一个 15m QQQ pullback 策略。
趋势过滤用 200 EMA，回撤后 RSI 修复进场，最多持仓 2 小时。
先不要自动交易。
```

系统行为：

1. Codex 使用 `strategy-designer` skill。
2. Codex 写入 `strategy_specs/drafts/qqq_pullback_15m.yaml`。
3. 系统用 schema 校验 spec。
4. Codex 实现策略代码。
5. Codex 编写测试。
6. Codex 运行回测。
7. Codex 生成回测报告。
8. 用户决定是否批准。

### 8.2 批准策略

从 draft 到 approved 的条件：

- spec 校验通过；
- 测试通过；
- 回测报告存在；
- strategy 声明 timeframe、universe、entry、exit、risk、data assumptions；
- 用户明确批准。

approved 不等于 active。

### 8.3 激活扫描

用户输入：

```text
把 QQQ pullback 策略设为 active。
15m bar close 后扫描 watchlist，只提醒我，不自动交易。
```

系统行为：

1. active strategy registry 更新。
2. scheduler 在 bar close 后运行 scanner。
3. scanner 读取本地缓存或 provider 数据。
4. scanner 输出候选 signal。
5. 只有出现候选 signal 时才运行 LLM review。
6. 系统写入 signal card 和 review card。
7. 用户收到通知。

### 8.4 手动决策

用户看到：

- signal 摘要；
- entry zone；
- invalidation level；
- 相关事件；
- 风险标记；
- `watch` / `avoid` / `valid setup` 等手动动作标签。

MVP 不提交 live order。

### 8.5 记录和复盘

用户执行或跳过后：

- journal 记录决策；
- signal id 和 strategy version 关联；
- review card 关联；
- weekly review 汇总有效信号、误判信号、用户偏差和策略改进建议。

## 9. MVP 功能范围

### 9.1 必须有

1. `README`
   - 解释产品是什么，怎么开始。

2. `AGENTS.md`
   - 定义 Codex 规则、策略生命周期、安全边界和验证要求。

3. `.agents/skills`
   - `strategy-designer`;
   - `backtest-reviewer`;
   - `signal-reviewer`;
   - `risk-reviewer`;
   - `weekly-reviewer`。

4. Strategy spec schema
   - 校验所有 draft 和 active 策略。

5. Python backtest / scanner
   - 将 `StrategySpec` 编译成 Python 回测和扫描代码；
   - 支持 sample data；
   - 支持 15m、1h、daily；
   - 输出 signal log 和 backtest report。

6. Pine export
   - 将 `StrategySpec` 导出成 Pine Script；
   - 支持 TradingView 图表观察和 alert；
   - 与 Python 信号做一致性检查。

7. Scan runner
   - 支持 watchlist；
   - 支持 bar-close；
   - 输出候选信号。

8. LLM review card
   - 使用结构化输出；
   - 只在候选信号之后运行。

9. Local audit store
   - SQLite 保存 metadata；
   - Parquet/CSV 保存行情缓存；
   - Markdown/JSON 保存报告。

10. Journal
    - 记录手动交易、跳过原因、交易理由和结果。

11. Doctor command
    - 检查 Python 环境、数据、OpenAI key、Alpaca key、MCP 可用性。

### 9.2 应该有

- OpenBB MCP example config；
- 通知输出；
- weekly review command；
- Alpaca market data adapter；
- Alpaca paper account reader；
- Lumibot paper execution adapter。

### 9.3 MVP 不做

- live automatic trading；
- full web dashboard；
- broker write access through MCP；
- Qlib-first implementation；
- Lumibot-first implementation；
- 多用户账号；
- 组织权限；
- sub-minute trading；
- fully autonomous LLM strategy router。

## 10. 产品对象

```text
StrategySpec
StrategyVersion
DataSnapshot
BacktestRun
Signal
ReviewCard
EventFeature
TradeJournalEntry
WeeklyReview
```

关系：

```text
StrategySpec -> StrategyVersion -> BacktestRun
StrategyVersion -> Signal -> ReviewCard -> TradeJournalEntry
EventFeature -> Signal / ReviewCard
TradeJournalEntry + BacktestRun -> WeeklyReview
```

## 11. MVP 验收标准

MVP 完成的标准：

1. 新用户可以 clone 后不配置 broker key，跑 sample strategy。
2. Codex 可以从自然语言生成 draft strategy。
3. strategy spec 可以校验。
4. 生成策略有测试。
5. 能生成回测报告。
6. 策略可以被批准并激活扫描。
7. scanner 可以基于 sample 或 provider 数据输出 signal。
8. 配置 OpenAI key 后可以生成结构化 review card。
9. 用户可以记录手动决策。
10. weekly review 可以总结信号、交易记录和改进建议。

## 12. 阶段路线

### Phase 0: 技术骨架

- 建项目结构；
- 写 `AGENTS.md`；
- 建 `.agents/skills`；
- 建 schemas；
- 建 sample data；
- 建 CLI skeleton；
- 建 doctor command。

### Phase 1: Composer-lite Core

- 定义 StrategySpec；
- 实现 `spec_to_python.py`；
- 实现 `spec_to_pine.py`；
- 用 sample data 回测；
- 输出 backtest report；
- 输出 Python/Pine signal parity report；
- 加 journal。

### Phase 2: Codex Workflow Hardening

- 写 repo-scoped skills；
- 固化 strategy lifecycle；
- 增加测试、回测、报告要求；
- 增加 strategy generation workflow。

### Phase 3: Real Data And Scanner

- 加 Alpaca / Polygon data adapter；
- 加 VPS scanner；
- 加 notification；
- 继续保持 manual signal mode。

### Phase 4: LLM Review

- 增加 review card schema；
- 接 OpenAI structured output；
- 增加 event feature schema；
- 增加 cached event context。

### Phase 5: Alpaca Paper / Lumibot

- 加 Alpaca paper account reader；
- 加 Lumibot paper execution adapter；
- 加 dry-run order proposal；
- 加 approval-gated paper order；
- broker write operations 默认关闭。

### Phase 6: Research Extensions

- 加 vectorbt parameter sweep；
- 加 Qlib factor/ML research；
- 加 OpenBB MCP research；
- 可选加 TradingView webhook。

### Phase 7: Thin UI

只有在闭环跑通后再做：

- latest signals；
- strategy list；
- reports browser；
- config status；
- journal view。

## 13. 主要风险

1. 在策略闭环验证前过早做 UI。
2. 太早让 MCP 或 Alpaca 暴露写权限。
3. 在产品流程未清晰前绑定 Qlib。
4. 把 LLM review 当成交易真理。
5. 使用质量差或非 point-in-time 的数据做回测。
6. 允许 Codex 直接修改 active strategy。

## 14. 成功定义

MVP 成功的标志是：

- 用户能用自然语言持续提出策略；
- Codex 能把策略变成可测试资产；
- runner 能输出可解释的非自动化信号；
- LLM review 能补充事件和上下文；
- 用户能以更有纪律的方式手动交易；
- weekly review 能持续改善策略和用户行为。
