# 做空开放后的方向复议（2026-09-29）

任务：T-20260929-32。2026-09-29 owner 把研究范围扩大到 Alpaca 模拟盘能交易的一切（含做空，仅 easy-to-borrow 名单、按 Alpaca 保证金规则、含借券成本），见 `CLAUDE.md`/`AGENTS.md` "Research scope"。此前约 15-17 条 `not_executable`（或 `partial`）的方向，唯一/主要理由是"空头腿不能交易"，本文逐条复议。

## 0. Alpaca 官方文档核实（联网打开，记录 URL 和访问日期）

- **做空与保证金规则**：`https://docs.alpaca.markets/docs/margin-and-short-selling`（访问 2026-09-29）
  - 保证金/做空最低权益 **$2,000**，低于此只有 1x 购买力。
  - **隔夜 2x**："a Reg T Margin Account holding $10,000 cash may purchase and hold up to $20,000 in marginable securities overnight"。
  - **日内最高 4x**：例如 $50,000 现金日内可买卖持有至 $200,000 证券，收盘前须降回合规水平（PDT 细则本页未提及，Alpaca 这份文档没有单独讲 $25,000 的 FINRA PDT 门槛，本轮未从 Alpaca 官方页面单独核实到，按 FINRA 通用规则知晓但不计入本文档的"已核实"部分）。
  - **Easy-to-Borrow（ETB）**：Trading API 用户 **$0 locate/borrow fee**，5,000+ 只标的，无需 locate。
  - **Hard-to-Borrow（HTB）**：下空单前需先拿到批准的 locate，仅限合格保证金账户；locate 以 100 股整手申请；平仓后重新开仓不能复用旧 locate。
  - **借券费**：保证金利息（借现金买股）5.00%（elite）/ 6.50%（非 elite），按每日收盘欠款计提；HTB 空头借券费公式：`每日 HTB 借券费 = Σ((该股 HTB 空头市值 × 该股 HTB 费率) / 360)`。页面没有把这些费率区分"模拟盘 vs 实盘"。
- **模拟盘是否模拟做空/借券**：`https://docs.alpaca.markets/docs/paper-trading`（访问 2026-09-29）
  - 对比表里 "Short Selling" 和 "Margin Trading" 都打 ✅，**模拟盘支持做空和保证金**。
  - 但 **"Borrow Fees" 一栏模拟盘是 ⛔️（"Coming Soon!"），实盘是 ✅ —— 模拟盘目前不模拟借券费**。这意味着：(a) 我们本地按券源分层假设的借券成本，是比 Alpaca 模拟盘账本更保守、更现实的估计；(b) 模拟盘账面收益会天然比我们本地算的"现实摩擦"版本更好看，报数字时必须两套都给。
  - 模拟盘也不模拟：延迟带来的滑点、订单的市场冲击、非市价单的排队位置、监管费、分红；成交假设是"10% 概率部分成交"，不是真实的盘口撮合。

## 1. 逐条复议

判定列："能测"＝空头腿不再是唯一/主要障碍，可以本地重新验证；"仍不能测"＝还有另一个独立障碍（非美股/无规则细节/已被否定/数据缺口），空头腿开放不改变结论。

