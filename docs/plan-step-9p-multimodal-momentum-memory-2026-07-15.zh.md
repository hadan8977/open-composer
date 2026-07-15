# Step 9.P：个股动量多模态研究与长期知识记忆

## 1. 目标

只针对当前 `mom_multiasset` 个股动量族，建立两项可复用能力：

1. 把 SEC 文件、盈利公告、可授权的电话会文本、新闻和市场状态转成严格 PIT、可回放、可消融的结构化特征，测试它们能否确认趋势、过滤假动量或改进风险控制。
2. 建立本地优先的研究知识与模型注册表，使旧来源、旧结论、失败实验、冻结模型和前向表现可以跨迭代复用；新一轮优先刷新过期知识和补充新证据，而不是重复检索或重复推理。

本轮不以“增加 LLM 调用次数”为成功标准。成功必须表现为来源覆盖、知识新颖度、PIT 完整性、可复现实验和相对确定性 12-1 动量的真实边际贡献。

## 2. 不可违反的边界

- 不修改 `strategy_specs/active/`、paper/broker 订单路径和 `.env`；所有新策略保持 `draft/manual_signal/broker=none`。
- 真实资金写入继续越界；任何新 sleeve 首先只能进入隔离虚拟观察。
- 外部文档是不可信读者输入；LLM 只能返回固定 schema，历史回填必须引用输入文档中的证据片段。
- 每条事件记录必须有 `published_at`、`fetched_at`、`visible_at`、`source`、`input_hash`、`prompt_hash` 和稳定 `dedupe_key`。
- 历史文档由 2026 模型转换时标记为 `retrospective_transform`，不得称为 pristine LLM OOS；正式 LLM 贡献证据从冻结后的前向 epoch 开始。
- 电话会文本只使用许可明确的来源；没有合规来源时记录 capability blocker，不以网页抓取或 fixture 伪装真实证据。
- 当前股票池在冻结日前存在幸存者偏差；历史结果保持探索性质。
- 模型不得读取 symbol identity；所有市场特征使用决策时点 `index-1` 或更早信息；标签继续执行完整 purge+embargo。
- 总候选硬上限 24，全部进入 append-only trial ledger；禁止根据暴露挑战集扩大搜索。
- 不新增依赖；优先复用 `feature_packets`、`source_cards`、iteration dossier、现有 ML backend 和模型制品格式。

## 3. Wave P.0：研究知识与模型记忆

新增本地结构化 knowledge index，扫描 source cards、iteration external briefs、trial ledgers、decision records 和模型制品，形成：

- canonical source：规范 URL、来源类型、首次发现、最近复核、过期时间和内容/声明哈希；
- claim memory：声明、主题、适用策略、支持/反证来源和是否仍待验证；
- empirical memory：该声明对应的实验、数据边界、候选数、OOS 结果和 continue/pivot/stop；
- model memory：模型哈希、训练数据快照、特征/提示词合同、验证状态、适用角色、失败原因和最近前向观察；
- novelty assessment：本轮复用、刷新、重复、新增、冲突和未覆盖主题。

提供薄 CLI：`oc research knowledge build|scout|assess`。`scout` 使用版本化 query manifest 查询近期论文/官方文档候选，先与已有 canonical source 和 claim 去重，再输出“复用、需刷新、真正新增、冲突、低可信”清单；来源是否有效最终由后续实验证据而不是发表时间决定。相同 source/claim/model 不重复写入；旧结论可以复用，但过期或冲突声明必须刷新。

知识按 `public_literature`、`train_only_empirical`、`challenge_result` 和 `forward_observation` 分区。训练或候选生成只能读取公开资料和当折训练结果，不得读取 challenge/forward 裁决后再回填历史候选。模型注册表默认只复用冻结推理制品；是否重训必须给出数据新增、漂移、校准或 cadence 理由，禁止无条件 warm start。

验收：重复 source card 去重；来源过期可识别；query manifest 能区分已有与新增候选；负面实验不会丢失；challenge 记忆不会进入 train-only context；相同输入/提示词/模型继续命中 LLM materialization cache；当前 iteration 生成机器可读 knowledge assessment。

## 4. Wave P.1：当前策略的多模态 PIT 合同

