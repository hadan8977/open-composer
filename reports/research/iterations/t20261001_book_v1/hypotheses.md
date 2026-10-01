# Hypotheses: t20261001_book_v1

## Hypothesis

H1: combining the slow themes (value, quality, investment/issuance, momentum, low risk, earnings, insider, short information, seasonality) under a factor risk model, modelled costs and an easy-to-borrow constraint gives an F1 book whose median-offset net Sharpe passes K1 (anchor >= 1.19, stress >= 0.65, 2x-cost excess > 0) or K2 (edge >= 0.05 over vol-matched S3 in both windows, raw and cash-matched), with placebo beat >= 0.95 overall and >= 0.80 per window, realised beta within +-0.15 (daily and Dimson) and solver failures < 2%. H2 (ml_contribution_pass): M2 or M3 beats M0 in net Sharpe in both windows in the same universe set-up.

## Failure mode

Signals too weak or regime-flipping in the liquid pool (Stage 0: P1000 8-book combo stress -0.23); edge concentrated in hard-to-borrow microcaps that SE_t excludes; costs at the open eat the turnover; the risk model fails to neutralise beta (D3 interim check shows realised book beta 0.3-0.7 for Stage 0 books); B infeasible under the industry constraint with ETF-only shorts.

## Measurement

evaluate.window_metrics (excess over BIL), k1_check, k2_edges on the model-cost series and on the cash-matched series, Dimson beta, solver failure counts, 2x-cost replay, 100-seed placebo for K1/K2 passers, DSR with 77 trials; per-variant turnover, cost share, exposures, leave-one-theme-out (M0_A offset 0) and fixed stress days.

## Stop/Pivot criterion

All 12 fail research_pass: book v1 refuted, infrastructure kept, expand the signal library (no parameter tuning); if M0's anchor residual IC also has NW t < 2, add signals before a v2 contract. Any pass: open the D6 forward shadow, propose a paper sleeve to the owner after 20 clean forward sessions.

## 预注册全文（2026-10-01 07:30 UTC 主审轮写，早于任何 Stage 2 数字）

依据 `docs/equity-book-design.zh.md` 第 9–10 节（06:32 UTC 冻结）。本节只补设计没写死的定义；凡是新增的条件都只会更严，不放宽任何冻结门槛。Stage 0 的 65 格是在同一段历史上看过的诊断，只用于设计，计入 DSR 试验数，不是候选。

### 1. 变体（12 个，全部计入试验）

| id | 合成 | 宇宙/空头 | 阶段 |
|---|---|---|---|
| M0_A / M0_B / M0_C | M0 主题等权 | A / B / C | 2a（T-20261001-08） |
| M1_A / M1_B / M1_C | M1 滚动 IC 加权 | A / B / C | 2a（T-20261001-08） |
| M2_A / M2_B / M2_C | M2 GBDT 集成 | A / B / C | 2b（T-20261001-09） |
| M3_A / M3_B / M3_C | M3 随机傅里叶特征岭回归 | A / B / C | 2b（T-20261001-09） |

### 2. 宇宙和空头

- U3000_t、P1000_t 按设计第 2 节，取 D2 面板的成员标记。SE_t 取 `borrow.short_eligible`，规则版本在 T-20261001-04 验收时确定。
- 对冲 ETF：SPY、IWM、IJR 和 11 只行业 SPDR（XLB XLC XLE XLF XLI XLK XLP XLRE XLU XLV XLY），即 `panel.HEDGE_ETFS` 去掉 SGOV、BIL、SHY；某天没有价格的 ETF 当天不可用。
- **A**：多头 U3000_t；空头 SE_t ∩ U3000_t 加对冲 ETF。
- **B**（F1b）：多头 U3000_t；空头只用对冲 ETF。
- **C**：多头 P1000_t；空头 SE_t ∩ P1000_t 加对冲 ETF。
- **ETF 的风险暴露**（设计没写）：对风险模型的日因子收益做过去 252 个会话的滚动时间序列回归，按 `etf_risk.py`（交互会话 D5 子代理在写）的"类股票"参数化：行业载荷之和等于市场载荷，这样复制市场的股票多头和 SPY 空头在每个行业都能抵消。确切实现和参数以修正案 A1 绑定的 `etf_risk.py` 哈希为准，A1 之后不再改。ETF 的 beta 和个股用同一种估计。
- 风险模型只在周五和月末存盘：调仓日不是存盘日时，用不晚于调仓日的最近一期（时点正确，只是旧几天）。

