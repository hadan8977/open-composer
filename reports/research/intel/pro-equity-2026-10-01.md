# 专业化美股多信号账本：开源组件调研（2026-10-01）

协调码：R1001-0606-TOOLS。撰写时间：2026-10-01 06:05–06:35 UTC。
来源快照：`reports/research/intel/sources/pro-equity-2026-10-01/tooling/`（每源一个文本文件，头部记录 URL 与 UTC 抓取时间；本地试验脚本在 `check-scripts/`，结果汇总在 `local-throwaway-venv-checks.txt`）。
所有版本号/日期来自 PyPI JSON 与 GitHub API/原文，未能核实的写“未找到”。GitHub 星数与“open”数含 PR（API 的 open_issues_count）。

## 1. 结论（逐层推荐）

1. 优化器：直接用 **cvxpy 1.9.3 + Clarabel**（Apache-2.0，随 cvxpy 自带，power cone 与 SOC 均支持）。1500 只、含因子风险、美元/beta/行业中性、持仓上限、半价差 + 3/2 次冲击 + 借券成本 + 换手上限，单次求解约 1 s、峰值 150 MB（本机实测）。
2. 风险模型：**skfolio 1.4.10 的 `CharacteristicsFactorModel`**（BSD-3，2026-08-23 的 1.0.0 引入）是目前唯一维护中的、可在本机跑的 Barra 类库（行业 + 风格因子、截面 WLS、因子协方差 EW/Newey-West、特异方差、事前/事后归因）；统计 PCA 模型用 sklearn `PCA` + 特异方差（10 行），协方差收缩用已装的 sklearn `LedoitWolf`/`OAS`。
3. 验证：**skfolio `CombinatorialPurgedCV`**（固定观测数的 purge/embargo）做组合级 CPCV 路径；需要按“标签结束时间”精确 purge 或 DSR/PBO 时加 **purgedcv 0.1.8**（MIT，单人维护、很新）。mlfinlab 排除（专有许可，PyPI 已 404）。
4. 多期交易与成本：成本公式直接照 **cvxportfolio** 的 `a|x| + b·σ·|x|^{3/2}/√V + c·x`、`StocksHoldingCost` 实现在自己的 cvxpy 循环里；cvxportfolio 本体（GPL-3.0，包内最后一次人工提交 2025-07-06）仅作 ≤300 只的独立交叉校验，N=800 时 20 天回测 106 s、1.85 GB，不适合在本机做主力。Gârleanu-Pedersen 闭式解未找到现成库。
5. 因子分析：**alphalens-reloaded 0.4.6** 在 pandas 2.3.3 下可跑（500×500 实测 2.5 s/300 MB），但依赖 IPython/statsmodels 且固定 pandas<3；IC/ICIR/分位收益/换手本身几行 numpy 即可，alphalens 只作截面分析 tear sheet 与交叉验证，不进核心路径。
6. 绩效/归因：沿用 **quantstats**（已是可选依赖，0.0.86 比 lock 的 0.0.81 新）+ skfolio `MultiPeriodPortfolio`/`realized_attribution`；不引入 vectorbt（1.1.1 要求 pandas>=3.0.3、许可含 Commons Clause）、zipline-reloaded、pyqlib（官方 US 数据集已关闭）。
7. 整套候选（cvxpy、skfolio、cvxportfolio、alphalens-reloaded、statsmodels、purgedcv）与项目现有依赖（含 nautilus-trader==1.219.0、pandas 2.3.3）在 Python 3.11 下 `uv pip compile` 可共同解析；磁盘增量约 412 MB（实测），其中 scs 106 MB 是最大单项。
8. 最大风险：skfolio 5 周内发了 34 个版本（API 变动快，必须钉版本）；其因子模型文档的结果基于 FactSet/RBICS 商业数据，我们的免费数据（SEC EDGAR + 价量）能否撑起同等质量的风险模型未经验证。

## 2. 项目现状（pyproject.toml / uv.lock）

