# 网页摘录与接口实测记录（2026-10-04，date -u 取时）

说明：下列网页摘要由 WebFetch 的小模型抽取，属二手摘录，已发现一次抽取错误（NBER w9587 摘录写成 $4/桶，原文 pdftotext 核对为 $1/桶，见 nber-w9587-wolfers-zitzewitz-iraq.txt 第 99-108 行）。关键数字以原文快照为准；仅有摘录者在报告中标"二手"。

## 原文快照（pdftotext 或 raw）
- hf-polymarket-v1-README.md：HF 数据集 README 原文（curl raw，01:13 UTC）。
- arxiv-2606.04217-polymarket-v1-database.txt：Qin & Yang, Polymarket-v1 Database（arXiv 2606.04217v2）。
- feds-2026-010-diercks-katz-wright.txt：FEDS 2026-010 全文。
- wang-learning-from-prediction-markets.txt：Goldstein, Li, Wang，2026-09-03 版，https://chenwang.one/files/predictionmkt.pdf 。
- nber-w9587-wolfers-zitzewitz-iraq.txt：Leigh, Wolfers, Zitzewitz, NBER w9587 (2003)。

## 二手摘录（未取得全文）
- Gómez-Cram, Guo, Jensen, Kung, "Financial Prediction Markets: A New Measure of Earnings Expectations", SSRN 5933475（2025-12-10 首发，2026-03 更新）。SSRN 与 HHS 页面 403/404，只读到摘要和报道：隐含预期更准确、无常见偏差、对盈利公告收益有增量信息、价格发现领先；7 天前正确分类 68%、前 1 天 77%，分析师 62%；前 1 天 81% 的合约定价高于 50 美分，实际 beat 率 74%，均价 0.71（来源：antoniomarrazzo.substack.com、ingame.com；样本约两个月，"年轻市场"）。未读到公告收益回归系数。
- Rabetti, Shao, Zhang, "Beating the Earnings Game", SSRN 6649938（2026-04）。SSRN 403。来自 cxoadvisory 与 247wallst：469 个 Polymarket 合约，383 家美国公司，2025-09..2026-02；市场 78.5% vs 分析师共识 43.7%；同期 beat 基准率 75.9%（247wallst 原话：一直假设 beat 也"看起来很准"，"不是交易配方"）。
- Bloomberg 2026-04-16 "Wall Street Quants See an Edge in Polymarket Earnings Forecasts"：403，只见标题。
- Diercks-Katz-Wright 的 NBER 版 w34702：见 FEDS 全文，不另存。
- Snowberg-Wolfers-Zitzewitz QJE 2007 / NBER w12073：只读到搜索摘要（共和党当选使股票估值 +2-3%，2004 年选举夜高频数据）。
- Angelini, "The Shape of Macroeconomic Beliefs", arXiv 2606.30040：只读摘要；只涉通胀分布，无资产收益。
- Abid, "The Polymarket Paradox", SSRN 6670638：只读摘要；单一交易者 11 个钱包把 Trump 概率抬高 10-15 个百分点（10 月）。
- Sherwood News 2025-11-05：UBS 关税敏感股篮子当日 +3.7%（13:48 ET），Polymarket"维持关税"概率从早间 >50% 降至 11:30 ET 约 18%、之后约 30%。
- OpenMarket, arXiv 2607.26245（摘要，经搜索）：54 个 Polymarket 日（2026-02-12..05-15）；Binance 大幅波动后约 347 ms Polymarket 报价才响应。方向与可交易性相反。

## 接口实测（2026-10-04 01:13-01:20 UTC，共约 25 个小请求）
- Polymarket Gamma `/events?tag_slug=earnings&closed=true&limit=100&offset=…`：共 1354 个已结算财报事件，结束日 2025-09..2026-10-05（另有 2 个 2024-01 与 2025-06 的异常条目）。清单见 polymarket-earnings-events-closed-gamma-2026-10-04.json（成交额分位数 10/25/50/75/90% = 915/2534/6310/14904/30097 美元；>=5k 美元 785 个，>=10k 美元 486 个）。
- Polymarket CLOB `/prices-history`：`interval=max&fidelity=1440` 对已结算的 "US recession in 2025?" 返回 359 个日点（2025-01-09..2026-01-01）。样本见 polymarket-clob-prices-history-recession2025-sample.json。`interval=max&fidelity=60` 返回空；`startTs/endTs` 窗口（一周）加 `fidelity=60` 返回 168 点，`fidelity=1` 返回 10080 点。结论：已结算市场的小时/分钟历史可取，但要按窗口分段。响应头未给出限速字段；官方文档（docs.polymarket.com/api-reference/rate-limits）：/prices-history 1000 次/10 秒，/events 500、/markets 300、/public-search 350 次/10 秒，IP 级、Cloudflare 排队不拒绝。
- 财报合约规则（TSLA 2025-10-22 样本，Gamma）：共识非 GAAP EPS 0.50；"严格大于"才算 Yes；最后一天价格约 0.83，结果为 No（outcomePrices ["0","1"]）。
- Kalshi `GET /series`（无需密钥）：14,584 个系列；类别计数见 kalshi-series-catalog-subset-2026-10-04.json。含 94 个标题带 tariff 的系列，shutdown、Fed chair 提名、公司 KPI（Starbucks、Carnival 等，2026-06 起）。`/historical/cutoff`：market_settled_ts 2026-08-04；`/historical/markets?series_ticker=` 的最早开市日：KXGOVSHUT 2021-09-28、KXFEDCHAIRNOM 2024-12-18、KXTARIFFCAN 2025-03-18、KXTARIFFSGLOBAL 2025-04-02。公司 KPI 系列 2026-06 才开，历史太短。成交量字段此次未能读到（返回 0），待核对。
- HF `TimeSeventeen/Polymarket-v1`（API tree，只看元数据）：README 与 HF 元数据均为 cc-by-4.0；arXiv 页摘要处理为 BY-SA 的说法未在原文核到（arXiv 文本里没有 license 条目），以 HF 为准。daily_aligned 前 1000 个文件合计 590,963,749 字节（至 2025_08_23，列表分页截断）；daily_aligned_multi 857 个文件合计 3,627,211,377 字节（2023_12_22..2026_04_28）；CTF 8,535,196,364；OrderFilled 42 个月文件合计 27,383,416,974（2026_04 单月 5.5 GB）。单日文件：2025_04_09 的 daily_aligned 1.6 MB（66,931 笔、984 个市场）、daily_aligned_multi 2.2 MB（98,652 笔、1,302 个市场）；该日含 us-recession-in-2025（858 笔）、中国 54% 关税、Fed 5 月降息等市场。字段为逐笔成交（price、p_event、block_timestamp、market_slug、category_refined），无逐日价格表，也无盘口；按 UTC 日分文件（实测 2025_04_09 的时间戳为 2025-04-09 00:00:01 至 23:59:59 UTC；README 第 41 行写 UTC+8，与第 275 行及实测不符）。
