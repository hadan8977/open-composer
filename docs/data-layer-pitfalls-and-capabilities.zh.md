# 数据层坑与能力清单

日期：`2026-09-02`
性质：**清单，不是计划**。这里只记录"有哪些坑、哪些能力、我们处在什么位置"，不排期、不指派。
维护要求：每次踩到新坑就加一条，并注明证据；修好一条就改状态，**不要删除**——踩过的坑本身是资产。

标注：✅ 已修 · ⚠️ 部分 · ❌ 未做 · 💥 = 本项目已实际中招（附证据）

相关文档：
- `docs/finding-iex-cache-price-adjustment-defect-2026-09-01.zh.md`（第一、二章多条的来源）
- `docs/review-kernel-search-2026-09-01.zh.md`（第四章全部条目的来源）

---

## 一、数据本体正确性

| # | 坑 | 状态 | 证据 / 说明 |
|---|---|---|---|
| 1 | 未复权拆股 → 幻影腰斩 | ✅💥 | IEX 缓存中 TQQQ/QLD 共 6 处 -50% 单日跳变，SIP 同期 0 处 |
| 2 | 未复权分红 → 现金腿收益记成 0 | ✅💥 | BIL 2024-2026 年化：IEX `0.01%` vs SIP `4.42%` |
| 3 | **幸存者偏差** | ❌💥 | 宇宙取自 `AssetStatus.ACTIVE`；SIVB / FRC / TWTR / ATVI / VMW / CS **各 0 条**，而 QQQ/AAPL/MSFT 各 2680 条。横截面回测永远买不到归零前的硅谷银行。**2026-09-02 实测**：对 Alpaca SIP 直接请求 SIVB/FRC/TWTR/ATVI/VMW/CS 均有日线到退市日（SIVB 297 行至 2023-03-09）；病根只是宇宙用了 ACTIVE。但 Alpaca `inactive` 资产列表（19,187 条）**不含**这些名字，退市名单必须来自外部 |
| 4 | 复权不可逆 | ❌ | 现用 `adjustment=all`，复权烘焙进价格。主流做法是存**原始价 + 复权因子表**，查询时施加，这样才能复现"某年的回测当时看到的是什么"。**2026-09-02 实测**：Alpaca 公司行动 API 在本账户可用（TQQQ 拆股 2021-01-21/2022-01-13/2025-11-20，BIL 2020 起 101 次分红）；2020 前可用同一标的 `raw` 与 `all` 两次抓取之比反推因子 |
| 5 | 双时间 / PIT | ❌ | 每条记录应带 `event_time` + `knowledge_time`。宏观与财报会被大幅修订（FRED vs **ALFRED** 是典型对照）。FRED API 的 `realtime_start/realtime_end/vintage_dates` 参数即 ALFRED 口径，同一 key，无需新供应商 |
| 6 | ticker 被回收 | ❌ | 需永久证券标识（PERMNO / FIGI）。退市公司的 ticker 会被重新分配给别的公司。Alpaca bars 端点的 `asof` 参数可按日期解析同一实体的改名（仓库未用）；Databento `instrument_id` 是主流做法 |
| 7 | 指数 / 宇宙成分历史 | ❌ | "2019-06 当时的标普成分股"，任何横截面策略的前提 |
| 8 | 数据源与复权口径未钉死 | ✅ | `frame.attrs` 固定记录 feed 与 adjustment；provider feed 已在 `auto_research` 永久关闭。**2026-09-03 补充**：spec 级接入 SIP 走 `data.source: alpaca` + `data.path: data/sip/daily`（`source` 的 Literal 集合不含 `sip_parquet`，不能改 `strategy_spec.py`），`load_ohlcv_for_spec` / `fetch_ohlcv` / `load_daily_dataset` 三处均已支持，`frame.attrs["data_source_mode"]="sip_parquet"` 全程透传到回测报告 |

## 二、时间与重采样

| # | 坑 | 状态 | 证据 / 说明 |
|---|---|---|---|
| 9 | 延长时段混入 | ❌ | QQQ 一周 3463 条分钟 bar 中 **1903 条落在盘前盘后**（04:00-19:00 ET）。直接 resample 会把盘前和开盘揉进同一根 |
| 10 | VWAP 取算术平均 | ❌ | 必须成交量加权 `Σ(vwap×vol)/Σ(vol)`。取均值数字看着正常但是错的 |
| 11 | 小时线不对齐交易时段 | ❌ | RTH 从 09:30 起，`resample('1h')` 对齐整点会错位半小时。30 分钟线恰好对齐，小时线不对齐。仓库已有 `market_calendar.expected_us_equity_rth_bar_starts()` 可用 |
| 12 | 缺失分钟 | ❌ | Alpaca 对无成交分钟不给 bar。VUSE 一周仅 59 条。由 2 分钟合成的 30 分钟线与由 30 分钟合成的，**schema 上完全看不出区别**，需最低覆盖率规则 |
| 13 | 半日市 | ❌ | 提前收盘日最后一根不完整。`market_calendar.us_equity_session_close()` 已知道这些日子 |
| 14 | 用分钟线合成日线 | ❌ | 日线 bar 含开盘/收盘集合竞价成交价，合成结果对不上。日线必须用日线的带子 |
| 15 | 归档静默变旧 | ✅💥 | 续传见分片文件即跳过 → 冻结在回补完成日。退役的 IEX 缓存曾停在 2026-08-04 仍在被使用，无人察觉 |
| 16 | 分片号语义漂移 | ✅💥 | `BATCH_SIZE` 40→12，同一分片号指向不同标的（分片 316 = VSS..VUSE，分片 317 = EP.PRC..EPM）。这次没丢数据**是运气**，批大小往大改就是静默缺口 |

