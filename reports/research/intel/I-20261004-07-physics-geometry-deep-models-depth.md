# I-20261004-07：物理、几何、拓扑和深度序列模型——做到什么程度才见效

写于 2026-10-05 04:34 UTC，Sonnet 5.5 high，协调码 R1004-T82，简报 `reports/research/control/briefs/T-20261004-82.md`。机器可读版：`I-20261004-07-physics-geometry-deep-models-depth.json`。
原文快照在 `reports/research/intel/sources/physics-geometry-2026-10-04/`（文件头有 `fetched_utc`，每个不超过 200 KB，超长的已截断；已有的 `methods-2026-10-04/` 没有重抓，只引用）。

证据档：1 无；2 只有回测；3 样本外或发表后；4 机构自述实盘；5 可核验或独立复现。
**读法**："摘要级"指原文打不开、只有搜索摘要，摘录见 `websearch_excerpts_blocked_sources.md`；"（我的推断）"指不是论文写明的，是我从论文推出来的。

## 1 一页结论

**机主的判断有证据支持：深度确实不是线性的。但只在下面四处，别的方法族缺的不是深度，是能胜过简单基线的样本外证据。**

1. **随机特征 SDF（DKKM/AIPT）**：夏普随复杂度 c=P/T 的变化不是单调的。无岭惩罚时在 c≈1 崩到 0，只有 c≫1 且加岭才持续上升，论文一直测到 c=1000（P=360,000）。只在 c<1 测，会得到"没有效果"或"崩溃"。我们的 M3 是 P=4000、23 个输入，c 约 10 到 73，已在 c≫1 区，缺的是信息集宽度（23 对论文的 130）和复杂度曲线。
2. **路径签名预测波动**：Horvath 等 2026 用 3 阶、时间增强的领先–滞后签名，拼最近 22 个交易日共 858 个特征，12 个货币对样本外 R² 0.361 对 HAR-RV 0.224。（我的推断）1–2 阶只对应二次变差一类标量，被 HAR-RS 吸收，浅测会得出假否定。
3. **多期限辅助目标**：TCTS（ICML 2021）一期任务 RankIC 从单任务 GRU 0.049，到普通多任务 0.061，到调度后 0.075；辅助任务集不是越大越好（10 个期限的普通多任务降到 0.052）。
4. **基础模型**：现成预训练模型零样本预测收益是负的（Chronos 样本外 R² -1.37%，TimesFM -2.80%，CatBoost -0.10%）；只有在大规模金融数据上从零预训练才有增益，规模要到 20 亿观测量级（搜索摘要，待核对）。这是"深度"的门槛，也是我们现在做不到的。

**三类结论**

- **第 1 类，直接采用**：HAR-RV 及半方差/跳扩展作波动预测基线（放进 `equity_book/risk.py` 旁的波动预测层）；协方差非线性收缩（QIS/DCC-NL）作风险模型对照。两者的增益在风险而不是夏普，v1.2 已是因子模型加收缩，增量要实测。
- **第 2 类，值得深做**（按优先级）：(a) M3 的复杂度曲线与信息集加宽（R1）；(b) 签名波动预测（R2）；(c) 多期限辅助目标进 M2（R3）。低优先：MSM 的 21 天对照；金融预训练序列模型（算力超预算，阶段 4）；动量子策略的崩盘叠加层。
- **第 3 类，不做**：现成基础模型零样本、Kronos、DMD/Koopman 交易、TDA 作 alpha、Wasserstein 聚类、HRP、粗糙波动率/MSM 用于股票组合、泛泛的波动管理、扩散映射/UMAP。理由和重开条件见第 7 节。

**三个警示**

- 这批论文的夏普几乎都是毛口径：DKKM 的 3.7（微盘影响大，大/超大盘约 1.6–1.8）、FinText 里 CatBoost 的 6.79（每天调仓、零成本）、Kronos 没有成本说明。目标一律按扣成本后的同波动口径定。
- 复杂不等于有增量：Nagel（NBER w34104）说 DKKM 一类模型退化为按波动择时的动量，Kelly–Malamud 2025 有回应但没有推翻。M3 必须带一个同输入的动量择时基线。
- 波动预测变夏普很容易落空：Cederburg 等 103 个策略里只有 53 个夏普差为正（零假设期望 66），样本外劣于不管理。波动类改进只按同波动配对夏普收。

**复现目标**：R1 DKKM 复杂度曲线；R2 签名预测波动（表 2）；R3 TCTS 表 3；R4 Gidea–Katz 加 Guritanu 的因果 TDA；R5 Ledoit 系收缩 N=1000。可选校准 R6。详见第 4 节。

**我对各线能在账户层面通过现行评价标准的先验（判断，不是数据）**：M3 加深约 15–20%；多期限辅助目标进 M2 约 20%；签名波动预测接入账户 10% 以下（但作为波动预测基线的改进概率高得多，它回答的是预测，不是夏普）；TDA 5% 以下。

**下一步**：阶段 0（10-05 至 10-08，本机）先做 R6、R5、R4 三个便宜复现，再按第 6 节推进。本任务没有创建迭代，没有跑实验；真要开跑需要 `oc research direction-check` 和现有迭代门禁。

## 2 方法族证据表

### F1a HAR-RV 及半方差/跳扩展（族：1 湍流/多重分形/粗糙波动率）
- **结论**：第 1 类：主流且样本外强，直接采用——直接采用，作波动预测基线。证据档 5（可核验或独立复现）
- **最强实现**：Corsi 2009 HAR-RV（日/周/月三个已实现波动分量的线性回归）；Log-HAR；HAR-RS/-J/-CJ
- **样本外/发表后证据**：独立评估一再把它当作最难打败的基线：Bennedsen 等 2022 的对比集；2026 年 TSFM 论文（50 个资产、9 个零样本基础模型对 8 个计量模型）结论是计量基准仍有竞争力，只有最小的 TTM 以微弱优势胜 Log-HAR；Horvath 等 2026 在外汇上 HAR-RV 的样本外 R² 为 0.224
- **限制**：预测精度不等于夏普。波动预测换成夏普要过同波动配对检验（见 F1d）
- **放进哪里**：波动预测层，接在 open_composer/research/equity_book/risk.py 的因子方差和特异方差之外；需要 SIP 分钟线算日内已实现波动
- **快照**：`sources/physics-geometry-2026-10-04/wu__corsi2009_har_rv.md`；`sources/physics-geometry-2026-10-04/arxiv__2607.05291_tsfm_realized_vol_vs_econometric.md`；`sources/physics-geometry-2026-10-04/arxiv__2607.17865_how_fast_do_signatures_learn.md`；`sources/physics-geometry-2026-10-04/arxiv__1610.00332_bennedsen_decoupling.md`

