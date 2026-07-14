# Step 9.N：AI 因子与横截面 ML 扩展

## 1. 目标

在 `mom_multiasset_r1` 与 `mom_multiasset_ml_r1` 的真实负面结果上继续研究，不扩大旧模型超参数，而是重构 AI 辅助量化方法：建立可审计的公式因子库、train-only 因子筛选、横截面 learning-to-rank、模型/规则集成、市场状态门和不确定性 abstention。最终只把具有稳定增量或明确诊断价值的策略加入隔离虚拟盘。

## 2. 不可违反的边界

- 活跃 spec、`.env`、broker、paper order 和真实资金路径零改动。
- LLM 仅作为离线研究编译器，产出静态公式、来源和哈希；不参与实时选股。
- 所有价格量因子使用 `index-1` 或更早数据；标签为未来 21 个 open-to-open 交易日。
- 训练按周频截面增加市场状态样本，组合评价保持月频；随机行切分禁止。
- 每折训练集在测试开始前执行完整 21 日 label purge 和不少于 21 日 embargo。
- 因子筛选只能读取该折训练集；测试折和历史 challenge 不得参与选因子。
- 本轮历史末段已在上一轮被观察，不再称为 pristine lockbox；正式证据从 `2026-07-14` 冻结 epoch 的 forward virtual paper 开始。
- 总候选最多 24 个，全部进入 append-only trial ledger；不新增依赖。

## 3. Wave N.0：外部研究与 AI 因子合同

1. 复核 Qlib Alpha158、Gu-Kelly-Xiu、Deep Momentum Networks、AutoAlpha、AlphaGen、R&D-Agent(Q)、AlphaBench 和 LightGBM ranking。
2. 形成静态 `factor-proposals.json`，每个 AI 公式记录公式、经济含义、来源、输入字段、lookback、方向、生成者、输入哈希和 prompt 哈希。
3. 因子组：多尺度趋势/反转、波动/尾部风险、流动性/量价、横截面残差、趋势质量、AI 非线性交互、市场状态。
4. 运行 `oc research iteration validate mom_multiasset_ai_r2 --stage pre-backtest`，失败禁止训练。

## 4. Wave N.1：样本、筛选与模型

1. 每 5 个交易日产生训练截面，每 21 个交易日产生组合评价截面。
2. 每折按训练期 rank-IC、覆盖率和相关性去冗余选择因子；记录每折入选因子，不生成全样本统一名单后回填历史。
3. 候选模型覆盖 ElasticNet、LightGBM regression、LightGBM LambdaRank、Extra Trees，以及确定性 12-1 与模型分数的离散 blend。
4. AI 角色覆盖 return ranking、rule-model blend、regime switch 和 ensemble disagreement abstention。
5. 同模型必须比较 core-only、expanded-quant 和 AI-formula 特征，形成 marginal-lift 与 missing-AI-factor fallback 证据。

## 5. Wave N.2：裁决与虚拟盘

历史 walk-forward 候选至少满足：四折中三折增量为正、最近两折不同时失败、成本后总收益和 mean rank-IC 至少一项优于确定性基线且另一项不显著恶化。AI contribution 只有在 AI 特征版本稳定优于同模型 core-only 版本时才通过。

通过门的候选可作为 `ai_research_challenger` 加入隔离虚拟盘；未通过者只能保持 diagnostic。所有新 sleeve 继续 `draft/manual_signal/broker=none/requires_order=false`。

## 6. Wave N.3：验收

运行：

```text
uv run ruff format .
uv run ruff check .
uv run pytest -q
uv run oc repo check --strict
make verify
```

最终必须分别报告 `workflow_pass`、`research_pass`、`llm_contribution_pass` 和 `paper_ready_pass`，不得把历史 challenge 或工作流成功表述成已证实 Alpha。
