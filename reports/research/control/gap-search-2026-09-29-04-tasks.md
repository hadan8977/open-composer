# New tasks from gap-search-2026-09-29-04

Coordinator: merge these blocks into `reports/research/control/autonomous-queue.md`
(do not edit that file directly from this task). Format matches
`docs/runbook-autonomous-round.zh.md` section 9.

### T-20260929-03 M&A 目标股公告后漂移（需先建一个免费 EDGAR 数据管道）
- status: blocked
- priority: 2
- not_before: 2026-10-01
- goal: 缺口搜索（`gap-search-2026-09-29-04`）核实 `event.8k_item_events` 格子自己的 gap 字段写的"offerings, spin-offs, M&A never searched"是准确的（不是像日历格子那样的陈旧记录）——同一个 8-K 事件格子里其它子方向（回购公告、Item 4.02 财务重述、SEO/ATM 增发、分拆）都已判定 evidence_too_weak/not_executable，唯独并购目标股公告后漂移从未搜索过、也从未在本仓库测过。搜到一篇 2025-10-13 的工作论文（`https://exa.ai/library/publication/k3grbvwxkr8`，只读到摘要，Exa 库全文在付费墙后，判定为 claim_only 未独立核实）：用新闻覆盖度、公告前成交量、交易类型（现金/换股）预测并购目标股公告后 30 天的收益，作者声称扣成本后夏普可超过 2.1（方法、样本、具体窗口都没读到，只能当方向性线索，不能当预注册的目标数字）。另一篇 1992-2021 年美国样本（51,780 个并购/公司行动事件，`https://ideas.repec.org/p/usi/wpaper/920.html`，同样只读到摘要）发现小盘并购目标股的超额收益主要在公告**之前**（信息提前泄露/分析师覆盖不足所致），提醒我们能交易的公告**之后**窗口可能比论文摘要暗示的要小。机制和已测过的所有 8-K 子方向（回购、Item 4.02、SEO/ATM、分拆）都不同，且是长仓可执行（买目标股，不需要卖空收购方或裸卖空）。
- plan: |
    **第一步（数据管道，免费，一次性）**：本地没有任何并购交易列表数据源（`capabilities/registry.yaml` 里没有 M&A 相关 capability；`data/features/` 下没有并购数据）。用 SEC EDGAR 全文检索 API（免费，无需密钥）：`https://efts.sec.gov/LATEST/search-index?q=%22Agreement+and+Plan+of+Merger%22&forms=8-K&dateRange=custom&startdt=2016-01-01&enddt=2026-09-29`（按年分页，每页最多 10 条需翻页；也可以退到季度全文索引 `https://www.sec.gov/Archives/edgar/full-index/{yyyy}/QTR{n}/form.idx` 过滤 `form=8-K` 后按关键词扫正文，作为交叉核对）。写 `scripts/collect_sec_ma_target_announcements.py`（照抄 `scripts/collect_sec_insider_transactions.py` 的结构和限速处理），产出 `data/features/sec_8k_ma_announcements/`：字段至少 `symbol, filing_date(visible_at), cik, item_codes, deal_type(cash/stock/mixed，若能从正文关键词判断; 否则留空)`。**不确认交易完成状态（是否成功交割）是否能免费拿到**——若拿不到，本任务只测"公告后固定期限持有"（不依赖完成状态），不测"持有到交割"版本，在 direction 的 notes 里如实记录。
    抽样核对：抓取后随机读 20-30 条正文，确认关键词"Agreement and Plan of Merger"命中的确实是标的公司自己被收购（不是标的公司作为收购方，需要用 8-K 正文里"Company"和交易对手的主谓关系粗判，或者用现成的"Subject Company"字段）；如果误判率明显高（类似 13G 那次 14% 的教训），如实记录并按比例打折信号强度或转 `blocked_data`。
    **第二步（信号检验，数据管道跑通后再做）**：新建迭代 `h20260929_03_ma_target_drift`，`direction-review.json` 引用 `dir:merger_arbitrage_target_announcement_drift`。用 `open_composer.research.signal_card` `--mode event`：`--sql` 从新建的 `data/features/sec_8k_ma_announcements` 取 `symbol, trade_date=filing_date, value=1`（entry 在 filing_date 后下一个交易日开盘，`signal_card` 自带的 next-open 对齐已经处理），`--primary-horizon 20`（对应论文摘要的"30 天"里最接近的内置选项；另跑一次不带 `--primary-horizon`（用默认 20）对照 60 日持有），跑两个变体：`ma_target_all`（全部标的）和 `ma_target_t3`（限定 t3 小盘/低流动性档，呼应机主"小盘可以做"的偏好，也是size-effect 论文提示信息滞后可能更小的那一档——但也要小心公告前已经涨了一截，用 redate 安慰剂能部分控制这个）。用 `run_capped.sh --mem 1.8G --` 跑（signal_card 读整张 universe_broad 面板）。
    判定：读 `card["flags"]` 的四项（`car_t_ge_3`、`beats_redated`（内置把事件在同一只股票上随机移动 ±126 交易日的安慰剂）、`book_positive_20bp`、`book_positive_20bp_recent`）。四项全真才算"信号采纳"；否则按 signal_card 自己的 admit/reject/evidence_too_weak 逻辑走。这一步只是股票层面信号库准入检验，不是策略级 K1/K2（`open_composer/research/signal_card.py` docstring 明确单个信号不适用策略门槛）；若信号被采纳，再决定是否值得单独建一个策略级批量任务。
