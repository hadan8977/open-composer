# Step 13-F 计划：导入公开因子库并筛选（搜索先行，不重复造轮子）

日期：2026-09-09（周三 14:30 UTC）。执行者：一名无上下文执行代理（F 轨）。本文自足。
上游：`docs/plan-step-13-recent-high-return-ml-and-llm-tracks-2026-09-09.zh.md`（M/L 两轨）、
门槛合同 `config/promotion/recent-regime-high-return-gates-v2.json`。本文是 M 轨的特征供给方。

## 0. 用户要求原话与翻译

用户 2026-09-09：
> 网上应该能一次性获取大量别人分享的因子库之类的吧，你可以节省很多重复造轮子的工作，这是最重要的，
> 多联网搜索而不是自己做。……在网上看论文、帖子、别人分享的 github 项目，由此获取他人分享的因子并
> 测试，可用省去很多挖掘因子的步骤，也可以对这些因子做进一步的优化迭代。

翻译：本轨的产出是**把公开因子库整体搬进特征库并系统筛选**，而不是手写新因子。筛选出的因子集
交给 M 轨的模型（LightGBM 近期窗）和规则基线用；筛选本身按预注册流程记录，避免"几百个因子里挑
最好看的"这种多重检验陷阱。

## 1. 仓库现状（诚实记录）

- `open_composer/research/factor_library.py`：84 个规则因子、20 个族，其中 50 个 `alpha101_*` 是
  2026-05 Step 6 搬的 WorldQuant Alpha101 子集，**只在旧的规则框架里用过，从没进入 Step 11 的
  ML 特征库**（Step 11 手写了 27 列日频特征）。
- `data/features/daily/{year}.parquet`：27 列（`open, close, ret_*, vol_*, beta_252_spy, idio_vol_63,
  max_ret_1_21, dollar_adv_*, amihud_21, dist_from_252d_high, momentum_252_21, *_rel`）+ 20 列日内
  均值（已证明为负，M 轨不用）。行 = (symbol, trade_date)，2016-2026 共 610 万行，宇宙并集 2,721 只。
- 日线原始表 `data/sip/daily/{year}/*.parquet`：Alpaca SIP 日线，字段见 §3.0（执行者先确认有无
  `vwap`/`trade_count`）。没有市值、行业、基本面、分析师数据。

## 2. 搜索结果与来源卡（2026-09-09 联网核实；卡片见 `reports/harness/source_cards/step13f_open_factor_libraries.jsonl`）

