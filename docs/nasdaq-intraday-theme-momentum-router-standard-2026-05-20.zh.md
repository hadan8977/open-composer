# Nasdaq Intraday Theme Momentum Router 标准文档

日期：2026-05-20

## 目标

建立一组新的纳指策略研究标准，用于从当前 QQQ/TQQQ beta router 扩展到半导体、科技主题和纳指高流动性个股的日内轮动。新策略必须先以 `StrategySpec` draft 存在，先回测和审查，再进入模拟盘候选；当前正在运行的模拟盘策略不受影响。

## 策略族

### 纯量化版

- 名称：`nasdaq_intraday_theme_momentum_router_1m`
- 交易方式：日内为主，开盘后确认信号，下一根 bar 开盘成交，收盘前或收盘时清仓。
- 标的池：纳指高流动性大盘股和半导体相关个股；首批限定在已有 1m 缓存能覆盖的股票，后续可扩展到 Nasdaq 100。
- 核心结构：单个策略内部包含多个子策略，不调用外部策略。
- 内部子策略：
  - 开盘动量：开盘区间强、相对量能强、短期动量强时追随。
  - 开盘反转：市场前期弱、开盘下探或弱反弹时择强反转。
  - Midday 动量：开盘后 15 到 60 根 1m bar 已确认后，只在趋势延续时介入。
  - Midday 反转：早盘过度下跌或低量回落后，只在回撤条件明确时介入。
- 市场扫描：
  - QQQ 开盘收益。
  - QQQ 近期动量。
  - QQQ 相对开盘量能。
  - 个股开盘强度、近 N 日动量、相对量能。
- 路由方式：市场扫描决定内部子策略优先级；当天最多触发一个内部路线。
- 风险控制：每笔固定目标权重，组合总暴露上限，最多持有 1 到 3 个标的，日内强制清仓。

### LLM 辅助版

- 名称：`nasdaq_intraday_theme_momentum_router_1m_llm`
- 交易方式：与纯量化版相同。
- LLM 作用边界：
  - 初期只做候选路线复核、事件风险解释、新闻/财报风险过滤建议。
  - 不允许直接把实时 LLM 输出作为买卖信号。
  - 只有当新闻/事件/LLM 特征具备 PIT replay 包、单模态基线、边际提升和缺失模态稳健性证据后，才允许影响交易。
- 优势使用方式：
  - 对结构化候选结果做 meta-selection，而不是让模型自由预测价格。
  - 对新闻、财报、SEC 事件做风险摘要和过滤建议。
  - 用模型识别“表面动量但事件风险过高”的情况，但必须留下可复放的 feature packet。

## 研究依据

- 日内动量：Gao、Han、Zhou 的 Market Intraday Momentum 研究支持日内早盘与尾盘信息存在可研究的延续效应。
- 行业/主题动量：Moskowitz 和 Grinblatt 的行业动量研究支持主题层面的轮动假设。
- 事件过滤：财报、重大新闻和 SEC filing 会改变短周期价格分布；在证据不足时先作为降权或阻断条件，而不是 Alpha 因子。
- 免费数据源：Alpaca IEX 和 Longbridge Nasdaq Basic 可以作为免费或已配置的数据能力，但都不是 consolidated SIP；Alpha Vantage/GDELT 新闻属于 trial capability。

参考链接：

- https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2440866
- https://doi.org/10.1111/0022-1082.00146
- https://www.alphavantage.co/documentation/
- https://www.sec.gov/search-filings/edgar-application-programming-interfaces

## 回测标准

### 数据与时间

- 首轮研究窗口：已有 1m 缓存覆盖期，预计约 2024-05 到 2026-05。
- 后续扩展：
  - 对日内策略：继续拉取最近 1 到 2 年 1m 或 5m 数据。
  - 对主题/轮动策略：使用 2022 至今 daily 数据做辅助 regime 研究。
- 所有信号必须 bar-close 确认，下一根 bar open 成交。
- 训练、验证、OOS 和 walk-forward 必须分开。

### 基准族

每次正式报告至少包含：

- 同标的池等权日内收益。
- QQQ 日内基准。
- TQQQ 日内压力基准。
- QQQ buy-and-hold。
- TQQQ buy-and-hold。
- 主题代理：SMH/SOXX/XLK，至少在 daily 主题辅助研究中出现。
- 现金代理。
- ex-post best symbol，作为过拟合警告，不作为必须击败项。

### 准入门槛

研究通过门槛：

- OOS 年化收益为正。
- OOS Alpha 相对等权日内基准为正。
- OOS Alpha 相对 QQQ/TQQQ 日内基准为正，至少一个为显著正。
- OOS Sharpe 在 `0.8` 到 `2.5` 区间。超过 `2.5` 需要额外过拟合解释。
- Profit Factor 大于 `1.5`，优先目标大于 `2.0`。
- 最大回撤不劣于 `-20%`，激进版绝对不劣于 `-30%`。
- OOS 交易日不少于 `40`，单个 fold 不少于 `15` 个交易日。
- walk-forward 至少多数 fold 为正 Alpha，纸盘候选要求全部或接近全部通过，且无灾难性 fold。
- 年化收益必须超过 QQQ buy-and-hold 或在显著低回撤下接近；激进版需挑战当前 beta router，但不能用未来函数或过窄周期解释收益。

纸盘候选门槛：

- `workflow_pass=true`
- `research_pass=true`
- `paper_ready_pass=true`
- promotion report ready。
- 策略必须 active + `paper_auto`，但只能在用户明确确认后启用。
- 持续运行路径必须能生成信号、写 signal log、尊重 kill switch、检查 open orders、接入 Alpaca Paper safety gate。

## 反过拟合规则

- 先写假设和参数范围，再跑搜索。
- 参数范围必须小而有经济含义，不根据 OOS 结果反向扩大搜索。
- 不允许只选单一年份表现最好的组合。
- 对高 Sharpe、低交易次数、单一标的贡献过大、极端近期收益集中做显式 warning。
- 所有 LLM/news 影响必须可复放；没有 PIT 证据时，LLM 只能 advisory。

## 当前执行计划

1. 创建两个 draft StrategySpec：纯量化版和 LLM 辅助版。
2. 用现有 1m 缓存跑首轮 bounded adaptive-intraday-router 研究，首轮候选上限 `864`，结果只作为研究证据，高候选数会触发过拟合审查。
3. 补齐 intraday router 的 paper runner 信号路径，使其符合持续运行产品要求。
4. 生成 promotion/readiness/risk 报告；未达标则继续迭代参数、标的池、事件过滤和主题辅助层。
5. 只有在用户确认后，才创建 active `paper_auto` 版本。
