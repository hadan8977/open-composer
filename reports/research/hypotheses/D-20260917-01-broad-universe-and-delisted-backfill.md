# D-20260917-01 数据卡：把股票池从"成交额前 500/1000"放开到全体可交易美股，并补被收购/退市的名字

- 性质：数据与框架修正，不是策略假设。触发：用户 2026-09-17 指出"前 500 是你自己定的，不合理就自己改"。
- 现状（2026-09-17 测量）：日线归档有 13,540 个代码（抓取时的全部活跃资产，含 ETF/基金），2025 年有数据的 11,399 个；
  其中日均成交额 ≥ 100 万美元且价格 ≥ 2 美元的 6,132 个。**被收购/退市的公司完全缺失**（TWTR、ATVI、SPLK、VMW、PXD、HES 都查不到），
  Form 4 里出现过的 11,455 个发行人代码有 6,274 个不在归档里（含基金、OTC、旧代码，也含全部退市名）。
- 为什么必须改：内部人买入、13D、财报后漂移的文献效应集中在小中盘，而且内部人买入的收益有相当部分来自后来被收购的公司；
  只看幸存的大中盘，等于在效应最弱、样本被削掉的地方找。个人规模的资金在小盘没有容量劣势。
- 要做的：
  1. 股票池：按"普通股（剔除 ETF/基金/权证/ADR 可选）、价格 ≥ 2 美元、日均成交额 ≥ 100 万美元"重建点时月度 cohort，保留 adv_rank 以便按流动性分段（1–500 / 501–1500 / 1501+）。
  2. 退市回补：用 Form 4 与 13D 里出现过的发行人代码作为历史代码清单，向 Alpaca 试取退市代码的历史日线；能取到多少、取不到的怎么办（记录偏差方向），写清楚。
  3. 特征重建：动量/波动/标签、内部人、13D、空头兴趣在新池子上重建；旧文件备份。
  4. 产出一张"每年 cohort 大小 × 流动性段 × 是否已退市"的表，后续所有卡引用。
- 完成标准：新池子文件 + 报告 `reports/research/control/broad-universe-2026-09-17.md`；不改任何已有实验的账本数字。

## 2026-09-17 07:20 UTC 探测结果（主会话自己测的，执行者直接引用，不要重测）

- **Alpaca 会返回退市公司的历史日线。** TWTR（到 2022-10-26）、ATVI（到 2023-10-11）、SPLK（到 2024-03-14）、PXD（到 2024-05-01）、SIVB（到 2023-03-09）都取到了完整的日线，`feed=SIP, adjustment=ALL`。
  所以退市回补可行，瓶颈只是"历史代码清单"。
- **资产列表接口不给退市名。** `GetAssetsRequest(status=INACTIVE)` 返回 19,178 个，其中 16,310 是 OTC，交易所挂牌的只有 2,868 个（XLNX、MXIM 在里面），TWTR/ATVI/SPLK/VMW/PXD/HES/CTXS/SIVB 全都不在。
  资产字段里没有"普通股/ETF"类型，只有 `name`；现有的 `open_composer/research/features/asset_metadata.py::is_probable_fund_or_etf` 是按名字关键词判断的，继续用。
- **历史代码清单的来源（取并集，减去归档已有的 13,540 个）：**
  1. SEC `data/raw/sec_13d/company_tickers.json`：10,422 个代码，3,219 个不在归档（都是现存公司，主要是小盘/OTC）。
  2. Form 4 原始季度包 `data/raw/insider/*.zip`（483 MB，2016q1–2026q1）里的 ISSUERTRADINGSYMBOL：之前测过 11,455 个代码，6,274 个不在归档。**注意 `data/features/insider/` 是按 top_n=1000 过滤过的（见 `_build_manifest.json`），不能拿它当清单。**
  3. Alpaca INACTIVE 且交易所为 NASDAQ/NYSE/AMEX/ARCA/BATS 的 2,868 个。
  4. 13D 表 `data/features/sec_13d/filings.parquet` 的 `issuer_symbol`：2,116 个，只有 31 个不在归档（该表建表时已按池子过滤，也不能当清单）。
  5. 之前（9 月 3 日）已经抓过的标普 500 剔除名单：`data/sip-delisted/daily/batch-00{0..4}.parquet`，243 个代码，457,428 行，同一列结构（symbol/timestamp/ohlcv/trade_count）。直接并入，不要重抓。