### F1b 马尔可夫切换多重分形 MSM（族：1 湍流/多重分形/粗糙波动率）
- **结论**：第 2 类：有部分样本外证据，值得深做——有部分证据；对我们的 21 个交易日预测期正好相关，但优先级最低。证据档 3（样本外或发表后）
- **最强实现**：Calvet–Fisher 2004（NBER w9839）：4 个参数、1000 多个状态的极大似然版本；Lux–Morales-Arias 2010 的 GMM 版本
- **样本外/发表后证据**：外汇日度数据：日、周频只比 GARCH(1,1) 略好，10–50 天上有明显增益（NBER w9839 摘要）。Lux–Morales-Arias 的蒙特卡洛：不论真实过程是哪种，MSM 预测波动最好（k=8 个乘子，模拟，不是真实数据）。股票上的独立比较没有打开原文，搜索摘要说 RV-ARFIMA 在平静期最好、MSM 在动荡期更好，原油上没有统一赢家
- **限制**：外汇数据，不是股票；增益主要在中长期限
- **放进哪里**：只在 HAR+签名的波动预测做出来、而且证明波动预测质量对账户有用之后，才补一个 21 天对照
- **快照**：`sources/physics-geometry-2026-10-04/nber__w9839_calvet_fisher_forecast_multifractal.md`；`sources/physics-geometry-2026-10-04/ifw__kwp1582_lux_moralesarias_relative_forecasting.md`；`sources/physics-geometry-2026-10-04/arxiv__condmat0005400_bacry_delour_muzy_mrw.md`

### F1c 粗糙波动率 RFSV 与分数阶模型（族：1 湍流/多重分形/粗糙波动率）
- **结论**：第 3 类：弱或炒作，不做——对股票组合弱；只在期权线开工时再看。证据档 3（样本外或发表后）
- **最强实现**：Gatheral–Jaisson–Rosenbaum（H≈0.1，改进已实现波动预测）；Bennedsen–Lunde–Pakkanen 2022 JFEC（Cauchy、Power-BSS 模型）
- **样本外/发表后证据**：Bennedsen 等：在 2013–2014 平静期的样本外窗口里，他们的模型多数情形损失最小，但 MCS 在日频上区分力弱，RFSV 在 1 天步长上最好。反面：Cont–Das 2022 认为已实现波动呈现的粗糙性主要来自估计误差，即使瞬时波动是布朗运动式的也会表现出 H<0.5。2025 嵌套因子模型：指数波动 H≈0.11，个股残差 H≈0（多重分形）
- **限制**：收益只在日内到 1 天的预测期；21 天预测期上 Log-HAR 与基础模型打平（F1a 证据）
- **放进哪里**：无
- **快照**：`sources/methods-2026-10-04/arxiv__1410.3394_volatility_is_rough.md`；`sources/physics-geometry-2026-10-04/arxiv__1610.00332_bennedsen_decoupling.md`；`sources/physics-geometry-2026-10-04/arxiv__2203.13820_rough_vol_fact_or_artefact.md`；`sources/physics-geometry-2026-10-04/arxiv__2505.02678_nested_factor_multifractal.md`

### F1d 波动管理组合（把波动预测变成夏普）（族：1 湍流/多重分形/粗糙波动率）
- **结论**：第 2 类：有部分样本外证据，值得深做——只在动量式、有崩盘风险的子策略上值得做；泛泛的波动管理归第 3 类。证据档 3（样本外或发表后）
- **最强实现**：Moreira–Muir 2017（未打开原文）；Barroso–Santa-Clara 动量风险管理（只读到二手转述）；Bongaerts 等条件波动目标（搜索摘要）
- **样本外/发表后证据**：Cederburg–O'Doherty–Wang–Yan（JFE 2020）：103 个策略，夏普差为正的只有 53 个，持续波动但无风险收益关系的零假设下平均应有 66 个（自助法 p=0.01）；可实时执行的样本外版本一般夏普和确定性等价收益低于不管理的原组合，原因是回归的结构不稳。正面：动量策略的风险管理（Barroso–Santa-Clara）据称把夏普近乎翻倍并消除崩盘（Nucera 2017 的转述）；Harvey 等：只对权益和信用类风险资产有效
- **限制**：Barroso–Santa-Clara、Moreira–Muir 原文未打开，二手摘要级
- **放进哪里**：v1.2 组合里的动量暴露的崩盘叠加层；任何版本都按同波动配对夏普检验，不接受只降波动的改进（机主 09-28 规则）
- **快照**：`sources/physics-geometry-2026-10-04/lehigh__cowy_volmanaged_oos.md`；`sources/physics-geometry-2026-10-04/garp__risk_managed_momentum.md`

### F2a 动态模态分解 DMD 交易（族：2 流体力学/动力系统）
- **结论**：第 3 类：弱或炒作，不做——弱；DMD 本质是低秩线性回归，先看它是否打得过滚动 VAR/岭回归。证据档 2（只有回测）
- **最强实现**：Mann–Kutz 2016（Quantitative Finance）；2023 图嵌入 DMD（Algorithmic Finance，只看到摘要，原文 403）
- **样本外/发表后证据**：每个行业取 10 只股票、每笔成本 8 美元、忽略滑点；窗口 (m,ℓ) 的"热点"和行业都是事后挑的：家居建筑行业最优窗口 (11,5) 十年年化 21.48%，命中率约 52.5%，同一行业别的窗口 18.6–19.2%；没有热点的行业表现差。没有找到独立复现或样本外检验
- **限制**：样本选择和窗口选择都在样本内
- **放进哪里**：无
- **快照**：`sources/physics-geometry-2026-10-04/arxiv__1508.04487_mann_kutz_dmd.md`

### F2b Koopman 算子深度预测器（族：2 流体力学/动力系统）
- **结论**：第 3 类：弱或炒作，不做——弱；对收益预测没有证据。证据档 1（无）
- **最强实现**：SKOLR（ICML 2025）、Koopman Neural Forecaster
- **样本外/发表后证据**：只有通用时间序列基准，两次搜索都没找到金融收益的样本外证据
- **限制**：只看到搜索摘要
- **放进哪里**：无

