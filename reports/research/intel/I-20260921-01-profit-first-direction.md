# I-20260921-01：以尽快实现可信净盈利为目标，先纠正方向再投入算力

- 截止：2026-09-21 UTC；各来源的精确抓取时刻在 source cards 和快照 metadata 内。
- 类型：方向调研与已有证据复核。没有生成候选、计算因子或收益、训练、回测、提交订单。
- 对齐用户目标：近期市场阶段有效的策略可以成立；不要求十年有效。衡量的是尽快获得可执行、扣成本后的盈利机会，以及为这个机会承担的亏损和研究成本。
- 本次没有确认任何能够保证短期盈利的策略。网页、论文、模型配方、执行彩排分别能证明什么，须分开记录。
- 来源卡：`reports/harness/source_cards/profit_first_direction_20260921.jsonl`；11 条已核实事实，9 个实际引用来源。
- 抓取与搜索记录：`reports/research/intel/sources/20260921-direction/query-log.json`。先联网，再读本地现状。Google 返回脚本页、DuckDuckGo 返回验证页、Bing RSS 多数结果无关，最终直接获取官方页、论文全文及官方代码；本次不能声称完成穷尽检索或已排除所有第三方复现。

## 结论：先做能改变决策的三件事

1. **让现有 ETF 模拟组合与可直接买到的动量 ETF、现金同期竞争。** 成交链已存在，离真实可执行结果最近。重点是收集冻结后的净结果、核对成交偏差和风险暴露，不继续开一大批轮动参数格子。
2. **FINRA 日做空成交量只做一次便宜的信息迁移检验。** 数据已在本地是优点；但“它直接对应已验证论文，因此优先级最高”的旧推理不成立。先判断信息是否独立于流动性、近期收益和场外交易结构，再决定是否值得训练。
3. **Qlib 先修标签语义，再恢复分片；保留一个固定的 LightGBM 基准。** 官方配方值得复用，官方中国市场数字不支持直接预期近期美股盈利。全池网格和 DoubleEnsemble 暂不能凭“已批准”就抢先消耗资源。

这是投入顺序，不是新的候选清单，也不替代 campaign / iteration / knowledge / candidate-manifest 的前置验证。下一轮任何因子评估、剪枝或训练之前，必须先通过项目规定的相应闸门。

## 新核实的证据改变了哪些判断

| 路线 | 这次联网核实到了什么 | 不能从中推导什么 | 对近期盈利目标的含义 |
|---|---|---|---|
| 现有 ETF 组合 / SPMO / 现金 | Invesco 官方有现成 SPMO 产品；Allocate Smartly 提供第三方策略复现和近实时模型组合，但明确单策略页面是研究回测，采用收盘成交与自定交易成本 | 第三方“实时更新净值”不等于券商真实成交或独立审计；不等于本地次日开盘也有同样收益 | 先读现成记录；本地只补策略选择冻结后及执行口径不同所缺的证据。SPMO 是机会成本对照，不是替用户改成长期指数投资 |
| FINRA 日做空成交量 | 官方说明它是场外公开申报流量；客户撮合相关的抵销买入可能不在日文件里；BJZ 原文使用 2000–2004 年 NYSE 私有订单与账户类别 | 高比例不能直接解释成“机构更看空”；CNMS 比率也不是原论文的原始数据，不能宣称直接复制了知情卖空效应 | 低成本、未验证的新代理变量，可以检验；应下调先验信心，暂不扩展参数或模型 |
| Qlib Alpha158 + LightGBM | 官方示例是 CSI300，2008–2014 训练、2015–2016 验证、2017–2020 测试，`deal_price: close`；默认标签是未来收盘到收盘 | 不能把中国基准 IC、20 个随机种子或框架知名度当美股近期 alpha；open/open 标签不是原标签的“等价实现” | 可复用工程与固定基准。只有本地确定性分支先有信号、同成本增量成立，才追加模型复杂度 |
| 滚动训练 / 现成模型复用 | Qlib 已有 RollingStrategy / RollingGen / 模型记录模式 | 滚动重训本身不会创造新信息；序列化估计器也不等于带训练窗口、标签、特征、成本、验证和状态的可复用知识 | 借已有流程，记录重训原因。用户电脑已有的模型应先按 provenance 接入评估，避免不知情地重新训练同一件事 |

## 1. FINRA：最需要立即纠正的研究推理

此前 `docs/current-view.zh.md` 与 `intel-free-alt-data-signals-2026-09-18.md` 将 FINRA 日流量描述为“直接对应 Boehmer–Jones–Zhang 的机制”。原论文全文使这个说法不能成立：其数据是 NYSE 订单，覆盖 2000 年 1 月到 2004 年 4 月，并能区分个人、机构、自营和程序化交易；最有信息的是机构非程序化卖空。免费的 FINRA CNMS 汇总文件缺少这些账户类别，交易场所与时代也不同。

