# t20260930_17_model_family_sweep — 纯量价排序换模型族、训练窗、预测周期（Opus 交互主审，2026-09-30 13:48 UTC 写，本步任何新运行之前）

队列任务 T-20260930-17，接手 T-20260929-30。T-30 从 09-29 起标着"交互会话派 Sonnet 在做"，但没有任何产物、进程或 Modal 作业（2026-09-30 13:40 核对 `reports/research/control/modal-ledger.jsonl`、进程表和迭代目录）。

## 为什么有这一步

机主 2026-09-29 问："XGBoost 等其他模型不行吗，多试一些，用最大的努力。"本步用证据回答：

> 同一批数据、特征、目标、股票池和走步切分下，换模型族、训练窗或预测周期，排序能力会不会实质变好？最好的几个格子做成扣成本的只做多组合，能不能过 K1/K2？

纲领（`docs/research-program.zh.md` 主线 D）已把"纯量价 ML 排序"列为否定。本步不是重开主线 D，是回答机主点名的问题，花费上限 $3。

## 已有证据

### 本仓库

- **T-20260928-10 第二次运行**（`reports/research/iterations/t20260928_10_ml_killtest/report.md`、`results_run2_keepna.json`）。B0 是 LightGBM 回归，24 个价量特征，月度形成，目标为 21 日 beta 调整超额收益（同日同成交额五分位内去均值），3 年滚动训练，季度重训，embargo 21。
  - 压力期走步 RankIC 0.0200（t 3.12）；流动性最差三分之一 0.031（t 5.75）。
  - 加上财报、内部人、空头、财报日数据层没有增益（0.018–0.019）。
  - LambdaRank 更差（0.0078）。
- **T-20260928-30**（`reports/research/iterations/t20260928_30_smallcap_ml_book/report.md`）：B0 做成只做多组合，两个版本都没过 K1/K2。
  - V1 对标窗夏普 0.05（基准成本），压力期 0.25；只扣固定 10 bp 时对标窗 0.21–0.33。
  - 年换手 12–17 次。
  - 那次的价差用日线 Abdi-Ranaldo 估计，已知在大盘股上高估 20–60 倍（数据坑 #58）。但固定 10 bp 也不过，所以结论不受这个偏差影响。

### 文献（2026-09-30 13:47 UTC 打开，文本快照在本目录 `sources/`）

- **Gu, Kelly, Xiu 2020**，RFS 33(5) 2223–2273（`sources/gu-kelly-xiu-2020-rfs-ml.txt`，全文）。
  - 个股月度样本外 R²：GBRT 0.34%、随机森林 0.33%、NN1 0.33%，NN3 最高 0.40%；PCR 0.26%，弹性网 0.11%。
  - 四层、五层网络不比 NN3 好。
  - "all methods agree on a fairly small set of dominant predictive signals"：各方法认定的主要信号是同一小组，最强的是价格趋势（反转、动量）。
  - **含义**：非线性模型之间差距小（R² 0.33–0.40），和线性模型差距大；这是 920 个特征、1957–2016 年的数据。换模型族的上限大约是相对 GBRT 两成的改进，不是翻倍。
- **Avramov, Cheng, Metzker 2023**，Management Science 69(5) 2587–2619（`sources/avramov-cheng-metzker-2023-ms-repec.txt`，只有摘要；SSRN 原文页要人机验证）。
  - 深度学习信号的利润来自难套利的股票和高限制套利的时期；剔除微盘股、困境股或高波动时期，利润明显变小。
  - 换手高、仓位极端，按合理交易成本计算后表现进一步变差。
  - 这和 T-20260928-30 的死因一致。

### 先验

- 换模型族大概率只把 RankIC 移动 ±0.005 以内。
- 63 日周期能降换手，但 T-28-30 的对标窗毛收益本来就弱。
- 任何格子过 K1 的先验概率低于 5%。本步的价值主要是给机主一个有证据的答案。

## 数据和切分（阶段 1，全部来自已缓存的数据，只看压力期）

- **面板**：`reports/research/iterations/t20260928_10_ml_killtest/cache/panel_monthly.parquet`。
  - 2016-05-02 → 2023-08-31，302,433 行，月度形成。
  - 股票池同 T-28-10：close ≥ $3，21 日平均成交额 ≥ $100 万，非基金/ETF，含退市股。
- **特征**：B0 的 24 个价量特征（`cache/candidate_B0.json` 的 `feature_columns`），按 T-28-10 `stage_train` 的做法逐日转成百分位秩。
- **缺失值**：只删目标缺失的行，同第二次运行。
  - LightGBM、XGBoost、CatBoost 原生处理缺失。
  - Ridge、MLP 把缺失的秩填 0.5。
