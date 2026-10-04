# Hypotheses: t20261004_book_v13_tc

## Hypothesis

The v1.2 primary book loses about 0.24 Sharpe (recent) and 0.18 (stress) to costs and borrow; its main themes are slow (value, quality, investment, momentum, low risk), so trading partially towards the target or inside a no-trade band should cut cost by more than it delays alpha.

## Failure mode

Alpha decays within one or two weeks (seasonality and short-volume themes, rank noise that is real signal), or the VIX halving loses its protection when smoothed, so the net gain is below +0.10 in at least one window; or the account layer's $100 minimum order and whole shares already remove the small trades the rules save.

## Measurement

Offset-median and blended net Sharpe per rule and window, Δ vs B0 per offset, paired NW t of the blended daily net difference, turnover, cost, gross exposure, realized beta, 2x cost; Stage 2 account-layer F1 overlay Sharpe and F2 IR, other variants, family DSR tier, 20-seed placebo.

## Stop/Pivot criterion

No rule meets E1 (+0.10 both windows): keep v1.2 full rebalancing, record the frontier and the death cause; a persistence-tilted aim (GP Proposition 3, a composite change) is the only follow-up and needs a new contract.

## 预注册全文（2026-10-04T01:28:15Z 写，2026-10-04 01:07 主审轮 Opus；早于任何规则的任何数字）

### 0. 为什么做，写之前看过什么

- 纲领主线 1 的"下一步 0‴"把 v1.2 降换手定为下一个主审轮的深挖候选（10-02 07:07）。v1.2 主变体 M0_U3000 已到 P1，正在接模拟盘，它的近期毛夏普 1.74、净夏普 1.51，2 倍成本下 1.23：成本是它最大的可控损耗，也是实盘最不确定的一项。
- **看过的数据**（只有 B0，即 v1.2/T-25 R6 本身；任何规则都没跑过、没模拟过）。本轮从 `data/research/equity_book/realism_ladder/R6_<变体>_o<k>.parquet` 算了成本拆分，5 个偏移取中位：
  - M0_U3000 近期：毛夏普 1.721，净 1.485，交易成本 224 bp/年，波动 10.5%，换手 32.0 倍/年，每单位换手 7.0 bp，借券 23 bp/年；压力期：毛 0.775，净 0.598，成本 152 bp/年，波动 9.6%，换手 26.0 倍/年。
  - VIX 规则翻转（0.5 ↔ 1）每档每年 7.5 次（压力期 6.4 次），翻转那次调仓换手约 1.02（平常 0.33），占成本 26%（两窗相同）。
  - 其他三个变体的成本 109–153 bp/年（近期）、83–122 bp/年（压力期）。
- **先验**：压力期要净夏普 +0.10，相当于在不损失任何毛 α 的前提下省掉约 63% 的成本；近期约 45%。按 T-17"63 日 IC 约为 21 日两倍"的慢衰减证据，部分调仓的 α 损失不大，但 +0.10 两窗都过的概率估计约 20%，最终替换约 12%。做它的理由：成本敏感度是 v1.2 进实盘前最大的未知；即使不替换，也能得到成本-α 的前沿和换手来源，供下一步（按持续性倾斜的瞄准组合）设计。

### 1. 问题

在不改信号、不改构造（合成分、行业去均值、易借空头、EWMA SPY 对冲、VIX 减半、5 档周频、D+1 收盘成交）的前提下，把"每档刷新时全量调到目标"换成成本感知的交易规则，能不能让 v1.2 主变体的净夏普在近期和压力期都至少高 0.10，并且在账户层（整股、$100 最小单）保持下来？

### 2. 基线 B0（不是试验）

B0 就是 v1.2 的策略层：`scripts/book_v12_account.py` 的 `strategy_pass`（它已和 T-25 R6 逐位一致，identity.json max_abs_diff 0.0）。第一步必须用新代码路径复现 `R6_M0_U3000_o0.parquet` 和 `R6_M0_U3000_o3.parquet` 的 gross、cost、borrow、net，最大绝对差 ≤ 1e-12。

### 3. 规则（5 个，参数全部写死）

记号：某档在决策位置 p（日期 t）刷新。
- `w_tgt`：R6 目标权重，即 `tranche_target(...).w`（已含易借限制、成交价缺失置零、VIX 缩放 s_t）；`w_unit` 为不含 VIX 缩放的同一向量（`.w_unit`），s_t = `.vscale`。
- `x_old`：该档上一块持有期结束时漂移后的权重（`strategy_pass` 里的 `w_state`），首块为 0。
- 成员集 M_t = {i : w_tgt_i ≠ 0}。
- 易借集 E_t：`decision_inputs` 的 `eligible`（映射到全局 symbol，未出现记 False）。

