# Open Composer 能力补全与 Dashboard 严格审查

日期：2026-05-10

审查对象：

- `docs/quant-capability-expansion-plan.zh.md`
- `knowledge/quant_capability_knowledge_base.yaml`
- 当前仓库中的 `StrategySpec`、回测、信号日志、Alpaca Paper、LLM review、capability registry、Dashboard 设计。

审查目标：

1. 判断每一项是否真的必要。
2. 判断每一项是否应该现在做。
3. 判断每一项是否会制造新的风险。
4. 把不成熟、不必要、容易误导用户的部分压下去。

## 总体裁定

方向成立，但必须坚持四条硬约束：

1. 先完成 Open Composer 能力补全，再做 Dashboard 的正式接入。
2. Dashboard 不是新真相源，只是 repo artifacts 和受审计命令的可视化层。
3. LLM 不能隐身在执行链路里，必须产出结构化、可回放、可审计的结果。
4. 远程管理只能先支持 Alpaca Paper，真钱写入继续排除。
5. 执行后端不继续自研全功能引擎，选 NautilusTrader 作为事件驱动执行核，当前 Python 引擎保留为 deterministic reference。
6. 低成本数据路线先采用 Longbridge + Alpaca 双源：Longbridge 做主行情候选，Alpaca 保留为已实现行情和第一 paper 通道。

## 主要结论

### 必须保留

- `StrategySpec` 作为源头。
- Python 作为策略语义主干。
- 现有 Python reference engine 作为 smoke test 和语义回归基线。
- NautilusTrader 作为事件驱动执行后端。
- 不可变版本模型。
- capability registry 和知识库。
- Longbridge + Alpaca 低成本双源路线。
- 结构化 LLM review。
- paper first 的执行顺序。
- Dashboard 作为控制平面和观察平面。

### 必须推迟

- 完整策略编排器的开放式可视化编辑。
- 多用户 / 远程实盘管理。
- 复杂 LLM orchestrator 的直接执行权。
- 任何试图把当前 Python engine 膨胀成全功能执行内核的路线。
- 任何超出当前数据能力的“全量量化支持”承诺。
- 把 IBKR 作为第一阶段默认低成本数据源。

### 必须拒绝

- 把 Pine 当成所有策略的主运行时。
- 把 Dashboard 当成第二个真相源。
- 在没有版本和审计之前开放宽泛写操作。
- 让 LLM 直接修改交易语义而不留结构化痕迹。
- 继续自研一个与 NautilusTrader 并行的全功能事件驱动引擎。

## 引擎选择复审

| 项目 | 裁决 | 理由 | 处理 |
|---|---|---|---|
| 自研全功能事件驱动引擎 | 拒绝 | 范围过大，重复造轮子，且会拖慢能力补全和 Dashboard。 | 不作为默认路线。 |
| NautilusTrader 后端 | 采用 | 官方强调 backtest/sandbox/live 同构，适合作为事件驱动执行核。 | 作为第一执行后端，承接可回放的策略语义。 |
| Python reference engine | 保留 | 快、确定性强，适合作为 sample-data smoke test 和回归基线。 | 保持在仓库内，但不继续膨胀成最终执行核。 |
| Pine 全量支持 | 拒绝 | 兼容目标只能是确定性子集，不可能承载所有复杂策略。 | 继续只做 subset 导出。 |

## 数据源选择复审