| 库 | 内容 | 许可 | 需要的数据 | 本仓库适配 | 备注 |
|---|---|---|---|---|---|
| Qlib **Alpha158**（microsoft/qlib `qlib/contrib/data/loader.py`） | 9 个 K 线形态 + 29 组滚动特征 × 窗口 {5,10,20,30,60} = 158 列 | MIT | OHLCV（+vwap 可选） | **直接可算** | Qlib 官方 CSI300 基准：LightGBM RankIC 0.047、年化 9.0%；AlphaMemo（2026-06）S&P500 2022-2025：Alpha158 RankIC 0.008、年化 14.4%、夏普 0.62 —— 在美股大盘上已衰减 |
| WorldQuant **Alpha101**（Kakushadze 2016, arXiv 1601.00991） | 101 个公式因子 | 论文公开；实现 yli188（859★）、lvlh2/alpha101（PyPI）、py-alpha-lib（BSD-2, Rust） | OHLCV+vwap；约 10 个用到 `cap`/行业中性化 | 可算（无市值/行业的那些按"不中性化"算并在清单里标记） | |
| 国泰君安 **Alpha191**（2017 研报） | 191 个公式因子 | 研报公开；实现 py-alpha-lib（190/191）、Daic115/alpha191、wukan1986/ta_cn | OHLCV+vwap+amount | 可算 | A 股来源，公式与市场无关 |
| **py-alpha-lib**（msd-rs, PyPI） | Rust 实现 Alpha101 全部 + Alpha191 190 个，面板原生（flat 数组 + groups） | BSD-2 | 扁平数组按 (security, time) 排序 | `pip` 轮子；4000 股×261 天 Alpha101 3.9 秒 | 本机（Ivy Bridge，无 AVX2）已验证能否安装，见 §3.0 |
| **KunQuant**（Menooker） | Alpha101 + Alpha158 的 C++ 代码生成器 | Apache-2.0 | [features, time, stocks] 数组 | 需要 AVX/AVX2；本机 CPU 无 AVX2，**不用** | |
| **OSAP** Chen-Zimmermann（openassetpricing.com, OpenSourceAP/CrossSection） | 313 个学术信号，其中 **28 个只用 CRSP 价量** | 代码公开（执行者核对 LICENSE） | 价量（部分需行业/VIX/FF3） | 可算约 20 个：Mom6m, Mom12m, Mom12mOffSeason, MomSeason*, MomOffSeason*, STreversal, LRreversal, MaxRet, RealizedVol, IdioVol3F（用 SPY 残差代替 FF3）, ResidualMomentum（同上）, DolVol, Price, PriceDelayRsq, MomVol, TrendFactor（MA 组合）, CoskewACX, BetaTailRisk；跳过 IndMom/IndRetBig（无行业）、betaVIX（无 VIX 则跳过） | 学术月频因子，我们按日频滚动版实现 |
| **JKP**（bkelly-lab/jkp-data, 153 因子） | 全球因子复现代码 | 公开 | 大部分需基本面 | 价量子集与 OSAP 重合，**只作参考** | |
| Alpha 挖掘：**AlphaGen**（KDD23）、**AlphaForge**（AAAI25）、**QuantaAlpha**（MIT, 2026-02）、**AlphaMemo**（2026-06）、**RD-Agent**（微软） | RL/进化/LLM 生成公式因子 | 各自 | Qlib 数据格式 + 大量 LLM 调用 | **本周不做**，下周 L 轨候选 | AlphaMemo S&P500 2022-2025 最优：年化 23.7%、夏普 1.07、回撤 -23.6% |

近期 regime（JPM Factor Views 3Q26、Morningstar、Counterpoint）：动量因子 2024 +32.9%、2025 +22.1%，
2025Q4 转向价值/小盘，2026 上半年动量再次领先，赢家从超大盘云厂商换成了存储芯片。含义：筛选要看
**近期 IC** 而不只是全样本 IC，且模型要按季重训（M 轨协议）。

对预期的校准（写进报告，不能省）：静态 Alpha158 + LightGBM 在美股大盘近三年接近零超额；2026 年
最好的公开方法在 S&P500 上做到年化 23.7%。我们的 30% 门槛只能靠 (a) 更宽的宇宙（top-1500 含中盘）、
(b) 近期窗重训 + 按近期 IC 刷新因子集、(c) 集中持仓 + 趋势门 三件事叠加；任何一件缺了都不要指望。

## 3. 本周任务（按顺序，每步一个提交）

### 3.0 依赖与数据核对（30 分钟）
- `uv add py-alpha-lib polars`（PyPI 有轮子但**未在本机验证**——协调者的临时 venv 安装被权限拦下；若在项目 venv 里
  失败，退回纯 pandas 移植，Alpha158 无论如何用 pandas/DuckDB 自己算）。
- 核对 `data/sip/daily` 字段：`vwap`、`trade_count` 有无；`amount` = `close × volume`（无成交额字段时）。
- 宇宙：所有表只算 `data/features/universe/` 并集里的 2,721 只（与 daily 表一致），按年落盘，输入窗口
  取 [year-1, year]（与 `scripts/build_daily_features.py` 一样的两年窗），float32，列名小写。

### 3.1 Alpha158 表 → `data/features/alpha158/{year}.parquet`（158 列 + symbol + trade_date）
定义（Qlib loader.py 原文，窗口 d ∈ {5,10,20,30,60}）：
- K 线 9 列：`KMID=(close-open)/open, KLEN=(high-low)/open, KMID2=(close-open)/(high-low+1e-12),
  KUP=(high-max(open,close))/open, KUP2=…/(high-low+1e-12), KLOW=(min(open,close)-low)/open, KLOW2=…,
  KSFT=(2close-high-low)/open, KSFT2=…/(high-low+1e-12)`