## 三、可交易性（上实盘前的硬门槛）

| # | 坑 | 状态 | 说明 |
|---|---|---|---|
| 17 | 流动性 / ADV 过滤 | ❌ | 选中 VUSE 这类标的的策略根本无法执行 |
| 18 | 真实买卖价差 | ❌ | 现在滑点是**固定 20bps**，不是真实 NBBO 价差 |
| 19 | 市场冲击模型 | ❌ | 平方根律 / Almgren-Chriss |
| 20 | 集合竞价成交 | ❌ | 大量成交发生在开盘与收盘竞价 |
| 21 | 融券可得性与费率 | ❌ | 做空策略的硬前提 |
| 22 | 分钟线内存天花板 | ✅💥 | 实测 10 标的 × 1 季度 = 1GB RSS；10 标的 × 1 年会 OOM（本机 3.8GB） |

## 四、评估方法论

本章全部来自 `docs/review-kernel-search-2026-09-01.zh.md`，均已修复。保留在此是因为**这些坑会在任何新写的搜索代码里重现**。

| # | 坑 | 状态 | 说明 |
|---|---|---|---|
| 23 | 固定参数当成流程验证 | ✅💥 | 仓库早有按折重选（`router_common.walk_forward_router`），kernel 另起炉灶做成全局固定的 |
| 24 | 选择层看到 OOS | ✅💥 | `development_fold_returns` 展平后与 `oos_return_stream` **1240/1240 逐元素相同**，名字造成的 |
| 25 | DSR 的 N 只算幸存者 | ✅💥 | 60 候选筛到 5 个再聚类 → 按 3 次试验收费。`campaign.py` 的防线逐字禁止"clustering a hand-picked subset" |
| 26 | 未来函数探针盲区 | ✅💥 | 固定探测 [40%, 90%]，绝对日期锚定在尾部的泄露可穿过，**加探针数无用** |
| 27 | 门槛可事后修改 | ✅ | 改为必须来自 git 已提交且无改动的合同 + `promotion_eligible` |
| 28 | 审计指标口径矛盾 | ✅ | `raw_candidate_count=65` 与 `breadth_ratio=0.5`（分母是 6）并排，读者会算错一个数量级 |
| 29 | 裸夏普偏好"假装现金" | ✅💥 | 常数信号 → 小正漂移 ÷ 近零方差 → 夏普爆表。下限设在共享质量函数，且不误伤防御型策略 |
| 30 | 按构造通过算进通过数 | ✅ | 与 QQQ 不相关时两个 capture 门槛自动通过；报告读起来比证据强 |
| 31 | 防护从不触发 ≠ 没有泄露 | ✅ | `rejected_lookahead_count: 0` 单独看无法区分"没泄露"和"防护是死的"。必须注入一个它该拦的东西 |
| 32 | 结构冻结掩盖噪声拟合 | ✅💥 | GP 改为逐折演化后 churn 从 0.25 变成 **1.00**（5/5 结构全不同）。旧设计看着稳，只是因为池子冻结、无可切换 |
| 33 | 绝对价格水平算子 | ✅ | 后向复权下历史价格水平不是当时成交价（BIL 显示为 81.74）。GP 终端全部改为比率型 |

## 五、搜索能力

| # | 能力 | 状态 | 说明 |
|---|---|---|---|
| 34 | 正确的多周期重采样器 | ❌ | 需同时处理第 9-14 条 |
| 35 | 特征存储 | ❌ | PIT + 内容哈希缓存，算一次复用。AI 量化标配 |
| 36 | 横截面宇宙 | ❌ | 现在只搜 QQQ/BIL 一个标的对，真正的 alpha 搜索是横截面的 |
| 37 | 列式查询 | ❌ | DuckDB / Polars 直查 parquet，比现在的分片扫描快一个量级 |
| 38 | 分片索引持久化 | ❌ | 冷启动日线 15s、分钟 47s，每个新进程重付一次 |

## 六、前沿能力

