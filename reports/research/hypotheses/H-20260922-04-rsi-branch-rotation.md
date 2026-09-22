---
card_id: H-20260922-04
lane: preregistered
status: 已执行，否定
iteration: h20260922_04_rsi_branch
brief: reports/research/briefs/B-1-rsi-branch-rotation-2026-09-22.md
上一环: H-20260918-05
---

# H-20260922-04 RSI 极值分支 + 板块/杠杆轮动 + 波动率对冲腿（复制 Composer 家族）

> **已执行，否定（2026-09-22）**：16 个预注册 cell 无一通过 G1/G1'（最高 anchor 夏普 0.97，低于同窗 SPY 的 1.02），RSI 分支信号被随机日历平移在留出窗打赢 55%–85%，UVXY 对冲腿 675 天里只触发 10–20 天且净贡献为负，日频换手 107–144 次/年、20 bp 下年化再掉 14 个点。复盘 `reports/research/iterations/h20260922_04_rsi_branch/report.md`，结果卡 `reports/research/briefs/B-1-result.md`，教训 `reports/research/lessons/L-20260922-04.md`。不开第 2 轮。

## 1. 情报（四问框架，引用 I-20260922-02）

- **新不新**：不新。分支式（RSI 过热 → 波动率多头／现金；RSI 超卖 → 杠杆博反弹；否则 → 近一月领涨板块）是 Composer 平台上被公开分享最多的 symphony 结构之一。`I-20260922-02` 采集 #1 的结论是：本周唯一值得本地复制的高近期收益家族就是它。
- **有没有人验过**：平台自己在页面上给了 out-of-sample 一栏。今天（2026-09-22）抓下来的两份快照给出的**不是**采集卡里那两个头条数字：
  - `Sector Rotator MS (CMS update 2025-09-08)`：头条（回测自 2019-10-30）年化 134.72%、夏普 1.7；但同页 Value prop 写的是 "Out-of-sample, this sector-rotation strategy delivered ~98% annualized return with Sharpe ~1.44 vs the S&P's ~18% and ~1.39. Calmar ~3.37; max drawdown ~29%."
  - `Portfolio Experiment: Volatility Minimization`：头条（自 2022-04-13）年化 116.11%、夏普 3.52；OOS 一栏是 "annualized return ~43.7% vs SPY ~20%, Sharpe ~1.92 vs ~1.55, Calmar ~2.90, with max drawdown ~15.1%"。
  **所以真正要复制的目标是 OOS 的 ~98% / 夏普 1.44 和 ~43.7% / 夏普 1.92，不是头条的 134.7% / 116.1%。** 头条数字含样本内，采集卡照抄了头条，这里更正。
- **有没有人分享实盘**：没有独立审计的实盘。Composer 发现页只展示赢家（幸存者偏差），作者可以改配方后重置 OOS 起点。页面数字只能当"值得本地验证的规则"。
- **能不能在我们机器/账户上跑**：能。全部标的是流动性极好的美股 ETF，日线，Alpaca 纸面盘现货多头。唯一的执行风险是 UVXY：ProShares 官方页明确 "seeks a return that is 1.5x the return of its underlying benchmark (target) for a single day"，且 "Due to the compounding of daily returns, holding periods of greater than one day can result in returns that are significantly different than the target return"。对冲腿只能按天持有，不能当长期保险。

**快照带来的关键更正**：采集卡说"阈值不公开"。今天抓下来的 `Sector Rotator MS` 页面**公开了阈值**——"If any sector looks overheated—using a 10-day "heat gauge" (RSI) above 80—it moves to UVXY, a fund that often jumps when markets suddenly drop. If a sector looks washed-out (RSI below 30), it bets on a short-term rebound in that sector"。所以 RSI 窗口 10、过热 80、超卖 30 都是**作者公开的规则**，不是我们要搜的参数。第 1 轮按公开值原样复制。