### 3. 信号、目标和合成

- **慢主题 9 个**（M0、M1 只用这些）：价值 {bm, ep, sp, cfp}；质量 {gp_at, roe, op_at, −accruals}；投资/发行 {−asset_growth, −nsi_12m}；动量 {mom_12_1, ind_mom_12_1, resid_mom_12_1}；低风险 {−beta_252, −idio_vol_63}；盈余 {sue_eps, sue_rev}；内部人 {cmp_opportunistic_buy_60d, net_buy_usd_nonplan_60d / 市值}；卖空信息 {−short_volume_ratio_mean_21, −SI/股本}；季节性 {同月 5 年平均收益}。快信号只进 M2、M3。
- 主题分 = 该主题内已处理 z 值的平均（缺失记 0）；合成分 = 9 个主题分的平均，再在该变体的多头宇宙内按日截面标准化。
- **目标**（IC、M1 权重、M2/M3 标签共用一个定义）：y_{i,t} = r^{开→开}_{i,t+1→t+22} − Σ_{k=t+1}^{t+21} X_{i,t}′f_k。开盘到开盘收益取 `returns.forward_open_to_open`，因子部分用风险模型的日因子收益；两端各差一个隔夜，接受并写进报告。
- **M1**：主题权重 ∝ max(0, 平均 IC_k / IC_k 标准差)。IC_k 是主题分 k 在月末形成日对目标的 Spearman 秩 IC，只用形成日 ≤ t − 22 个会话的观测，最多 60 个月、至少 24 个；不足 24 个或权重全为 0 时用 M0 的权重。每个月末之后的第一次调仓更新权重。
- **α 的缩放**：α_i = IC_t × σ_i × score_i，σ_i = √(21 × D_i)。IC_t = 0.5 × IC_hat + 0.5 × 0.03，IC_hat 是该变体自己的合成分在最近至多 36 个形成月末（形成日 ≤ t − 22 个会话，至少 12 个，否则 IC_t = 0.03）的平均秩 IC；IC_t 下限为 0。
- **M2**（现在固定，防止看到 2a 结果后再调）：LGBM（`kt.LGBM_REG_PARAMS`）、XGB、CAT 三个模型，超参数与 `t20260930_17_model_family_sweep/hypotheses.md` 的表格逐字相同；每个形成日把三者的预测转成百分位秩后取平均。特征是信号库全部列（含快信号），标签是 y 在形成日内的百分位秩。训练用月末形成日、扩展窗口，训练标签的形成日 ≤ 重训日 − 22 个会话；第一次在 2017-10 前拟合，之后每年 1 月重训。
- **M3**（同样现在固定）：特征同 M2，缺失记 0；ω_j ~ N(0, I_d)，2,000 组，特征为 [sin(Xω_j/√d), cos(Xω_j/√d)]，共 P = 4,000；种子 20261001。岭惩罚 λ ∈ {1e−3, 1e−2, 1e−1, 1, 10, 100, 1000} × tr(S′S)/P，在训练窗最后 24 个月（与训练段间隔 ≥ 22 个会话）上按验证 MSE 选，再在全训练窗重拟合。标签和重训日程同 M2。

### 4. 组合构建和回测

