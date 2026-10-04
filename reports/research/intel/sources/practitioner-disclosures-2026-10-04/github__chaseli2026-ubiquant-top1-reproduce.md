# github__chaseli2026-ubiquant-top1-reproduce
URL: https://github.com/chaseli2026/ubiquant-top1-reproduce
Fetched: 2026-10-04 18:20 UTC (text only, tags stripped)

GitHub - chaseli2026/ubiquant-top1-reproduce: Reproducing the 1st-place solution of Kaggle Ubiquant Market Prediction (LGBM + time_id mean features). · GitHub

 Skip to content

Navigation Menu

Sign in
Appearance settings

Search/

Sign inSign up
Appearance settings

 You signed in with another tab or window. Reload to refresh your session.
 You signed out in another tab or window. Reload to refresh your session.
 You switched accounts on another tab or window. Reload to refresh your session.

Dismiss alert

{{ message }}

 chaseli2026

 /

 ubiquant-top1-reproduce

 Public

 Notifications
 You must be signed in to change notification settings

 Fork
 0

 Star
 0

main

BranchesTags

Go to fileCode
Open more actions menu

Latest commit

History1 Commit

1 Commit
Folders and files
NameName
Last commit message
Last commit date

reproduce/results

reproduce/results

.gitignore

.gitignore

README.md

README.md

convert_to_notebook.py

convert_to_notebook.py

explore_data.py

explore_data.py

explore_report.txt

explore_report.txt

pytorch-template-transformer-data-augmentation.ipynb

pytorch-template-transformer-data-augmentation.ipynb

requirements.txt

requirements.txt

ubiquant_top1_reproduce.ipynb

ubiquant_top1_reproduce.ipynb

ubiquant_top1_reproduce.py

ubiquant_top1_reproduce.py

verify_report.txt

verify_report.txt

verify_stats.py

verify_stats.py

verify_stats.txt

verify_stats.txt

verify_structure.py

verify_structure.py

思路.txt

思路.txt

View all files

Repository files navigation

Ubiquant Market Prediction — 第 1 名方案复现

在 Kaggle Ubiquant Market Prediction 赛题上，复现冠军方案的核心部分（LGBM + 100 个 time_id 横截面均值特征），并给出本地可复现的量化结果。

一句话结论：LGBM baseline 在 250 期 out-of-time 测试集上取得 official score 0.1169；冠军的 +100 个 time_id 均值特征在本机（16GB 内存 / 无独显）可用数据规模下 未带来提升（0.1163 → 0.1141，-1.9%），且 ICIR 从 1.48 降到 1.23。详见 关键发现。

1. 赛题与评价口径

任务：用 300 个脱敏特征 f_0 ~ f_299 预测 target（与交易决策相关的模糊指标）。

面板结构：3,141,410 行 = 1,211 个 time_id × 3,579 个 investment_id，非平衡面板（每期 2,000~3,438 只）。

官方指标（已在 Kaggle 官方页核实）：

score = mean over time_id [ pearson(pred_i, target_i) ] # 每期截面算一次，再跨期取算术平均

提交机制：Kaggle Time Series API —— 提交 notebook 后由后端逐 time_id 推送未见数据，防前视。真实测试集永不落盘，且官方数据已下架，本仓库用的是社区镜像 robikscube/ubiquant-parquet，其中不含 test。

2. 本地切分（严格按时间，绝不随机切）

段
time_id
期数
行数
占比

train
0 – 849
841
1,974,893
62.9%

val
850 – 969
120
364,243
11.6%

test
970 – 1219
250
802,274
25.5%

选 250 期作 test 的依据：指标是跨期 IC 的均值，精度由期数而非行数决定，标准误 ≈ std(单期 IC)/√T。250 期下 SE ≈ 0.004，足以分辨 0.005 量级的模型差异。

3. 冠军方案要点（摘自 思路.txt）

项
冠军做法
本仓库复现情况

模型
LGBM(5-fold KFold 平均) + TabNet(5-fold) 融合
✅ LGBM 部分；❌ TabNet（本机无 NVIDIA 独显，见 硬件限制）

特征工程
300 原始 + 100 新增（|corr| top100 特征的每期横截面均值）
✅ 完整复现

特征选择
corr.iloc[3:103]（跳过 target 自身与最强前 2 个）
✅ 完整复现

数据采样
拼接后取最后 240 万行
⚠️ 受内存限制取 50–80 万行

训练
KFold + 限制轮数 + early stop，loss=rmse，eval=pearson
✅ 单模型 + early stop；⏸ KFold 集成受内存所限未跑

4. 复现结果

全部为 test 段（time_id 970–1219，250 期）上的官方指标：

实验
训练行数
rounds
official_score
IC 标准差
ICIR
IC>0 占比
t 值

baseline（300 原始特征）
800,000
200
0.116915
0.0792
1.477
92.8%
23.35

baseline（300 原始特征）
650,000
150
0.116271
0.0787
1.478
92.4%
23.37

fe100（+100 time_id 均值）
650,000
150
0.114061
0.0929
1.228
88.8%
19.42

fe100（+100 time_id 均值）
500,000
150
0.113212
0.0894
1.266
90.4%
20.02

严格同条件对照（65 万行 / 150 轮）：0.116271 → 0.114061，即 -0.0022（-1.9%），且 ICIR 由 1.478 降至 1.228（稳定性变差）。两个数据规模下结论一致，负结果稳健。