### F2c 储层计算/回声状态网络 ESN（族：2 流体力学/动力系统）
- **结论**：第 3 类：弱或炒作，不做——目前弱；日内引擎立项后可作低成本预测器重访。证据档 3（样本外或发表后）
- **最强实现**：Ballarin–Capra–Dellaportas 2025（arXiv 2504.19623，v2 2026-09）
- **样本外/发表后证据**：1290 只美股，10 分钟到收盘五个期限，滚动岭回归，一个日历年（约 16000 个观测）：均方误差最多降 0.87%（10 分钟），到收盘几乎消失；均值方差组合毛夏普 ESN 1.529、等权 1.422、线性 -1.181、岭 -1.044、随机森林 0.166；计入交易成本后被动等权可以胜过主动组合
- **限制**：毛收益；只有一年
- **放进哪里**：无（日内线）
- **快照**：`sources/physics-geometry-2026-10-04/arxiv__2504.19623_esn_intraday_multihorizon.md`

### F3a 持续同调做危机/状态识别（族：3 拓扑数据分析）
- **结论**：第 3 类：弱或炒作，不做——弱；先证明它胜过"平均相关+已实现波动+VIX"，否则就是波动的代理。证据档 3（样本外或发表后）
- **最强实现**：Gidea–Katz 2018（Physica A）；Guritanu 等 2025 的严格因果版本（MDPI 原文 403，只有搜索摘要）
- **样本外/发表后证据**：Gidea–Katz：4 个美股指数，只检验 2000、2008 两次危机，景观范数在危机前上升。后续：Guritanu 等（摘要级）1999–2021 四个指数，固定因果参数（α=β=3.1，s=57，t=16）F1≈0.50，平均提前约 34 天，四次经典危机预警两次；Song–Li 2025：提前 0–5 天、样本内外灵敏度约 60%；2026 年零模型论文：景观 L1 范数与随机波动强共动，作者把"是否有预测价值"列为未解问题
- **限制**：事件个数很少，阈值在同样的危机上定；WIG20 "持续熵是否只是波动代理"一文被网站拦截，只有标题
- **放进哪里**：无；若通过，作为压力期风险开关的一个输入
- **快照**：`sources/physics-geometry-2026-10-04/arxiv__1703.04385_gidea_katz_fulltext.md`；`sources/methods-2026-10-04/repec__song_li_2025_physica_a_tda_crypto.md`；`sources/physics-geometry-2026-10-04/arxiv__2602.00383_null_validated_topological_signatures.md`；`sources/physics-geometry-2026-10-04/frontiers__fams2022940133_tda_crashes_recent.md`；`sources/physics-geometry-2026-10-04/arxiv__2203.05603_ph_turbulence_index.md`

### F3b 拓扑特征做收益或波动预测、拓扑组合（族：3 拓扑数据分析）
- **结论**：第 3 类：弱或炒作，不做——弱；Souto 式的做法并入签名/HAR 的波动预测程序，作为一个特征族。证据档 2（只有回测）
- **最强实现**：Souto 2023 JFDS（拓扑尾部相关，只拿到摘要）；2026 年拓扑风险组合（arXiv 2601.03974）
- **样本外/发表后证据**：Souto：加入持续同调信息使非线性和神经网络模型在动荡期更好地预测已实现波动（摘要）；拓扑组合：近十年标普 500 回测胜过 7 个组合模型（摘要，回测，无成本和样本外细节）。没有收益预测的样本外结果
- **限制**：摘要级
- **放进哪里**：无
- **快照**：`sources/physics-geometry-2026-10-04/hbo__souto_topological_tail_dependence.md`；`sources/physics-geometry-2026-10-04/arxiv__2601.03974_tda_portfolio_sp500.md`

### F4a 签名回归预测已实现波动（族：4 路径签名）
- **结论**：第 2 类：有部分样本外证据，值得深做——值得深做；第一个复现目标。证据档 3（样本外或发表后）
- **最强实现**：Horvath 等 2026（arXiv 2607.17865）：Signature-LASSO 选特征、Signature-OLS 重估
- **样本外/发表后证据**：12 个美元货币对 1 分钟中间价 2013–2023，按时间前 80% 估计、后 20% 样本外；每天把累计收益路径做时间增强的领先–滞后变换，取 3 阶签名，拼接最近 22 个交易日共 858 个候选特征。样本外 R² 0.361，HAR-RV 0.224，HAR-RS 0.237；RMSE 0.749 对 0.827；12 个货币对全胜，平均 RMSE 比最强非签名基线低 7.9%。入选特征以高阶领先–滞后项为主
- **限制**：同一研究组、未被独立复现；外汇、24 小时报价；HAR 基线只用标量摘要，没有喂同样的日内路径信息，对比不完全公平
- **放进哪里**：波动预测层（与 F1a 同一接口），也可作 M2 的一个特征族
- **快照**：`sources/physics-geometry-2026-10-04/arxiv__2607.17865_how_fast_do_signatures_learn.md`

### F4b 签名交易/组合框架（族：4 路径签名）
- **结论**：第 3 类：弱或炒作，不做——对收益没有证据，不做。证据档 2（只有回测）
- **最强实现**：Futter–Horvath–Wiese 2023（arXiv 2308.15135）
- **样本外/发表后证据**：理论加合成数据和市场数据例子（动量、配对），没有扣成本的样本外夏普
- **限制**：示例性质
- **放进哪里**：无
- **快照**：`sources/physics-geometry-2026-10-04/arxiv__2308.15135_futter_horvath_wiese_fulltext.md`

### F4c 签名做分类和异常检测；Oxford-Man 与 Man 的使用（族：4 路径签名）
- **结论**：第 3 类：弱或炒作，不做——用于微观结构分类可以，用于收益不做。证据档 3（样本外或发表后）
- **最强实现**：Gyurko–Lyons–Kontkowski–Field 2014（Oxford-Man 研究所与 Man Group Plc 的员工合著）；Akyildirim 等 2022（ETH）
- **样本外/发表后证据**：Gyurko 等：WTI 原油期货 30 分钟桶和母单市场冲击的分类，LASSO 线性回归，留出样本外；Akyildirim 等：加密货币拉高出货识别，无监督 F1 最高 88%。这是分类和微观结构，不是收益预测。没有找到 Man AHL 自述在生产中使用签名的文字，只有合著者单位这一层关系
- **限制**："业界谁在用"这一问没有证据支持到第 4 档
- **放进哪里**：无
- **快照**：`sources/physics-geometry-2026-10-04/arxiv__1307.7244_gyurko_signature_financial_stream.md`；`sources/physics-geometry-2026-10-04/arxiv__2201.02441_signature_market_anomaly.md`；`sources/physics-geometry-2026-10-04/arxiv__2006.00873_generalised_signature_method.md`