- 优化器按设计第 8 节，由 `optimize.py`（T-20261001-06，交互会话在写）实现，版本由修正案 A1 绑定：目标 α′w − 半价差·|Δw| − 冲击·|Δw|^1.5 − 借券，约束美元中性、|β′w| ≤ 0.02、行业 ≤ 0.01、规模 ≤ 0.10、其他风格 ≤ 0.25、单名 ≤ 0.01、总敞口 ≤ 1.0、事前年化波动 ≤ 5%、空头资格、E = $100 万下单笔 ≤ 1% ADV；空头整股，多头允许碎股。主审对实现的最低要求：约束按设计逐条实现、不放宽；短债腿补足到现金为 0。
- 求解失败（Clarabel 没有给出 optimal 或 optimal_inaccurate，或抛异常）时沿用漂移后的旧持仓，记一次失败（设计第 8 节）。
- `backtest.run_book`：`BookConfig(freq="W", offset=k, exec_price="open", cost_fn=成本模型 v1, borrow_bp_per_year=25, tbill_symbols=("SGOV","BIL"), margin_rate=0.065)`，k = 0…4。第一笔成交 2017-10-02 开盘，判定窗到 2026-09-17；2026-09-18 以后只作前向报告。
- 退市按最后有效收盘价；多头退市额外 −30% 的敏感性只报告。
- 每次运行把每个调仓日的目标权重存成 parquet。2 倍成本、固定 10 bp 和 20 bp 都**重放同一条权重路径**（决策仍按 1 倍模型成本），不重新优化，只改记账成本，所以比"按 2 倍成本重新优化"更严。2 倍成本 = 半价差、冲击、费用各乘 2，借券对全部空头按 100 bp/年。

### 5. 判定（全部取 5 个偏移的中位数）

**(1) K1 或 K2**
- K1：`evaluate.k1_check`，对标窗夏普 ≥ 1.19、压力期 ≥ 0.65，两窗 2 倍成本年化超额收益 > 0。夏普一律是对 BIL 的超额收益（`evaluate.window_metrics`）。
- K2：`evaluate.k2_edges` 在模型成本序列上两窗都 ≥ 0.05（冻结规则），**并且**在"现金对齐"序列（净收益 − BIL + SHY）上两窗也都 ≥ 0.05（主审新增，只会更严）。≥ 0.10 记强保留，也要两种口径都满足。
  - 加这一条的原因：主审 07:2x 用零 α、年化 5% 波动的空书做了检查（20 个种子）。冻结口径下 K2 增量是压力期 −0.276、对标窗 −0.020，现金换成 SHY 后是 −0.309、−0.114。差出来的 +0.03 / +0.09 来自 F1 的短债腿拿 BIL、而对照组拿 SHY 的利差，不是 α。按机主规则，多放短债不算改进。空书的 K2 增量在种子之间的标准差约 0.05–0.06，所以 K2 本身噪声大，必须和安慰剂一起看。

**(2) 必要条件，四条都要过**
- 安慰剂：见第 6 节。全样本 2017-10-02 → 2026-09-17 打赢比例 ≥ 0.95，压力期、对标窗各 ≥ 0.80。
- 实现 beta：`window_metrics` 的日 beta 两窗都在 [−0.15, 0.15]，**并且** Dimson beta（日净收益对 SPY_t 和 SPY_{t−1} 回归的两个系数之和）两窗也都在 [−0.15, 0.15]（主审新增：小盘股价格滞后会让日 beta 偏低）。
- 求解失败率：各偏移失败率的中位数 < 2%；任一偏移 > 5% 记为工程问题，由主审复核，但不改判定。
- 2 倍成本下两窗年化超额收益 > 0。

**research_pass** = (1) 且 (2)。

**ml_contribution_pass**（单独判）：存在某个宇宙 u 和 m ∈ {M2, M3}，使 m_u 的净夏普在两窗都高于 M0_u。另报日净收益差的 NW t，只作参考。

**DSR**：`evaluate.deflated_sharpe`，试验数 77，报对标窗和全样本，只报告，不作门槛。

### 6. 安慰剂

- 种子 s = 0…99，随机数种子 20261001 + s，偏移 = s mod 5（每个偏移 20 个种子）。
- 在每个调仓日、变体自己的多头宇宙内打乱合成分（α 缩放之前；`evaluate.permute_within_date`）。IC_t 序列、风险模型、成本、约束和空头集合都与真实运行相同。
- 打赢 = 真实运行在同一偏移上的夏普 > 该种子的夏普，按压力期、对标窗、全样本分别算比例。
- 只对过了 (1) 的变体做：research_pass 需要 (1) 和 (2) 同时成立，(1) 不过时安慰剂不改变结论。

### 7. 报告（每个变体）

