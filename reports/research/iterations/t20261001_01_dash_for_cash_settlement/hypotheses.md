# Hypotheses: t20261001_01_dash_for_cash_settlement

## Hypothesis

H1: SPY earns a higher return from the open after the settlement-implied marginal cash-raising day b (tau-4 before 2024-05-28, tau-3 after; tau = last trading day of the month) to the open after tau+3 than at other times of the month, enough that DFC_U or DFC_C (a) beats E0 under the four-part replacement rule or (b) passes K1 or K2, with a 100-seed random-entry placebo beat rate >= 0.90 in the judged windows.

## Failure mode

Post-2015 decay of turn-of-month returns (TOM_SPY close tau -> close tau+4 already has anchor Sharpe -0.69 and stress -0.10 here); about 12 round trips a year at 10 bp/side cost about 2.4%/yr against an index edge the papers put at 48-77 bp per month before costs; SPY calendar windows from 2016 on are contaminated by E0-E7 and TOM_SPY.

## Measurement

scripts/screen_batch.py --batch t20261001_01_dash_for_cash --iteration t20261001_01_dash_for_cash_settlement (judged Sharpe in select, anchor, stress and the contaminated 2026 window at 10 bp; 20 bp CAGR; K2 edge vs vol-matched S3; DSR), plus scripts/run_t20261001_01_dfc_placebo.py for the 100-seed random-entry placebo, the SPY day-position profile by settlement era and the pre/post window correlation.

## Stop/Pivot criterion

Stop the index line if DFC_U and DFC_C both fail the replacement rule, K1 and K2. Keep the line open for the cross-sectional stage only if T-20261001-02 passes M1. Adopt nothing automatically: a replacement pass is a proposal to the owner because C2 runs on paper under a fixed rule.

## 预注册全文（2026-10-01 01:07 主审轮写，早于本档案任何数字）

### 机制

养老金、共同基金等机构在月末要付钱（养老金、分红、赎回集中在月初前后）。股票要过结算期才拿到现金，所以它们必须在"结算截止日"前卖出。卖压在最后一个能及时交割的交易日 b 达到顶点，之后停止；新月份的现金回流买入，价格回升（Etula 等 RFS 2020）。Nathan、Suominen、Tasa（2026-06）用 1980–2025 年数据看到输家股在 [τ−9, τ−4] 被集中卖出、约 70% 在 [τ−3, τ+3] 反弹，并且 2024-05-28 美国改 T+1 后，边际卖出日从 τ−4 移到 τ−3（DiD +85.9 bp，t 2.68）。付款日历和结算规则都是制度常量，所以会重复。

和本仓库已有的区别：TOM_SPY（τ 收盘 → τ+4 收盘）已否定，E0–E7 都在月末收盘才进场。月末前、b 之后的这段窗口和 2024 年的换窗都没算过。

### 定义

- τ：每月最后一个交易日（SPY 日线的交易日历）。τ−i、τ+i 按交易日计；τ+3 是下个月第 3 个交易日。
- b（边际卖出日）：τ < 2024-05-28 的月份 b = τ−4；τ ≥ 2024-05-28 的月份 b = τ−3（SEC 2023-29：T+1 合规日 2024-05-28）。
  - 例：2024-04 的 τ = 04-30，b = 04-24；2024-05 的 τ = 05-31，b = 05-28。
  - 2017-09-05 的 T+3→T+2 不换窗：两篇论文对 T+3 时代的边界差一天，压力期里 T+3 只有 16 个月。
- 前窗收益：SPY 收盘 b−6 → 收盘 b（6 个交易日，同 Nathan 等 PreTOM 的宽度）。
- 持有：收盘 b 出信号、b+1 开盘买入 SPY；收盘 τ+3 出信号、τ+4 开盘卖出（冻结合同：收盘出信号、次日开盘成交）。不持有时为现金，现金口径与 E0 在 screen_batch 里相同。
- 窗口：选择窗 2023-09-18→2025-12-31，对标窗 2024-01-08→2026-09-17，压力期 2016-05-02→2023-09-15，2026 污染窗 2026-01-02→2026-09-17（screen_batch 默认）。

### 候选（4 个计入试验；E0_REF 只作复现参照）

| id | b | 条件 | 角色 |
|---|---|---|---|
| DFC_U | 换窗 | 无条件，每月都持有 | 判定 |
| DFC_C | 换窗 | 前窗收益 < 0 才持有 | 判定 |
| DFC_U_FIX4 | 恒为 τ−4 | 无条件 | 对照，不可采用 |
| DFC_C_FIX4 | 恒为 τ−4 | 前窗收益 < 0 | 对照，不可采用 |
| E0_REF | — | 现有 E0（4th Friday→月末 < 0 → 持有下月） | 复现，必须与 H-20260928-20 相差 ≤ 0.01：选择窗 1.339、对标窗 1.241、压力期 0.584、2026 −0.574 |

E0_REF 复现不过，或下面安慰剂引擎与 screen_batch 的夏普差超过 0.05 → `verdict = parity_failed`，照常写出全部数字，由主审决定。

### 判定

1. **替换 E0**（只看 DFC_U、DFC_C），四条全满足：
   - a. 选择窗 10 bp 夏普 ≥ E0 + 0.10 = 1.439；
   - b. 2026 污染窗 10 bp 夏普 ≥ E0 − 0.10 = −0.674；
   - c. 选择窗 20 bp 夏普 ≥ E0 选择窗 20 bp + 0.10 = 1.171 + 0.10 = 1.271；
   - d. 压力期 10 bp 夏普 ≥ E0 的 0.584。

   并且安慰剂打赢比例在选择窗和压力期都 ≥ 0.90。a、b、c 照抄 H-20260928-20 的机主规则，d 是本档案新加的，只会更严。过了记 `replace_proposal`：C2 在模拟盘上按冻结规则运行，改 E 腿要机主同意，所以这是提议，不是自动替换。