- 滚动 29 组：`ROC=close[t-d]/close, MA=mean(close,d)/close, STD=std(close,d)/close, BETA=slope(close,d)/close,
  RSQR=rsquare(close,d), RESI=resi(close,d)/close, MAX=max(high,d)/close, MIN=min(low,d)/close,
  QTLU=quantile(close,d,0.8)/close, QTLD=quantile(close,d,0.2)/close, RANK=rank(close,d)（当日在窗内的分位）,
  RSV=(close-min(low,d))/(max(high,d)-min(low,d)+1e-12), IMAX=idxmax(high,d)/d, IMIN=idxmin(low,d)/d,
  IMXD=(idxmax(high,d)-idxmin(low,d))/d, CORR=corr(close, log(volume+1), d), CORD=corr(close/close[-1],
  log(volume/volume[-1]+1), d), CNTP=mean(close>close[-1], d), CNTN=mean(close<close[-1], d), CNTD=CNTP-CNTN,
  SUMP=sum(max(close-close[-1],0),d)/(sum(|close-close[-1]|,d)+1e-12), SUMN=同理负向, SUMD=SUMP-SUMN,
  VMA=mean(volume,d)/(volume+1e-12), VSTD=std(volume,d)/(volume+1e-12),
  WVMA=std(|close/close[-1]-1|·volume, d)/(mean(|close/close[-1]-1|·volume, d)+1e-12),
  VSUMP=sum(max(volume-volume[-1],0),d)/(sum(|volume-volume[-1]|,d)+1e-12), VSUMN, VSUMD`
- 实现：pandas `groupby(symbol).rolling(d)`（含 `rolling.rank`、`rolling.apply` 只在 slope/rsquare/resi/idxmax
  上用 numpy 闭式解，别用逐行 apply），按 300 只一批（沿用 `build_intraday_daily_features.py` 的分批
  写法）；单元测试：随机 3 只 × 80 天，与直接 numpy 手算对比 `rtol 1e-6`。
- 验收：2025 年表 65 万行 × 158 列 float32 ≈ 410MB 落盘前分批 concat；峰值 RSS < 1.5GB（`run_capped.sh --mem 1.8G`）。

### 3.2 Alpha101 + Alpha191 表 → `data/features/alpha101/`、`data/features/alpha191/`
- 用 py-alpha-lib 的面板接口（flat 数组 + `set_ctx(groups=…)`）；按年 × 全宇宙一次算（2,721 只 × 504 天 ×
  8 字段 float64 ≈ 90MB 输入，输出 191 列 × 137 万行 float32 ≈ 1GB → **按 100 列一批**写临时 parquet 再
  合并，或按 700 只一批）。
- 需要 `cap`/行业中性化的 Alpha101 因子：按库的默认（无中性化）计算，并在
  `data/features/alpha101/MANIFEST.json` 里列出这些 id 与偏差说明；算不出来的 id 记 `skipped`。
- 单元测试：任取 3 个公式（如 alpha001、alpha012、gtja alpha 003）用 pandas 独立实现对照。

### 3.3 OSAP 价量因子表 → `data/features/osap_price/{year}.parquet`（约 20 列）
按 §2 表格的清单，用日频滚动版：`mom6m=ret_126 跳过最近 21 天, mom12m=ret_252 跳过 21 天（= 现有
momentum_252_21，保留以对齐）, mom12m_offseason, momseason_short（去年同月收益）, momseason_2_5
（2-5 年前同月均值）, momoffseason（其余月份均值）, streversal=-ret_21, lrreversal=-(ret_756-ret_252),
maxret=21 日最大日收益, realizedvol_21/63, idiovol_spy_63（对 SPY 回归残差 std）, residualmom_252_21
（残差累计）, dolvol_63, log_price, pricedelay_rsq（周频对 SPY 滞后回归的 R² 差）, momvol
（动量 × 换手率分位的交互）, trend_ma{3,5,10,20,50,100,200}/close, coskew_252, betatail_252（可选）`。
每列在 `open_composer/research/features/osap_price.py` 的 docstring 里写原论文与 OSAP 缩写。

### 3.4 特征集注册 + 面板加载器
- `open_composer/research/features/feature_sets.py`：`FEATURE_SETS = {"daily27": [...], "alpha158": [...],
  "alpha101": [...], "alpha191": [...], "osap_price": [...], "screened_top40_recent": <由 3.5 生成的 json 读入>}`
  与 `resolve_feature_set(name) -> (columns, roots)`。
