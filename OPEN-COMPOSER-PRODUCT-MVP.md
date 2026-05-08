# Open Composer Product MVP

Date: 2026-05-08

## 1. 产品定义

Open Composer 是一个**面向个人使用的、对话式的策略工作台**。

它不是一个传统 dashboard，也不是一个自动交易机器人。它的核心是：

- 你用自然语言描述交易想法；
- Codex 帮你把想法变成策略 spec、代码、测试和回测；
- 系统把行情和事件转成候选信号；
- LLM 只在需要时做结构化审查；
- 你自己决定是否下单，系统负责记录和复盘。

## 2. 产品目标

MVP 的目标不是追求复杂度，而是建立一个可持续、可审计、可迭代的个人交易工作流。

具体目标：

1. 让用户可以用自然语言创建或修改策略。
2. 让策略可以被代码化、测试化和回测化。
3. 让系统能在 15m / 1h / daily 等周期上扫描候选信号。
4. 让事件和文本信息可以进入策略判断。
5. 让用户以 manual trading 方式完成最终执行。
6. 让每次决策都可追溯、可复盘、可改进。

## 3. 目标用户

第一版只面向单个用户：

- 有基本交易兴趣；
- 不是专业量化团队；
- 想借助 Codex 提高策略生成、整理和复盘效率；
- 希望保持手动交易或低风险 paper 流程；
- 不想被大型 Web 系统和复杂配置拖住。

## 4. MVP 的产品假设

如果我们把“策略生成”做成一个对话式流程，并用确定性 runner 保证执行和审计，那么：

- 用户不需要懂完整的工程实现；
- Codex 可以承担大部分策略工程工作；
- 事件和文本可以通过 LLM 变成可用特征；
- 人工只保留最终交易权和少量关键确认。

这会比“先做完整 dashboard，再让人点来点去”更快形成可用闭环。

## 5. 产品形式

### 5.1 第一阶段的形式

MVP 不是大 App。

它采用以下组合：

- 仓库即产品；
- 文档即说明；
- CLI / TUI 即操作入口；
- JSON / YAML spec 即策略描述；
- SQLite + 文件即状态与审计；
- skills / MCP 即 Codex 的能力扩展；
- 薄 UI 以后再补。

### 5.2 为什么是这种形式

- 比单纯项目文件夹更强，因为有清晰的工作流和硬约束；
- 比只做 skills + MCP 更完整，因为有产品状态和运行闭环；
- 比先做完整 Web App 更轻，因为把不确定性放在策略流程而不是 UI 上；
- 最适合 Codex，因为 Codex 最强的是仓库内持续生成、修改、验证和复盘。

## 6. 核心用户流程

### 6.1 创建策略

用户输入：

```text
帮我做一个 15m QQQ pullback 策略，趋势过滤用 200 EMA，回撤后 RSI 修复进场，最多持仓 2 小时。
```

系统行为：

1. Codex 生成策略草案 spec。
2. Codex 生成代码、测试和回测脚本。
3. 系统验证 spec 和测试。
4. 系统运行回测。
5. 系统输出策略报告。
6. 用户决定是否进入 approved。

### 6.2 激活扫描

用户确认策略可用后：

1. 将策略加入 active 列表。
2. 定时 runner 在对应周期扫描 watchlist。
3. 若出现候选信号，生成 signal card。
4. LLM 在候选信号上做文本/事件审查。
5. 输出 review card。
6. 用户决定是否手动交易。

### 6.3 交易记录

用户交易后：

- 记录是否执行；
- 记录入场、出场和理由；
- 记录是否因事件、风险或直觉而跳过；
- 关联 signal、strategy version 和 review card。

### 6.4 周期复盘

每周或每月：

- Codex 读取报表和 journal；
- 找出有效信号和误判信号；
- 找出用户偏差和策略偏差；
- 给出下一轮优化建议；
- 只生成 draft，不直接改 active 策略。

## 7. MVP 功能范围

### 7.1 必须有

1. **策略 spec**
   - 所有策略先写成结构化 spec。
   - 包含 universe、timeframe、entry、exit、risk、data assumptions。

2. **Codex 策略生成**
   - 支持自然语言生成策略草案。
   - 支持修改现有策略。
   - 支持生成测试和报告。

3. **回测**
   - 支持 daily、1h、15m。
   - 输出收益、回撤、胜率、交易数、样本区间和假设。

4. **扫描**
   - 支持 watchlist。
   - 支持 bar close。
   - 支持候选信号输出。

5. **事件审查**
   - 只在候选信号出现后调用 LLM。
   - 输出结构化 review card。

6. **journal**
   - 记录手动交易、跳过原因和复盘注记。