2. **K1**：对标窗 ≥ 1.19 且压力期 ≥ 0.65（10 bp），20 bp 下两窗年化 > 0。**K2**：与 S3 的组合增量（screen_batch 的 `diversifier.*.judged_edge`）两窗都 ≥ +0.05。任一过、且安慰剂在对标窗和压力期都 ≥ 0.90 → `keep`。对标窗 ≥ 1.19、压力期没到 0.65、对标窗安慰剂 ≥ 0.90 → `watch_recent`。
3. 都不过 → `refuted`。
4. DSR 按 screen_batch 报（试验数 = 批内 5 个），另写明家族累计 13 个（E0–E7、TOM_SPY 和本批 4 个），只报告。

### 安慰剂（100 个种子，基础种子 20261001）

- 每个种子、每个月：在当月交易日里均匀随机抽一个入场信号日 e，收盘 e 出信号、e+1 开盘买入。持有交易日数与真实候选当月相同：换窗候选在 τ < 2024-05-28 的月份为 7、之后为 6；FIX4 对照恒为 7。到期后下一开盘卖出。
- 条件版的前窗换成收盘 e−6 → 收盘 e，< 0 才持有。
- 相邻月份的持有期重叠时合并为连续持有，只付一次进出成本。
- 打赢比例 = 真实候选夏普高于种子夏普的种子占比，按窗口分别报（10 bp）。
- 真实候选用同一个简单引擎重算，每个窗口与 screen_batch 的 judged 夏普相差 ≤ 0.05。

### 机制诊断（只报告，不进判定）

- SPY 日位置剖面：τ−12..τ+8 每个位置的收盘到收盘平均收益和标准误，按 τ < 2024-05-28 / ≥ 分段，再按压力期、选择窗、对标窗分别报。
- 前窗收益与后窗收益（收盘 b → 收盘 τ+3）的相关系数（Etula 等 2003–2013 为 −0.54），按两段报。
- 指数版换窗检验：(τ−3 日均 − τ−4 日均) 在 2024-05-28 前后之差。机制预测为负：T+1 后 τ−3 变成卖压日、τ−4 不再是。报 NW t。
- C2 近似组合：0.5 × DFC 日净收益 + 0.5 × S0 日净收益（S0 取 `reports/research/screens/h20260928_20_recent_opt/returns.parquet` 的 10 bp 净收益），与同法近似的 0.5 × E0 + 0.5 × S0 比四个窗口的夏普。按日 50/50 是近似（C2 实际按月重置），只报告，不改 C2。

### 横截面机制测量（T-20261001-02，不是候选）

- 池：每月最后一个交易日按 63 日成交额中位数取前 500 只普通股（P500），读 `data/sip/daily` 加 `data/sip-delisted/by_year`（含退市股，T-14 的读法）。
- 动量 12-1：收盘 t−252 → t−21，每月末分十组，D1 输家、D10 赢家，下个月内组别不变。成交额加权为主（63 日成交额中位数代替市值），等权另报。
- 日度市场调整收益：r_i − r_SPY（收盘到收盘）。
- **M1**（机制在我们的数据里存在，门槛）：D1 在前窗日 [b−5, b] 与其余日的市场调整日均收益之差 < 0，且 NW t ≤ −2.0。全样本 2016-05 → 2026-09-17，成交额加权。
- **M2**（反弹，只报告）：D1 在后窗 [b+1, τ+3] 的市场调整日均收益和 t。
- **M3**（换窗，只报告）：Nathan 式 DiD，θ = [D1(τ−4) − D1(τ−3)]_改革后 − [同]_改革前，对照日 [τ+5, τ+8]，剔除 2024-05。2024-06→2025-12（与论文样本重合）和 2026-01→2026-09（论文样本外）分开报。预测 θ > 0。
- 只做多交易经济性（设计证据，不判定）：D1 在 b+1 开盘买、τ+4 开盘卖，报每月毛收益、每边 10/20 bp 的净收益和夏普；D1 − SPY 对冲版（两腿各 10 bp）；D10 和 P500 等权用同法对照。
- 幸存者偏差：加了退市股，但退市当月最后一段收益缺失记 0，对做多输家有利，写进报告。

### 过了之后做什么

- `replace_proposal`：汇报写进"需要你决定"，问机主是否把 C2 的 E 腿换成 DFC。同时从 2026-10 月末起做前向影子（T+1：b = τ−3 = 10-27，10-28 开盘买，11-05 开盘卖）。
- `keep` / `watch_recent`：写 kept.jsonl，冻结规则前向跟踪。
- M1 过：阶段 2 另立预注册，测横截面只做多输家反弹，判定放在没看过的池（dv21 501–1500）上；Hartzmark-Solomon 的派息资金流只作条件变量候选。
- 指数候选全不过且 M1 不过：关闭 dash-for-cash 线，E0 不变。

### 先验

- DFC 过 K1 的概率不到 10%：TOM_SPY 近期为负，每年约 12 次往返在每边 10 bp 下约 2.4%。
- 替换 E0 约 20%。
- M1 过约 60%：Nathan 等 2002–2025 的 β2 为 −8.5 bp（t −2.2），S&P 500 成分股更强。

### 已知偏差

- SPY 2016–2026 的月末窗口在 TOM_SPY、E0–E7 里看过；本档案的判定量（b+1 起的月末前窗口、2024 换窗）没算过。
- 前窗宽度 6 天、出场 τ+3 都来自论文，不是在本仓库数据上选的。
- 改革后样本只有 28 个月末（2024-06 起），换窗检验的功效低，所以只报告。