- `panel.py::load_feature_panel(..., extra_feature_roots: Sequence[Path] = ())`：对每个 root 按
  (symbol, trade_date) **左连接**，只选请求的列，FLOAT 转 float32，缺失保留 NaN（LightGBM 原生处理）；
  单元测试：临时目录里造两张小表验证连接和列选择；现有 3 个测试不得改动。这是本周唯一允许的
  `panel.py` 改动，A/B 两个代理都会调用它。

### 3.5 因子筛选 `scripts/screen_factors.py` → `reports/research/factor_screen/step13f_screen.parquet` + `.md`
预注册协议（先写进本节再跑，不许事后改）：
- 样本：周五调仓日行（`weekly_rebalance_dates`），宇宙 = 当月 PIT top-1500；标签 `label_excess_5`、
  `label_excess_10`（`data/features/labels/`）。
- 每个因子 × 每个标签：按日横截面 Spearman 秩相关（rank IC）序列 → 全样本 2018-2026 与近期窗
  2024-01-02→ 的 `ic_mean, ic_std, icir=mean/std, t=icir·sqrt(n)`, 按年 IC 均值与**符号稳定性**
  （9 个年份里同号的比例），因子秩的周自相关（换手代理），缺失率。
- 多重检验：约 520 因子 × 2 标签 ≈ 1,040 个检验，用 Benjamini-Hochberg q=0.05 在全样本 t 上做 FDR，
  记录通过数；"近期有效、全样本无效"的因子单列一张表（regime 因子），不进 FDR 通过集但供 M 轨
  作为 `screened_top40_recent` 的候选。
- 输出：按近期 ICIR 排序的前 40（同一族里高度相关的只留一个：秩相关 > 0.9 视为重复，保留 ICIR 高者）
  写 `config/feature_sets/screened_top40_recent.json`（含每个因子的 IC 数字与来源库），以及全表 markdown。
- 内存：一次只加载一个库的一年（≤ 8 万行 × 191 列），逐年累积 IC 序列；不要把 520 列全拼一张表。

### 3.6 交接
- 完成 3.4 后立即给协调者发消息（特征集 id、根目录、列数、峰值内存），M 轨会把 `feature_set` 作为
  网格维度：`daily27`、`alpha158`、`screened_top40_recent`（`all_open` 500+ 列只做筛选，不进 M 网格：
  2022 起的周频行 39 万 × 500 列 float32 ≈ 0.8GB，再加 LightGBM 直方图会顶到 1.8GB 上限）。
- 报告章节写进 `reports/research/control/step13-recent-high-return-2026-09.md` 的 "F 轨：公开因子库"，
  并在 `reports/research/control/step13-2026-09-09-progress.md` 逐项加行。

## 4. 时间线
- 周三 09-09 晚：3.0-3.1（Alpha158 表全部年份跑完，约 1 小时计算）。
- 周四 09-10 12:00 UTC 前：3.2-3.4；18:00 前：3.5 筛选 + 交接给 M 轨。
- 周五 09-11：报告章节；若 M 轨用了筛选集，把筛选的多重检验披露放进 M 轨候选的账本记录。

## 5. 纪律
- 重任务一律 `./scripts/run_capped.sh --mem 1.8G -- …`，同一时间本代理只跑一个；DuckDB `memory_limit ≤ 1.5GB, threads=2`；
  A 组代理的新闻抽取和 B 组代理的 M 网格会同时在跑，看到 `free -m` 可用 < 600MB 就等。
- 提交只用路径：`git add <路径>` + `git commit -m … -- <路径>`；禁止 `git add -A`。
- 不读不打印 `.env`；不改 `loop.py`（M 轨代理的）、不改 `open_composer/research/news/`（L 轨代理的）。
- 每张表都要有 `MANIFEST.json`（列名、来源库、公式版本、跳过项、构建时间、行数）。
- 所有搜索到的外部事实追加来源卡到 `reports/harness/source_cards/step13f_open_factor_libraries.jsonl`
  （schema：`open_composer/models/source_card.py`），不要写"据说"。
- 等待循环用 `pgrep -f "build_alpha158_feature[s]"` 这类防自匹配写法。
- 给协调者发消息的时机：3.1 完成、3.4 完成、3.5 完成、任何阻塞。