| 来源 | 裁决 | 适合用途 | 主要风险 | 处理 |
|---|---|---|---|---|
| Longbridge 免费基础行情 | 采用为 trial 主行情候选 | 美股 watchlist 的 1m/5m/15m/1h/daily 数据、本地缓存、基础扫描、基本面和新闻补充。 | 美股免费基础权限不是 consolidated SIP；分钟历史范围、symbol 配额、复权和盘前盘后覆盖会影响回测。 | 新增 adapter 前必须进入 capability evaluation；报告必须显示 feed、延迟级别、历史范围和覆盖 caveat。 |
| Alpaca IEX | 继续保留 | 当前已实现的 OHLCV 获取、扫描、回测、paper context。 | IEX 覆盖不是全市场，成交量和价格可能与 SIP / Nasdaq Basic / broker fill 不一致。 | 保持 approved，但所有报告必须显式标注 `feed=iex`，并在严肃回测前与 Longbridge 做差异比对。 |
| Alpaca Paper | 继续作为第一 paper 通道 | 模拟盘自动下单、订单同步、kill switch、Dashboard paper monitor。 | paper fill 与真实成交不同；自动化误操作风险高。 | 继续强门控：active + paper_auto + explicit allow + audit。 |
| Longbridge trading / paper | 后续候选 | 第二 broker adapter、与 Alpaca paper 做执行对照。 | 订单生命周期、权限隔离、状态同步、错误处理尚未接入。 | 不在文档里承诺可用；先做 paper/sandbox 级验证。 |
| IBKR | 暂缓 | 后续专业实盘账户、更多资产覆盖、成熟 broker 执行。 | 数据订阅、TWS/Gateway、API 权限和工程复杂度较高；不符合当前低成本优先。 | 不作为第一阶段默认数据源；保留在知识库和后续路线。 |
| Alpha Vantage / GDELT / FRED / SEC | 保留为补充源 | 新闻情绪、广谱事件、宏观和官方 filings。 | 新闻噪声、免费限额、发布时间和回测泄漏风险。 | 只作为 context / feature source；影响交易前必须可回放、去重和审计。 |

严格结论：

- Longbridge + Alpaca 的组合适合当前“美股、5m 及以上、小到中等 watchlist、低成本 paper 验证”的产品阶段。
- 这条路线不能被表述成“全市场高质量数据已经解决”；它只解决第一阶段低成本可用性。
- Longbridge capability 没有实现和通过测试前，任何策略不能把它列为 required capability。
- Longbridge 基本面不能在当前 registry schema 里硬塞成已支持能力；要么先扩展 `Capability.kind`，要么先作为结构化事件快照试点。
- 对同一策略，要支持 `sample -> Longbridge -> Alpaca` 的逐级验证，不能只看单一数据源收益。

## 逐项必要性裁决

| 项目 | 裁决 | 理由 | 处理 |
|---|---|---|---|
| 中文能力补全计划 | 必要 | 后续会频繁跨策略、数据、执行、LLM 和 Dashboard 协作。 | 保留为正式主文档。 |
| 知识库 | 必要 | 不能靠临时聊天记忆做长期判断。 | 继续使用 `knowledge/` 下的结构化知识库。 |
| 不可变版本库 | 必要 | 没有版本就没有回滚、比较和审计。 | 放在 Dashboard 写操作之前完成。 |
| Longbridge 数据适配 | 部分完成，仍先 trial | 已有 cache replay、manifest、capability registry 和增强差异报告；差异报告已包含 feed、manifest、覆盖率、bps、缺失样本和 caveat。仍需真实 SDK 联调与覆盖验证。 | 继续保持 trial，等真实刷新、延迟与覆盖测试通过后再考虑升为 approved。 |
| Alpaca 数据与 paper | 必要且保留 | 当前已实现，能支撑扫描、paper 和安全门控。 | 继续作为第一 paper 通道，并补足 feed 标注和差异报告。 |
| NautilusTrader 执行后端 | 必要，单标的 backtest 已接入 | 需要事件驱动 backtest/sandbox/live 同构，且能接 replayable custom data。当前已完成单标的 OHLCV 真实 backtest adapter。 | 继续补 sandbox/paper、多标的、组合目标和更完整 custom data replay。 |
| Nautilus paper runtime MVP | 必要且已完成第一步 | 当前 paper runner 已能为 active `nautilus_trader` 策略写出 `reports/runs/nautilus_paper/*.json`，并以 `nautilus_paper` execution backend 生成最新 bar paper 信号，再交给 Alpaca Paper readiness / kill switch / explicit allow gate。 | 继续把后续订单生命周期、持续同步和多资产 routing 放到 Paper 服务化与组合阶段。 |
| Pine 全量支持 | 不必要且错误 | Pine 有明确限制，不适合作为全量量化运行时。 | 只保留 deterministic subset 导出。 |
| LLM review | 必要 | 用户需要上下文和风险解释。 | 保持 advisory，并结构化存档。 |
| LLM orchestrator | 必要但后置 | 组合策略是真需求，但依赖版本、分层和审计。 | 放到能力补全后再开放。 |
| Dashboard | 必要 | CLI 对长期观察和管理不够直观。 | D1 静态只读 HTML 已接入，继续保持先只读、后命令。 |
| SQLite / read model | 必要 | 只扫文件会慢且难查询版本和运行关系。 | 作为可重建目录库，不是新真相源。 |
| 策略组 | 必要 | 组合策略不是普通标签。 | 作为一等对象实现。 |
| 远程 paper 管理 | 必要但强门控 | 比和 Codex 对话更可靠，但误操作风险高。 | 只允许 paper_auto 且 active。 |
| 真钱实盘写入 | 拒绝 | 当前 MVP 没有足够审计、权限和风控。 | 继续 out of scope。 |