FINRA 还专门解释过：券商帮助客户卖出已经持有的股票时，可能先从自身账户卖出，再向客户买入；部分抵销买入不进入公开日文件。结果看起来有较高的做空成交占比，但并不等于建立了相同规模的净空头，更不自动代表知情看空。

因此，原来存量空头信号被分母解释，并不能反过来证明“换成流量就会有信息”。这只是一个仍可证伪的迁移假设。现有数据管道值得保留，预测力尚未被本次调研确认。

可复用本地资产：`data/features/short_volume_broad/{2018..2026}.parquet` 和 `scripts/build_short_volume_features.py`。本次只读取了构建器与现有卡片；没有重新计算覆盖率，先前的 96% 不作为本轮新验证结果。固定滞后一个交易日是现有设计，正式采用前还需核对实际文件可见时间与交易时钟。

## 2. ETF：现成产品和跟踪记录应减少重复研究，不能替代执行核对

SPMO 官方产品机制已重新核实：S&P 500 高动量股票、按市值和动量得分加权，每年 3 月和 9 月重组与再平衡。这使它成为现实中的可买替代方案。无需自己再发明一套 S&P 500 动量复制品来证明同类机制存在。

Allocate Smartly 的价值是集中复现公开策略、统一比较和维护模型记录。它的 FAQ 同时明确：单策略回测用于研究，统一假设在 16:00 ET 收盘成交，每次交易费用加滑点 0.10%。这与本地收盘后产生信号、次日开盘执行存在口径差异。本次没有进入会员区取得完整发布后净值、真实成交对账单或策略代码。

因此应修正旧 intel 规则里“公开实时跟踪 = 比我们回测更强的实盘证据”的等号：先看是否事前冻结、是否在发表后、是否模型净值、是否实际成交、是否扣全成本。读现成记录可以省掉重复历史回测；本地执行差异和冻结后的记录仍需要补齐。

本地现状依据是 `docs/current-view.zh.md` 与 H-20260918-05/06、H-20260919-01 已有记录；本次没有复算净值。它们已指出成长菜单的事后挑选和杠杆组合收益来源，不宜继续以漂亮年化为由增加相似搜索。已经看过的 2026 留出期不能在下一张卡里重新称“完全没碰过的 OOS”。近期策略可以只针对近期市场，但后续选择不能用已经揭晓的留出结果替代新证据。

## 3. Qlib：一次明确的实现口径错误，应先于分片重跑处理

`H-20260918-03-qlib-recipes-on-broad-universe.md` 写：`Ref($close,-2)/Ref($close,-1)-1` 是“次日开盘到再次日开盘”，本地 open/open 与之等价。官方 handler 与 YAML 共同否定这个解释：它是 t+1 收盘至 t+2 收盘，示例执行价也是 close。

本地使用 open/open 可以是合理的执行适配；但必须把它写成有意更换标签与执行时点，并分别追踪与原配方的差异。否则模型没通过时，无法判断是论文无效、市场迁移、标签改变还是实现错误。

官方 benchmark 仍清楚标注中国 A 股 / CSI300 和 20 个随机种子；本次没有取得独立、近期美股宽池、含退市收益、匹配成本的复现证据。不要把“没有取得”写成“世界上不存在”。Qlib 官方滚动训练组件值得直接借鉴，没必要为了这次基准重建另一套全量研究平台。

旧卡的六个单元（模型 × 标签）与额外组合构造都会形成实际试验暴露；如果恢复，必须沿用可验证的冻结范围，或开新轮登记变更，不能顺手扩大。数据分片只修资源问题，不自动通过标签、PIT 股票池与研究闸门。

## 只建议以下三项下一步实验

下列时间和内存是拟议上限，未做性能实测；不是对用户预算的代为授权。全部优先复用已有免费数据，不要求购买数据或启动新的付费模型 API。

