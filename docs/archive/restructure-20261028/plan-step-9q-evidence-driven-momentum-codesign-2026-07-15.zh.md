# Step 9.Q：证据驱动的个股与日内动量共同设计

## 1. 目标

在现有 `mom_multiasset` 与 `mom_minute` 负面和诊断结果之上，重新共同设计数据、频率、标签、策略结构和模型任务。交付一组逻辑互异的确定性、ML 原生和混合候选，并进入隔离虚拟模拟盘；不把工作流完成、当前成分股历史或 IEX 分钟结果宣传为 Alpha 或 paper readiness。

## 2. 研究结论

- 个人账户最现实的主线是长仓中期横截面动量、行业/行业中性动量和成交量条件化动量。
- 日内动量是独立策略族。首小时延续、反转、隔夜/日内分解和固定时段横截面必须分别检验；IEX 结果只能支持研究。
- ML 不再默认叠加在确定性冠军之上。排序、下行风险、市场上下文和成本感知组合分别定义任务，再比较 ML 原生与混合路径。
- LLM 优先用于有证据片段的 SEC/新闻事件抽取、叙事变化和关系候选；没有不可变 PIT 正文时只做前向采集。
- 当前 7140 条 Nasdaq 快照可作为前向母池，不能回填为历史成员资格。历史当前成分股结果保留幸存者偏差标签。

## 3. 边界

- 不修改 active spec、paper/broker 写入路径或 `.env`，不新增依赖。
- 所有新 spec 保持 `draft`、`manual_signal`、`broker=none`。
- 每轮先通过 iteration dossier、knowledge scout/assessment、capability 和数据可行性门禁。
- 所有候选进入跨轮可累计 trial ledger；特征、标签、校准、阈值和组合参数只在训练折确定。
- benchmark family、成本压力、purge/embargo、退市/公司行动和数据 feed 差异均为显式验收项。

## 4. Wave Q.0：知识与计划

- 修复非 Web 相对路径进入外部知识索引的问题。
- 让 scout 同时接收 arXiv 查询与已联网核验的论文、官方文档、GitHub 和 practitioner 候选。
- 为 iteration 生成按主题检索的 knowledge context，主动取回旧来源、失败实验和冻结模型。
- 固化本计划、来源卡、假设、角色矩阵、搜索预算和停止条件。

验收：来源可追溯、重复项去重、未验证搜索结果不升级为知识、挑战/前向结果不进入候选生成上下文、`oc research iteration validate` 与 `oc research knowledge assess` 通过。

## 5. Wave Q.1：数据、PIT 与可行性

- 从完整当前快照建立 500-1500 条前向母池，再按类型、价格、流动性、历史完整度和行业集中度缩至可研究池；成员冻结日起才可作为前向证据。
- 日线和日内分别生成覆盖、缺口、公司行动、symbol mapping、feed 和成本报告。现有 1 分钟个股缓存可重采样用于研究，但不得伪装成 SIP。
- 扩展事件 packet 的 revision、rights、availability quality 和 acquisition mode；SEC 使用 acceptance/first-seen 语义，新闻历史回填不得把发布时间冒充首次可见时间。
- 无凭证或无授权来源形成机器可读 capability blocker，不使用 fixture 制造历史收益。

## 6. Wave Q.2：受限共同设计实验

预注册总预算 48，分为四类：

- 中期确定性：12 个，覆盖 12-1、行业/市场相对、成交量条件与低换手实现。
- 日线 ML 原生/混合：16 个，覆盖线性和浅树排序、下行分位数/分类、regime context 与成本感知权重。
- 日内独立策略：12 个，覆盖首小时延续/反转、隔夜分解、固定时段横截面，以及相同任务的低容量 ML 对照。
- 事件/LLM：8 个，只有真实 PIT packet 可用时运行；否则计入预算并明确跳过。

强制比较确定性、ML 原生、混合、缺失模态、时间延迟、shuffled/placebo 与成本压力。裁决同时看净收益、RankIC、回撤、换手、日期组稳定性和完整 benchmark family，不按单一最好回报选冠军。

## 7. Wave Q.3：隔离模拟与产品闭环

- 选择 4-6 个逻辑不同的候选；未通过研究门禁但有诊断价值的候选明确标记为 diagnostic。
- 每个 sleeve 使用独立虚拟现金、持仓、信号、spec/model/data hash 和冻结 epoch；共享 broker 账户不作为独立绩效证据。
- 每次观察追加到账本与知识库，不因单日表现自动重训。重训必须有数据新增、漂移、校准或 cadence 理由。
- 最终分别报告 `workflow_pass`、`research_pass`、`llm_contribution_pass` 和 `paper_ready_pass`。

## 8. 验证与提交

Wave 顺序固定为 `Q.0 -> Q.1 -> Q.2 -> Q.3`，每个 Wave 独立提交。每个 Wave 先跑 focused tests，最终运行：

```text
uv run ruff format .
uv run ruff check .
uv run pytest -q
uv run oc repo check --strict
make verify
```

红灯先修复。真实凭证、SIP、历史 PIT 成分、许可文本和新增前向交易日是外部证据，不允许由代码或回填报告伪造。