## 多视角审查

### 产品视角

结论：Part I 和 Part II 的顺序是对的，但 Part II 不该比 Part I 先拿到真实写权限。

- 用户真正需要的是“看懂策略、看懂版本、看懂执行”，不是先做一个会动但不可信的 UI。
- Dashboard 的价值在于降低 Codex 对话成本，而不是替代产品逻辑。
- 对于当前项目，Dashboard 必须是工作台，不是 landing page，也不是策略玩具。

### 量化研究视角

结论：计划必须明确“支持更多策略类型”不等于“支持所有策略类型”。

- 单资产技术策略可以作为当前主线。
- 横截面、组合、统计套利、ML alpha、options overlay 都需要不同的数据和研究语义。
- Pine 只适合作为兼容导出，不可能容纳所有因子、事件和组合逻辑。
- Dashboard 必须展示回测假设、数据时间戳、成本、滑点和版本绑定，避免漂亮曲线掩盖研究缺陷。

### 执行与风控视角

结论：远程管理可做，但只能在版本、审计和门禁成熟后做。

- Dashboard 上的开关比 CLI 更容易误点。
- 所有启停、回滚、重跑都必须留下审计。
- 纸面执行必须绑定 `strategy_id + version_id + spec_hash`。
- 必须有 kill switch 和状态重建能力。
- 没有订单同步，就没有可信的 live/paper 监控。

### 架构视角

结论：Dashboard 应该分成 read model 和 command model。

```text
repo files / reports / logs
  -> catalog indexer
  -> read-only dashboard views

dashboard command
  -> command service
  -> existing Python lifecycle / runner / review / journal logic
  -> audit log
  -> repo artifacts
```

禁止：

- UI 直接改 YAML；
- UI 直接提交订单；
- UI 在内存里维护唯一状态；
- UI 把 LLM 结果藏在不可审计字段里。

### LLM / AI 视角

结论：不要把“量化 + LLM”写成一个模糊大筐。

正式分类应至少区分：

1. `llm_role=none`：纯量化。
2. `llm_role=review`：只做信号后审核。
3. `llm_role=feature_extraction`：把事件、新闻、宏观转成结构化因子。
4. `llm_role=orchestrator`：参与市场状态、频率、权重和策略组选择。

要求：

- Review 类策略在普通详情页展示 review 卡即可。
- 扫描机会类必须进入事件 / 新闻 / 宏观中心。
- 组合策略类必须进入策略组 / 编排器页。
- LLM 输出必须记录 prompt、model、输入 packet、输出 schema、时间戳。

### UX / 运营视角

结论：这是交易工作台，不是营销站点。