与冠军自报数（LGBM 单模型 CV 0.141 → 加特征后 0.154）的差距，主要来自训练数据量（240 万 vs 65 万）与 boosting 轮数，见下方分析。

中间产物

文件
内容

metrics_summary_*.csv / .json
上表的机器可读版本，含 LGBM 参数

00_feature_corr_rank_*.csv
300 特征与 target 的 |corr| 排名，及被选中构造 time_id 特征的 100 个

ic_series_*.csv
每个 time_id 的 IC 序列（官方指标即其均值）

feature_importance_*.csv
特征增益重要性，is_time_id_feat 标记新增特征

01_IC_timeseries_*.png
逐期 IC 与累计 IC 曲线

02_IC_distribution_*.png
IC 分布直方图

03_feature_importance_*.png
Top25 重要性（橙色 = 新增的 time_id 特征）

5. 硬件限制与未复现部分

本机配置：i5-1240P（12 核 16 线程）/ 16GB 内存 / 仅 Intel Iris Xe 核显（无独立显卡）。

TabNet 未复现：需要 NVIDIA 独显（CUDA）。核显算力约 1.7 TFLOPS，且不支持 CUDA，无法承担 230 万行的训练。

训练规模受限：16GB 内存下，train 段最多采样到约 65–80 万行（全量 197 万行 × 400 特征会 OOM）。这直接限制了冠军特征的发挥空间。

若需复现完整方案，建议使用免费云 GPU（Kaggle Notebook 每周约 30 小时 T4×2、Google Colab）。

工程中踩到的三个内存坑（已固化在代码里）

ds.dataset().to_table(filter=...) 面对单个 row group 的 3.4GB 文件，会把整个文件解码进内存再过滤 —— 改用 ParquetFile.iter_batches 流式读取。

读完后 pyarrow 内存池不归还内存给系统，表现为可用内存骤降 5GB —— 加 pa.default_memory_pool().release_unused()。

一次性分配 80 万 × 400 的 float32 连续数组会失败（连续内存不足而非总量不足）—— 预测阶段改为分块 PRED_CHUNK=100_000。

6. 关键发现

6.1 time_id 均值特征在截面内是常数（机制性解释）

实测确认：time_id_xxx 特征在同一个 time_id 内标准差为 0（它就是该期横截面均值）。而官方指标恰恰是"每期截面内算 Pearson"—— 所以这 100 个特征对截面排序没有直接贡献。

它们只能通过树模型"先按市场状态分裂、再在状态内套用不同规则"间接起作用。这解释了两个现象：

模型确实大量使用了它们：总重要性占比 35.4%，Top100 中占 56 个；

但转化为截面排序能力有限，且引入了新的不稳定性（IC 标准差从 0.079 升到 0.093）。

6.2 为什么与冠军结论相反

冠军报告 CV 0.141 → 0.154（+9%），本复现为 -1.9%。可能原因，按可能性排序：

数据量差一个量级：冠军用 240 万行，本复现 65 万行。这类"状态条件"特征需要足够多的期数和样本才能学到稳定交互；数据不足时更接近噪声。

boosting 轮数：本复现 150–200 轮（受时间约束），深层交互需要更多轮才能建立。

参数差异：冠军未公开 LGBM 参数，本复现用的是社区通用配置。

需要强调的是：这不构成对冠军方案的否定，只能说明该特征工程对数据规模敏感，在单机 16GB 环境下难以收益。

6.3 方法论副产品

官方指标对预测值的整体缩放和平移不变（每期独立算 Pearson），因此输出 rank 或 z-score 不影响分数，且能压制 target 极值（-9.4~12.0）对 Pearson 的干扰。

数据中存在 0 值填充痕迹：f_200 全市场 21.4% 取值为 0，f_0 0.9%、f_20 1.4%，其余多数列 < 0.1%。

7. 如何运行

# 环境：Python 3.13，见 requirements.txt
# 数据：下载 robikscube/ubiquant-parquet 并解压到 data/

# 快速验证流程（约 1 分钟）
python ubiquant_top1_reproduce.py --scale smoke --exps baseline,fe100 --rounds 60

# 正式实验（建议分两次跑，避免单进程内存峰值）
python ubiquant_top1_reproduce.py --scale full --exps baseline --rounds 150 --subsample 650000
python ubiquant_top1_reproduce.py --scale full --exps fe100 --rounds 150 --subsample 650000

参数说明：--scale（smoke/small/full 切分）、--exps（baseline/fe100/kfold/corrall）、--rounds、--early-stop、--subsample（训练段最大行数，内存不足时启用）。

产物默认写入 reproduce/results/，文件名带时间戳，不覆盖历史结果。

8. 仓库结构

Ubiquant Market Prediction/
├── README.md 本文件
├── 思路.txt 冠军方案原文
├── ubiquant_top1_reproduce.py 主复现脚本
├── ubiquant_top1_reproduce.ipynb 同上（notebook 版）
├── explore_data.py / verify_structure.py / verify_stats.py 数据结构探查
├── explore_report.txt / verify_report.txt / verify_stats.txt 探查输出
└── reproduce/results/ 实验产物（csv / json / png）

注意：data/（约 12GB）不入库，见 .gitignore。

About
Reproducing the 1st-place solution of Kaggle Ubiquant Market Prediction (LGBM + time_id mean features).
Resources
Readme

Activity

Stars
0 stars
Watchers
0 watching
Forks
0 forks
Report repository

Releases

Packages

Contributors

Languages

 You can’t perform that action at this time.