已锁定：numpy 2.4.4、pandas 2.3.3、scipy 1.17.1、scikit-learn 1.9.0、lightgbm 4.6.0（PyPI 最新 4.7.0）、duckdb 1.5.5、nautilus-trader 1.219.0；可选 `workbench` 组：quantstats 0.0.81（PyPI 最新 0.0.86）、mlflow 3.16.0。`.venv` 里另有 polars_lts_cpu 1.33.1，但不在 pyproject/uv.lock 中（临时安装，`uv sync` 可能清除）。
未安装：cvxpy、clarabel、osqp、scs、ecos、statsmodels、numba、skfolio、cvxportfolio、alphalens、pyfolio、empyrical、riskfolio、arch。所以优化/风险模型栈需要新增依赖（本任务未改动 pyproject.toml/uv.lock，由 planner 决定）。
共存性证据：`local-compile-coresolve-with-project-deps.txt`（`uv pip compile --python-version 3.11`，nautilus-trader==1.219.0 同时解析成功，numpy 2.4.6、pandas 2.3.3、scipy 1.17.1）。

## 3. 决策表

“活跃度”= GitHub 最近推送/最新发布；“重量”= 安装体积与重依赖（本机 3.9 GB 内存）。除特别说明外均支持 Python 3.11（requires_python 核实）。

