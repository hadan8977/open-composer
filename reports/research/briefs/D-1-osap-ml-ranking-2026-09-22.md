# Brief D-1：Open Source Asset Pricing 特征库 → 截面 ML 排序（候选 H-20260922-06，轨道 D）

执行者：Codex（工程部分）→ Opus（建模与评估）。读本文件、`reports/research/intel/I-20260922-03-giants-census.md` E 组、工厂计划第 1、2、6 节、`reports/research/hypotheses/H-20260917-02-broad-universe-ml-ranking.md`（其目标/切分设计沿用，特征换成 OSAP）。

巨人：Chen & Zimmermann《Open Source Cross-Sectional Asset Pricing》，209 个已发表特征的月度个股宽表，v2.0.0 覆盖至 2024-12，PyPI `openassetpricing`；Gu-Kelly-Xiu 2020 证明多信息源截面 ML 的样本外增量来自全市场 + 多特征，不是价量。

## 工程（Codex，先做，不需要模型额度）

1. `scripts/fetch_osap.py`：用 `openassetpricing` 包（或官方 release 链接）下载个股月度特征宽表与 SignalDoc 到 `data/raw/osap/v2.0.0/`；记录版本、发布日、覆盖月份、行数、列数、许可；不进仓库（gitignore），写 `data/raw/osap/README.md`。
2. **标识对齐（09-22 已探明口径）**：`openassetpricing` 包可用（本机 CPU 无 AVX2，必须 `polars-lts-cpu` + `POLARS_SKIP_CPU_CHECK=1`）；`OpenAP().dl_signal('pandas',[acronym])` 返回 `permno, yyyymm, value`，覆盖 1926-11→2024-12，28,065 个 permno；SignalDoc 已存 `data/raw/osap/signal_doc.parquet`（212 个 Predictor：Accounting 99、Price 45、Analyst 18、Trading 13、Other 12、Options 9、13F 8、Event 8）。**没有 ticker/CUSIP，也没有月收益**。做法：用**信号匹配**建交叉表——对本地日线里 2016-01→2024-12 每个代码每个月末自算 Mom12m、Mom6m、DolVol、ShareVol（按 SignalDoc 定义），与 OSAP 同名信号按 permno 做时间序列匹配（≥ 24 个月、四个信号相关系数均 ≥ 0.98 才算命中；一对多或冲突写 `ambiguous`），方法与 `scripts/detect_delisted_aliases.py` 的收益匹配同源。输出 `data/features/osap_crosswalk.parquet`（permno, ticker, first_month, last_month, n_months, match_score）与覆盖率报告。月度收益标签用本地日线算，不依赖 CRSP；因此训练样本只能是 2016 年起（本地日线起点），切分改为训练 2016–2021、验证 2022、测试 2023-01→2024-12。
3. **可实盘子集**：把 209 个特征分三类并写成 `config/osap_live_subset.json`：(a) 纯价量、可由本地日线按原文定义重算；(b) 需要财务数据、可由 SEC XBRL Financial Statement Data Sets 近似；(c) 需要 CRSP/IBES/其它，不可算。给出每类计数与前 40 个 (a)+(b) 特征的定义引用（SignalDoc 行）。
4. 与本地日线对齐：把 OSAP 月末与 `data/sip/daily` 的次月收益对齐（用交叉表），生成 `data/features/osap_panel/{year}.parquet`（permno, ticker, month_end, 特征…, fwd_1m_excess, fwd_3m_excess），报告对齐率。

验收：交叉表覆盖率 ≥ 80%（按 2016 年后的 permno-月）；(a)+(b) 子集 ≥ 40 个特征；全部有单元测试（小样例）；一个 commit。

## 建模与评估（Opus，工程验收后）

- 卡 `H-20260922-06-osap-cross-sectional-ml.md`（上一环 H-20260917-02），iteration `h20260922_06_osap_ml`，direction-review 引用 OSAP 与 GKX，过 direction-check 与 iteration validate。
- 目标：次月超额（剔除市场与规模组均值）；备选 3 月。切分：训练 2005–2018、验证 2019–2021、**测试 2022-01→2024-12（OSAP 数据终点，不再往后）**；隔离 1 个月。
- 模型：LightGBM 回归与 LambdaRank（按月分组）、岭回归基线；特征三档：(a) 只用可实盘子集 40；(b) 全部 209；(c) 价量类 only（对照，回答"文献 ML 的增量是不是来自非价量特征"）。≤ 9 个单元。
- 组合：前十分位等权 long-only；同时报多空。成本 10/20 bp，月频。安慰剂：标签在月内随机重排 ×20；特征列随机置换 ×20。
- 判定（测试段 2022–2024）：long-only 前十分位年化 ≥ 30% 且夏普 ≥ 1.2 且打赢 SPMO 同期；(a) 子集不能明显弱于 (b)，否则实盘不可行；(c) 必须明显弱于 (a)，否则说明特征没带来文献声称的增量。
- 通过后：用 (a) 子集在本地日线 + XBRL 上重算 2025-01→今的特征，做 2025–2026 的真前向检验（这是 OSAP 数据没覆盖的段，最干净），再决定是否上模拟盘。

约束：不改门槛；不跑全量 pytest；长任务走 run_capped；OSAP 数据与交叉表不进仓库；结果文件 `reports/research/briefs/D-1-result.md`。