7. **weekly review**
   - Codex 自动汇总本周信号和交易记录。
   - 输出改进提案。

8. **配置和检查**
   - 能检查 key、数据源和运行状态；
   - 能明确告诉用户哪些能力可用、哪些降级。

### 7.2 可延后

- 全功能 Web dashboard；
- 自动 live trading；
- 重型多 agent 协作；
- Qlib 深度绑定；
- 完整 broker 托管；
- 高级组织权限；
- 实时秒级决策。

## 8. 产品对象

### 8.1 关键对象

- `StrategySpec`
- `StrategyVersion`
- `Signal`
- `ReviewCard`
- `EventFeature`
- `TradeJournalEntry`
- `BacktestReport`
- `WeeklyReview`

### 8.2 这些对象的关系

```text
StrategySpec -> StrategyVersion -> BacktestReport
StrategyVersion -> Signal -> ReviewCard -> TradeJournalEntry
EventFeature -> Signal / ReviewCard
TradeJournalEntry + BacktestReport -> WeeklyReview
```

## 9. 交互原则

1. 用户主要说自然语言，不需要手动穿透每一层模块。
2. Codex 负责把自然语言变成可执行资产。
3. 系统优先输出结构化结果，再输出解释。
4. 任何会影响交易决策的内容都必须可追溯。
5. 任何默认动作都应偏保守。
6. 任何自动执行都默认关闭。

## 10. 约束和边界

### 10.1 绝不作为 MVP 默认能力的内容

- 不给模型 live broker 写权限；
- 不做全市场高频扫描；
- 不做 1m / tick 级决策；
- 不做“LLM 说了算”的自动买卖；
- 不做没有审计的黑盒策略；
- 不做默认打开的自动下单；
- 不把复杂 UI 当成第一优先级。

### 10.2 必须长期保留的边界

- 策略 spec 必须版本化；
- 回测必须可复现；
- 事件审查必须带证据；
- journal 必须能追溯；
- active 策略必须经过确认；
- 风险规则必须先于执行。

## 11. 推荐的技术组织方式

### 11.1 Codex 的位置

Codex 是策略工程师和复盘工程师，不是执行引擎。

它最适合做：

- 生成策略草案；
- 生成和修改代码；
- 跑测试；
- 跑回测；
- 生成报告；
- 周期复盘；
- 改进策略结构。

### 11.2 skills 的位置

skills 用来把重复工作流程固化成任务单元，例如：

- `strategy-designer`
- `backtest-reviewer`
- `event-analyst`
- `risk-reviewer`
- `weekly-reviewer`

### 11.3 MCP 的位置

MCP 用来接数据和工具，例如：

- 行情；
- 财报；
- 新闻；
- SEC 文档；
- paper 账户信息；
- 研究查询工具。

默认只读，先不接写权限。

### 11.4 Runner 的位置

runner 负责真正的确定性执行：

- 拉数据；
- 算指标；
- 扫信号；
- 触发 review；
- 写审计记录；
- 输出报告。

## 12. 成功标准

MVP 成功的最低标准是：

1. 用户能在较短时间内创建第一条策略。
2. 不依赖复杂配置就能跑 sample strategy。
3. 能输出可读回测报告。
4. 能对 15m / 1h 信号进行扫描。
5. 能生成 review card。
6. 能记录手动交易和跳过原因。
7. 能做周复盘并提出改进建议。

## 13. 第一版不追求的事

第一版不追求：

- 复杂 UI；
- 多人协作；
- 自动赚钱神话；
- 所有市场都覆盖；
- 所有策略都通吃；
- 所有决策都自动化。

第一版只追求一个事实：

> 用户可以用自然语言持续生成、优化、验证、审查和复盘策略，并在 manual trading 场景里形成稳定闭环。

## 14. 分阶段路线

### Phase 0

- 确定产品语言和目录结构；
- 建立 spec 和 report 规范；
- 建立 sample strategy。

### Phase 1

- 完成策略生成、回测、扫描、journal；
- 完成一条最短闭环。

### Phase 2

- 加入事件审查和 review card；
- 加入 weekly review。

### Phase 3

- 增加 MCP 数据源；
- 增加 paper tracking；
- 增加薄 UI。

### Phase 4

- 再考虑更强的策略库、更完整的市场覆盖和更细的工作流。

## 15. 与现有产品的差异

- 比 Composer 更个人化、更开放、更适合 Codex 驱动的工程工作流；
- 比 TradingView 更偏策略生成和复盘，而不是只看图表；
- 比 Capitalise.ai 更适合复杂事件和策略工程；
- 比 QuantConnect 更轻，适合第一版个人工作台；
- 比 EvoQ 原方案更贴近你的真实使用方式。