| 包 | 层 | 版本/日期 | 活跃度 | 许可 | 重量 | 适配 | 局限 |
|---|---|---|---|---|---|---|---|
| cvxpy | 优化 | 1.9.3 / 2026-09-19 | 6352★，推送 2026-09-28，184 open | Apache-2.0 | wheel 4.4 MB；依赖 osqp/clarabel/scs/highspy/qdldl/sparsediffpy；scs 单项 wheel 43 MB（装后 106 MB） | 主力：因子风险二次型 + `cp.power(cp.abs(z),1.5)` + 线性等式/不等式；Clarabel 默认可用 | 每次调用重新规范化（实测含编译 0.6–1.2 s）；DPP 参数化可再提速（未测） |
| Clarabel | 求解器 | 0.11.1 / 2025-06-11 | 613★，推送 2026-04-13 | Apache-2.0 | 约 1.1 MiB（uv 下载日志） | SOCP + 幂锥（cvxpy 求解器表标 POW），3/2 冲击项走它 | 内点法，N 很大时单次秒级 |
| OSQP | 求解器 | 1.1.3 / 2026-06-12 | 推送 2026-06-17 | Apache-2.0 | 0.4 MB | 只含二次项与线性成本的 QP，快 | 不支持 SOC，无法表达 3/2 次冲击 |
| SCS | 求解器 | 3.3.1 / 2026-09-05 | — | MIT | wheel 43.2 MB，装后 106+39 MB | 备用/回退（cvxportfolio 默认回退） | 一阶法精度低 |
| ECOS | 求解器 | 2.0.14 / 2024-06-18 | 停滞 | GPLv3 | 0.2 MB | 不推荐 | cvxpy 1.9.3 已不再依赖它；GPL |
| PIQP | 求解器 | 0.6.4 / 2026-08-28 | 近期 | BSD-2 | 2.1 MB | 若冲击项线性化为 QP 可用 | 仅 QP/LP |
| skfolio | 风险模型 + 优化 + CV + 回测 | 1.4.10 / 2026-09-30 | 2454★，推送 2026-09-30，37 open；v1.0.0 起 34 个版本/5 周 | BSD-3 | wheel 1.4 MB；plotly 7.1（41 MB）、cvxpy-base、clarabel、sklearn>=1.6 | `CharacteristicsFactorModel`（Barra 类）、`MeanRisk`（线性成本、`previous_weights`、`max_turnover`、`budget=0`、`linear_constraints="industry==0"`、`add_objective` 加冲击项）、`CombinatorialPurgedCV`、`online_predict` 走前验证、事前/事后归因 | 成本仅线性（冲击/借券“计划原生支持”，当前经 `add_objective`/`add_constraints`）；API 变动极快；权重变量只含当日可投资子集（实测 422/500），自定义项需用 `investable_mask_`；官方因子文档用 FactSet 商业数据，教程用合成数据；时间序列 PCA 因子模型“尚未实现”（官方文档原话） |
| cvxportfolio | 多期交易 + 成本 + 回测 | 1.5.1 / 2025-07-06 | 1292★，包目录最后人工提交 2025-07-06，之后只有策略机器人自动提交（到 2026-04-27）；PR #205–#208 未合并；32 open | GPL-3.0 | wheel 0.4 MB；curl_cffi（38 MB）、matplotlib、cvxpy、scs | `StocksTransactionCost`（a、`pershare_cost`、b·σ·\|x\|^{3/2}/√V、c）、`StocksHoldingCost`（空头借券年化费，默认 5%）、`DollarNeutral`/`MarketNeutral`/`FactorNeutral`/`MaxWeights`/`MinWeights`/`LeverageLimit`/`TurnoverLimit`/`ParticipationRateLimit`、`SinglePeriodOptimization`/`MultiPeriodOptimization`（planning_horizon）、`ProportionalTradeToTargets`、`UserProvidedMarketData`（开盘到开盘收益、美元成交量、开盘价）、`MarketSimulator` | 慢且吃内存（N=800：20 天 106 s、峰值 1.85 GB；N=300：4.8 s/20 天、481 MB）；GPL-3.0（私人研究可用，分发需遵守）；基本停更；默认数据源是 Yahoo/FRED，必须用 `UserProvidedMarketData` 喂自己的数据 |
| Riskfolio-Lib | 优化 | 7.3.0 / 2026-05-31 | 4528★，推送 2026-09-30，14 open；GitHub 无 release（只有 PyPI） | BSD-3 | wheel 0.3 MB，但硬依赖 vectorbt(>=0.28.0)、astropy、statsmodels、arch、networkx、xlsxwriter、pybind11（PyPI requires_dist；vectorbt 又带来 numba/plotly，装后明显更重，并把 vectorbt 的 pandas/plotly 冲突带进来） | 风险因子约束、换手/跟踪误差约束 | 无 3/2 冲击项；依赖链重；功能与 skfolio 重叠 |
| PyPortfolioOpt | 优化 | 1.6.0 / 2026-02-26 | 6070★，推送 2026-07-07，116 open | MIT | 0.1 MB + cvxpy、scikit-base | `transaction_cost(w,w_prev,k)` 线性、L2 正则、行业约束、`market_neutral=True`、LedoitWolf/OAS 收缩封装 | 无因子模型风险项，无冲击项；`market_neutral` 仅限 efficient_risk/return |
| scikit-learn | 协方差收缩/PCA | 1.9.1 / 2026-09-10（项目锁 1.9.0） | — | BSD-3 | 已装 | `LedoitWolf`、`OAS`、`ShrunkCovariance`、`PCA` | 非线性（QIS）收缩没有；见下 |
| statsmodels | 统计检验 | 0.15.0 / 2026-08-27 | 11666★ | BSD-3 | wheel 12.1 MB（装后 53 MB） | Newey-West t 值、WLS 截面回归 | 2847 open（体量大） |
| nonlinshrink | 非线性收缩 | 0.7 / 2019-11-18 | 停滞 | MIT | 极小 | Ledoit-Wolf 解析非线性收缩 | 2019 年后无更新；另一实现 Jebel-Quant/shrinkage 只能从 git 装（未在 PyPI 找到），不如自写约 40 行 QIS |
| alphalens-reloaded | 因子分析 | 0.4.6 / 2025-06-02 | 659★，推送 2025-12-15，14 open | Apache-2.0 | 0.1 MB；IPython(jedi 33 MB)、statsmodels、seaborn、empyrical-reloaded；pandas<3 | IC、分位收益、秩自相关/分位换手（实测可跑） | 近一年只有零星维护；固定 pandas<3；输出是画图导向 |
| pyfolio-reloaded / empyrical-reloaded | 绩效 | 0.9.9 / 2025-06-02；0.5.12 / 2025-06-01 | 推送 2025-12 | Apache-2.0 | pyfolio wheel 6.2 MB，pandas<3 | tear sheet | 与 quantstats 重叠 |
| quantstats | 绩效 | 0.0.86 / 2026-09-27 | 7677★，10 open | Apache-2.0 | 0.1 MB（依赖 yfinance） | 已在可选组 | 只做收益序列层面的统计 |
| purgedcv | 验证 | 0.1.8 / 2026-09-26 | 35★，推送 2026-09-27，2 open；2026-05 才首发 | MIT | 0.06 MB | `CombinatorialPurgedCV`/`PurgedKFold`/`WalkForwardSplit`（按 prediction_times/evaluation_times 精确 purge）、`deflated_sharpe_ratio`、`probability_of_backtest_overfitting`、`reconstruct_paths`、`audit_splitter` | 单人维护、很新；成熟度未知 |
| mlfinlab | 验证 | PyPI 404；GitHub 推送 2023-10-02 | 4937★ | 专有 Hudson & Thames 授权协议（LICENSE.txt 2021-11，订阅制） | — | 排除 | 非开源，仓库只收 issue |
| mlfinpy | 验证 | 0.1.2 / 2024-10-09 | 停滞 | MIT | 要求 numpy<1.27、numba<0.61 | 排除 | 与 numpy 2.4 冲突 |
| timeseriescv / timeseries-cv | 验证 | 0.2 / 2018-09-07；0.1.5 / 2021-12-12 | 停滞 | MIT | timeseries-cv 要求 numpy<2 | 排除 | 已死 |
| pyqlib | 回测/ML 框架 | 0.9.7 / 2025-08-15 | 49086★，推送 2026-09-22，483 open | MIT | 依赖 redis、pymongo、jupyter、gym、mlflow、cvxpy 等 | 只借鉴 Alpha158 特征思路 | 官方数据集“暂时关闭”（README），社区数据源 chenditc 是 A 股；US 只能走 Yahoo collector，issue #1953 报错；自带数据层与我们重复 |
| vectorbt | 向量化回测 | 1.1.1 / 2026-09-26 | 9248★，推送 2026-09-26，140 open | Apache-2.0 + Commons Clause（不得“出售”） | 1.1.1 要求 numpy>=2.4.6、pandas>=3.0.3、numba>=0.66 | 不适合（无横截面中性账本/冲击模型） | 与 pandas 2.3.3、alphalens 固定的 pandas<3 冲突；1.0.0 在 plotly 7.1 下 import 失败（实测） |
| zipline-reloaded | 事件驱动回测 | 3.1.1 / 2025-07-19 | 1949★，推送 2026-01-06，48 open | Apache-2.0 | wheel 12.2 MB；bcolz-zipline、h5py、alembic 等 | 不适合 | 反向拆股等回测正确性 issue（#332，2026-09-23）；需自建 bundle |
| bt / ffn | 配置式回测 | 1.2.3 / 2026-09-12；1.2.2 / 2026-09-17 | 近期 | MIT | 小 | 不适合 | 无成本冲击/中性约束 |
| risk-prism | 风险模型参考 | model-2026-09-28 | 10★，推送 2026-09-28 | MIT | 纯 Python + 周度产物 | Barra 类美股风险模型（9 风格 + 30 行业 + 市场，SEC EDGAR 基本面 + Yahoo 价格），可当免费数据管线样例与交叉校验 | 很新、单人；仅最新周度产物，历史 PIT 一致性未验证 |
| toraniko | 风险模型参考 | v1.1.0 / 2024-08-05 | 976★，推送 2024-08-16 | MIT | numpy + polars | 市场/行业/风格因子收益估计 | 仅 value/size/momentum 三个风格；2 年未更新 |

