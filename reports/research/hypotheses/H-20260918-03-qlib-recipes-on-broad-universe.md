# H-20260918-03 直接照搬别人已发表的模型配方（Qlib LightGBM-Alpha158 / DoubleEnsemble）跑我们的宽池子

- 状态：on hold（2026-09-21 口径复核；原 2026-09-18 approved，不代表现已可训练）· 假设族：ml_ranking_broad（与 H-20260917-02 同族，合计预算 6）· 前置依赖：D-20260917-01（宽池子）、Alpha158 等因子表在宽池子上重建、标签/成交/特征语义核对
- 触发：用户 2026-09-18「不要完全从零开始做策略，站在巨人的肩膀上」。

## 我们要照搬什么（原封不动，不调参）

微软 Qlib 的 `examples/benchmarks` 是公开的、带基准数字的配方库。它自己在 CSI300 + Alpha158 上报告（20 个随机种子的均值）：

| 配方 | IC | ICIR | Rank IC | Rank ICIR |
|---|---:|---:|---:|---:|
| LightGBM（Alpha158） | 0.0448 | 0.366 | 0.0469 | 0.388 |
| DoubleEnsemble（Alpha158） | 0.0521 | 0.422 | 0.0502 | 0.412 |

LightGBM 超参（原文 `workflow_config_lightgbm_Alpha158.yaml`）：`loss=mse, learning_rate=0.2, colsample_bytree=0.8879, subsample=0.8789, lambda_l1=205.6999, lambda_l2=580.9768, max_depth=8, num_leaves=210`。
DoubleEnsemble（`workflow_config_doubleensemble_Alpha158.yaml`）：`base=gbm, num_models=3, enable_sr=True, enable_fs=True, alpha1=1, alpha2=1, bins_sr=10, bins_fs=5, decay=0.5, sample_ratios=[0.8,0.7,0.6,0.5,0.4], sub_weights=[1,1,1], epochs=28`，子模型超参同上。
组合规则也照搬它的 `TopkDropoutStrategy`：`topk=50, n_drop=5`（每期只换 5 只，换手远低于"每期重建前 10%"）。

**我们已经有 Alpha158 的实现**（`scripts/build_alpha158_features.py`，源卡注明来自 qlib `Alpha158DL`，154 个因子），所以这是"同一套特征 + 同一套超参 + 同一套组合规则"，只换数据：美股宽池子 2016–2026，而不是 CSI300 2008–2020。

## 一句话假设

把 Qlib 这两个配方原封不动搬到美股宽池子上，样本外（滚动、每季重训）的 Rank IC 能达到它在 CSI300 上报告的量级（0.04–0.05），且 `topk=50, n_drop=5` 的组合在 2024-01 起的窗口里，年化和最大回撤至少在一个维度上优于 SPMO（34.7% / -20.1%）。

## 设计

- 特征：`data/features/alpha158_broad`（154 列）为主；另外报一版加上已筛出的跨库 top-40（`config/feature_sets/screened_top40_recent_broad.json`）与内部人/13D/空头列的版本，回答"多加这些层有没有增量"。
- 标签纠正（2026-09-21）：Qlib 的 `Ref($close,-2)/Ref($close,-1)-1` 是 t+1 **收盘**到 t+2 **收盘**，官方示例 `deal_price: close`。旧文“开盘到开盘且等价”是错误的。本地 open/open 可作为执行适配，但必须明确登记为改动；不得冒充原配方复现。本地 154 列与完整 Alpha158、预处理和 DoubleEnsemble 近似也必须逐项披露。修复分片不自动授权原六单元开跑，训练前重做方向检查并核对冻结清单。依据：`reports/research/intel/I-20260921-01-profit-first-direction.md` 第 3 节。
- 切分：滚动，训练 3 年、验证 1 季、隔离 21 日、每季重训（与 H-20260917-02 一致，便于对比）。
- 模型：(1) Qlib LightGBM 超参；(2) DoubleEnsemble；(3) 我们自己的 ridge 基线（已有）。每个 × 2 个标签 = 6 个单元，正好是本族预算。
- 组合：TopkDropout(50, 5) 为主，等权；另报"前 10% 等权"以便和 H-20260917-02 对齐。
- 对照与诚实性：同尺寸随机、动量孪生、内部人孪生、SPY/IWM/SPMO；打乱标签占位 ≥ 5 个种子；每个单元报验证集与测试集的 Rank IC、ICIR、以及按层的特征重要性。

## 否定条件

测试集 Rank IC < 0.02，或打乱标签占位达到真实的 50%，或 `topk=50` 组合在 2024 年起的窗口两个维度都输给 SPMO 且同波动超额 ≤ 0。

## 备注：为什么不直接装 Qlib

Qlib 需要它自己的二进制数据格式和一套 provider；把 10 年美股塞进去的转换成本、以及它对 torch 的依赖（本机没有 torch，内存 3.9GB）都不值得。我们只借它的**配方**（特征定义、超参、组合规则、基准数字），执行仍用本地已有的管道。下一步要借的是 AlphaForge（AAAI'25）的"动态组合因子权重"和 AlphaGen/AlphaSAGE 的公式化因子挖掘搜索空间——那是另一张卡。
