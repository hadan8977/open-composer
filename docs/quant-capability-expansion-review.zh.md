# Open Composer 能力补全与 Dashboard 严格审查

日期：2026-05-09

审查对象：

- `docs/quant-capability-expansion-plan.zh.md`
- `knowledge/quant_capability_knowledge_base.yaml`
- 当前仓库中的 StrategySpec、回测、信号日志、Alpaca Paper、LLM review、capability registry 设计。

审查目标：

1. 判断每一项是否真的必要。
2. 判断每一项是否应该现在做。
3. 判断每一项是否会制造新的风险。
4. 把不成熟、不必要、容易误导用户的部分压下去。

## 总体裁定

计划方向成立，但必须坚持四条硬约束：

1. Dashboard 不是新真相源，只是 repo artifacts 和控制命令的可视化层。
2. 版本库必须先于远程管理，否则启停策略时无法追溯“到底启用了哪一版”。
3. LLM 不能直接隐藏在执行链路里，必须产生结构化、可回放、可审计的产物。
4. 远程管理只能先支持 Alpaca Paper，真钱实盘写入继续排除。

## 逐项必要性裁决

| 项目 | 裁决 | 理由 | 执行动作 |
|---|---|---|---|
| 中文能力补全计划 | 必要 | 项目后续会频繁跨策略、数据、执行、LLM 和 Dashboard 协作，需要中文主文档。 | 保留为正式计划。 |
| 研究知识库 | 必要 | 不能靠临时聊天记忆做长期产品判断。 | 用 `knowledge/` 存结构化来源和设计原则。 |
| Dashboard | 必要 | CLI 对小白用户不够直观，也不适合长期监控。 | 进入路线图，但先只读。 |
| Streamlit 第一版 | 必要但阶段性 | 对本地单用户、表格/图表/控制按钮场景足够快。 | 第一版采用，未来再拆 FastAPI + 前端。 |
| SQLite dashboard catalog | 必要 | 只扫文件会慢且难以做版本、运行和审计查询。 | 作为可重建 read model，而不是新真相源。 |
| 策略版本库 | 必要 | Codex 多轮迭代会产生大量隐性版本，不做版本会无法回滚和复盘。 | 在远程管理前实现。 |
| 策略风险分类 | 必要 | 用户需要知道哪些策略稳健、哪些高风险。 | 同时保留人工声明和系统推导。 |
| LLM 中心 | 必要但先只读 | LLM 产物需要可见和可追溯。 | 先展示 review/context，不让它直接执行。 |
| 事件/新闻/宏观中心 | 必要 | 扫描机会类策略必须看到数据来源和转换链路。 | 作为 LLM 和因子层之间的桥。 |
| 策略组 / 编排器 | 必要但后置 | 组合策略是真实需求，但依赖版本、组合和风险层。 | Phase 5 做，不进入第一版。 |
| 可视化节点编辑器 | 暂缓 | OpenAlgo/Composer 证明有价值，但现在先把已有策略管理好。 | 不进入第一版。 |
| 远程启停模拟盘 | 必要但强门控 | 比和 Codex 对话可靠，但有误操作风险。 | 只允许 active + paper_auto + alpaca_paper。 |
| 真实资金管理 | 拒绝 | 当前 MVP 没有足够审计、权限和风控。 | 继续 out of scope。 |

## 产品视角审查

结论：Dashboard 必须做，但第一版不能贪多。

理由：

- 用户现在必须通过 Codex 对话理解策略状态，这对长期管理不可靠。
- 策略版本、回测、paper 状态、LLM review、新闻事件散落在不同文件夹里，缺少总览。
- Dashboard 能降低认知负担，但如果一开始做成完整可视化策略编辑器，会失控。

要求：

- 第一版只做策略库、详情、版本、运行状态和只读监控。
- 写操作只开放最小集：approve、activate、disable、paper runner start/stop。
- 每个按钮必须显示结果和审计记录。

## 量化研究视角审查

结论：Dashboard 展示不能掩盖当前量化能力仍然有限。

风险：

- 用户看到漂亮曲线后容易高估策略质量。
- 回测报告现在还没有完整费用、滑点、分红、拆股、点时数据和 walk-forward。
- LLM 或新闻类数据如果没有发布时间约束，会产生未来函数。

要求：

- Dashboard 必须显示“能力兼容性”和“回测假设”。
- 每个策略卡必须显示 `python_mvp_backtest`、`pine_strategy`、`alpaca_paper`、`llm_quant` 状态。
- LLM/新闻/事件参与的策略必须显示“是否可回放”。
- 任何高风险策略默认不能一键启用 paper_auto。

## 交易执行与风控视角审查

结论：远程管理可以做，但只能通过已有安全门。