### F5a 协方差非线性收缩与随机矩阵清洗（族：5 统计力学/随机矩阵/组合）
- **结论**：第 1 类：主流且样本外强，直接采用——直接采用，作风险模型的对照与替换候选。证据档 5（可核验或独立复现）
- **最强实现**：Ledoit–Wolf 2017 RFS（非线性收缩）；Zhao–Ledoit–Jiang 2023 JFEC（DCC-NL）；Bun–Bouchaud–Potters 综述（作者为 CFM 员工）
- **样本外/发表后证据**：Ledoit–Wolf：回测里非线性收缩优于线性收缩。Zhao–Ledoit–Jiang：N=1000 时全局最小方差组合的样本外年化标准差，样本协方差 13.54%，DCC-NL 8.16%，约束总敞口越紧收益越小，且多种交易成本假设下合适的收缩总是优于任意设定的敞口约束。反面：2023 年一篇 arXiv 预印本比较最小方差组合，高斯图模型（直接估精度矩阵）优于收缩和随机矩阵方法。CFM 在生产里使用的自述：打开的原文里没有找到
- **限制**：增益在风险（标准差），夏普上不保证；v1.2 已是结构化因子模型加收缩，增量可能有限
- **放进哪里**：open_composer/research/equity_book/risk.py 的因子协方差/残差相关；pro-equity-2026-10-01 记录 sklearn 没有非线性收缩，自写约 40 行 QIS
- **快照**：`sources/physics-geometry-2026-10-04/uzh__rfs2017_ledoit_wolf_markowitz_meets_goldilocks.md`；`sources/physics-geometry-2026-10-04/uzh__jfec2023_zhao_ledoit_jiang_gross_exposure_shrinkage.md`；`sources/physics-geometry-2026-10-04/arxiv__1610.08104_bun_bouchaud_potters_fulltext.md`；`sources/physics-geometry-2026-10-04/arxiv__physics0507111_potters_bouchaud_laloux_fulltext.md`；`sources/physics-geometry-2026-10-04/arxiv__2305.11298_precision_vs_shrinkage.md`

### F5b 层次风险平价 HRP（族：5 统计力学/随机矩阵/组合）
- **结论**：第 3 类：弱或炒作，不做——对我们的多空因子组合不做；组合已用带风险模型的优化器。证据档 3（样本外或发表后）
- **最强实现**：López de Prado 2016（原文未打开）；skfolio 的实现
- **样本外/发表后证据**：巴西市场样本外全面比较：HRP 一般不是最好，部分指标与其他方法持平，跑赢市场指数；Cotton 2024：HRP 与最小方差由一个连续参数连起来（Schur 补配置）；2026 年一篇论文指出 HRP 和 Schur 配置都对收益信号视而不见，只解最小方差
- **限制**：LdP 原文的"样本外更好"主张是二手
- **放进哪里**：无
- **快照**：`sources/physics-geometry-2026-10-04/fgv__rbfin_hrp_brazil_oos.md`；`sources/physics-geometry-2026-10-04/arxiv__2411.05807_schur_complementary_allocation.md`；`sources/physics-geometry-2026-10-04/arxiv__2604.23833_beyond_deprado_cotton.md`

### F6 Wasserstein k-means 状态聚类（族：6 信息几何/最优传输）
- **结论**：第 3 类：弱或炒作，不做——弱；只能当诊断，不是信号。证据档 2（只有回测）
- **最强实现**：Horvath–Issa–Muguruza（J. Computational Finance 2024）
- **样本外/发表后证据**：用类内/类间最大均值差异分数比较聚类方法，说明自己远胜对手；没有交易或样本外收益评估
- **限制**：评价指标是聚类质量，不是赚钱
- **放进哪里**：无
- **快照**：`sources/physics-geometry-2026-10-04/arxiv__2110.11848_horvath_wasserstein_regimes.md`

### F7a IPCA 与条件自编码器（族：7 流形与潜在因子）
- **结论**：第 2 类：有部分样本外证据，值得深做——已在 v1.4 的 M3/M2 里；见 F7b。证据档 3（样本外或发表后）
- **最强实现**：Kelly–Pruitt–Su 2019（只有搜索摘要）；Gu–Kelly–Xiu 2021 JoE 自编码器资产定价；Gu–Kelly–Xiu 2020 RFS 机器学习（打开了 NBER 版本）
- **样本外/发表后证据**：GKX 2020：神经网络价值加权多空十分位样本外夏普 1.35，用神经网络预测给标普 500 择时夏普 0.77 对买入持有 0.51（毛）。自编码器论文：样本外定价误差远小于其他因子模型（搜索摘要）。反面：Fieberg 等说 IPCA 分不清"特征即协方差"还是"特征即收益"；Avramov–Cheng–Metzker（搜索摘要）：利润集中在微盘和高套利限制状态，计入合理成本后恶化
- **限制**：毛收益；微盘集中
- **放进哪里**：open_composer/research/equity_book/ml_composite.py
- **快照**：`sources/physics-geometry-2026-10-04/nber__w25398_gu_kelly_xiu_autoencoder.md`

### F7b AIPT/DKKM 随机特征 SDF（族：7 流形与潜在因子）
- **结论**：第 2 类：有部分样本外证据，值得深做——值得深做；我们的 M3 已在跑，缺的不是 P 而是信息集宽度和复杂度曲线。证据档 3（样本外或发表后）
- **最强实现**：Didisheim–Ke–Kelly–Malamud（NBER w33012，2024）
- **样本外/发表后证据**：130 个特征、T=360 个月；最大模型 P=360,000（复杂度 c=P/T=1000）样本外切点夏普 3.7，对比 FF6 的 0.8 和 Hou 五因子的 1.2；同一信息集下 FF6 简单版 0.74，高复杂度版 1.93–2.50；定价误差比 FF6 低 54.8%。无岭惩罚时在 c≈1 夏普崩到 0（双重上升），有岭惩罚则 c>1 之后持续上升。大/超大盘上夏普约 1.6–1.8（毛）。反面：Nagel（NBER w34104）证明此类模型退化为按波动择时的动量；Cartea 等 2025：特征带噪声时复杂度会损害样本外；Kelly–Malamud 2025 回应（搜索摘要）
- **限制**：毛收益；微盘影响大；Nagel 的"就是动量择时"反驳没被推翻
- **放进哪里**：M3（ml_composite.py）
- **快照**：`sources/physics-geometry-2026-10-04/nber__w33012_didisheim_aipt.md`；`sources/methods-2026-10-04/nber__w34104_nagel_seemingly_virtuous_complexity.md`；`sources/methods-2026-10-04/nber__w30217_kelly_malamud_zhou_virtue_of_complexity.md`