## 4. 各层首选的最小代码草图

下列片段在 `/tmp` 临时 venv 里实际运行过（`check-scripts/sketches.py` 与 `t_skmr.py`，结果见 `local-throwaway-venv-checks.txt`）。

### 4.1 协方差/风险模型拟合

```python
from sklearn.covariance import LedoitWolf, OAS
from sklearn.decomposition import PCA
lw = LedoitWolf().fit(R)                       # R: T x N 日收益；线性收缩，shrinkage_ 可查
pca = PCA(n_components=K).fit(R)               # 统计 (PCA) 因子模型
F = pca.components_.T * np.sqrt(pca.explained_variance_)      # N x K，因子协方差 = I
d = (R - pca.inverse_transform(pca.transform(R))).var(0, ddof=1)   # 特异方差

# 基本面精简版 Barra：行业 + 风格，截面回归（skfolio 1.4.10）
from skfolio.prior import CharacteristicsFactorModel
from skfolio.factor_exposure import GlobalFactor, OneHotCategoricalFactors, FixedWeightedFactor
from skfolio.descriptor import LogMarketCap
model = CharacteristicsFactorModel(
    factors=[("market", GlobalFactor(family="market")),
             ("industry", OneHotCategoricalFactors(category="industry", family="industry")),
             ("size", FixedWeightedFactor(descriptors=[("log_market_cap", LogMarketCap())],
                                          transform_by_group="industry"))],
    constrained_families=[("industry", None)], exposure_lag=1, n_jobs=1)
model.fit(characteristics=panel)               # panel: skfolio AssetPanel（returns/market_cap/industry…，时点数据）
cov = model.return_distribution_.covariance    # N x N；model.factor_model_.summary() 看因子
```