| id | 状态(旧→新) | 能测? | 现有证据 | 先验 | 最便宜的测试 |
|---|---|---|---|---|---|
| `dir:cross_sectional_gap_fade` | not_executable → **见下方 Part B** | 能测，已测（本任务 Part B） | 本地复现：早窗毛 +99.0%/夏普3.01，边际几乎全在空头腿+最不流动档 | 高 | 见结果 |
| `dir:dual_class_share_arbitrage_pwb` | not_executable → **queued** | 能测 | paperswithbacktest 复跑：5.20% CAGR / 夏普 1.68 / 回撤 -12.47%，196 仓位，月频 | 中高 | 只用美股内高流动性双股权对（GOOG/GOOGL、NWS/NWSA、FOX/FOXA、BRK.A/BRK.B 等），全部是 ETB 巨型股，配对内多空市值中性，本地 SIP 日线直接回测 |
| `dir:etf_constituent_lead_lag_reversion` | not_executable → **queued** | 能测 | 一个 hobby repo（无独立复现）：ETF 大跌日次日成份股反转，corr≈-0.14，分层后夏普 0.9→1.3；本地已有两条相关的负面证据（IBS 择时安慰剂失败、5 日反转无可交易档） | 中 | XLK/SOXX + 最大成份股全是 ETB，直接在本地 SIP 日线上复现多空账本，和已有的两条负面证据做交叉对照 |
| `dir:sectoral_intramonth_momentum` | not_executable → **queued** | 能测 | 仅 Quantpedia 推文摘要（原文本轮仍未打开），"多空"5.99%/0.55、"市场中性"3.77%/0.54，毛口径夏普已经不到 1 | 中低 | 9 只 Sector SPDR 全部 ETB、极高流动性；先补开原文，打不开就按推文描述的三段窗口机制在本地 ETF 日线上重建，net of cost |
| `dir:nasdaq_long_short_event_router_1m` | partial（不改） | 部分能测 | 已到 research_pass（score 28.55），但 `data_acquisition_tier=cached_live` 不满足 `promotion:strict_data`；空头腿授权只是两个阻塞之一 | 中高（工作已大半完成） | 不需要新研究，需要 SIP 分钟线重新验证同一条路线；空头腿不再是障碍，数据层仍是 |
| `dir:letf_decay_short_beta_neutral` | not_executable → **parked** | 名义能测，但撞上既有风控规则 | 仅 SSRN 摘要（Sharpe 最高 2.12，全文未读） | 低（策略本身要求做空杠杆 ETF，正是 2026-09-19 教训 L-20260919-01 要求"按招募说明书杠杆倍数/资产类别排除"的那类产品——SVXY 曾单日 -90%，波动率毫无预警） | 先读 SSRN 全文核实机制是否真的规避了单名杠杆 ETF 的尾部风险，再决定是否值得挑战既有排除规则 |
| `dir:sector_residual_reversal_statarb_decay` | not_executable（不改） | 仍不能测 | 独立复现已经是决定性负面结果：样本外 2019-2024 扛不住真实成本，与空头腿无关 | 低 | 不测——空头腿开放不改变"已经在成本上被否定"这个结论 |
| `dir:deep_learning_stat_arb_residual` | not_executable（不改） | 仍不能测 | 是上一行（已被否定）的近重复机制 | 低 | 不测，理由同上 |
| `dir:classic_anomalies_beta_size_europe_pwb` | not_executable（不改） | 仍不能测 | 需要欧洲上市个股，不在 Alpaca 可交易范围内 | — | 空头腿不是真正的障碍，标的范围才是；不测 |
| `dir:frontier_market_factor_pricing_pwb` | not_executable（不改） | 仍不能测 | 前沿市场（越南/尼日利亚/哈萨克斯坦级）个股，Alpaca 不可交易 | — | 同上，不测 |
| `dir:market_inefficiency_scoring_pwb` | not_executable（不改） | 仍不能测 | 只有 12 个仓位（容量/集中度问题）且隐含非美股范围 | — | 同上，不测 |
| `dir:classic_anomalies_factor_reviews_pwb` | not_executable（不改） | 仍不能测 | 两个长仅美股变体真正缺的是 PIT 价值/账面市值比数据，不是空头腿 | — | 数据缺口，不是空头腿问题；不测 |
| `dir:risk_based_portfolio_construction_pwb` | not_executable（不改） | 仍不能测 | 11 篇文献讲的是"给定选股后怎么加权"（收缩估计/GARCH/风险平价），不是选股信号，不属于本次范围放宽能解决的类别 | — | 不测 |
| `dir:ml_implied_risk_premia_pwb` | not_executable（不改） | 仍不能测 | 除了空头腿，还继承了 `dir:osap_ml_ranking` 同样的 permno-ticker 映射数据缺口（已 parked） | 低 | 空头腿开放不解决数据缺口；不测 |
| `dir:long_short_ratio_extension_pwb` | not_executable（不改） | 名义能测但先验太低 | 130/30 扩展本身刚过夏普 1.00 但回撤 -43.33%，且同家族的 `classic_long_short_anomalies_recent` 已经在近窗测出偏弱 | 低 | 优先级低于上面三条 queued 方向，暂不占用本轮配额 |
| `dir:collective2_extreme_os_reversal_live` | not_executable（不改） | 仍不能测 | "Short-term Reversal" 只是风格标签，没有可执行的规则表，与空头腿无关 | — | 不测 |
| `dir:macro_relative_value_us_vs_canada_pwb` | not_executable（不改） | 仍不能测 | 多空只是"示例性"配置，页面自己说不是处方规则 | — | 不测 |

## 2. 排名前五

1. **`dir:cross_sectional_gap_fade`** —— 唯一已经有强证据（本地复现 Sharpe 3.01）且边际被明确定位在空头腿的方向；本任务 Part B 直接把它跑完。
2. **`dir:dual_class_share_arbitrage_pwb`** —— 配对做多做空全部是巨型股（GOOG/GOOGL 级），借券成本和挤仓风险最低，已发表回测有具体数字，最省钱可测。
3. **`dir:etf_constituent_lead_lag_reversion`** —— 标的同样是超高流动性 ETF 成份股，本地已有两条相关负面证据可以直接交叉核对，避免重复犯错。
4. **`dir:sectoral_intramonth_momentum`** —— 9 只 Sector SPDR 全部免摩擦做空，数据已在手，但报的毛夏普本来就不到 1，优先级低于前两条。
5. **`dir:nasdaq_long_short_event_router_1m`** —— 研究工作已完成大半（score 28.55），空头腿障碍解除后只剩数据层（SIP 分钟线）一个已知阻塞，是"最快能转正"的候选,但不属于本轮新开工作，留给后续按既有 SIP 验证任务处理。

**明确不重开**（空头腿不是真正/唯一障碍，已在表中逐条标注理由）：`dir:sector_residual_reversal_statarb_decay`、`dir:deep_learning_stat_arb_residual`、`dir:classic_anomalies_beta_size_europe_pwb`、`dir:frontier_market_factor_pricing_pwb`、`dir:market_inefficiency_scoring_pwb`、`dir:classic_anomalies_factor_reviews_pwb`、`dir:risk_based_portfolio_construction_pwb`、`dir:ml_implied_risk_premia_pwb`、`dir:long_short_ratio_extension_pwb`、`dir:collective2_extreme_os_reversal_live`、`dir:macro_relative_value_us_vs_canada_pwb`。

`dir:letf_decay_short_beta_neutral` 改判 **parked**（不是 queued）：机制本身要求做空杠杆 ETF，直接撞上 2026-09-19 教训里"按招募说明书杠杆倍数/资产类别排除做空波动率与杠杆产品"的规则；先读全文再决定是否值得挑战这条规则。
