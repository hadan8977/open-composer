# Chart-image CNN (JKX I20/R5) kill test —— 修复渲染瓶颈后的完整结果

方向档案：`reports/research/harvest/directions.jsonl` 行 `dir:chart_image_cnn_jkx_replication`。
代码：`scripts/modal_cnn_chart.py`（本次重写，模型/universe/label/周期/组合规则/kill 判定线均未改动）。
原始结果：`reports/research/iterations/cnn_chart_i20r5_2026-09-28/results.json`（`modal volume get oc-data reports/cnn_i20r5/full_result.json`）。

**结论：FAIL（否定）。** 2021–2023 kill 窗口 decile10-universe 超额收益 Newey-West t = **-1.18**（要求 ≥2），
top-decile 10bp 净夏普 **-0.65** 低于 universe 等权夏普 **0.02**（要求更高）。2020、2024+ 两个对照窗和三个流动性
分层同样没有信号；5 个调仓日偏移的净 10bp 夏普中位数为 **-0.16**（5 个偏移全部为负）。

## 数据调整核查

本仓库 SIP 日线是 split-adjusted：NVDA 2024-06-10 10:1 拆股当天 open/close/volume 连续，仅 high 出现一次
明显坏点（high=195.61，而当天 open/close 都在 ~120 附近）。渲染代码对每日 intraday 极值做了 clamp（限制在
当天 open/close 的 ±15% 以内），避免这一个坏点主导整张 20 日图的 min-max 缩放（见 `scripts/modal_cnn_chart.py`
`_load_panel` 里的注释和实现）。除这一个已知坏点外未发现其他拆股/派息导致的不连续。

## 本次修复了什么（不改变模型/标签/universe/周期/组合规则/kill 判定线）

第一次跑（今天早些时候）训练在 GPU 上 45 分钟内收敛（epoch 29 早停，best val loss 0.6632 vs 随机猜测 0.693），
但随后的 OOS 推理花了 80 分钟，撞到 120 分钟超时，训练权重从未落盘，全部结果丢失（≈$2.45）。原因：OOS 推理按
~1,700 个交易日循环，每天对 ~4,000 个不同 symbol 各自调用一次渲染（≈680 万次几乎单行的调用），而训练阶段之所以
快是因为训练样本本来就按 symbol 分组渲染。

修复：拆成 `train`（渲染训练图、训练、**立即**把 state_dict/像素均值方差/训练历史存到 volume 的
`models/cnn_i20r5/full/` 并 `volume.commit()`）和 `oos`（读取该 checkpoint，用一次向量化 filter+join 取出全部
OOS 行 —— 每个交易日恰好属于 5 个调仓日偏移之一，一次性覆盖 2020-01-01 到最新交易日 —— 按 symbol 排序后切成
~20 万行一块的 chunk，一个 symbol 的全部 OOS 历史至多 ~1,700 行、必落在同一个 chunk 里，因此仍然是"每个 symbol
一次批渲染调用"，只是现在这一次调用覆盖它全部 OOS 历史而不是一天一行；每个 chunk 由 15 个 fork 出的 worker
进程并行渲染，GPU 按 8192 一批做推理，渲染完立刻写 parquet 到 volume 并 commit，超时不会再丢已完成的工作，
重跑会跳过已经在 volume 上的 chunk）。`bench`（纯 CPU，$0.01 量级）在真实启动前先测量了渲染吞吐并做了预测。

## Modal 耗时与花费

| 阶段 | 容器 | 实际耗时 | 备注 |
|---|---|---|---|
| smoke（train→save→oos，玩具子集） | CPU 2 核 6GiB | 34s | n_oos_predictions=960，与修复前的旧 smoke 基线完全一致，确认新流水线正确性 |
| bench（渲染吞吐预测） | CPU 8 核 8GiB | 102s | 4,985 行/秒（15 worker），预测全量 OOS 22.7 分钟，`fits_45min_budget=true` |
| train | T4 8核 32GiB | 2428.2s = 40.5 分钟 | epoch 1–29 loss 曲线与今早丢失的那次完全一致（同一随机种子），best_val_loss=0.6632，`stopped_for_time=false` |
| oos | T4 8核 32GiB | 785.2s = 13.1 分钟 | 38 个 chunk、7,436,061 行，实测 9,900+ 行/秒（远快于 bench 的保守预测），远低于 45 分钟目标和 60 分钟超时 |

本次任务总花费（smoke+bench+train+oos 实际用量）≈ **$1.1**，加上今天早些时候丢失的第一次尝试 ≈$2.45，
本次任务合计 ≈ **$3.55**（Modal 月度账本 `python3 scripts/modal_budget.py status`：本月累计 billed ≈$4.33，
projected ≈$9.17，远低于 $25 上限）。