风险：

- Dashboard 上的开关比 CLI 更容易误点。
- 如果没有版本绑定，启用的可能不是用户以为的版本。
- 如果没有订单同步，Dashboard 会展示过时状态。

要求：

- 所有启停操作必须写入 `AuditEvent`。
- 每次启用 paper_auto 必须绑定 `strategy_id + version_id + spec_hash`。
- 必须显示上次心跳、最后订单、最近异常。
- 必须有 kill switch 和停用确认。
- 不允许 real-money broker write。

## 架构视角审查

结论：Dashboard 应该分成 read model 和 command model。

正确架构：

```text
repo files / reports / logs
  -> dashboard catalog indexer
  -> read-only dashboard views

dashboard command button
  -> command service
  -> existing Python lifecycle / runner / paper functions
  -> audit log
  -> repo artifacts
```

禁止：

- UI 直接改 YAML；
- UI 直接提交订单；
- UI 在内存里维护唯一状态；
- UI 把 LLM 结果当成不可追溯的隐藏字段。

## LLM / AI 视角审查

结论：LLM 策略必须分层，不要统一叫“有大模型介入”。

正式分类：

1. `llm_role=none`：纯量化。
2. `llm_role=review`：只做信号后审核。
3. `llm_role=feature_extraction`：把事件、新闻、宏观转成结构化因子。
4. `llm_role=orchestrator`：参与策略组、市场状态、频率或权重选择。

要求：

- Review 类策略在普通策略详情页展示 review 卡即可。
- 扫描机会类必须进事件/新闻/宏观中心，展示转换链路。
- 组合策略类必须进策略组/编排器页。
- LLM 输出必须记录 prompt、model、输入 packet、输出 schema、时间戳。

## UX 视角审查

结论：这是交易工作台，不是营销站点。

要求：

- 首页必须是操作总览，不是 hero。
- 颜色和标签用于状态，不用于装饰。
- 策略列表要能筛选、排序、搜索。
- 重要操作必须用 icon + tooltip + confirmation。
- 文本要短，长解释放到详情页和文档。
- 高风险和 blocked 状态要比收益数据更显眼。

## 数据与审计视角审查

结论：版本和审计是 Dashboard 的地基。

要求：

- 每个 run 必须链接到具体 strategy version。
- 每个 signal 必须能追溯到 run、version、数据源和条件。
- 每个 order 必须能追溯到 signal。
- 每个 LLM review 必须能追溯到 signal/context/model/prompt。
- 每个 Dashboard 写操作必须能追溯到用户动作。

## 策略组归属裁定

用户提出的问题：组合策略应该放在“策略组”还是“管理组”？

裁定：

- `管理组` 是 UI/运营分组，用来筛选和治理，例如“中等风险”“memory storage”“paper only”。
- `策略组` 是会影响执行语义的一等对象，例如“市场状态切换组”“多频率组合组”“AI 主题策略组”。
- 组合策略必须归入 `策略组 / 编排器`。
- 策略组也可以显示在管理组里，但管理组不能替代策略组。

原因：

- 组合策略有自己的输入、判断、子策略、资金分配和运行状态。
- 如果只放在普通管理组里，会隐藏它的真实执行逻辑。

## 修订后的正式路线

### Phase 0：知识库和目录库

- 扩展 `knowledge/quant_capability_knowledge_base.yaml`。
- 建立 dashboard catalog 设计。
- 明确 Strategy、Version、Run、Signal、Order、Context、Group、Audit 的关系。

### Phase 1：只读 Dashboard

- 策略库；
- 详情页；
- 回测和 signal viewer；
- capability badge；
- 本地离线可运行。

### Phase 2：版本管理

- 不可变版本快照；
- diff；
- rollback；
- run-version 绑定；
- active 指针。

### Phase 3：Paper 监控和管理

- active paper_auto 列表；
- 订单、持仓、PnL；
- 启用/停用；
- 审计；
- kill switch。

### Phase 4：LLM 和事件工作区

- Review 卡；
- 新闻/事件/宏观流；
- feature extraction 记录；
- replay cache；
- prompt/model 版本。

### Phase 5：策略组 / 编排器

- 子策略树；
- 市场状态；
- 频率；
- capital allocation；
- group-level 风险。

### Phase 6：高级能力接入

- 因子库；
- 横截面；
- walk-forward；
- ML prediction store；
- 更完整的成本和执行模型。

## 最终审查结论

该计划可以进入下一阶段，但第一版必须控制范围：

- 先做只读 Dashboard 和版本目录；
- 再做 paper 管理；
- 最后做策略组和 LLM 编排；
- 不允许在没有版本和审计的情况下做远程启停；
- 不允许把 LLM 结果直接嵌入交易执行链路。
