# I-20260928-05：机主现在的标准下，还有哪些美股股票类 ETF/个股规则值得批量筛选

任务来源：缺口搜索指令（`found_by: gap-search-2026-09-28-1907`），目的是给自动研究轮补可做的任务，只调研登记、不跑回测。范围限定：只用美股股票类 ETF 或个股日线；不许提跨资产（债券/黄金/商品/美元/Defense First/跨资产趋势/管理期货）、大模型联网选股（arXiv 2601.11958）、MarketSenseAI；个股 ML 选股在现有免费数据上已关闭（不再同一批数据换模型）。

## 起点：覆盖地图（`reports/research/harvest/coverage.json`）

`trend_momentum.etf_letf_rotation` 是唯一 `status: live` 的格子（S1/S2/S3 的来源方向 `dir:recent_window_etf_menu_rotation`）。它目前只有 4 个菜单：`A1_global`（宏观混合）、`A2_sector`（11 个 SPDR 板块）、`A3_growth`（成长概念混 SMH）、`A4_levered`（5 只杠杆 ETF）。搜索最少、和近期盈利最相关、且不属于已否决范围的格子选定为：**同一台已验证的跨截面 ETF 动量轮动引擎（`scripts/run_h20260918_05_recent_menu.py:rotation_cell`），换一个从未测过的 ETF 菜单**——这是复用现有实现、不是新方向，成本几乎为零（不用改机制，只改 `MENUS` 列表）。

其余候选格子逐一查过：
- `flows_structural.calendar_and_fomc`／`rebalance_and_hedging_flows`：月初效应、月末反转、板块季节性领跑、FOMC 前漂移已测（批次 2，0/7 + 2 条近期观察）；指数加入/剔除效应已判 `evidence_too_weak`（Greenwood & Sammon：graduation 效应已消失）。期权到期周对个股的效应本次搜索没有找到独立可信证据，且是个股事件类机制（不是 ETF 菜单轮动），和本次"菜单换血"批量任务不是同一类，未继续深挖。
- `reversal.*`、`intraday_hf.*`：已 `tested_refuted`。
- `event.8k_item_events`：个股事件类，需要新数据管线，超出本次"只调研登记"60 分钟预算，留给以后。

## 证据表（每条都打开过原文，不是只看摘要）

| 方向 | 来源（URL，抓取时间） | 样本期/机制 | 已知夏普 | 本地先例 | 取舍 |
|---|---|---|---|---|---|
| 因子风格 ETF 动量轮动（MTUM/QUAL/USMV/VLUE/SIZE） | Quantpedia, https://quantpedia.com/strategies/momentum-factor-and-style-rotation-effect（2026-09-28，WebFetch 读全文）；iShares, https://www.ishares.com/us/insights/dynamic-factor-rotation-investing（2026-09-28） | 1972-2005，6 只 Russell 风格 ETF（大/中/小盘价值/成长），12-1 月动量多空月度调仓；年化 9.25%、夏普 0.33、回撤 -52.5%；无近期窗口、无只做多数字 | 0.33（多空，老样本） | 无——`recent_window_etf_menu_rotation` 从未用过因子风格 ETF 菜单 | **登记为任务**：机制已在本机验证（S1-S3），只是换菜单；Quantpedia 数字本身弱且老，但用它做否定测试成本几乎为零 |
| 细分行业 ETF 动量轮动（SMH/XBI/KRE/ITB/IGV/XOP/XRT/IHI） | Molchanov & Stangl, https://acfr.aut.ac.nz/__data/assets/pdf_file/0005/294287/The-Myth-of-Sector-Rotation-non-blind.pdf（2026-09-28）；GitHub, https://github.com/segobooking-finanz/momentum-sector-rotation/blob/main/README.md（2026-09-28）；drksci, https://drksci.com/algorithmic-trading-ai-sector-rotation-momentum（2026-09-28） | Molchanov & Stangl 否定的是宏观周期预测板块轮动（放宽的领先滞后搜索和随机无差异），不是价格动量机制；GitHub/博客复现都没有披露样本外或实盘数字 | 无独立数字；S1（11 个 SPDR 板块，同机制）对标窗中位数夏普 1.33-1.35 | S1 本身就是本地先例 | **登记为任务**：比 S1 的 11 个板块更细、离散度更高，同引擎换菜单，最便宜 |
| 单一国家股票 ETF 动量轮动（EWJ/EWG/EWU/EWA/EWC/EWZ/INDA/EWY/EWT） | Quantpedia, https://quantpedia.com/strategies/momentum-factor-effect-in-country-equity-indexes（2026-09-28） | 18 个国家 MSCI 指数，1975-2014，动量+低波动择时（本次只读了设计摘要，没有提取完整夏普数字） | 未提取 | `dir:etf_dual_momentum_rotation_gem_pools`（GEM，聚合美国 vs 国际 vs 债券的双动量，已测 duplicate/passed）是聚合层面，不是国家层面的截面选择，机制不同 | **登记为任务，但标为边界**：严格讲是美股交易所上市的股票类 ETF，不是跨资产，但和已否决方向相邻，任务里第一步要机主确认范围 |
| JKP 近期高 IC 会计变化类因子（ocf_at_chg1/niq_at_chg1/niq_be_chg1） | 已有调研 `reports/research/intel/I-20260928-04-recent-high-ic-factors.md`（2026-09-28，S3 直接下载 JKP 官方数据+文档） | 2023-2025，多空月度，本地可复现的 3-4 个因子 t 统计量在乘数检验下站得住 | 多空价差夏普 1.4-2.3；换算成多头腿本身年化只有 14-16%、夏普 <1 | `dir:jkp_accounting_change_factors`（parked，同一批数据）；T-10 多源 LightGBM 排序（用了同一批基本面字段）已否定（压力期 RankIC 0.018-0.019，低于 0.030 门槛） | **不单独开任务**——见下方专门说明 |