两窗和间隔期的净夏普（5 个偏移逐个列出加中位数）、年化超额收益、波动、最大回撤、K1、K2 两种口径、日 beta 和 Dimson beta、行业和风格暴露的均值与最大值、换手、成本占比（半价差、冲击、费用、借券分开）、多空和短债敞口、求解失败率和求解时间、固定压力日（2020-03、2020-11、2025-01-27、2025-04、2025-06/07、2025-10、2026-06/08）、2026-09-18 以后的前向段、DSR。只对 M0_A 偏移 0 做"去掉一个主题"的 9 次重跑（诊断，不判定）。另报 t+1 收盘成交的敏感性：夏普比开盘成交低一半以上时，标"对成交时点敏感"，开前向影子前由主审复核。

### 8. 运行顺序和前置

1. T-20261001-05（信号库）、T-20261001-06（优化器）完成，且 D2–D4、D7 已验收。
2. 修正案 A1（只填版本，不改任何规则）：`risk.py`、`costs.py` + `cost_model_v1.json`、`borrow.py`、`optimize.py`、`signals.py` 的 sha256，风险模型构建的 `meta.json`，以及对应提交号。写 A1 时本档案下不得有任何 Stage 2 结果文件。A1 写完以前不运行。
3. T-20261001-08 先跑 M0_A 偏移 0，作为管道检查（报运行时间和失败率），再跑其余。单次回测本机超过 20 分钟就上 Modal，启动前先过 `scripts/modal_budget.py check`。
4. T-20261001-09 在 T-08 完成后运行；M2、M3 的设置已在第 3 节固定，看到 T-08 的结果后不能再改。

### 9. 先验

- 任一变体过 K1：< 5%（K1 约是系统化多空基金 90 分位的水平）。
- 任一变体过 K2（两种口径）：约 10%。主审 07:4x 用合成书标定了 K2 的实际门槛（年化 5% 波动、与 S3 零相关、每格 12 个种子）：压力期要组合净夏普约 0.75（冻结口径）/ 0.85（现金对齐）才到 +0.05，对标窗只要约 0.13 / 0.26。设计第 0 节按 (SR_S3 + SR)/√2 估的是压力期 0.41、对标窗 0.69，两窗正好反了：压力期 S3 自身夏普只有 0.645，按 63 日波动率倒数加权时组合风险大半落在 5% 波动的书上；对标窗 S3 的波动择时反而抬高组合夏普。所以 K2 卡在压力期，需要的净夏普接近职业基金 75 分位（0.87），而 Stage 0 流动池合成在压力期是 −0.23。
- research_pass：约 8%。ml_contribution_pass：约 35%。

### 10. 过了之后做什么

- 有变体 research_pass：另立 D6 前向影子的预注册（每天 23:05 前记目标持仓和信号日志），前向满 20 个会话且无工程故障后，向机主提交模拟盘提议（预算、做空授权、整股处理）。不自动上模拟盘。
- 12 个都不过：组合 v1 记为否定，基础设施保留；用"去掉一个主题"和 M0 的残差 IC 诊断死因；下一步扩信号库（文本等免费来源），不调参数。M0 在对标窗的残差 IC 的 NW t 也 < 2 时，先补信号再开 v2 合同。
- B 的求解失败率 ≥ 2%：记为"冻结的行业约束下只用 ETF 对冲不可行"，这不是放宽约束的理由。

### 11. 已知风险（写在结果之前）

- D3 验收记录（提交 12d9cef，交互会话）：对标窗里按预测 beta 中性化的动量/COMP4 组合仍有 +0.40（EWMA-63）到 +0.75（模型隐含）的有符号 beta 偏差，压力期约为 0；残差 PCA 显示还缺共同因子。交互会话已排 D3.1 修正。D3.1 修不好的话，Stage 2 多半过不了 beta 条件，这是诚实的结果，不放宽；A1 绑定的是 D3.1 之后的版本。
- 流动池信号弱、会随市场状态翻转（Stage 0）；空头资格会排除次流动池里收益最高的稀释型小微盘。
- 早期的 M2/M3 模型训练数据很少（2017-10 前只有约 8 个月的标签）。