### 4.2 带中性约束、上限、线性 + 3/2 成本、换手惩罚的优化器（cvxpy + Clarabel）

```python
w = cp.Variable(N); z = w - w0                                  # w0：上期权重
impact = cp.sum(cp.multiply(vol*np.sqrt(book/adv), cp.power(cp.abs(z), 1.5)))   # b·σ·|x|^1.5/√V
risk = cp.sum_squares(F.T @ w) + cp.sum_squares(cp.multiply(np.sqrt(d), w))      # 因子 + 特异
obj = cp.Maximize(alpha @ w - gamma*risk - half_spread*cp.norm1(z) - impact
                  - borrow_daily*cp.sum(cp.neg(w)) - lam*cp.norm1(z))           # lam：换手惩罚
cons = [cp.sum(w) == 0, beta @ w == 0, S.T @ w == 0,            # 美元/beta/行业中性（S: N x 行业 one-hot）
        cp.abs(w) <= 0.02, cp.norm1(w) <= 2.0, cp.norm1(z) <= 0.25,    # 上限、总杠杆、换手上限
        w[np.where(hard_to_borrow)[0]] >= 0]                    # 非 ETB 只能做多
cp.Problem(obj, cons).solve(solver="CLARABEL")                  # N=1500 约 1 s / 150 MB
```

同一问题的 skfolio 写法（因子模型作 prior，行业/风格中性用字符串约束，冲击项用 `add_objective`；`MAXIMIZE_UTILITY` 下自定义项在最大化目标内，所以成本取负号，`+cost` 会报 DCPError）：

```python
mr = MeanRisk(objective_function=ObjectiveFunction.MAXIMIZE_UTILITY, risk_aversion=1.0,
              prior_estimator=model, budget=0.0, max_long=1.0, min_weights=-0.03, max_weights=0.03,
              transaction_costs=0.0005, previous_weights=w0, max_turnover=0.25,
              overwrite_expected_return=lambda w, m: alpha[m.investable_mask_] @ w,
              add_objective=lambda w, m: -cp.sum(cp.multiply(c_imp[m.investable_mask_],
                                                             cp.power(cp.abs(w - w0[m.investable_mask_]), 1.5))),
              linear_constraints=["size == 0"] + [f"{n} == 0.0" for n in industry_names],
              fallback="previous_weights", solver="CLARABEL")
mr.fit(X, characteristics=panel)               # 走前：online_predict(mr, X, warmup_size=..., test_size=21)
```

（`max_turnover` 参数名来自 MeanRisk 签名核实；上面草图里该参数的数值效果未单独测，实测过的是 `previous_weights`、`transaction_costs`、`budget`、`linear_constraints`、`add_objective`、`overwrite_expected_return`。）

### 4.3 多期交易与成本（cvxportfolio，仅作交叉校验）

```python
md = cvx.UserProvidedMarketData(returns=ret_open2open, volumes=dollar_vol, prices=open_px,
                                cash_key="cash", min_history=pd.Timedelta("90d"))
obj = (cvx.ReturnsForecast(alpha_df) - 5.0*cvx.FactorModelCovariance(num_factors=5)
       - cvx.StocksTransactionCost(a=2.5e-4, b=1.0, exponent=1.5) - cvx.StocksHoldingCost(short_fees=3))
pol = cvx.MultiPeriodOptimization(obj, [cvx.DollarNeutral(), cvx.MarketNeutral(), cvx.MaxWeights(0.05),
                                        cvx.MinWeights(-0.05), cvx.LeverageLimit(2), cvx.TurnoverLimit(0.25)],
                                  planning_horizon=3, solver="CLARABEL")   # SinglePeriodOptimization 为实测版本
res = cvx.MarketSimulator(market_data=md, costs=[cvx.StocksTransactionCost(a=2.5e-4),
                          cvx.StocksHoldingCost(short_fees=3)]).backtest(pol, start_time=t0, end_time=t1)
```

