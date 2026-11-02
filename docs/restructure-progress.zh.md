# Claude 整体改造当前状态

当前依据是 [Claude 最终交接](handoff-2026-10-28-restructure.md)及重新接手的[实施计划](claude-takeover-plan.zh.md)。计划已获[独立审阅接受](claude-takeover-review.zh.md)，这是实施依据，不是效率提升证明。此前 Codex 四份自拟计划和 plan-review 已按机主要求删除，Git 历史保留。

| 原交接 | 当前实际状态 |
|---|---|
| 精简入口 | AGENTS、rules、control 和短角色提示生效；旧手写 lead-handoff 已删除，重复说明正在收敛。原科学合同和历史证据保留。 |
| 完整研究循环 | 有限 worker→fresh Lead、系列接续、同会话恢复已实现。Martin 原 16:23 手动恢复仍在运行；新版恢复不热加载，不能据此宣称无人介入成功。 |
| 共享引擎 | 正在把原 ETF 筛选入口的收益、成本、组合漂移实际计算与 trial ledger 收敛到 lab；此前 wrappers、示例和旧账户导入不算完整交付。 |
| 生产迁移 | 实际服务 active，调用版本化包、config/paper 配置和 runtime/paper/six 状态。Claude 的 SIGTERM/OOM 修复已保留。 |
| Claude / A/B | 结果和任务格式保持厂商中立；实际调用当前仅 Codex。A/B 等机主明确开始。 |

Martin 标签、HGB、TCN 与账户输入已获有限科学接收；四账户正在原任务内计算，最终经济比较尚未完成。原在途作业与冻结定义不变。结果以 [run.json](../research/martin_model_completion_20261102/runs/model-completion-20261102-1/run.json) 和原生账户为准。

普通研究按真实带成本结论、全角色实际 token/时间和机主介入记录评价，缺口明确保留。重构、验证和导入不计入研究成果或改造后的研究效率，不做摊销、回本或新增效率门禁。

历史错误判断和更正留在 [11 月 2 日审计](restructure-review-2026-11-02.zh.md)；当时快照不能代替当前运行结果。最终实施结果追加在本页，避免再建一套状态文档。

## 本次已落地的改造

- 删除四份旧 Codex 计划/plan-review 和自拟 lead-handoff；恢复生效入口与 Claude 五项交接的对应关系。发现 `task-owned-research.zh.md` 虽已指向 archive，内容仍自称 current working method；已将该兼容入口改为指向当前研究流程，归档原文不变。角色配置中仍供既有报告使用的部分保留。
- 项目启动包上界为 **7,994 bytes**（含 1,000-byte brief、400-byte board 行及 500-byte dispatch）；流程 README 从 125 行收敛到 67 行。不会把平台注入的工具/技能目录算成仓库材料缩减。
- `lab.accounting` 实际承担收益、换手成本、缩放权重及组合漂移；salvage、voltarget、defense、tranching、screen 与组合入口共同调用。七个被改动函数与 Git 中重构前实现逐值相等，保留原始浮点运算次序。不同的股票现金账本和 intrabar 成交模型继续复用现有公共引擎。
- 原 `screen_batch.py` 已改走公共 batch/TrialLedger/Results；按方向累计旧暴露、失败启动与新变体。新结果写不可覆盖的批次目录，保存原逐次 DSR 和最终累计 DSR 的区别、每个偏移的实际换手及 10/20bp 成本。已用真实调用路径的受控输入核实“5 个旧试验 + 1 个成功 + 1 个失败 = 7”，DSR 使用 7，旧结果未覆盖。
- 21 项受影响原检查通过；追加批次路径检查后，受影响 6 项复验通过。未运行全套测试。证据在 `reports/ops/claude-takeover-20261102/`，这些是重构验证，不计研究产出。
- 生产迁移保留：43 份打包源文件全匹配；service 和 inference 两环境固定项检查通过；实际服务仍 active，未调用 broker、未重启或改账本。四项依赖 BASE 的策略仍缺 11 月模型，H5/LSTM 有有效目标；这是科学输入依赖，不能拿授权续期替代。

## 普通研究接续

Martin 原 worker 与原账户队列继续计算。最终 request 已改交既有 fresh Lead 独立验收，worker 完成后提交经济结果，不再等已退出的逐阶段 peer；没有代写 final acceptance，也没有重放账户。

另已从原 D1 的 K1 保留结果和近期同风险组合增量出发，启动 `cross_asset_mechanisms_20261102`。新范围审阅发现旧组合算法让新权重赚取成交前隔夜收益，已据此限定旧结果为历史证据；新分支改用公共 `book_engine` 的资产级现金账本，并补齐开发期配对美元账户、10/20bp 成本、24 个明确机制与风险匹配说明。该科学审阅和随后 worker/Lead 属普通研究；源代码迁移、文档和测试仍属重构。当前尚未生成新的经济结论，不宣称效率达标。

新普通研究已经完成同一次范围审阅的修订接收，完整 worker 正在执行。实际运行还暴露了一个格式兼容问题：reviewer 把“已接受的审查报告路径”放入 checkpoint，运行器会误当未解决阻塞。本次保留原 Reply，将明确 complete/accept 的审查报告与真正 blocked 的检查点区分；五项受影响流程检查通过，普通 worker/Lead 的未解决检查点仍阻止重复启动。当前驱动已加载旧版本，后续自然恢复才使用修复，不为热加载重启任何研究作业。