| # | 能力 | 评估 |
|---|---|---|
| 39 | 期权衍生特征（IV、偏斜、gamma exposure） | 高价值低成本，对指数方向信息量大，Alpaca 有期权数据 |
| 40 | LLM 特征 + knowledge-time 纪律 | ⚠️ **隐蔽陷阱**：用 2026 年训练的模型给 2019 年新闻打分，模型本身知道后来发生了什么，这是未来函数。缓解：只做抽取不做判断，或使用训练截止早于测试期的模型 |
| 41 | 订单流不平衡 / 微观结构 | 签名成交量、Kyle's lambda。有分钟线后成本很低 |
| 42 | regime 检测作为数据产品 | 标注成共用特征列，而不是每个策略各做一遍 |
| 43 | 合成数据增强 | 谨慎——生成模型容易学到伪影，策略再去拟合伪影 |

## 七、流程

| # | 坑 | 状态 | 说明 |
|---|---|---|---|
| 44 | 代理报告不核对就采信 | ✅💥 | 降解计数报告 47 / 产物 108；"8 门槛全挂" / 实际过 3。**产物永远为准** |
| 45 | 另起炉灶不先查仓库已有 | ✅💥 | 本轮三次教训的共同根因。`campaign.py` 早有有效 N 防线、`router_common.py` 早有按折重选、`optimizers/` 早已存在 |
| 46 | 收盘后自动更新 + 告警 | ❌ | 增量抓取与 `check_sip_freshness.py` 均已就绪，**未挂定时任务**。2026-09-02 复查：`crontab -l` 为空，paper systemd 单元 mask 到 `/dev/null` |

## 八、2026-09-02 复查新增（引擎、执行、运营、AI 层）

本章来自 `docs/capability-gap-analysis-2026-09-02.zh.md` 的全项目复查。数据层以外的坑也记在这里，因为它们同样会让回测数字失真。

| # | 坑 | 状态 | 证据 / 说明 |
|---|---|---|---|
| 47 | 模拟盘取数与研究取数不同源 | ❌ | `.env` `ALPACA_DATA_FEED=iex`，`config.py:116` 默认 iex；抓取脚本硬编码 `feed="sip"`。运行时走 `data_feed()` 的路径看 IEX，研究看 SIP。受影响路径待核实 |
| 48 | 两套回测引擎成本口径不同且无互校 | ❌ | `engines/backtest_engine.py` 逐笔乘法成本；`router_common.backtest_router_params` 用 L1 换手 × 费率。`tests/test_backtest_reference_parity.py` 只覆盖前者 |
| 49 | 路由器收益求和丢弃负权重但计其换手成本 | ❌ | `router_common.py:559-563` `if weight > 0` |
| 50 | 无 embargo 的前推验证仍在生产使用 | ❌💥 | `router_common.walk_forward_router:492/507` `end_index=test_start`；所有 `*-router-research` CLI 仍走它；内核 `nested_walk_forward.py` 已指出但未替换 |
| 51 | "冲击模型"是常数 bps，不随成交规模变化 | ❌ | `backtest_engine.py:473` `_impact_rate`：sqrt→`eta/1e4`，almgren_chriss→`(eta+gamma)/1e4`。是第 19 条的具体形态 |
| 52 | Nautilus 从未产生 parity 证据 | ❌ | `backtest_engine.py:69-73` 守卫 `len(universe)==1`；`reports/parity/` 0 文件；readiness 却有 `nautilus_backend` 检查名 |
| 53 | 告警从未送达 | ❌💥 | `reports/notifications/log.jsonl` 24 条，Telegram 23/23 skipped（disabled）；无邮件通道 |
| 54 | TCA 门槛完整但零观测 | ❌ | `paper_tca.py` 唯一报告 `valid_observation_count: 0`；成交回执未自动转成 observation |
| 55 | 开盘/收盘竞价单可能需要 Elite 权限 | ❌ 待核实 | Alpaca 学习文章称 OPG/CLS 仅 Elite Smart Router 可用；canary 只允许 `opg_limit`/`loo_limit`；6 月以来所有出场单取消/过期与此吻合，需在本账户实测 |
| 56 | PDT 规则已取消，执行假设未更新 | ⚠️ | SEC 2026-04-14 批准、2026-06-04 生效（FINRA Notice 26-10）；分钟级往返不再受 4 次/5 日限制，但仍需保证金账户。这是环境变化，不是缺陷 |
| 57 | `llm_contribution_pass` 在中心 readiness 路径硬编码 `None` | ❌ | `paper_readiness.py:1401`；AGENTS.md 与 repo check 都把它列为必需门 |

---

## 统计

**57 项：已修 20（其中 12 项本项目已实际中招）、部分 2、未做 35（其中 2 项本项目已实际中招）。**

2026-09-02 复查前为 46 项：已修 20、部分 1、未做 25。

已中招的 12 项分布在数据本体（2）、时间与重采样（2）、可交易性（1）、评估方法论（5）、流程（2）——
**没有一项是靠"仔细一点"能避免的，全部是靠对照实测或对抗性检验才暴露的。**
这是本清单存在的理由。