- **代码复用问题**：一个退市代码后来可能被别的公司再用。处理办法：对每个回补代码取 2016-01-01 至今全程日线，按 ≥ 30 个交易日的空档切成"上市段"，每段单独算一个 (symbol, episode) ；能用 Form 4 的 ISSUER CIK + 交易日期范围对上的段标 CIK，对不上的段照常留着但打 `cik_unknown`。
- **过滤到"普通股"**：先用 `is_probable_fund_or_etf` 剔除基金/ETF，再剔除代码含 `.`/`-`/`/` 或长度 > 5 的（权证、单位、优先股），再剔除名字含 Warrant/Unit/Preferred/Depositary/Notes 的。ADR 保留（用户目标是美股收益，不限本土公司）。
- **池子参数**：价格 ≥ 2 美元（现在的默认是 5），日均成交额 ≥ 100 万美元（60 日），不设 top_n 上限；每个月末 cohort 带 `adv_rank`，流动性段 1–500 / 501–1500 / 1501+。`scripts/build_feature_universe.py` 现有参数 `--top-n/--min-close/--adv-lookback-days`，需要加"按成交额下限而不是名次"的模式，旧模式保留。
- **必须重建的特征**（旧文件先搬到 `data/features/_pre_broad_2026-09-17/` 备份，不删）：`data/features/universe`、`data/features/daily`（回补的代码要补进日线特征）、`data/features/insider`（把 `feature_universe_top_n` 放开）、`data/features/sec_13d`（检查 `data/raw/sec_13d` 是否保留了原始索引，能重建就重建，不能就在报告里写清楚）、空头兴趣（等 H-07 执行者交付后再说）。
- **报告必须有的表**：每年 × 流动性段 × 是否已退市 的 cohort 数量；回补前后每年 cohort 大小对比；取不到日线的代码数量和它们在 Form 4 里的申报数（说明偏差方向）。

## 2026-09-17 07:40 UTC 第二个坑：改名别名（主会话发现并处理）

- 现象：Alpaca 把改名公司的**全部历史挂在新代码下**（ELV、XYZ、LUMN、GTM 都从 2016 年起有数据），同时**旧代码也能取到改名前的历史**（ANTM 到 2022-06-27、SQ 到 2025-01-17、CTL 到 2020-09-17、ZI 到 2025-05-12）。回补按"不在归档里的代码"取，就把旧代码当成退市名补了进来，宽池子里同一家公司出现两次。
- 第一版按 (日期, 复权收盘, 成交量) 精确匹配只抓到 371 个：改名后如果新代码有分红/拆股，两条序列的复权价差一个常数因子，精确匹配就漏（ANTM/ELV 就是这样漏的）。
- 第二版按 (日期, 日对数收益率保留 5 位) 匹配、排除 |r| < 5bp 的平盘日、再要求成交量比值近似常数（标准差 ≤ 0.05）。匹配天数 ≥ 20 且占该代码有效天数 ≥ 80% 的整条删除；低于 80% 的只删匹配区间（代码被另一家公司复用的情况）。回补内部也做同样的自匹配（改名后又退市的公司，保留结束更晚的那条）。
- 处理：`scripts/detect_delisted_aliases.py` 产出 `data/sip-delisted/broad/_alias_exclusions.parquet`，`scripts/repartition_delisted_by_year.py` 应用它；`universe_broad/daily_broad/labels_broad` 全部重建（含别名的旧版本挪到 `data/features/_*_aliasdup_2026-09-17/`，不删）。