实测的是 `SinglePeriodOptimization`；`MultiPeriodOptimization(planning_horizon=3)` 来自源码签名，未单独跑。“朝目标组合分批交易”：库里有 `ProportionalTradeToTargets`（按剩余交易日等比例交易）与带 `planning_horizon` 的多期优化；Gârleanu-Pedersen 闭式解未在任何候选库中找到（需按论文自写）。

### 4.4 Purged / embargoed CV

```python
from skfolio.model_selection import CombinatorialPurgedCV
cv = CombinatorialPurgedCV(n_folds=10, n_test_folds=2, purged_size=H, embargo_size=H)  # H=标签跨度(交易日)
for train_idx, test_folds in cv.split(X):      # test_folds 是 2 个折的下标数组列表（实测 45 个 split、9 条路径）
    ...                                        # LightGBM 等任何 sklearn 风格模型都可套
# 需要按每个样本的标签结束时间 purge，或要 DSR / PBO 时：
from purgedcv import CombinatorialPurgedCV as CPCV2, deflated_sharpe_ratio, probability_of_backtest_overfitting
cv2 = CPCV2(n_splits=10, n_test_groups=2, prediction_times=t_pred, evaluation_times=t_eval, embargo_observations=H)
```

## 5. 本机实测摘要（临时 venv，已与项目 .venv 隔离）

- 全部候选可在 Python 3.11.15 + pandas 2.3.3 + numpy 2.4.6 下 import（vectorbt 1.0.0 除外，plotly 7.1 报错）。
- 优化器：N=500/1000/1500，求解 optimal，耗时 1.2/0.6/0.8 s，峰值 129/140/150 MB（合成数据，只证明可行性与量级，不含任何收益结论）。
- skfolio 因子模型：500×500 拟合 2.7 s / 411 MB；1000 资产×1500 日只含 3 个因子就 8.8 s / 1.38 GB（接近 1.8 GB 上限，完整多风格模型或 1500 只应走 Modal 或降低内存）。
- cvxportfolio：N=80（60 天）4.4 s；N=300（20 天）4.8 s / 481 MB；N=800（20 天）106 s / 1.85 GB。
- 磁盘：基线（numpy/pandas/scipy/sklearn/lightgbm/matplotlib/seaborn）344 MB；加上 cvxpy、skfolio、cvxportfolio、alphalens-reloaded、statsmodels、purgedcv 后 756 MB（+412 MB）。完整试验环境（含 riskfolio、vectorbt、astropy 等）1.1 GB；vectorbt 是被 riskfolio-lib 硬依赖拉进来的。
- 临时 venv `/tmp/tools-check`（1.1 GB）、`/tmp/tools-base`（756 MB）本应在完成后删除，但 `rm -rf` 被权限系统拒绝，两个目录仍在 `/tmp`，需要 planner 或 owner 手动删除；它们不在仓库内，不影响项目 .venv。

## 6. 风险与未知

1. **skfolio API 不稳定**：v1.0.0（2026-08-23）到 v1.4.10（2026-09-30）共 34 个版本；`TimeSeriesFactorModel` 在 1.0.0 已有破坏性改动。必须钉版本并写回归测试；因子模型的 `add_objective` 符号约定、`investable_mask_` 子集坑已踩（见 4.2）。
2. **数据质量决定风险模型质量**：skfolio 因子模型 46 个描述符多数需要时点基本面（账面价值、盈利、分析师预期、空头比例等）。我们只有免费数据：SEC EDGAR（已有 `data/sec/` 未跟踪目录）、价量、SIC 行业码。“基本面精简版”（行业 + 规模/beta/动量/波动/流动性/反转/简单价值）可行，但文档里 58 因子 FactSet 结果不能当作我们能达到的水平。risk-prism（MIT）用同一类免费数据链，可作参照与交叉校验（成熟度很低）。
3. **内存**：skfolio 因子拟合在 1000×1500 已 1.38 GB；1500 只 + 多风格 + 多年历史大概率超过 1.8 GB 上限，需要分块、降频或 Modal。cvxportfolio 在 N≥800 过慢，不应当作回测主力。
4. **许可**：cvxportfolio 是 GPL-3.0，mlfinlab 是专有协议（已排除），vectorbt 含 Commons Clause。当前仓库是 MIT 私人研究，只调用 GPL 库问题不大，但若要分发该仓库需另行评估。
5. **GP 闭式解与 3/2 冲击的原生支持缺失**：skfolio 文档明说“市场冲击与借券成本原生支持在计划中”；GP 闭式没有库。冲击项需自己维护，且参数（b、σ、ADV 口径）要用我们冻结的 10 bp/边成本口径校准，不能直接用库默认值。
6. **alphalens-reloaded 固定 pandas<3**、vectorbt 1.1.1 需要 pandas>=3.0.3：一旦项目升级 pandas 3，它们会互斥。
7. **未验证项**：DPP 参数化后的 cvxpy 求解提速；skfolio `max_turnover` 约束的实际效果；`MultiPeriodOptimization` 实跑；risk-prism 历史构建的时点一致性；skfolio 的 `AlphaForecastEvaluation`（IC 评估，文档列出，未试）；非线性收缩（QIS）的 PyPI 维护实现（只找到 2019 年的 nonlinshrink 与仅 git 的 shrinkage）；Barra CNE5 类 GitHub 仓库面向 A 股，未评估。
8. 本次试验全部使用合成数据，没有任何市场数据或收益结论；也没有改动 pyproject.toml/uv.lock，没有向项目 .venv 安装任何东西。