所有规则共用的硬约束：
- (a) i ∉ M_t：x_new_i = 0（离开宇宙、空头不再易借、D+1 无成交价的名字当次全部平掉，与 B0 相同）；
- (b) i ∉ E_t：x_new_i = max(x_new_i, 0)（不易借的名字永不持空）；
- (c) 对冲 h_new = −Σ x_new_i β_i，β 用 `tranche_target` 同一口径（EWMA，缺失 1.0，截断 [−1, 4]），每次刷新全量调整；
- (d) 成本 = `T25.real_cost(ctx, t, symbols, x_new − x_old, h_new − h_old, attrs)`，换手 = Σ|x_new − x_old|；借券、持有、漂移与 B0 完全相同（`bv.hold_block`，25 bp/年）。

| 规则 | 对 i ∈ M_t 的定义 | 来源 |
|---|---|---|
| P2 | x_new = x_old + ½ (w_tgt − x_old) | GP 2013 命题 2 的固定速率形式 |
| P3 | x_new = x_old + ⅓ (w_tgt − x_old) | 同上 |
| P2V | u_old = x_old / s_prev（s_prev 是该档上次刷新用的 VIX 缩放，首块记 1）；u_new = u_old + ½ (w_unit − u_old)；x_new = s_t · u_new | GP：风险变大时交易更快；VIX 缩放整体立即生效 |
| N25 | x_new = clip(x_old, w_tgt − δ, w_tgt + δ)，δ = 0.25 × std({w_tgt_i : i ∈ M_t})（总体标准差，ddof = 0） | NMV 2016 买入/持有价差的连续权重版 |
| N50 | 同上，δ = 0.50 × std(...) | 同上 |

τ 取 ½、⅓，带宽取 0.25、0.50 个截面标准差，都按文献形式事先定（NMV 的 10%/20% 在正态分数上约 0.44 个标准差），不搜索。

### 4. 计算

- **策略层**：每个（规则, 偏移 o ∈ {0..4}）在 M0_U3000 上跑 2017-10-02 到数据末（标签日与 T-25 相同），输出与 R6 相同的列（gross、cost、borrow、turnover、spy、hedge_size、vix_scale、net），另加 `gross_exposure` = Σ|x_new|（刷新当天的值，持有期内沿用）。
- **窗口**（标签日）：近期 2024-01-08..2026-09-15；压力期 2017-10-02..2023-08-31；全样本 2017-10-02..2026-09-15；A 2024-01-08..2026-06-30、B 2026-07-01..2026-09-15 只报告。
- **指标**：用 `scripts/realism_ladder_book_ls.py` 的 `series_metrics` 和 `blend`（同一年化、同一 OLS/Dimson beta）。每个（规则, 窗口）报：偏移中位净夏普、偏移中位毛夏普、5 档混合净夏普、年成本 bp、单边年换手、平均总敞口、OLS 和 Dimson beta、2 倍成本净夏普（同一权重路径，成本乘 2，不重跑）。
- **相对 B0**：每个偏移的净夏普差；混合日净收益差 d_t = net_rule,blend − net_B0,blend 的 Newey-West t（滞后 5），全样本和两窗分别报。

### 5. 判定（机械，写死）

**资格**（规则必须全部满足）：
- E1（runbook 第 5 节"优化迭代"规则，原样执行）：偏移中位净夏普 − B0 ≥ +0.10，近期和压力期**都**满足；
- E2：两窗各自至少 4/5 个偏移的净夏普高于 B0；
- E3：全样本 d_t 的 NW t（滞后 5）≥ 2.0；
- E4：混合净收益的 OLS beta 和 Dimson beta 绝对值在两窗都 ≤ 0.15。

**选择**：满足 E1–E4 的规则里，近期偏移中位净夏普最高的记为 R*；差距 ≤ 0.01 时取近期换手低的。

**阶段闸门**：没有规则满足 E1–E4 → 第 1 阶段结束，不跑第 2 阶段，结论"保留 v1.2 全量调仓"，写死因（哪一条没过、差多少）。

