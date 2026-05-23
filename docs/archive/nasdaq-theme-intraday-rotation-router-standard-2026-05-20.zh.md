# Nasdaq Theme Intraday Rotation Router 标准文档

日期：2026-05-20

## 目标

在不打断当前模拟盘策略的前提下，研究一组更宽的纳指策略：从单一 QQQ/TQQQ 暴露扩展到半导体主题、科技主题和纳指高流动性个股。策略必须先以 draft `StrategySpec` 和研究报告存在；只有在通过研究、风险、执行映射和纸盘就绪门槛后，才允许作为模拟盘候选。

## 策略族

### 纯量化版

- 名称：`nasdaq_theme_intraday_rotation_router_daily`
- 交易频率：每日收盘后扫描，下一交易日开盘建仓，当日收盘退出。
- 交易模式：日内持仓为主，不持隔夜个股仓位；核心 beta 仓位也按同日开平建模。
- 标的范围：
  - 市场核心：`QQQ`、`QLD`、`TQQQ`
  - 主题代理：`SMH`、`SOXX`、`XLK`、`IGV`、`ARKK`
  - 个股池：纳指高流动性科技/半导体个股，例如 `NVDA`、`AVGO`、`AMD`、`AMAT`、`QCOM`、`MSFT`、`AAPL`、`META`、`AMZN`、`GOOGL`、`TSLA`、`NFLX`、`MU`、`LRCX`、`ASML`、`KLAC`、`MRVL`、`PLTR`
- 内部结构：单个策略内部包含市场扫描、主题确认、个股排序、仓位分配和风险缩放，不调用外部策略。
- 信号时点：所有扫描仅使用前一交易日已确认的收盘数据。
- 成交假设：下一交易日 regular session open 进场，当日 regular session close 出场。

### LLM 辅助版

- 名称：`nasdaq_theme_intraday_rotation_router_daily_llm`
- 交易核心：与纯量化版一致。
- LLM/news 边界：
  - 初版只做 advisory review，不直接改变交易权重。
  - 允许生成结构化事件审查：财报、SEC filing、监管/出口限制、诉讼、重大产品/客户新闻。
  - 只有当 feature packet 具备 `visible_at`、`published_at`、`fetched_at`、`source`、`input_hash`、`prompt_hash`，并通过单模态基线、边际提升和缺失模态稳健性验证后，LLM/news 才能影响交易。
- LLM 优势用法：
  - 对结构化候选和事件文本做分类，而不是自由预测价格。
  - 对“动量很强但事件风险不可控”的候选生成降权/阻断建议。
  - 输出可审计的 review card，供人和后续 PIT 验证使用。

## 研究依据

- Market Intraday Momentum：开盘信息与日内后续收益存在可研究关系，尤其在波动和成交活跃阶段。
- Industry Momentum：行业/主题层面的动量能解释一部分个股动量，适合作为半导体个股确认条件。
- Momentum Crashes：动量策略在高波动反弹和剧烈风格切换中有崩盘风险，因此必须加入波动缩放、回撤刹车和仓位上限。
- Earnings/filing event risk：财报和重大 filing 会改变短周期分布；没有 PIT 包前只作为审查项，不作为自动交易因子。

参考：

- https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2552752
- https://doi.org/10.1111/0022-1082.00146
- https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2371227
- https://www.sec.gov/edgar/sec-api-documentation
- https://www.alphavantage.co/documentation/

## 因子和路由

### 市场扫描

- QQQ 是否在 SMA 上方。
- QQQ 近 20/60 日动量是否为正。
- QQQ 20 日年化波动是否超出目标。
- QQQ 60/120 日回撤是否触发降档。

### 主题确认

- SMH/SOXX 半导体主题动量。
- XLK/IGV 科技和软件主题动量。
- 半导体个股必须经过 SMH 主题确认，避免单股假突破。

### 个股排序

- 主动量：近 20/40/60 日收益。
- 短确认：近 5/20 日收益。
- 风险调整：动量除以近 20 日波动。
- 排名方式：raw、composite、risk_adjusted。

