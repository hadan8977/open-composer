# Nasdaq Core Beta Satellite Router 标准文档

日期：2026-05-20

## 目标

在不打断当前模拟盘策略 `nasdaq_beta_exposure_router_daily` 的前提下，研究一个更宽但更克制的新策略：保留已经验证过的 QQQ/TQQQ/CASH beta router 作为核心，只允许小比例 NASDAQ/半导体/科技卫星仓位在核心风险打开时参与。新策略必须证明卫星仓位相对“核心-only ablation”有边际贡献，否则不能因为总收益高就认为新模块有效。

## 策略结构

- 单个策略内部完成市场扫描、核心 beta 路由、主题确认、卫星排序、仓位合成和风险缩放。
- 不调用外部策略下单；核心 beta 路由逻辑以固定 route label 打包进内部结构。
- 纯量化版：`nasdaq_core_beta_satellite_router_daily`。
- LLM 辅助版：`nasdaq_core_beta_satellite_router_daily_llm`，当前只能 advisory。
- 交易频率：日频 open-to-open，前一日收盘后确认信号，下一 regular session open 调仓。
- 总仓位：默认不超过 100% gross。

## 研究假设

- 时间序列动量和绝对动量适合作为 QQQ/TQQQ 核心风险开关。
- 行业/主题动量可以辅助个股动量，但不能独立替代核心 beta。
- 半导体和纳指大盘股卫星只在 QQQ 或 SMH/XLK 主题确认时启用。
- 杠杆 ETF 的日重置和路径依赖风险必须通过仓位上限、回撤控制、核心状态和卫星边际贡献检查约束。

## 参数空间

- `core_variant`: `[active75, aggressive100]`
- `universe_mode`: `[semiconductor, wide_mega, theme_etf]`
- `satellite_budget`: `[0.0, 0.10, 0.20]`
- `satellite_momentum_days`: `[20, 60]`
- `confirmation_days`: `[5]`
- `top_n`: `[2, 3]`
- `max_symbol_weight`: `[0.10]`
- `score_mode`: `[raw, risk_adjusted]`
- `theme_gate_symbol`: `[QQQ, SMH, XLK]`
- `theme_sma_days`: `[50]`
- `theme_momentum_days`: `[20]`
- `target_satellite_volatility_pct`: `[none, 60.0]`

## 准入门槛

- train/OOS/full 相对 QQQ buy-and-hold 年化 Alpha 均为正。
- full 年化相对当前 active beta router 不差超过 3 个百分点。
- 卫星相对 selected core-only ablation 的 full 年化边际贡献为正。
- OOS 卫星边际贡献不能低于 -3 个百分点。
- OOS Sharpe 在 `0.7` 到 `2.5`。
- full 最大回撤优于 `-32%`。
- gross exposure 不超过 100%。
- walk-forward 至少 60% folds 对 active beta 和 core-only ablation 非明显有害。
- LLM/news 没有 PIT marginal-lift 证据前，`llm_contribution_pass=false`。
- paper readiness、target-weight/Nautilus 映射、promotion 和用户确认之前，`paper_ready_pass=false`。

## LLM 版本边界

LLM 不预测价格，也不直接生成交易权重。当前只允许：

- 对候选股票做事件风险结构化审查。
- 识别财报、SEC filing、监管、出口限制、诉讼、重大客户/产品新闻等风险。
- 生成可复放的 review card。

LLM 只有在 feature packet 具备 `visible_at`、`published_at`、`fetched_at`、`source`、`input_hash`、`prompt_hash`，并且通过单模态基线、边际提升、缺失模态稳健性验证后，才可影响交易。

## 回测和防过拟合

- 先固定假设和参数空间，再回测。
- 训练窗口使用 2022-2024；2025、2026、last_12m、last_24m 只做验证。
- 所有目标权重使用 `index-1` daily close，收益用下一 open-to-open。
- 输出 active beta 对照、core-only ablation、QQQ/TQQQ buy-and-hold、卫星等权 buy-and-hold。
- 高 Sharpe、卫星过少、只靠 2026 YTD、current-constituent universe、IEX/cache 数据都必须写入风险结论。

## 参考

- Moskowitz, Ooi, Pedersen, Time Series Momentum.
- Moskowitz and Grinblatt, Do Industries Explain Momentum?
- Barroso and Santa-Clara, Momentum Has Its Moments.
- SEC Leveraged and Inverse ETFs Investor Bulletin.