## JKP 因子是否值得单独开任务：不值得

**判断依据**：多源 ML 排序的否定（T-10）和"单因子只做多排序"是不同的检验，本可以分开重开——但 `I-20260928-04` 自己已经做过这个更便宜的否定测试，不需要我再另开一条：
1. **乘数检验**：153 个因子里过 |t|≥2.6 门槛的只有 4 个可本地复现（ocf_at_chg1、niq_at_chg1、niq_be_chg1，还有一个方向相反的空头信号），比随机噪音期望的 1.43 个略多，但这 4 个高度同族（全部是"基本面环比变化"），有效独立检验数远小于表面的 153。
2. **多头腿本身的检验已经做过**（该笔记 Part 1 末尾）：4 个因子对应的高分组年化只有 14-16%、夏普 <1，和大盘同期涨幅同量级——这正是本次批量任务 K1 门槛（对标窗夏普 ≥1.19）会直接否掉的水平，不需要再跑一次批量筛选去确认。
3. **和已否定路线的区别**：T-10 是"财报+内部人+空头+财报日"合并 LightGBM 排序，RankIC 0.018-0.019；这里是单一基本面因子的十分位排序，机制确实不同。但两者共享同一个数据源（`sec_fundamentals` 的基本面字段），T-10 用了更丰富的信息量还是没能把信号做到超过量价基线，单一更弱的因子在同一份数据上不可能表现更好——这不是"因为多源 ML 被否定所以单因子也不测"，而是"单因子的多头腿检验已经在无需新回测的情况下做过了，结果已经清楚"。
4. 这批因子最强的几个（tax_gr1a、dsale_dsga 等）本地缺数据（税费、SG&A、员工数、存货、PP&E 明细），复现不了，进一步降低了开任务的价值。

结论：`dir:jkp_accounting_change_factors` 维持 `parked`，不新开方向条目、不进队列。

## 排序（按"同样算力下更快得到近期能赚钱且可执行的结论"）

1. **T-20260928-40（因子风格 + 细分行业 ETF 菜单，24 候选）**——复用已验证机制（S1-S3 的引擎），零工程成本，K1/K2 判定路径和 DSR 都是现成通道，是本轮成本最低的决定性测试。
2. **T-20260928-41（单一国家 ETF 菜单，8 候选）**——同样便宜，但先要机主确认范围，避免测完被否决。
3. JKP 单因子多头——已用现成调研笔记的乘数检验+多头腿检验否定，不重复花算力。
4. 期权到期周/节前个股事件——证据不足独立开卡，本轮未继续搜索，留作以后缺口搜索的候选格子。

## 搜索记录（`reports/research/harvest/search-log.jsonl`）

- `search:20260928:web:factor_etf_rotation_mtum_627aa0`（web，"factor ETF rotation MTUM QUAL USMV VLUE SIZE momentum backtest"）
- `search:20260928:web:quantpedia_factor_rotation_strategy_ba93da`（web，"Quantpedia factor rotation strategy momentum quality value size low volatility ETF"，含国家指数因子页）
- `search:20260928:web:narrow_industry_etf_momentum_5adf68`（web，"narrow industry ETF momentum rotation SMH XBI KRE ITB IGV live track record"）
- `search:20260928:web:allocate_smartly_sector_momentum_8c8549`（web，"Allocate Smartly sector momentum rotation strategy live track record"，无新信息）
- `search:20260928:web:sector_rotation_momentum_strategy_6e372e`（web，"sector rotation momentum strategy does not work overfit criticism evidence"，找到 Molchanov & Stangl 否定证据）
- `search:20260928:github:sector_etf_momentum_rotation_f62c74`（github，"sector ETF momentum rotation backtest python"，个人复现仓库，无披露的实盘/样本外数字）

四类证据（论文复现、反面证据、开源代码、从业者实盘记录）都覆盖到，但从业者实盘记录这一类找到的多是通用板块热力图/筛选工具（SSGA、tradestie 等），没有披露可信的独立回测夏普——已在证据表和登记簿里注明"claim_only"/无披露数字。

## 产出

- `reports/research/harvest/directions.jsonl` 新增 3 行：`dir:factor_style_etf_momentum_rotation`（queued）、`dir:narrow_industry_etf_momentum_rotation`（queued）、`dir:international_country_etf_momentum_rotation`（queued，边界标注）。
- `reports/research/harvest/coverage.json`：`trend_momentum.etf_letf_rotation` 补充 3 个新方向 id 和本次搜索的 `next` 说明。
- `reports/research/control/autonomous-queue.md` 追加 T-20260928-40（批量，24 候选）、T-20260928-41（小批量，8 候选，机主先确认范围）。