### F7c 扩散映射、UMAP 状态嵌入（族：7 流形与潜在因子）
- **结论**：第 3 类：弱或炒作，不做——弱。证据档 2（只有回测）
- **最强实现**：无成熟的交易实现
- **样本外/发表后证据**：搜索只见到可视化聚类、压力测试里扩散映射的平均绝对误差比 PCA 低最多 55%（摘要级）；没有样本外交易结果
- **限制**：只有搜索摘要
- **放进哪里**：无

### F8a Jane Street 的思路及其学术对应（族：8 深度序列与同时预测未来特征）
- **结论**：第 2 类：有部分样本外证据，值得深做——多期限辅助目标值得深做；"未来特征预测"本身没有公开结果，不能当证据。证据档 3（样本外或发表后）
- **最强实现**：Jane Street 2026 实习项目（预测收益和未来输入特征，检验树搜索推演加自蒸馏是否胜过直接预测）；多期限辅助任务 TCTS（ICML 2021）；Kaggle Jane Street 市场预测冠军方案的自编码器加多目标 MLP
- **样本外/发表后证据**：Jane Street 页面写明"深度学习是量化交易的未来"并列出噪声、状态频繁变化两个难点（机构自述，第 4 档，但没有方法细节）；实习项目只写了"测试是否胜过"，结果没有公布。TCTS：沪深 300 300 只股票，2016–2020 测试，一期任务 RankIC：GRU 0.049、LightGBM 0.038、GAT 0.052、普通多任务（3 个期限）0.061、TCTS 0.067–0.075；辅助任务并非越多越好（10 个期限的普通多任务 0.052）。Kaggle：冠军用自编码器特征加多目标 MLP（Numerai 论坛转述）
- **限制**：TCTS 在 A 股、毛指标（RankIC），没有成本；Jane Street 的项目是研究课题而非结论
- **放进哪里**：M2（GBDT 集成）和一个小神经网络的预注册变体
- **快照**：`sources/methods-2026-10-04/janestreet__machine-learning.md`；`sources/methods-2026-10-04/janestreet__wrought-2026.md`；`sources/physics-geometry-2026-10-04/arxiv__2007.05290_tcts_wu_etal_icml2021.md`；`sources/physics-geometry-2026-10-04/numerai__forum4338_ae_multitask_mlp_janestreet.md`；`sources/physics-geometry-2026-10-04/arxiv__2302.10175_spatio_temporal_momentum.md`

### F8b 现成时间序列基础模型零样本（Chronos、TimesFM、Moirai）（族：8 深度序列与同时预测未来特征）
- **结论**：第 3 类：弱或炒作，不做——不做。证据档 5（可核验或独立复现）
- **最强实现**：Chronos、TimesFM、Moirai
- **样本外/发表后证据**：Rahimikia–Ni–Wang 2025：美股日度超额收益，Chronos(large) 样本外 R² -1.37%、TimesFM(500M) -2.80%，CatBoost -0.10%、线性 -0.47%；2026 年五只流动股票的对比：相对随机游走的增益小而稀，单侧 DM 检验只在 10 个任务里拒绝 2 个；已实现波动上也没有统一增益。项目的方向登记表已把它登记为 evidence_too_weak
- **放进哪里**：无
- **快照**：`sources/physics-geometry-2026-10-04/arxiv__2511.18578_rahimikia_fintext_tsfm.md`；`sources/physics-geometry-2026-10-04/arxiv__2606.27100_pretrained_tsfm_financial_return.md`；`sources/physics-geometry-2026-10-04/arxiv__2607.05291_tsfm_realized_vol_vs_econometric.md`

### F8c 金融数据上从零预训练的序列模型（族：8 深度序列与同时预测未来特征）
- **结论**：第 2 类：有部分样本外证据，值得深做——有部分证据，但最低有效深度（20 亿观测、算力）超出现在的预算，先不做。证据档 3（样本外或发表后）
- **最强实现**：FinText-TSFM（Rahimikia–Ni–Wang 2025，613 个预训练模型；代码仓库未找到）
- **样本外/发表后证据**：搜索摘要称预训练用了 89 个市场、超过 20 亿观测、613 个模型（快照正文没有这些数字，待核对）；快照里：测试集超过 1800 万个日度超额收益、约 1 万只美股；摘要说在金融数据上预训练的模型取得"显著的预测和经济增益"，数据越大、合成数据增广和调参都更好。但组合是每天调仓的零成本等权十分位多空，同文中 CatBoost 毛夏普 6.79，不可信到净值上
- **限制**：毛收益；算力需求未核对
- **放进哪里**：无（阶段 4 才考虑）
- **快照**：`sources/physics-geometry-2026-10-04/arxiv__2511.18578_rahimikia_fintext_tsfm.md`

### F8d Kronos K 线基础模型（族：8 深度序列与同时预测未来特征）
- **结论**：第 3 类：弱或炒作，不做——不做。证据档 2（只有回测）
- **最强实现**：Kronos（AAAI 2026；120 亿 K 线、45 个交易所）
- **样本外/发表后证据**：作者自测：RankIC 比最强 TSFM 高 93%，波动预测 MAE 低 9%，A 股只做多 top-k 的投资模拟年化超额和信息比率最高；快照里没有找到成本说明。独立证据只有一个个人在 Hugging Face 上的印度股票微调记录：信息系数 -0.0114，12-1 动量 +0.0376，十分位价差 0.139% 低于约 10bp 的往返成本（第 2 档，单人）。GitHub 上有商业用户自述在跑日志但没有结果。项目方向登记表已是 evidence_too_weak
- **放进哪里**：无
- **快照**：`sources/physics-geometry-2026-10-04/arxiv__2508.02739_kronos_html.md`；`sources/physics-geometry-2026-10-04/hf__sahil007123_kronos_nse_1d_no_alpha.md`；`sources/physics-geometry-2026-10-04/github__kronos_issue273.md`

