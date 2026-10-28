# Step 9.M 多资产动量研究与模拟盘组合计划

日期：2026-07-14

## 1. 目标

从成熟、可复现的公开方法出发，而不是继续局部修改现有 QQQ/TQQQ 规则，建立一组适合个人量化的动量策略：ETF 时间序列动量、行业 ETF 轮动、个股横截面动量、52 周高点/趋势质量动量，以及针对幸存策略的多角色 ML 版本。最终输出隔离 virtual-paper sleeves、逐日目标权重、完整试验账本和 forward 验证合同；不启用真实或 Alpaca Paper 订单写入。

## 2. 不可违反的边界

- 活跃 spec、broker、paper order 和 `.env` 零改动。
- 所有候选先进入 draft/research，LLM 不进入实时决策热路径。
- 当前成分股快照的历史回测带幸存者偏差，只能用于淘汰和工程验证；正式个股证据从冻结快照后的 forward virtual paper 开始。
- 所有因子在决策日使用 `index-1` 或更早信息；标签按完整预测 horizon purge，并设置不少于 21 个交易日的 embargo。
- 每个候选、模型和阈值进入 append-only ledger；不得打开未过门的 lockbox。
- 不新增依赖，不提交 `data/` 大文件或模型大制品。

## 3. Wave M.0：外部研究、股票池与数据合同

1. 从 Nasdaq 官方 screener 当前全市场快照开始，不预选现有缓存股票。
2. 初筛普通股：美国上市、价格不低于 10 美元、市值不低于 50 亿美元、当日成交量不低于 50 万股，排除 ETF、权证、单位和特殊证券。
3. 按市值和当前美元成交额取得最多 120 个初始候选；按行业设上限后选择最多 60 个下载调整后日线。
4. 使用 Longbridge `adjusted=true`；要求至少 1,000 个交易日、最近数据完整、价格有效、60 日中位美元成交额不低于 5,000 万美元。
5. 冻结最多 40 只个股作为 `2026-07-14` forward universe；保存筛选原因、拒绝原因、来源时间和哈希。
6. ETF 母体覆盖宽基、行业、债券、黄金和现金代理；ETF 与个股策略分别评估。

验收：迭代 dossier `mom_multiasset_r1` pre-backtest validation 通过；股票池 snapshot、data manifest、capability review 和 source cards 完整。

## 4. Wave M.1：确定性策略族

总预算上限 60 组，每个 path 不超过 16 组。

- P1 ETF 绝对/相对动量：63/126/252 日趋势，周或月调仓，top 1/2，BIL 绝对动量门。
- P2 行业 ETF 风险调整轮动：6/12 月动量组合、波动率惩罚、top 2/3、换仓 buffer。
- P3 个股经典长-only 横截面动量：6-1、12-1、6/12 月组合，top 5/10，月调仓。
- P4 个股 52 周高点/趋势质量：距 252 日高点、趋势一致性、downside-vol penalty，top 5/10。
- P5 个股残差/行业相对动量：相对 SPY 与行业代理的残差趋势，限制单行业和单股权重。

共同基准：同标的 buy-and-hold、等权母体、SPY、行业/主题代理、BIL、ex-post best symbol。共同成本：单边 5/10/20 bps；个股额外检查换手和容量。

淘汰门：至少 4 个 chronological folds；最近两个 fold 不得同时为负；OOS Sharpe、IR、MaxDD 和成本后收益不得全面劣于等权与 SPY；少于 30 次 rebalance 或严重依赖单只股票的候选不得进入 ML。

## 5. Wave M.2：策略专属 ML

只对 M.1 幸存方法训练。横截面样本单位是“决策日 × 股票”，按决策日分组，禁止随机切分。

- ML-L：ElasticNet/Logistic，作为可解释低方差基线。
- ML-T：LightGBM 回归或排序，预测未来 21 日横截面超额收益。
- ML-R：Random Forest/Extra Trees 稳健性对照。
- ML-D：下行风险分类器，预测未来 21 日大幅回撤，仅调整风险预算。
- ML-S：基于预测分位数和波动率的离散仓位模型。

特征按组消融：多尺度动量、52 周高点、趋势斜率/一致性、波动率/downside volatility、drawdown/recovery、成交量 surprise、SPY/行业相对强弱。模型不得直接使用证券 ID 记忆个股。

验收：nested chronological CV、21 日 purge/embargo、逐 fold IC/rank-IC/ICIR、Brier/AUC（分类任务）、成本后组合指标和 marginal lift 全部写入 ledger。未达到至少 3/4 fold 正向增量的模型保持 diagnostic，不进入组合。

## 6. Wave M.3：组合与模拟盘

形成相互独立的 sleeves：ETF 趋势、行业轮动、个股经典动量、个股趋势质量，以及最多三个通过门的 ML sleeve。每个 sleeve 初始虚拟资金相同，独立持仓和现金，不在单一 broker 账户中伪造策略级持仓隔离。

每日或调仓日输出：模型/规则版本、输入数据 as-of、目标权重、未交易原因、成本假设、风险状态和完整哈希。模拟盘阶段不根据 forward 结果临时调参；任何新一轮修改需要新 iter-id 和新 dossier。

验收：最新目标权重可重复生成；无 broker writes；portfolio evaluation、forensics、execution reality、capability review、decision record 和 observation state 完整。`workflow_pass`、`research_pass`、`llm_contribution_pass`、`paper_ready_pass` 分开报告。

## 7. Wave M.4：工程与最终验证

运行：

```text
uv run ruff format .
uv run ruff check .
uv run pytest -q
uv run oc repo check --strict
make verify
```

任一红灯先修复。计划完成不等于宣称 Alpha；最终状态必须准确反映数据、幸存者偏差、模型 OOS 和 forward observation 尚未自然经过的时间。