- 首页必须是操作总览。
- 颜色和标签用于状态，不用于装饰。
- 列表要能筛选、排序、搜索。
- 重要操作必须有 icon、tooltip 和 confirmation。
- 高风险和 blocked 状态要比收益数据更显眼。

### 数据与审计视角

结论：版本、数据 provenance 和审计是 Dashboard 的地基。

- 每个 run 必须链接到具体 strategy version。
- 每个 run 必须显示数据源、feed、延迟级别、历史范围、缓存版本、抓取时间和调整方式。
- 每个 signal 必须能追溯到 run、version、数据源、条件和输入 bar / feature packet。
- 每个 order 必须能追溯到 signal。
- 每个 LLM review 必须能追溯到 signal / context / model / prompt。
- 每个 Dashboard 写操作必须能追溯到用户动作。
- Longbridge 与 Alpaca 的数据差异不能被隐藏；Dashboard 应该显示数据源兼容性和最新差异检查状态。

### 成本与路线视角

结论：不能一口气把所有高级能力、UI 和执行控制一起做。

- 先做能力补全，再做只读 Dashboard。
- 再做版本、审计和 paper 控制。
- 最后才做策略组和 LLM 编排页。
- 如果顺序倒置，Dashboard 会变成一层漂亮但不可信的壳。

## Part I 复审

| 项目 | 裁决 | 理由 | 处理 |
|---|---|---|---|
| 策略 AST / 类型化 `StrategySpec` | 必要 | 复杂策略无法再只靠 entry/exit 文本承载。 | 保留并优先。 |
| 不可变版本记录 | 必要 | 没有版本就不能回滚和审计。 | 放在最前面。 |
| 因子目录与数据时点 | 必要 | 高级策略和 LLM 都依赖 point-in-time 语义。 | 作为研究地基。 |
| Longbridge + Alpaca 双源校验 | 必要 | 单一免费数据源容易把覆盖偏差误当成 alpha。 | 建立同标的同周期差异报告和 provenance manifest。 |
| 研究 / 回测增强 | 必要 | 当前能力偏基础。 | 加成本、滑点、walk-forward、横截面等。 |
| LLM review card | 必要 | 用户需要可解释上下文。 | 保持 advisory。 |
| LLM 直接改交易语义 | 拒绝 | 风险太高，难以审计。 | 只允许结构化特征或审查。 |
| Pine 全量导出 | 拒绝 | 不符合平台限制。 | 只做兼容子集。 |
| 纸面执行和审计 | 必要 | 这是后续 Dashboard 管理的前提。 | 优先于远程控制。 |

### Part I 的严格结论

Part I 必须先做，而且必须是“先语义、后界面、先版本、后控制”。如果这个顺序不成立，Dashboard 没有真实对象可看，也没有可信对象可控。执行侧则必须用 NautilusTrader 承接事件驱动语义，Python 引擎只做参考和回归。

## Part II 复审