## 3 最低有效深度

### AIPT/DKKM（M3）
- **论文写明的**：复杂度 c=P/T：c<1 时夏普随复杂度升；c≈1 无岭惩罚时崩到 0；c>1 有岭惩罚时一路升到 c=1000（P=360,000，T=360 个月，130 个特征）。信息集固定时，FF6 的 5 个特征从 0.74 升到 1.93–2.50
- **我们现在**：M3：P=4000，23 个输入，周频训练，T=55 周（2019）到 407 周（2026），所以 c 约 73 到 10，已在 c≫1 区
- （我的推断）P 可能不是瓶颈；信息集宽度（23 对 130）和训练长度是。先画 P∈{500,4000,32000} 的复杂度曲线，看 4000 是否已在平台上
- 对应复现目标：R1

### 路径签名做波动预测
- **论文写明的**：时间增强的领先–滞后路径，3 阶截断，每天 39 项（3+9+27，已代码核对），拼最近 22 个交易日 858 个候选特征，LASSO 选入后 OLS；入选以高阶领先–滞后项为主
- **我们现在**：SIP 有分钟线，可构造同样的日内路径
- （我的推断）1–2 阶的领先–滞后项只对应二次变差、半方差一类标量，被 HAR-RS 吸收；增益要靠 3 阶和跨多日的拼接。所以测 1–2 阶得到"没有增益"不能当作否定
- 对应复现目标：R2

### 多期限辅助目标
- **论文写明的**：辅助期限集 T3/T5/T10；普通多任务在 T3 最好（0.061），T10 反而降到 0.052；需要调度器才在 T5 达到 0.075。GRU 隐层 32、输入序列 60 天、沪深 300
- **我们现在**：M2 现在是 21 个交易日单一标签
- （我的推断）先做普通多任务（便宜），再决定要不要调度器；增益靠"期限相近的任务"，不是任务越多越好
- 对应复现目标：R3

### TDA 状态识别
- **论文写明的**：滑动窗口把 4 个指数日收益变成 4 维点云，算 1 维持续同调的景观 L1/L2 范数；因果规则 α=β=3.1，s=57，t=16；F1≈0.50，只预警 4 次危机中的 2 次
- **我们现在**：4 个指数点云太少
- （我的推断）公平的检验至少要有多资产点云（行业 ETF 或几十只股票）、事前冻结的因果规则、与"平均相关+已实现波动+VIX"比，并覆盖 2020 和 2022 这两个文献里失败的场景。深度不是缺的东西，缺的是胜过简单基线的证据
- 对应复现目标：R4

### 协方差收缩
- **论文写明的**：N 与样本长度同量级时增益最大（N=1000）；约束总敞口越紧收缩的增益越小
- **我们现在**：U3000 面板，结构化因子模型加收缩
- （我的推断）v1.2 的风险模型已吃掉大部分收益；增量要用预测/实现波动比和最小方差组合的样本外标准差来量
- 对应复现目标：R5

### 金融预训练序列模型
- **论文写明的**：（搜索摘要，待核对）20 亿观测、89 个市场；现成预训练模型不行，从金融数据重新预训练才行（快照确认）
- **我们现在**：Modal 每月 25 美元以内，T4 GPU 超出要机主批准
- （待核对）训练算力需求论文里没有读到，不能估美元数
- 对应复现目标：无（阶段 4）

### MSM
- **论文写明的**：Calvet–Fisher：4 个参数、1000 多个状态（k 个乘子，2^k 个状态）；Lux 蒙特卡洛只用 k=8
- （我的推断）k 小时估计便宜，深度要求不高，但证据只在外汇的 10–50 天
- 对应复现目标：无

**深度合格的否定**：以后登记这些方向的否定结论，要写"在什么深度上测的、论文要求的深度是多少"。深度不够的负结果不算否定，只算"未测到有效深度"。

## 4 复现目标

复现成功只说明我们的实现没问题；之后才改到我们的品种和成本。数据可得性和算力都标了"待核对"，没有在本任务里下载或运行。

### R1 Didisheim–Ke–Kelly–Malamud，NBER w33012，复杂度曲线与 FF6 对比图（文中图 2 和图 4）
- **目标数字**：样本外切点夏普随 c 单调上升（有岭）、c≈1 无岭时崩溃；FF6 简单版 0.74，P=360,000（c=1000）版 1.93–2.50；整体 3.7
- **数据**：论文用的 130 个特征可得性待核对；免费近似：Xiu 的 datashare.zip（特征数和年份待核对，HTTP 200，约 1.5 GB）或 JKP 因子数据（jkpfactors.com，HTTP 200）
- **算力**：对偶形式的岭（T×T），随机傅里叶特征分块现算；本机内存 3.9 GB 吃紧，倾向 Modal CPU；美元数待核对，发射前必须过 scripts/modal_budget.py check
- **复现成功的判据**：曲线形状复现（单调与双重上升），夏普水平在 0.5 倍以内；再把 M3 搬到流动股票并扣成本

### R2 Horvath 等，arXiv 2607.17865，第 6.1 节表 2
- **目标数字**：12 个货币对次日对数已实现波动：Signature-OLS 样本外 R² 0.361、RMSE 0.749；HAR-RV 0.224、0.827；12/12 全胜
- **数据**：HistData 的 1 分钟外汇数据（免费，使用条款和可下载性待核对）；我们的版本：SIP 分钟线，约 100 只流动股票
- **算力**：858 个特征乘约 2800 天乘 12 个货币对，LASSO 加 OLS，本机即可
- **复现成功的判据**：外汇上 R² 差距（0.36 对 0.22）复现到 ±0.05；股票上签名模型相对一个喂了同样日内路径信息的强 HAR 仍有增益才算有效

### R3 Wu 等，Temporally Correlated Task Scheduling for Sequence Learning，ICML 2021，表 3
- **目标数字**：沪深 300，测试 2016-01 到 2020-08，一期任务 RankIC：GRU 0.049，普通多任务 T3 0.061，TCTS T5 0.075，LightGBM 0.038
- **数据**：Qlib 社区数据（可得性待核对）；代码 qlib/examples/benchmarks/TCTS（MIT，49,132 星）
- **算力**：2 层 GRU、隐层 32，CPU 可跑
- **复现成功的判据**：普通多任务相对单任务 GRU 的 RankIC 增量方向与量级（+0.012）复现；再搬到 U3000 周频 M2 的预注册变体，用同波动配对 t 判