## 训练

train_n=413,128, val_n=177,055（70/30 split，来自 590,183 条训练池样本，2016-03-01→2019-12-31）。
GPU（T4，mixed precision）；epoch 1 val_loss=0.7004 → epoch 24 达到最优 val_loss=**0.6632**（vs 随机猜测的
ln(2)≈0.6931）→ 之后连续 5 个 epoch 未再改善，epoch 29 早停。验证损失只比随机猜测好一点点，训练阶段
就已经能看出这个二分类信号很弱。

## OOS 结果（长仓 top-decile,按 5 个调仓日偏移取中位数;10bp/边)

全部 3.5 年 OOS（2020-01-01 至 2026-09-25）共 7,436,061 条预测，5 个偏移（offset 0–4，覆盖全部交易日）都跑了。

| 窗口 | n周 | top-decile 净10bp 年化/夏普/回撤 | top-decile 净20bp 年化/夏普 | universe 等权 年化/夏普 | SPY 买入持有 年化/夏普 | excess 均值(周) | excess NW-t | rank IC 均值 | rank IC NW-t | top-decile 单边换手 |
|---|---|---|---|---|---|---|---|---|---|---|
| 2020 | 50 | 18.6% / 0.77 / -21.2% | 8.5% / 0.44 | 33.9% / 1.15 | 37.3% / 1.45 | -0.076% | -0.73 | 0.0090 | 1.00 | 88.2% |
| **2021–2023（kill 窗口）** | 151 | **-13.3% / -0.65 / -46.6%** | -20.9% / -1.12 | -1.4% / 0.02 | 9.1% / 0.60 | **-0.076%** | **-1.18** | -0.0019 | -0.34 | 89.1% |
| 2024-01-08→最新(2026-09-16) | 135 | -2.5% / -0.13 / -14.9% | -10.9% / -0.80 | 11.0% / 0.85 | 20.6% / 1.64 | -0.081% | -1.44 | 0.0008 | 0.14 | 88.5% |

**5 个调仓日偏移的净10bp夏普（不挑日子）：** offset0=-0.177, offset1=-0.167, offset2=-0.159, offset3=-0.149,
offset4=-0.041 → **中位数 = -0.159**（全部 5 个偏移都是负夏普，不是挑到了一个坏日子）。

**流动性三分位（top-decile,净10bp)：**

| 窗口 | 低流动性 | 中流动性 | 高流动性 |
|---|---|---|---|
| 2020 | 0.74 | 0.71 | 0.84 |
| 2021–2023 | -1.06 | -0.63 | -0.20 |
| 2024+ | -0.13 | -0.15 | -0.15 |

三个分层在 kill 窗口和 2024+ 窗口全部为负夏普，且和总体一致（不是低流动性单独拖累）。

## Kill 判定

规则：`decile10_minus_universe_excess_t>=2 AND long_only_top_decile_net_10bp.sharpe>universe_equal_weight.sharpe`
（2021–2023 窗口）。

- excess t = **-1.176**（远低于 2.0 的门槛，方向还是负的）
- top-decile 净10bp 夏普 = **-0.648** < universe 等权夏普 **0.025**

**两条都不过 → FAIL / 否定。** rank IC 在三个窗口都在 ±0.01 以内、t 统计量都不显著（|t|<1.5），说明这个 CNN
在本仓库的 SIP 日线上，用独立复现仓库的图像布局和 JKX 的模型结构，没有产生可用的横截面排序信号——不是"信号太弱
没抗住成本"，而是训练阶段 val loss 就只比随机猜测好一点，OOS 里跨三个窗口、跨流动性分层都测不出正的、显著的
排序能力。

## 下一步

- 该方向按预注册的分档标准写为 `refuted`（不满足冻结的 kill 判定）。发表论文和独立复现仓库(MIT license)在美股
  2001–2019/中国市场上的结果依然成立，但这两条证据都没有覆盖本仓库自己的 2020+ 美股窗口——本次是该方法首次在
  这个窗口、这批数据上跑出的直接证据，负面。
- 若要重新打开：需要新的、可指认的信息（例如不同的图像编码/更长历史窗口 I60、或不同的训练窗口/更大模型)，而不是
  重跑同一配置。
- 渲染流水线的修复（train/oos 拆分 + checkpoint + 分块并行渲染 + 断点续跑）本身是可复用的基础设施，为将来任何
  基于图像的 CNN 方向节省了这次踩坑的成本。