| 项目 | 裁决 | 理由 | 处理 |
|---|---|---|---|
| 只读 Dashboard | 必要 | 这是最安全、最有价值的第一步。 | 优先实现。 |
| 静态 HTML Dashboard | 必要且已完成第一步 | 当前仓库未看到可运行的 Figma 前端代码，先用 repo-native HTML 生成器把 catalog 变成可查看页面，并生成策略详情页和数据质量区。 | 保留为 D1 基线，后续前端必须读取同一 catalog。 |
| 版本页 | 必要 | 没有版本页就无法解释策略迭代。 | 必须包含 lineage。 |
| Paper Monitor | 必要 | 用户最需要看到 active paper 状态；基础 kill switch/status 读模型已具备。 | 写控制仍必须只对 paper_auto 和 command gate 开放。 |
| Paper cycle read model | 必要且已完成第一步 | Dashboard 现在能收录 paper runner cycle，并显示 `kind=paper`、version、spec hash、backend、backend plan 和信号数量。 | 继续补订单同步、持仓、PnL 和 Nautilus paper runtime。 |
| Paper account / positions snapshot | 必要且已完成第一步 | `oc paper sync-account` 可同步 account / positions 到本地 JSON，paper status 和 Dashboard summary 已读取 equity、cash、buying power、持仓数量、市值和 unrealized PnL。 | 继续补自动刷新、异常告警和订单/持仓一致性检查。 |
| Paper reconciliation | 必要且已完成第一步 | `oc paper reconcile` 可检查本地 paper orders、account、positions 的一致性，并把 status / issue count 汇总到 paper status 与 Dashboard。 | 后续接入自动刷新、异常告警和 broker order lifecycle 细节。 |
| Paper alerts | 必要且已完成第一步 | `oc paper alerts` 可把 kill switch、reconciliation、open orders、缺失 account snapshot、unrealized loss 汇总成统一告警，并进入 paper status 与 Dashboard。 | 后续把 alerts 接入自动刷新和通知。 |
| Paper monitor refresh | 必要且已完成第一步 | `oc paper monitor` 可一次性刷新 reconciliation、alerts、status 和 monitor report，是后续自动调度的最小闭环。 | 下一步接入定时 loop / 服务化调度和通知。 |
| Paper monitor loop | 必要且已完成第一步 | `oc paper monitor-loop` 可按 interval / max_cycles 重复刷新，并写入 `monitor_cycles.jsonl`。 | 后续再服务化、加通知和进程健康检查。 |
| LLM feature replay view | 必要 | feature packet 是 llm_feature 的回放输入，Dashboard 需要可见。 | 已接入 read model / HTML，后续可增加过滤和版本对照。 |
| LLM Center | 必要但先只读 | LLM 产物需要可见和可追溯。 | 先展示 review / context。 |
| 策略组 / 编排器页 | 必要但后置 | 这是高级能力，不该比版本和 paper 先出现。 | 放到后期。 |
| 可视化策略编辑器 | 暂缓 | 现在先管理已有策略，不先做自由拖拽编辑。 | 不进入第一版。 |
| 远程启停 paper | 必要但强门控 | 比对话控制更可靠，但风险高。 | 需要确认、审计、版本绑定。 |
| 真钱实盘管理 | 拒绝 | 风险和合规都不足。 | 继续排除。 |

### Part II 的严格结论

Dashboard 是必要的，但它的第一版必须是“可观察、可回放、可审计”，不是“可任意编辑、可任意下单、可任意改状态”。当前 `oc dashboard html` 已经把这个原则落到静态只读首页、策略详情页和数据质量区，后续任何 Figma / Web 前端都必须复用 `reports/dashboard/catalog.json`，不能另建真相源。
Dashboard 还必须显式展示每个运行的 backend、兼容等级、replay 来源和 paper 安全门状态，否则用户会把参考引擎误认为最终执行核。

## 需要写进最终计划的硬约束

1. Part I 完成前，不开放 Dashboard 的宽泛写权限。
2. Part II 只读版先行，命令版后行。
3. 任何 LLM 相关页面都必须显示 prompt / model / 输入 / 输出 / 时间戳。
4. 任何策略组页面都必须明确它是执行语义对象，不只是标签。
5. 任何 Pine 导出都必须标注兼容范围。
6. 任何 paper 控制都必须通过统一命令服务和审计日志。

## 最终审查结论

该计划可以进入下一阶段，但前提是：

- 先完成 Open Composer 的能力补全；
- 把 Longbridge 作为 trial 主行情候选、Alpaca 作为已实现行情和第一 paper 通道；
- 对 Longbridge / Alpaca 数据做 provenance、差异检查和能力评估，不把免费行情误标为全市场数据；
- 再重审 Dashboard 计划；
- 先做只读 Dashboard 和版本目录；当前静态 HTML 只读页已完成第一步；
- 再做 paper 管理和有限命令；
- 不允许在版本、审计、状态同步没成熟时开放广泛远程控制；
- 不允许把 LLM 结果直接嵌入交易执行链路。