### R4 Gidea–Katz 2018 加 Guritanu 等 2025（Computers 14(10):408）
- **目标数字**：标普 500、道琼斯、纳斯达克、罗素 2000 日收益，窗口滑动，景观 L1/L2 范数在 2000、2008 前上升；因果规则 α=β=3.1，s=57，t=16，F1≈0.50，平均提前约 34 天
- **数据**：四个指数日收益 1999–2021，需要 Stooq/Yahoo/FRED 之类（Alpaca SIP 的起始年份待核对）
- **算力**：ripser，本机几分钟
- **复现成功的判据**：复现两次危机的上升形态与 F1；然后在同样规则下加入基线（平均相关、已实现波动、VIX），并检验 2020 和 2022

### R5 Zhao–Ledoit–Jiang，JFEC 2023，N=1000 全局最小方差组合
- **目标数字**：样本外年化标准差：样本协方差 13.54%，DCC-NL 8.16%
- **数据**：我们自己的 U3000 日度面板
- **算力**：本机；QIS 约 40 行自写
- **复现成功的判据**：方向与量级复现；再量 v1.2 风险模型的预测对实现波动比，看收缩能否改进

### R6 （可选校准）Cederburg 等 JFE 2020 的自助法；Barroso–Santa-Clara 动量缩放
- **目标数字**：103 个策略中 53 个夏普差为正，自助法零假设期望 66，p=0.01
- **数据**：Ken French 数据库日频因子（免费）
- **算力**：本机几分钟
- **复现成功的判据**：复现"泛泛的波动管理不稳"和"动量缩放有效"这两个相反的结论，用来校准我们的同波动配对检验

## 5 开源实现表

数据来自 GitHub 未认证 API（`sources/physics-geometry-2026-10-04/github_api__repo_stats.json`，取数时间见文件头）。

| 工具 | 仓库 | 星数 | 许可证 | 最近推送 | 用法 |
|---|---|---|---|---|---|
| Kronos | shiyu-coder/Kronos | 39,912 | MIT | 2026-04-13 | 不用（F8d） |
| giotto-tda | giotto-ai/giotto-tda | 1,007 | NOASSERTION | 2024-06-18 | R4 可选，已 2 年多未更新 |
| ripser.py | scikit-tda/ripser.py | 342 | NOASSERTION | 2026-09-12 | R4 首选 |
| persim | scikit-tda/persim | 143 | MIT | 2026-08-27 | R4，景观/图像 |
| giotto-ph | giotto-ai/giotto-ph | 59 | NOASSERTION | 2024-05-30 | 备选 |
| GUDHI | GUDHI/gudhi-devel | 329 | MIT | 2026-09-30 | 备选，景观 |
| signatory | patrick-kidger/signatory | 312 | Apache-2.0 | 2024-01-11 | GPU 签名；多年未更新 |
| iisignature | bottler/iisignature | 123 | MIT | 2026-06-03 | R2 首选（CPU） |
| esig | datasig-ac-uk/esig | 55 | GPL-3.0 | 2024-12-17 | GPL，避免 |
| pysiglib | daniil-shmelev/pysiglib | 27 | Apache-2.0 | 2026-09-27 | 新，星少，备选 |
| Chronos | amazon-science/chronos-forecasting | 5,974 | Apache-2.0 | 2026-09-17 | 不用 |
| TimesFM | google-research/timesfm | 34,103 | Apache-2.0 | 2026-09-29 | 不用 |
| Moirai/uni2ts | SalesforceAIResearch/uni2ts | 1,604 | Apache-2.0 | 2026-06-02 | 不用 |
| granite-tsfm（含 TTM） | ibm-granite/granite-tsfm | 907 | Apache-2.0 | 2026-10-02 | TTM 在波动预测上唯一微弱胜 Log-HAR，F1a 之后可作对照 |
| PyDMD | PyDMD/PyDMD | 1,262 | MIT | 2026-10-03 | 只用于一次性对照 |
| pykoopman | dynamicslab/pykoopman | 456 | MIT | 2026-01-22 | 不用 |
| skfolio | skfolio/skfolio | 2,458 | BSD-3-Clause | 2026-10-03 | R5；已在 pro-equity 调研里采用 |
| Riskfolio-Lib | dcajasn/Riskfolio-Lib | 4,533 | BSD-3-Clause | 2026-10-04 | 备选 |
| arch | bashtage/arch | 1,586 | NOASSERTION | 2026-09-27 | GARCH 基线 |
| Qlib | microsoft/qlib | 49,132 | MIT | 2026-09-22 | R3 的 TCTS 基准在其 examples |
| ipca | bkelly-lab/ipca | 266 | MIT | 2022-08-15 | 多年未更新 |
| MFDFA | LRydin/MFDFA | 165 | MIT | 2022-08-15 | 不用 |
| mlfinlab | hudson-and-thames/mlfinlab | 4,935 | NOASSERTION | 2023-10-02 | 商业许可，不用 |
| neuralforecast | Nixtla/neuralforecast | 4,277 | Apache-2.0 | 2026-09-24 | 备选 |

NOASSERTION 指 API 没有识别出许可证，使用前要自己读仓库的 LICENSE。

## 6 分阶段路线

### 阶段 0（10-05 至 10-08，本机）：复现校准
- **做什么**：R6、R5、R4：先证明我们的实现能复现已发表的数字，再改到我们的品种和成本
- **证据要求**：每项复现到容差内：方向一致且效应量不低于原文的一半（这个容差是我的判断，不是数据）；复现不出来先查实现，不下方向结论
- **停止条件**：单项 5 个工作日内复现不出来就停；R4 若加基线后拓扑特征没有增量，TDA 线关闭并写死因

### 阶段 1（10-08 至 10-14，本机）：签名波动预测与多期限辅助目标
- **做什么**：R2（外汇复现，再股票 RV）；R3（普通多任务，再预注册 M2 变体）
- **证据要求**：R2：样本外 R²/QLIKE 相对喂了同样日内信息的强 HAR 有增量，DM/MCS 通过，至少含一个压力期；R3：简化毛夏普和 RankIC 同时改进，同波动配对 t≥2 才进下一步。预注册每个候选，记录"在多深度上测的"
- **停止条件**：R2 在股票上输给强 HAR 就把签名降为特征族备选；R3 的普通多任务无增益就不上调度器

