# Open Composer 回测与优化迭代能力审查

日期：2026-05-13

## 结论

Open Composer 需要加强回测与优化迭代能力，但不能为了“看起来专业”而引入一个平行量化平台。正确路线是：

```text
StrategySpec
  -> 受控参数网格
  -> 复用现有 backtest_frame 语义
  -> 生成 ranked JSON / Markdown 研究报告
  -> 只把少量 top candidates 写成 draft specs
  -> 后续再做样本外、walk-forward、成本/数据源敏感性
```

本轮新增的能力是“通用参数批量扫描基线”，用于一次性跑多组参数组合，解决原有 `optimize_strategy` 只能跑硬编码候选的问题。

## Benchmark 展示规则

README、Dashboard 首页或任何面向用户的摘要不允许展示短样本夸张收益作为 Example Benchmark。尤其是：

- 少于可解释样本长度的 sample-data 回测不得展示年化收益或 Sharpe 作为产品能力证明。
- sample / fixture / fallback 数据只能证明工作流可运行，不能证明策略收益。
- 参数扫描产生的 top candidate 只能是 research candidate，不能自动成为 benchmark。
- 如果要展示性能数字，必须同时显示数据源、bar 数、交易数、样本区间、成本/滑点、样本外结果、walk-forward 结果和数据源对照。
- 对异常高年化、异常高 Sharpe、极少交易、极短窗口结果，报告必须给出 data sanity warning。

当前实现状态：

- Python reference 与 Nautilus backtest 都已经写入 `BacktestRun.data_sanity`。
- Backtest report 已有 `## Data Sanity` section，显示证据等级、数据源、fallback/fixture/sample 状态、bar/signal/trade、样本起止、样本跨度、平均持仓天数和 warning。
- Dashboard catalog / HTML 已读取 evidence level、sanity status 和 warning count。
- `oc strategy promotion-report` 已能输出 full-window、out-of-sample、walk-forward、cost sensitivity 和 data comparison 的最小 promotion gate，并已接入 paper readiness。
- 这只是可信度门禁，不替代样本外、walk-forward、成本敏感性和多数据源验证，也不代表实盘收益。

## 调研校准

| 参考 | 观察 | 对本项目的取舍 |
|---|---|---|
| QuantConnect LEAN | 成熟平台把参数优化、研究、回测和 live 语义放在统一框架下，并强调避免未来函数。 | Open Composer 不能只调一组参数；但也不需要复制整个平台。 |
| vectorbt | 向量化研究适合大规模参数矩阵和多维结果比较。 | 当前先做轻量网格和报告，未来可在研究侧借鉴向量化加速。 |
| Backtrader | `optstrategy` 证明批量组合测试是传统回测框架的基础能力。 | Open Composer 需要 CLI 级参数网格，而不是只靠 Codex 手动改 YAML。 |
| NautilusTrader | 事件驱动 backtest 更接近执行语义。 | 参数筛选先用 Python reference 快速跑，再用 Nautilus 做同构验证。 |
| Qlib | AI/ML 量化需要数据、特征、模型、回测、记录器和实验管理分层。 | LLM feature 不能直接进入执行 loop，必须落为可回放 feature packet。 |
| Bailey / López de Prado 过拟合研究 | 大量试错会抬高过拟合风险，单一最佳收益不是可靠证据。 | 参数扫描报告必须标注 in-sample，promotion 前必须补样本外和 walk-forward。 |

## 本轮新增能力

新增命令：

```bash
uv run oc strategy parameter-sweep strategy_specs/drafts/qqq_pullback_15m.yaml \
  --param risk.stop_loss_pct=0.8,1.0,1.2 \
  --param risk.take_profit_pct=1.5,2.0,3.0 \
  --param costs.slippage_bps=0,5 \
  --max-candidates 27 \
  --top-n 10 \
  --write-top 2
```

支持能力：

- 一次性组合多组参数。
- 支持 scalar 参数：`risk.stop_loss_pct`、`risk.take_profit_pct`、`risk.max_trades_per_day`、`costs.slippage_bps`、`costs.commission_pct`。
- 支持表达式路径：例如 `entry.all.0=close > ema(close, 5)|close > ema(close, 8)`。
- 只允许修改 `entry`、`exit`、`risk`、`costs`、`factors`，不允许扫 `execution`、`broker`、`lifecycle`、`data`。
- 候选策略会强制写成 `draft + manual_signal + broker=none`，避免把研究候选直接变成自动交易策略。
- 生成 `reports/research/<strategy>-parameter-sweep.json` 和 `.md`。
- 可选写入 top N 个 draft specs，默认只写 top 1，避免污染策略目录。
- 复用现有 `backtest_frame`，保留 bar-close confirmation 和 next-bar-open fill assumption。

## 为什么这是正确切口

1. 它补上了用户明确需要的“参数调整时一次性多跑很多组”。
2. 它没有新建执行引擎，符合项目约束。
3. 它把输出落到文件和报告，Dashboard 后续可以读取。
4. 它保留候选上限，避免一次性生成过多运行结果。
5. 它把结果标成 in-sample research，避免把最佳参数误认为可交易证据。

## 多视角审查

### 量化研究视角

通过：参数网格是必要基础能力。

限制：这只是 in-sample 筛选。它不能证明策略稳健，也不能代替样本外、walk-forward、成本敏感性、数据源比较。

### 架构视角

通过：新能力复用 `StrategySpec`、`load_ohlcv_for_spec`、`backtest_frame` 和现有评分逻辑，没有引入新执行路径。

限制：当前仍是顺序执行。后续如果候选数量很大，再考虑 chunking / multiprocessing / vectorized research。

### 风控视角

通过：候选强制保持 draft/manual，不会直接进入 paper。

限制：如果后续 Dashboard 增加参数扫描按钮，也必须显示 in-sample warning，并要求 promotion gate。

### LLM 视角

通过：LLM 可以用来提出合理参数范围、解释结果、总结敏感区间，但不能在回测 loop 内动态改参数。

限制：LLM 推荐的参数范围必须写入审计或报告，不能只存在聊天上下文中。

### 测试视角

通过：本轮测试覆盖了标量网格、表达式路径、禁止 execution path、CLI 输出和 JSON/Markdown 产物。

限制：还需要在全量测试中确认不会破坏现有 optimizer、Dashboard command 和 paper workflow。

## 后续只做这些增强

按照当前个人版边界，后续研究验证只补以下内容：

1. 样本外切分。
2. walk-forward。
3. 成本/滑点敏感性。
4. Alpaca / Longbridge / sample 数据源比较。
5. Dashboard 读取 parameter sweep 报告。
6. LLM 对 sweep 结果做结构化 review summary。

暂不做：

- 完整因子平台。
- 自动机器学习 alpha factory。
- 多资产组合优化器。
- 云端大规模并行优化。
- 自动把最佳参数升为 active/paper_auto。

## 验收口径

本轮能力只在下面条件下算通过：

- `oc strategy parameter-sweep` 可以从 sample data 无凭证运行。
- 参数组合数量受 `--max-candidates` 限制。
- 结果写入 JSON / Markdown。
- top specs 是 draft/manual。
- 研究报告明确 in-sample 和 promotion 前置验证。
- 聚焦测试和全量测试通过。

参考资料：

- https://www.quantconnect.com/docs/
- https://vectorbt.dev/
- https://www.backtrader.com/docu/
- https://nautilustrader.io/docs/latest/concepts/backtesting/
- https://www.microsoft.com/en-us/research/publication/qlib-an-ai-oriented-quantitative-investment-platform/
- https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2326253