**第 2 阶段确认**（只对 R*，全部满足才替换）：
- K1 其他变体：M0_P1000、M1_U3000、M1_P1000 各跑 B0 和 R* 的 5 个偏移，近期偏移中位净夏普差 > 0 的至少 2/3。
- K2 账户层：用 `book_v12_account.py` 的模拟器（整股、$100 最小单、保证金表、F1 k_eff、T-bill 腿、F2 叠加层），把规则作用在档的虚拟股数上（换算到权重：x = v × P_ref / (E/5)，按第 3 节算出 x_new 再换回股数；死亡名字照旧置零；对冲虚拟股数 = h_new × (E/5) / SPY_ref，h_new 按 x_new 算）。要求：F1 叠加层近期净夏普(R*) − F1 叠加层近期净夏普(B0) ≥ +0.05，压力期的同一差值 ≥ 0；F2 近期相对 SPY 的信息比率(R*) ≥ B0；保证金违规会话 0。B0 账户层取已有的 `data/research/book_v12/A1_M0_U3000_F1_overlay.parquet` 和 `A1_M0_U3000_F2.parquet`，先核对近期 F1 叠加层净夏普复现 v1.2 的 1.4124（差 ≤ 0.001）。
- K3 档位：评判标准 v2.0.1，族 = v1.2 的 10 条 + 本合同 5 条（N = 15），全项目 N = 116（ρ̄ 0.5，var_SR 规则同 v1.2）；R* 的 20 个种子安慰剂（`book_v12_placebo.seed_pass` 的同日打乱，规则同样作用在打乱后的目标上）净、毛分位都 ≥ 0.95；稳健性和否决项同 v1.2 记分。R* 档位 ≥ P1。

**结果**：
- 全部满足 → v1.3 = v1.2 + R*。生产端目标生成器和下单引擎的改动另立任务；切换不早于 v1.2 两周执行验证之后的第一次月度复评；前向记录按规则版本分开记。
- 否则保留 v1.2，写明哪一条没过。

### 6. 诊断（不参与选择，只用不含收益的量）

- D1 换手来源（B0，两窗）：VIX 翻转调仓与其余调仓的换手和成本占比；漂移量 Σ|x_old − x_prev_new|（上次刷新后的持仓到这次刷新前的漂移）与目标变化量 Σ|w_tgt − w_tgt,prev| 各自的年化值。
- D2 主题持续性（偏移 0 的决策日、相邻两周）：9 个主题分数和 M0 合成分的截面秩自相关，两窗各取中位数。
- D3 所有规则在 2 倍成本下的前沿（只报告）。

D1/D2 不含收益信息，可以直接用于下一份合同（按持续性倾斜的瞄准组合）的设计。

### 7. 适用状态、有效期、失效信号、退出规则

与 v1.2 第 7 节相同，不因交易规则改变。替换后另加一条：前向实际成本（对账价 vs 决策价）连续 4 周低于模型的 0.5 倍时，复核是否回到 B0（成本低时快交易更优，GP 命题 2）。

### 8. 试验登记

- 本合同新增 5 个可选试验（P2、P3、P2V、N25、N50），只在 M0_U3000 上选。B0 是基线，不计试验；K1 的其他变体只跑 R*，不可选，不计试验。
- 定档族 N = 15，全项目 N = 116。
- 不在本合同下尝试第 3 节以外的速率或带宽。

### 9. 局限（事先写明）

- 规则在每档内独立作用，账户层是 5 档轧差：账户层的效果可能小于策略层（$100 最小单本身就是一道隐性的不交易区间），所以 K2 是必要条件。
- 成本模型是 NBBO 抽样校准的 v1 模型；实际成交成本未知，2 倍成本前沿只作参考。
- 部分调仓让新进入的名字分几周建仓，平均总敞口会低于 B0；判定用夏普（与规模无关），总敞口只报告。
- 压力期 2017–2023 用于 E1 是 runbook 的规则；按评判标准 v2，压力期只用于否决，这里取两者中更严的一个。

### 10. 过了之后做什么 / 不过做什么

- 过：另立生产任务（目标生成器保存每档漂移后的虚拟股数，按 R* 更新；引擎不变），并把 R* 写进 v1.2 模拟盘的月度复评。
- 不过：按 D1/D2 的结果判断换手主要来自哪些主题；若季节性、卖空成交比这类快主题贡献大，就写"按持续性倾斜的瞄准组合"（GP 命题 3）的新合同，主题权重只用 D2 这种不含收益的持续性量来定。