- **目标**：
  - h21：面板里的 `target_excess_21`。
  - h63：`kt.build_target(formation, close_sanitized, 63)`，close 来自 `cache/close_wide.parquet`，按 T-28-10 `stage_panel` 同样清洗。
  - **口径核对**：先用 `build_target(..., 21)` 重算 h21，与面板里的 `target_excess_21` 逐行比，最大绝对差 < 1e-9，才可以用 h63。
- **走步切分**：`h02.build_folds`，季度重训，同 T-28-10。
  - embargo：h21 为 21，h63 为 63。做法同 T-28-10：临时改 `h02.EMBARGO_DAYS`，用完还原。
  - 训练窗 W3：3 年滚动（B0）。
  - 训练窗 WX：扩张窗，从数据起点开始用全部历史。
- 只用验证角色的日期算 RankIC，同 T-28-10 的 `run_training_stage1`。

## 网格（24 格，超参数现在写死，不调参）

| 模型族 | 设置 |
|---|---|
| LGBM | `kt.LGBM_REG_PARAMS`（B0 原样），`n_jobs` 按容器核数 |
| XGB | `XGBRegressor(tree_method="hist", max_depth=6, learning_rate=0.05, n_estimators=400, subsample=0.8, colsample_bytree=0.8, min_child_weight=200, reg_lambda=1.0, random_state=20260930)` |
| CAT | `CatBoostRegressor(depth=6, learning_rate=0.05, iterations=400, loss_function="RMSE", rsm=0.8, bootstrap_type="Bernoulli", subsample=0.8, min_data_in_leaf=200, random_seed=20260930, verbose=0)` |
| RIDGE | `Ridge(alpha=1.0)`，缺失填 0.5 |
| MLP | `MLPRegressor(hidden_layer_sizes=(32, 16, 8), activation="relu", alpha=1e-4, learning_rate_init=1e-3, batch_size=2048, max_iter=100, early_stopping=True, validation_fraction=0.1, n_iter_no_change=5, random_state=20260930)`；结构即 GKX 的 NN3；缺失填 0.5，目标在训练集内标准化 |
| ENS | 同一（训练窗, 周期）下前五个模型族的预测，每个形成日转成百分位秩后取均值 |

- 6 个模型族 × 2 个训练窗（W3、WX）× 2 个周期（h21、h63）= 24 格。
- 格子编号 `{LGBM,XGB,CAT,RIDGE,MLP,ENS}_{W3,WX}_{H21,H63}`。
- **B0 复现核对**：`LGBM_W3_H21` 就是 B0。全部 RankIC 必须等于 0.0200 ± 0.0010，否则停下，报"复现失败"，其余格子不解读。
- **去掉 5 日周期**（T-30 原计划有）：已缓存的只有月度面板；T-28-30 的死因是换手，更短的周期换手更高。

## 阶段 1：排序能力（压力期，只报告验证日期）

每格报告：

- 全部 RankIC 均值和 NW t（h21 滞后 0，h63 滞后 2，因为目标重叠三个月）；
- 流动性三分位各自的 RankIC；
- 分年 RankIC；
- 验证日期数；
- 相邻形成日预测秩的相关系数（换手代理）。

**模型族效应**（回答机主的问题，机械计算）：

- 对每个（训练窗, 周期），取最好的非 LGBM 模型族，与同组 LGBM 的 RankIC 差。
- 差值 ≥ +0.010 且该格 t ≥ 3.0，记为"实质改进"。
- `answer_family`：只要有一组是实质改进就写 `material`，否则写 `none`。

**进入阶段 2 的格子**（机械选择，只看压力期）：

- 在除 B0 以外的 23 格里，按压力期 NW t 取前 3。
- 只有 t ≥ 2.0 的格子才能入选：不足 3 个就少选；一个都没有，阶段 2 不做，结论为否定。

## 阶段 2：组合（主审审完阶段 1 后另发简报执行；规则现在写死）

- **预测和组合**：照 T-20260928-30 的做法，只把模型换成入选格子的（模型族, 训练窗, 周期）。
  - 同一全日历预测面板、同一股票池。
  - V1：全池前 50；V2：流动性最差三分位内前 50。
  - 等权，缓冲 150，21 个月度偏移取中位数，单只 ≤ 21 日成交额中位数的 1%，账户 $10 万。
- **成本**：
  - 判定用固定 10 bp/边（基准）和 20 bp/边（压力）。
  - T-28-30 的 AR 价差成本只报告，标明偏高（数据坑 #58）。
  - 理由：小盘股的真实成本不会低于 10 bp/边，所以固定 10 bp 都不过就足以否定。过了也不够，要先用实测 NBBO 价差核对持仓，才能提议模拟盘。
