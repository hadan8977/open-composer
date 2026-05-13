# Open Composer 下一阶段完整优化计划

日期：2026-05-13

## 背景判断

README 中曾出现 `mu_breakout_volume_15m_optimized_volume_plus` 的短样本高收益示例。这个例子不适合作为项目 benchmark：它只基于 52 根 sample bar，年化收益和 Sharpe 会被样本长度、交易次数和数据选择严重放大。

这个问题本身暴露出下一阶段必须优先补的能力：不仅要能跑回测，还要能判断“这个回测有没有资格被展示、比较、推广或进入 paper”。

## 总原则

1. 不在 README 或首页展示 sample-data 高收益。
2. sample / fixture 只证明工作流可运行，不证明策略有效。
3. 所有策略候选必须按证据等级分层。
4. 参数扫描是研究工具，不是自动寻找可交易策略的机器。
5. LLM 可以帮助提出假设、解释敏感性和生成 review，但不能替代数据验证。
6. Dashboard 只能展示真实证据链，不能把短样本最优结果包装成成果。

## 证据等级

| 等级 | 名称 | 能做什么 | 不能做什么 |
|---|---|---|---|
| E0 | sample smoke test | 证明 spec、表达式、回测、报告链路能运行 | 不能展示为收益能力 |
| E1 | 单数据源研究回测 | 初步筛掉明显无效策略 | 不能进入 paper |
| E2 | 参数敏感性 + 成本敏感性 | 判断策略是否只靠单点参数成立 | 不能证明跨时期有效 |
| E3 | 样本外 + walk-forward | 作为 paper candidate 的最低研究证据 | 仍不能代表实盘收益 |
| E4 | 多数据源对照 | 检查 Alpaca / Longbridge / sample 数据差异 | 不能替代 broker fill 验证 |
| E5 | Nautilus parity + Paper 观察 | 接近产品闭环验证 | 仍然是模拟盘，不是真钱证据 |

## P0：立即完成的文档与展示修正

目标：消除误导性 benchmark。

任务：

- 删除 README 中短样本高收益 Example Benchmark。
- 修改历史审计文档，把该策略标记为 smoke-test / 反例，而不是高门槛达标策略。
- 在回测与优化审查文档中加入 Benchmark 展示规则。
- 后续任何 README / Dashboard 首页展示性能数字，都必须先过 evidence gate。

验收：

- README 不含短样本收益宣传。
- 文档明确 sample-data 不等于策略有效。

## P1：回测报告可信度增强

状态：本轮已完成第一版 data sanity gate。

目标：让系统能识别明显不可信的回测结果。

任务：

- 给 backtest report 增加 data sanity section。
- 标记 bar 数、交易数、持仓天数、样本跨度、数据源、fallback 状态。
- 对短样本年化、极高 Sharpe、交易数过少、费用为零、sample/fallback 数据给 warning。
- 对 annualized return 增加展示限制：短样本可以计算，但报告必须标注不可用于比较。

实现记录：

- `BacktestRun` 增加 `data_sanity` 结构化字段。
- Python reference 与 Nautilus backtest 都会写入同一套 `data_sanity` 结果。
- Backtest report 新增 `## Data Sanity`，显示 evidence level、数据源、数据模式、bar/signal/trade、样本起止、样本跨度、平均持仓天数和 warning。
- Dashboard catalog / HTML 显示 evidence level、sanity status 和 warning count。
- sample / fixture / fallback / 短样本 / 少交易 / 异常年化 / 异常 Sharpe / 零费用假设都会触发 warning。

验收：

- 52 根 bar 的 sample 回测会被明确标为 smoke-test。
- Dashboard 和 README 不会把 warning 结果当 benchmark。

## P2：研究验证硬化

状态：最小 promotion gate 已实现，仍需和 paper gate 做强制联动。

目标：补齐从 research-only 到 paper candidate 的验证门。

任务：

- 在 parameter sweep 后增加成本/滑点敏感性。
- 增加 out-of-sample split。
- 增加 walk-forward。
- 增加 Alpaca / Longbridge / sample 数据源比较。
- 生成 promotion report，明确是否允许进入 paper candidate。

实现记录：

- 新增 `oc strategy promotion-report`。
- report 会跑 full-window、out-of-sample、walk-forward、cost sensitivity 和 data comparison 汇总。
- 报告与 JSON 明确列出缺失项和 warning，不把单次收益当作 promotion 证据。

验收：

- 任何策略进入 paper 前，必须有 promotion report。
- promotion report 必须列出缺失项，不能只看单次收益。

## P3：参数扫描质量提升

目标：让参数扫描服务于稳健性，而不是制造过拟合。

任务：

- 给 `oc strategy parameter-sweep` 增加 result quality flags。
- 支持 min bars、min trades、max suspicious annualized return、min data span 之类的警戒线。
- 增加 grouped summary：哪些参数区间稳定，哪些只是单点最优。
- 记录 Codex / LLM 给出的参数假设来源。

验收：

- 参数扫描报告能区分“稳定区间”和“孤立最优点”。
- top candidate 仍保持 draft/manual，不自动进入 active。

## P4：LLM 与研究流程结合

目标：发挥 LLM 的优势，但不让它破坏可复现性。

任务：

- LLM 生成参数范围建议时，输出结构化 hypothesis packet。
- LLM 对 sweep 结果做 structured review：稳定性、过拟合风险、数据缺口、下一步测试。
- LLM review 只进入报告和 Dashboard，不改变 backtest loop。
- 所有 LLM 输入、prompt hash、model、输出 schema 都记录。

验收：

- LLM 对策略优化的贡献可追溯。
- 同一数据和 packet 可以复跑。

## P5：Dashboard 接入研究证据

目标：Dashboard 帮助用户看懂策略证据等级，而不是展示漂亮收益。

任务：

- Strategy Detail 显示 evidence level。
- Research 页面显示 parameter sweep、data sanity、OOS、walk-forward、cost sensitivity。
- 首页不展示没有通过 evidence gate 的收益数字。
- 对 sample/fallback/short-window 结果显示明显 warning。

验收：

- 用户能直接看出某策略是 smoke-test、research-only、paper candidate 还是 active paper。
- Dashboard 的收益展示必须能回链到报告和数据 provenance。

## P6：Nautilus 与 Paper 闭环

目标：把研究通过的策略接到更接近执行语义的路径。

任务：

- 对 paper candidate 运行 Nautilus backtest / Python reference parity。
- paper runtime 使用同一 spec hash、version、data manifest、feature packet。
- Paper monitor 同步 broker orders、fills、positions、account、PnL。
- 所有 order 绑定 signal id、version id、spec hash。

验收：

- paper 结果能回链到研究证据。
- paper 与 backtest 差异能被解释。

## 暂不做

- README 展示收益排行榜。
- 自动把最佳 sweep 结果变成 active / paper_auto。
- 真钱交易。
- 机构级因子平台。
- 多资产组合优化器。
- 云端大规模并行优化。

## 下一步执行建议

P1 已完成。下一轮实现型 `/goal` 建议只做 P2 的最小闭环，不跳到 Dashboard 美化或高级策略扩展：

```text
Research promotion gate
  -> out-of-sample split
  -> walk-forward
  -> cost/slippage sensitivity
  -> Alpaca / Longbridge / sample data comparison summary
  -> promotion report
  -> tests
```

完成 P2 后再复审 Dashboard 研究证据页；不要把 P2 扩展成机构级研究平台。