| 优先级与实验 | 最便宜、能改变决策的检查 | 数据 / 成本 / 依赖 | 证伪及停止条件 |
|---|---|---|---|
| P0：冻结现有 ETF 的前向净结果对照 | 从同一冻结时点对现有 sleeve、SPMO 和 BIL/现金记录实际信号、目标、成交、持仓、净收益与风险暴露；优先从现有 ledger 生成，不重跑已公开的完整历史策略 | 现有日线、纸面成交账本；首份核对建议最多 1 个执行者小时，此后增量更新；沿用既有模拟授权期限，任何续期和实盘不由本简报授权 | 账本不一致则不能得出绩效结论；执行滑点或暴露超合同则暂停受影响 sleeve；期末不能显示可辨认增量就不扩大预算。十余天只足够部分执行检验，不能据此宣布 alpha 成立 |
| P1：FINRA 的增量信息迁移检验 | 先按成本、标签时钟、PIT 股票池冻结少量检验；在已声明 development 区间比较短量比率与流动性/近期收益/场外占比对照，并做同样暴露的置换；只让有独立增量的方向进入后续组合评估 | 现有 FINRA 特征、清洗后的行情与历史资格；缺永久证券身份、退市收益或必要的场外占比分母时登记 dependency_skipped；计划最多半天、CPU 单任务，无新模型训练 | 被价格/流动性对照或置换解释，或在预登记成本下无新增价值，则封存；不能改方向/阈值反复在 OOS 找正号。缺必要字段时不把缺口包装成“已复制论文” |
| P2：Qlib 语义对齐与分片资源验证，然后一个固定基准 | 首先核对标签、因子列、训练预处理 fit 窗与执行价；用小分片量峰值内存和耗时，再决定是否构建完整宽池。仅在确定性分支已示信号且前置闸门通过后，运行预登记固定 LightGBM 与规则/线性对照 | 复用本地 Alpha158 公式与官方配方；建议 pilot 10 分钟上限、峰值 RSS 目标 ≤1.2 GiB，为已知 1.8 GiB 帽留余量；实际是否达标由测量决定。外部用户模型若可导入，先做模型 provenance 与输入契约核对 | 小分片无法保持跨分片 warmup、截面归一化或训练 fit 范围一致，或资源超限，则不启动全量；固定模型不能超过匹配确定性与价量对照、缺失模态和 placebo 不过，则不给 ML 增量信用，不追加 DoubleEnsemble 网格 |

P1 / P2 不是获准开始因子评估或训练的 manifest。启动时须先通过 campaign pre-discovery、iteration validate；AI/ML 或新模态还需知识索引、版本化 scout 和 knowledge assess；候选、数据分区、标签、成本、基准、消融与 fallback 先绑定。新的可选候选沿用已规定的 **20 bps、日连续、无终端清仓 OOS、相对 BIL 的年化夏普严格 >1.0** 门槛；旧冻结合同不事后重写。本次未检查或宣称任一候选通过这些门槛。

## 可复查的来源摘录

完整 URL、抓取时间、SHA-256、快照文件与每项限制在来源卡中。以下是方向判断所依赖的短引文：

| 来源与日期 | 摘录 | 核实范围 |
|---|---|---|
| [FINRA, Short Interest – What It Is, What It Is Not](https://www.finra.org/investors/insights/short-interest)，2023-01-25 | “is not consolidated with exchange data” | 场外流量与空头余额、交易所数据的区别 |
| [FINRA Information Notice](https://www.finra.org/rules-guidance/notices/information-notice-051019)，2019-05-10 | “some offsetting buying activity … would not be reflected in the Daily File” | 券商客户撮合会影响比例解释 |
| [Boehmer / Jones / Zhang 全文稿](https://www.top1000funds.com/wp-content/uploads/2011/08/Which-shorts-are-informed.pdf)，2007-02-04 稿 | “using proprietary NYSE order data” | 原研究数据与 FINRA CNMS 并不等价；非最新收益证据 |
| [Invesco SPMO 官方产品页](https://www.invesco.com/us/en/financial-products/etfs/invesco-sp-500-momentum-etf.html)，本次抓取 | “reconstituted and rebalanced twice a year” | 有现成动量 ETF；未查证本次实时收益 |
| [Allocate Smartly FAQ](https://allocatesmartly.com/faqs/)，本次抓取 | “designed purely for research” | 第三方模型跟踪与真实成交不能混同 |
| [Qlib 官方 Alpha158 YAML](https://raw.githubusercontent.com/microsoft/qlib/main/examples/benchmarks/LightGBM/workflow_config_lightgbm_Alpha158.yaml)，本次 main 快照 | `market: &market csi300`；`deal_price: close` | 示例的市场及执行假设 |
| [Qlib 官方 handler](https://raw.githubusercontent.com/microsoft/qlib/main/qlib/contrib/data/handler.py)，本次 main 快照 | `Ref($close, -2)/Ref($close, -1) - 1` | 标签是收盘至收盘 |
| [Qlib 官方 benchmark](https://raw.githubusercontent.com/microsoft/qlib/main/examples/benchmarks/README.md)，本次 main 快照 | “20 runs with different random seeds” | 中国市场自报基线，非美股独立复现 |
| [Qlib Online Serving 文档](https://qlib.readthedocs.io/en/latest/component/online.html)，服务器 Last-Modified 2025-11-10，本次重取 | “always uses the latest rolling model” | 复用滚动任务和模型状态；不证明盈利 |

本轮未新增数据采购、量化打标/交易模型 API 请求、训练或下单。当前会话与研究子代理的模型消耗属于本次研究工作，尚未核算费用，不能据此声称总模型费用为零。未核实的范围是：现有 sleeve 截至今天的净收益、FINRA CNMS 的近期可交易 alpha、Qlib 近期美股独立复现、第三方策略的审计实盘，以及用户本地模型内容。收益相关判断维持待验证，工程与数据口径判断具有较高置信度。