- done_when: `data/features/sec_8k_ma_announcements` 建好并有抽样核对记录（误判率数字）；`ma_target_all`、`ma_target_t3` 两张 signal card 都生成在 `reports/research/signal-cards/`；`dir:merger_arbitrage_target_announcement_drift` 从 queued 更新为终态（admitted/refuted/evidence_too_weak/blocked_data）并带 verdict、evidence（signal card 路径 + 数据管道抽样核对结果）、reopen_if；若数据管道本身建不成（EDGAR 限速或 Item 1.01 无法可靠识别），直接标 `blocked_data`，不勉强跑后半段。
- notes:
  - 2026-09-29 gap search (`gap-search-2026-09-29-04`) 添加。
  - not_before 设到 2026-10-01：这是一个新数据管道任务，不需要 DeepSeek 打分，但涉及新脚本和抽样核对，按惯例给协调者一天余量排期；也避免和当前排队中的其它数据管道任务（如 T-20260928-16/-17 的打分通道）抢注意力。
  - **待机主决定**：如果最终发现交易完成/交割状态无法免费获取，"持有到交割"版本的并购套利（更接近论文摘要里 Sharpe>2.1 的那种设计）就做不了，只能做"固定期限持有"这个更弱的版本——这不需要机主现在决定，只在测完第一步再报告。

### T-20260929-04 内部人集群买入：补测 H-20260916-08 唯一还空着的精确设计（top-500 池、周频）
- status: ready
- priority: 3
- not_before:
- goal: 登记簿里 `dir:insider_cluster_buy_top500` 明确写着"top-500/周频这个精确设计仍未测试"（`H-20260916-08`，2026-09-16 立项后一直排在其它卡片后面、预算 3 用了 0）。这是内部人集群买入方向里唯一还留白的精确 scope；两头都已经关闭：作为事件特征已采纳但很小（CAR +0.78%/20 日，t=5.0；`reports/research/signal-cards/insider_cluster_buy.md`），作为全池月频独立策略在 1501+ 档已被否定（跑输同波动 SPY，`dir:insider_buy_independent_broad_universe`）。**预期不高**——两头都已经不理想，周频换手只会加成本——排这个任务主要是花几分钟把登记簿这最后一条空白关掉，不是一个有前景的新线索。不需要新数据，直接复用已有 Form 4 特征和 `signal_card.py`。
- plan: |
    直接用 `open_composer.research.signal_card` `--mode event`：`--source` 指向 `data/features/insider`（或 `insider_broad`，两者都已确认存在且覆盖到 2026），`--column` 用 `buyers_60d`（或等价的集群买入计数列，跑之前先 `python3 -c "import pandas as pd; print(pd.read_parquet(...).columns)"` 核对实际列名），`--where`/`--sql` 限定 `top_n=500`（H-20260916-08 原始设计的 top-500 池）、事件定义为 `buyers_60d>=2`，信号日期为每周五（周频，照抄 H-20260916-08 卡片里"weekly, top-500 pool, equal-weight up to 30 names"的设计，不要改成月频或改变阈值）。`--primary-horizon 20`（约等于原设计的持有期，若原卡片写的是不同持有期，以卡片为准并在结果里注明与卡片一致）。数据量小（只是 top-500 池的事件表 + 已有 insider 特征），本机内存放得下，不需要 `run_capped.sh`。
    判定：同 T-20260929-03，读 `card["flags"]` 四项；因为已有两个非常接近的变体都失败，这次结果无论真假都应该直接写成对整个 `insider_cluster_buy_independent` 家族的收尾判断（不要因为"万一这次不一样"而放宽判定标准或加做变体）。
- done_when: signal card 生成在 `reports/research/signal-cards/`；`dir:insider_cluster_buy_top500` 和新建的 `dir:insider_cluster_buy_top500_weekly_independent` 都从 queued/partial 更新为终态，带 verdict、evidence、reopen_if；在 `current-view.zh.md` 的下一次更新里注明"内部人集群买入方向的三个 scope（事件特征、月频全池、周频 top500）已全部有定论"。
- notes:
  - 2026-09-29 gap search (`gap-search-2026-09-29-04`) 添加。

## 本次缺口搜索的登记簿/覆盖地图更新（非任务，供协调者知晓）

- `reports/research/harvest/directions.jsonl`：新增 `dir:merger_arbitrage_target_announcement_drift`、
  `dir:insider_cluster_buy_top500_weekly_independent`（均 `status: queued`，`triage` 齐全，
  `uv run oc research directions validate` 已过）。
- `reports/research/harvest/coverage.json`：
  - `factor_library.anomaly_replication` 的 gap/next 已更正（"small-cap 从未测试"是陈旧记录，
    实际 `idio_vol_63.md`/`max_ret_21.md`/`high_52w.md` 已按 t1/t2/t3 三档测过，illiquid 档全部为负）。
  - `trend_momentum.stock_momentum` 的 gap/next 已更正（residual momentum 已按档测过，
    t1 强/t2 弱/t3 为负；industry-relative momentum 仍然是真的空白，留待有行业分类数据源再排）。
  - `event.8k_item_events`：`status` 从 `untested` 改为 `searched`，新增
    `dir:merger_arbitrage_target_announcement_drift`，gap/next 反映本轮搜索结果。