## 7. 来源清单（均已保存快照，路径相对 `reports/research/intel/sources/pro-equity-2026-10-01/tooling/`）

- PyPI JSON：`pypi-<name>.txt`（cvxpy、clarabel、osqp、scs、ecos、piqp、qpsolvers、cvxopt、cvxportfolio、skfolio、riskfolio-lib、pyportfolioopt、statsmodels、arch、numba、scikit-learn、lightgbm、pyqlib、alphalens-reloaded、alphalens、pyfolio-reloaded、pyfolio、empyrical-reloaded、empyrical、zipline-reloaded、zipline、vectorbt、quantstats、bt、ffn、purgedcv、mlfinpy、timeseriescv、timeseries-cv、nonlinshrink、openbb、pandas-ta、backtrader、portfolio-optimizer）；`mlfinlab-pypi-404.txt`（PyPI 对 mlfinlab 返回 Not Found）。
- GitHub API（仓库/提交/发布）：`gh-<owner>_<repo>.txt`（cvxpy、cvxportfolio、skfolio、alphalens/pyfolio/empyrical/zipline-reloaded、qlib、vectorbt、quantstats、Riskfolio-Lib、PyPortfolioOpt、clarabel.rs、osqp-python、arch、statsmodels、risk-prism、toraniko、skill-risk-model、purged-cross-validation、mlfinlab）；issue 列表：`gh-issues-*.txt`。
- skfolio：`skfolio-readme.txt`、`skfolio-changelog-head700.txt`（CHANGELOG.md）、`skfolio-docs-factor-models.txt`、`skfolio-docs-cpcv-api.txt`、`skfolio-docs-meanrisk-api.txt`、`skfolio-docs-model-selection.txt`、`skfolio-docs-optimization-userguide.txt`（`skfolio-docs-release-notes.txt` 是 404 页面，保留作证）。
- cvxportfolio：`cvxportfolio-readme.txt`、`cvxportfolio-src-costs-py.txt`、`cvxportfolio-src-constraints-py.txt`、`cvxportfolio-src-market_data-py.txt`。
- cvxpy 求解器表：`cvxpy-docs-solvers.txt`。
- 其他：`riskfolio-readme.txt`、`pyportfolioopt-readme.txt`、`pyportfolioopt-src-objective_functions.txt`、`alphalens-reloaded-readme.txt`、`zipline-reloaded-readme.txt`、`quantstats-readme.txt`、`vectorbt-readme.txt`、`vectorbt-license.txt`、`qlib-readme.txt`、`qlib-issue-1953.txt`、`qlib-docs-data-us.txt`、`risk-prism-readme.txt`、`toraniko-readme.txt`、`skill-risk-model-readme.txt`、`jebel-quant-shrinkage-readme.txt`、`mlfinlab-github-license.txt`、`mlfinlab-github-readme.txt`、`mlfinlab-hudsonthames-pypi-index.txt`。
- 本地试验：`local-throwaway-venv-checks.txt`、`local-compile-coresolve-with-project-deps.txt`、`check-scripts/`。
- 搜索（仅作发现线索，不当作已读）：Barra 类开源库搜索、Qlib US 数据状态搜索、Ledoit-Wolf 非线性收缩搜索、alphalens 替代品搜索；结论均以上面的原文快照为准。