### 仓位管理

- 总仓位上限：100%。
- beta 核心仓位：0% 到 40%，可选 `QQQ`、`QLD`、`TQQQ`。
- 卫星仓位：40% 到 75%，分散给 top-N 个股/主题。
- 单标的上限：10% 到 20%。
- QQQ 弱势但未破坏趋势时，可降档持有部分 beta；趋势破坏时空仓。
- 波动超目标时按比例缩放。
- 回撤触发时将整体暴露减半。

## 参数空间

首轮搜索必须保持有经济含义，避免无约束暴力调参：

- `market_sma_days`: `[50, 100, 150]`
- `market_momentum_days`: `[20, 60]`
- `signal_momentum_days`: `[20, 40, 60]`
- `confirmation_days`: `[5, 20]`
- `top_n`: `[2, 3, 5]`
- `beta_symbol`: `[QQQ, QLD, TQQQ]`
- `beta_weight`: `[0.0, 0.25, 0.4]`
- `satellite_weight`: `[0.4, 0.6, 0.75]`
- `max_symbol_weight`: `[0.1, 0.15, 0.2]`
- `market_below_sma_scale`: `[0.0, 0.25, 0.5]`
- `target_market_volatility_pct`: `[none, 30.0, 40.0]`
- `drawdown_lookback_days`: `[60, 120]`
- `max_market_drawdown_pct`: `[none, 12.0, 20.0]`
- `score_mode`: `[raw, composite, risk_adjusted]`
- `semiconductor_gate`: `[true]`

## 基准族

每次正式报告必须至少包含：

- QQQ buy-and-hold。
- TQQQ buy-and-hold。
- QQQ open-to-close intraday proxy。
- 等权候选池 buy-and-hold。
- 等权候选池 open-to-close intraday proxy。
- SMH buy-and-hold。
- ex-post best symbol。
- 现金代理。
- 当前 active beta router 的 full annualized return 作为升级门槛。

## 准入门槛

研究通过：

- train/OOS/full 相对 QQQ buy-and-hold 年化 Alpha 均为正。
- full 年化收益必须超过当前 active beta router 的 full 年化收益。
- OOS Sharpe 在 `0.8` 到 `2.4`，超过 `2.4` 触发过拟合警告。
- OOS 最大回撤优于 `-25%`，full 最大回撤优于 `-28%`。
- full Profit Factor 不低于 `1.2`。
- walk-forward 至少 80% fold 的 QQQ Alpha 为正。
- 不能依赖 2026 YTD 单段极端行情撑起结果。

模拟盘候选：

- `workflow_pass=true`
- `research_pass=true`
- `llm_contribution_pass` 仅在 PIT marginal-lift 通过后才可为 true。
- `paper_ready_pass=true`
- 必须有 target-weight/Nautilus 或 paper runner 映射。
- 必须生成信号日志、审查卡、paper readiness、promotion report。
- 必须由用户明确确认后才能启用 `paper_auto`。

## 反过拟合和未来函数规则

- 先写标准和参数范围，再跑回测。
- 训练分数只使用训练窗口；OOS、固定年份和 walk-forward 只做验证。
- 所有信号用 `index-1` 收盘数据，交易收益用下一交易日 open-to-close。
- 不允许按验证结果临时扩大搜索空间。
- 高 Sharpe、低交易数、单一标的贡献过高、近期收益过度集中必须写入 warning。
- LLM/news/event/macro 没有 PIT 证据前不能改变交易。

## 当前执行计划

1. 创建纯量化和 LLM advisory 两个 draft StrategySpec。
2. 实现 deterministic Python 研究模块，输出报告和 JSON。
3. 使用已有 Alpaca IEX daily cache 跑首轮研究。
4. 若研究不通过，记录失败原因并迭代路由；不进入模拟盘。
5. 若研究通过，再补 target-weight 执行映射、promotion report、risk review 和 paper readiness。