先运行 capability review，再按以下优先级建立数据合同：

1. SEC `10-K/10-Q/8-K`、盈利公告附件和 filing metadata；
2. 有明确许可和 PIT 时间戳的电话会文本；
3. Alpha Vantage/GDELT 或后续注册的新闻能力；
4. SPY/行业 ETF 的价格、波动、广度和横截面离散度。

LLM 文本输出固定为可审计字段：`catalyst_strength`、`guidance_revision`、`earnings_quality`、`management_uncertainty`、`demand_signal`、`risk_event_score`、`narrative_novelty`、`information_half_life` 和 `evidence_spans`。同时生成不依赖 LLM 的 filing/news count、时效、词典情绪和事件类型基线。

每条 packet 必须保留原文哈希和来源引用。历史回填输出与冻结后的 forward packet 分开存储和标记；缺失任何模态时确定性 12-1 行为必须完全保持。

SEC 拉取必须使用明确的产品 User-Agent/联系标识并遵守官方访问策略；配置缺失时输出 blocker，不伪造联系人。电话会、付费新闻或再分发受限正文没有许可时只登记元数据和缺口，不落盘受限全文。

验收：使用小型真实/脱敏 fixture 验证 dedupe、可见时间、证据片段、迟到修订、缺失模态回退和 prompt/model 版本隔离；capability 报告不得把 fixture/cache fallback 标记成 paper-ready。

## 5. Wave P.2：受限模型与策略协作实验

预注册不超过 24 个候选，角色而非模型数量优先：

- Champion：确定性 12-1 动量；
- Quant ranker：价格量、行业相对和风险因子；
- Text-only diagnostic：只读 PIT 文本/事件特征；
- Quant+text ranker：测试文本边际贡献；
- Catalyst confirmation：只在文本确认时调整 ML 分数；
- False-momentum veto：只减少高风险候选，不创造独立买入；
- Regime/meta gate：决定何时允许 ML 覆盖 champion；
- Cost-aware shrinkage：ML 权重向确定性权重收缩并惩罚换手。

强制比较 `quant_only`、`text_only`、`quant_plus_text`、`missing_text_fallback`、`shuffled_text_placebo` 和 `stale_text_placebo`。训练目标比较行业中性前瞻收益、Top-K relevance、未来回撤风险和扣除估算成本后的组合目标。因子选择、缺失值填充、校准和阈值只在训练折完成。

正式通过至少要求：多折增量稳定、最近折不同时失败、成本后优于 champion、文本边际贡献通过、缺失文本退回行为锁定、placebo 不产生同等提升。历史回溯转换只能支持探索 verdict；冻结后前向 packet 才能支持 `llm_contribution_pass=true`。

## 6. Wave P.3：把要求固化进产品

- iteration dossier 可声明 `knowledge_contract`、`modality_role_matrix` 和 refresh/novelty 目标；声明后 `validate` 必须检查 knowledge assessment。
- source policy 增加论文/方法、公司文件、电话会和新闻的不同刷新周期与许可状态。
- 每轮自动输出角色矩阵、来源复用率、来源新颖度、过期/冲突声明、模型复用/重训理由和算力/调用成本。
- 模型只有在数据新增、漂移、校准失效或预注册 cadence 到期时重训；否则复用冻结制品并追加前向观测。
- promotion 继续分别裁决 `workflow_pass`、`research_pass`、`llm_contribution_pass` 和 `paper_ready_pass`。
- repo check 注册本计划，并用测试锁定知识去重、PIT、消融、回退、candidate cap 和无订单权限。

## 7. Wave 顺序与停止条件

执行顺序固定为 `P.0 -> P.1 -> P.2 -> P.3`。P.0 knowledge assessment 和 P.1 capability/PIT 合同未通过时，禁止训练 P.2。真实历史文本覆盖不足时，不用 fixture 凑收益；完成基础设施和前向 challenger，但将研究裁决保持为负面/未确认。

每个 Wave 完成后运行相关 focused tests。最终运行：

```text
uv run ruff format .
uv run ruff check .
uv run pytest -q
uv run oc repo check --strict
make verify
```

任何红灯先修复，不把工作流成功描述成 Alpha、LLM 贡献或 paper readiness。