- **K1**：压力期夏普 ≥ 0.65 且对标窗 ≥ 1.19（偏移中位数），并且 20 bp 下两窗年化收益 > 0。
- **K2**：与 S3 同波动对比的组合夏普增量，两窗都 ≥ +0.05。
- 20 个随机排名安慰剂，报告打赢比例。
- 窗口同 T-28-30：压力期、选择窗、对标窗、留出窗（受污染，只参考）。
- **DSR**：试验次数 30，即本步 24 格加 T-28-10 的 4 格和 T-28-30 的 2 个组合。只报告。

## 判定（脚本机械算出，结论由主审下）

- 阶段 1：`b0_parity`（true/false）、`answer_family`（material/none）、`stage2_cells`（0–3 个）。
- 阶段 2：`k1_any`、`k2_any`。
- 总档：
  - `pass_pending_spreads`：任一组合在固定成本下过 K1 或 K2。下一步是实测 NBBO 价差。
  - `refuted`：其余情况。

## 过了 / 没过之后

- **refuted**：给机主的答案是"在这批价量特征和近两年的市场里，排序能力受特征和市场状态限制，不受模型族限制"。
  - 机器学习的算力转向放大已有的信号：如果 T-20260930-14 过了，就用模型组合多个隔夜特征去预测下一晚收益，另写预注册。
  - 纯量价排序不再加格子。
- **pass_pending_spreads**：主审另写"实测价差"任务；再过，才向机主提议。

## 已知偏差

- 阶段 1 只在压力期（2016–2023）。机主关心的近期窗只在阶段 2 看。
- 超参数不调，某些模型族可能吃亏。但 GKX 用了调参，模型族之间的差距仍然很小。
- MLP 用 scikit-learn，不是 GKX 的集成加批归一化版本。
- 面板在 2023-08-31 截止，h63 的最后三个月没有目标。

## 算力

- Modal，每格一个容器：≤ 4 核、≤ 4 GiB、超时 ≤ 60 分钟。每次启动先过 `python3 scripts/modal_budget.py check`，本步合计 ≤ $3。
- xgboost、catboost 只装进 Modal 镜像；本地测试用 `uv run --with xgboost --with catboost`。不改 pyproject.toml、uv.lock。

## 来源

- Gu, Kelly, Xiu (2020) "Empirical Asset Pricing via Machine Learning", RFS 33(5)：https://dachxiu.chicagobooth.edu/download/ML.pdf （全文，2026-09-30 13:47 UTC 经 r.jina.ai 抓取）
- Avramov, Cheng, Metzker (2023) "Machine Learning vs. Economic Restrictions: Evidence from Stock Return Predictability", Management Science 69(5)：https://econpapers.repec.org/RePEc:inm:ormnsc:v:69:y:2023:i:5:p:2587-2619 （摘要，13:47 UTC）；SSRN https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3450322 要人机验证，打不开
- 执行轮补开（档案要求至少 8 个来源）：
  - Grinsztajn, Oyallon, Varoquaux (2022) "Why do tree-based models still outperform deep learning on tabular data?", NeurIPS Datasets & Benchmarks：https://arxiv.org/abs/2207.08815
  - Chen, Pelger, Zhu (2024) "Deep Learning in Asset Pricing", Management Science：https://arxiv.org/abs/1904.00745
  - LightGBM、XGBoost、CatBoost、scikit-learn MLPRegressor 的官方文档
- 本仓库：
  - T-20260928-10：`reports/research/iterations/t20260928_10_ml_killtest/report.md`
  - T-20260928-30：`reports/research/iterations/t20260928_30_smallcap_ml_book/report.md`
  - 纲领主线 D：`docs/research-program.zh.md`
  - 数据坑 #58：`docs/data-layer-pitfalls-and-capabilities.zh.md`

---

### Hypothesis

在 B0 的数据、特征、目标和走步切分下，XGBoost、CatBoost、Ridge、MLP（NN3 结构）或它们的秩均值集成，都不会让压力期 RankIC 比同组 LightGBM 高出 0.010 以上。63 日周期和扩张训练窗也不会让最好的组合在对标窗过 K1。这是本步的零假设。

### Failure mode

如果某个模型族抓到了 LightGBM 漏掉的交互，它的 RankIC 会高出 0.010 以上且 t ≥ 3。或者 63 日周期让换手降到可承受的水平，使组合在固定 10/20 bp 下过 K1 或 K2。

### Measurement

- 阶段 1：24 格的压力期走步 RankIC、NW t、三分位、分年、换手代理，以及 B0 复现核对。
- 阶段 2：前 3 格的 V1/V2 组合在固定 10/20 bp 下的 K1/K2、安慰剂、DSR。

### Stop/Pivot criterion

- `refuted`：关闭"换模型族"这个问题，机器学习转去放大已有信号。
- `pass_pending_spreads`：先做实测 NBBO 价差任务，再决定是否提议。
- B0 复现失败：停下，查差异，不解读其余格子。