### 阶段 2（10-14 至 10-20，Modal CPU（先过预算检查））：M3 复杂度曲线与信息集
- **做什么**：R1：P∈{500, 4000, 32000}，信息集 23 个输入对加宽；流动股票子集上看夏普
- **证据要求**：复杂度曲线上 4000 是否已在平台；加宽信息集后 M3 在两个窗口是否仍胜 M0；毛、净两套
- **停止条件**：曲线在 4000 之前已平且加宽无增益，M3 不再追深度；Nagel 式的"只是动量择时"检验（同输入的动量择时基线）不过也停

### 阶段 3（阶段 1–2 通过后，本机）：接入组合
- **做什么**：RV 预测进风险模型（预测对实现波动比，最小方差组合标准差）；动量崩盘叠加层
- **证据要求**：走现行评价标准 docs/evaluation-standard.zh.md 的门槛，不改标准；波动管理一律同波动配对夏普
- **停止条件**：只降波动不升同波动夏普的改动一律不收

### 阶段 4（条件触发，需要机主批准算力）：金融预训练序列模型、日内 ESN
- **做什么**：从金融数据重新预训练的小序列模型；日内线的 ESN
- **证据要求**：触发条件：阶段 1 或 2 里至少一项证明"深度换来样本外增益"，并且日内引擎立项；先核对论文的算力需求再估预算
- **停止条件**：未触发则不做

每个阶段的候选都要先预注册（模型、特征、期限、基线），Modal 任务先过 `scripts/modal_budget.py check`，美元数在这之前不估。

## 7 不做清单

| 不做 | 理由 | 重开条件 |
|---|---|---|
| 现成基础模型零样本预测收益（Chronos、TimesFM、Moirai） | 独立评估多次为负（F8b） | 有人在我们的成本口径下复现出正的样本外 IC |
| Kronos | 无独立证据，唯一外部记录不赚钱（F8d） | 有第三方扣成本的样本外结果 |
| DMD/Koopman 做交易信号 | 样本和窗口事后挑选，无独立复现（F2a、F2b） | 出现独立的样本外交易结果 |
| TDA 作 alpha 来源或主攻方向 | 只有少数危机的事后识别，很可能是波动代理（F3） | R4 加基线后仍有增量 |
| Wasserstein 聚类当信号 | 只有聚类质量指标（F6） | 有样本外交易评估 |
| HRP | 对收益信号视而不见，样本外不稳定占优（F5b） | 无 |
| 粗糙波动率/MSM 用于股票组合 | 收益在日内到 1 天、外汇（F1b、F1c） | 期权线开工 |
| 泛泛的波动管理 | 103 个策略里 53 个为正，样本外劣于原组合（F1d） | 只在动量子策略上按 F1d 做 |
| 扩散映射、UMAP | 没有交易样本外（F7c） | 无 |
| 拿毛夏普当目标 | DKKM 3.7、FinText 的 CatBoost 6.79、Kronos 都是毛口径，微盘或零成本 | 无；所有目标按扣成本后的同波动口径定 |

## 8 我补充的、机主没提到的问题

1. **毛口径陷阱**：见一页结论的第一个警示。落实办法：复现目标里每个夏普同时记毛和净，净值按我们的成本模型（`cost_model_v1.json`）算。
2. **多重检验**：签名有 858 个候选特征，DKKM 有成千上万个随机特征，辅助任务有多个期限集。每个都要预注册，并报告 deflated Sharpe（pro-equity 调研记录 purgedcv 带这个函数）。
3. **Nagel 反驳要当基线**：M3 加深之前先跑"同输入的波动择时动量"基线；M3 的增量必须相对它。
4. **波动预测与夏普的鸿沟**：F1a 的预测增益只在波动层，上账户要过同波动配对夏普；Cederburg 等说泛泛的结果会落空。
5. **Jane Street 的实习项目没有公布结果**："同时预测未来特征"只能当可试的点子，不能当证据。机构自述只到"深度学习是未来"这一层。
6. **"业界谁在用"的诚实答案**：Man 的签名、CFM 的随机矩阵清洗，都只查到合著者单位，没有查到自述的生产使用；TDA 在资管里没有公开的生产使用（搜索摘要）。
7. **数据口径**：Alpaca SIP 分钟线的起始年份、免费外汇分钟线的条款、Xiu 数据的特征数，都待核对，开跑前先查。

## 9 未核对项与限制

- 原文被 403 或付费墙拦住，只有搜索摘要，已标"摘要级"：Moreira–Muir 2017、Barroso–Santa-Clara、Bongaerts 等、Harvey 等、Patton–Sheppard、Guritanu 等 2025、WIG20 持续熵一文、Avramov–Cheng–Metzker、Fieberg 等的 IPCA 批评、Gu–Kelly–Xiu 自编码器论文、Kelly–Malamud 2025 回应、López de Prado 2016、Raffinot、图 DMD 2023、SKOLR/KNF。摘录见 websearch_excerpts_blocked_sources.md
- 没有跑任何复现，本任务只做调研；R1–R6 的数据可得性和算力美元数都标了"待核对"
- 股票上 MSM 与 HAR 的直接样本外对比没有找到可打开的原文
- "业界谁在用"：Man AHL 使用签名、CFM 在生产里使用随机矩阵清洗，两条都只有作者单位这一层关系，没有找到机构自述；Jane Street 只有"深度学习是未来"的总体表述
- Kronos 论文的成本口径只用关键词搜索了正文快照，附录没有逐段读
- GitHub 数据来自未认证 API，pyRMT 等 4 个仓库名返回 Not Found，可能是名字猜错而非不存在
- 各档证据的评级和"先验"是我的判断，不是数据

## 10 引用到的已有文件

- `reports/research/intel/I-20261004-03-geometry-physics-methods-and-jane-street-playbook.md`（第一版回答）
- `reports/research/intel/sources/methods-2026-10-04/`（Gatheral 等、Song–Li、Nagel、KMZ、Jane Street 页面）
- `reports/research/iterations/t20261004_book_v14_ml/`（M3 的 P=4000、23 个输入、训练周数）
- `reports/research/harvest/directions.jsonl`（`dir:tsfm_zero_shot_returns`、`dir:kronos_kline_foundation_model` 已是 evidence_too_weak）
- `reports/research/intel/pro-equity-2026-10-01.md`（skfolio、QIS 自写、purgedcv）