**与原规则的两处已知差异（必须写在报告里）**：
1. 原规则是**逐板块**算 RSI（"if ANY sector looks overheated"）；我们按 brief 预注册的是在**单一指数**（SPY 或 QQQ）上算 RSI。指数 RSI 触发频率远低于"11 个板块里任意一个"，这会低估对冲腿的触发次数。
2. 原规则超卖时买**那只被打穿的板块本身**（普通或杠杆版）；brief 固定为 TQQQ。

## 2. 最便宜的决定性测试

一次跑完 16 个预注册 cell（日线、CPU 几分钟）：选择窗排名 → 留出窗验证 → 两套安慰剂（日历平移 1–20 日 × 20 种子检验分支有效性；菜单内随机挑 1 只 × 60 种子检验排名有效性）→ 20 bp 压力口径。窗口、成本、成交假设、安慰剂实现全部复用 `scripts/run_h20260918_05_recent_menu.py`。

## 3. 预注册网格（16 cell，见 candidate-manifest.json）

固定（来自公开规则）：RSI 窗口 10；过热阈值 80；超卖阈值 30；超卖分支 TQQQ；正常分支 = 菜单中 21 日收益最高的 1 只；信号日收盘出信号、次日开盘成交；成本 10 bp/边主口径、20 bp/边压力口径。

| 维度 | 取值 |
|---|---|
| RSI 标的 | SPY, QQQ |
| 过热分支资产 | UVXY, BIL |
| 正常分支菜单 | sector1x = 11 只 SPDR 行业 ETF；levered3x = TECL, FAS, ERX, CURE, DUSL |
| 再平衡 | daily, friday |

**对 brief 的一处收窄（不是扩网格）**：brief 写的是"≤ 32 cell"，其中含过热阈值 {80, 85}。两个原因把它固定成 80：(a) 主来源快照公开了 80，第 1 轮是"原样复制"，85 是我们自己加的参数搜索；(b) 用指数 RSI 代替逐板块 RSI 已经让触发频率偏低，往 85 走只会更低，方向是错的。同时，`oc research iteration validate` 对不绑 campaign 的单机制迭代的硬上限是 24 个候选，32 无法通过闸门，16 通过且把多重检验减半。

## 4. 基准与必报数

SPY / MTUM / SPMO / 同波动超额 / 安慰剂五个数，外加 QQQ、TQQQ、S1 现役 sleeve（rot_A2_sector_lb252_top2_weekly）、两个菜单的等权持有。另外必报：每日再平衡的年换手与 20 bp 下的衰减；UVXY 分支的持有天数与收益贡献；三分支（过热 / 超卖 / 正常）各自的贡献分解。

## 5. 否定条件

任一条成立就判否并写 `reports/research/lessons/L-20260922-04.md`：
- 没有任何 cell 同时满足 G1（对标窗年化 ≥ 50% 且回撤 ≤ 35%）或 G1'（夏普 ≥ 2.0 且年化 ≥ 30%）；
- 通过 G1/G1' 的 cell 在留出窗夏普 < 1.0 或收益为负（G2）；
- 安慰剂打赢真值的比例 > 10%（G3）——特别是：如果把 RSI 信号日历平移后收益不变，说明赚的是菜单和牛市，不是分支；
- 20 bp/边下 G1/G1' 不再成立（G4）；
- 规则需要做空、期权、日内或非 Alpaca 可交易标的（G5）。

## 6. 与既有证据的关系

`L-20260918-05`：单一均线门控在这个牛市窗口过不了安慰剂。本卡的新元素正是 **RSI 极值分支** 与 **UVXY 对冲腿**——如果安慰剂再次显示平移信号不掉分，那就是同一条教训的第二次确认，家族整体否定。
`H-20260918-05` S1 是现役 sleeve，用作同窗对照：任何新 cell 必须在对标窗同时打赢 S1 的夏普和年化才值得再占一个 sleeve 名额。
