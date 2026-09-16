# H-20260916-01 Form 4 内部人确认门：内部人在买的动量股才满仓

- 状态：running（第 0 步完成 2026-09-16；第 1–2 步执行中）· 假设族：insider_form4_gate（族预算 6）
- 层：择时 / 信号接受（对动量组合整体或逐股门控）· 数据层：**一级**（SEC Form 4，免费、官方、2006 起）
- 一句话假设：规则动量 top50 中，过去 60 个交易日"机会型"内部人净买入比例高于截面中位数的股票，其后 4 周收益显著高于其余；
  以此门控（不合格者减半或转 BIL）能改善回撤和同波动超额。

## 为什么用这个方法（出处）
- 机会型内部人买入组合价值加权异常收益 82 bp/月，例行交易 ≈ 0；区分方法是"是否在往年同月重复交易"。【lit:insider_opportunistic_vs_routine_decay】
- 内部人在异象多空腿的买卖比例能预测该异象未来收益，支持"确认门"而非"独立选股"的用法。【lit:jef2025_insider_trading_and_anomalies】
- 数据：SEC Insider Transactions Data Sets（季度 zip，as-filed XML 展平，含 FILING_DATE / TRANS_DATE / TRANS_CODE / TRANS_SHARES），
  尾段用 EDGAR 日更 Form 4 索引补齐。可见日 = FILING_DATE 的次一交易日。【lit:sec_insider_transactions_data_sets】
- 用户框架把内部人排在一级第一位；本卡是一级数据管道（能力登记 → 采集器 → 点时特征 → 筛选器 → 孪生单元）的第一次走通。

## 设计
- 第 0 步（本卡的主要工程）：在 `capabilities/registry.yaml` 登记 `events.sec_form4_insider`，跑能力评估；写采集器
  `scripts/collect_sec_insider_transactions.py`：下载 2016 起的季度数据集 + 2026 年最近季度的 EDGAR 日更补尾，落到 `data/raw/insider/`，
  点时特征落到 `data/features/insider/`（每股每日：过去 60 日净买入股数 / 流通股、净买入人数、是否机会型、最近一笔可见日）。
- 第 1 步：特征进现有筛选器（IC / ICIR / FDR / 符号稳定性），与价量因子同协议。
- 第 2 步：孪生单元。门关 = 现有规则动量；门开 = 内部人净买入比例 > 中位数满仓，否则减半（或 BIL）。周频，2016 →。
- 占位：把每条申报的 FILING_DATE 随机平移 ±30 个交易日重算特征。效应若仍在，说明抓到的是市值/行业代理，不是内部人信息。

## 预期与否定判据
- 预期（判断，非文献数字）：回撤改善 3–8 个百分点，CAGR 变动 -3 到 +5 个百分点；同波动超额从 -11% 改善到 > -3%。
- 否定（任一命中即停）：(1) 门开 vs 门关的同波动超额改善 < 3 个百分点；(2) 占位平移后效应仍在；(3) 内部人特征在筛选器 recent 窗 |t| < 2 且符号稳定性 < 0.7；
  (4) 10b5-1 计划交易无法从字段区分且占比 > 50%；(5) 门每年切换 < 4 次。
- 必报：SPY / MTUM / SPMO / 同波动超额 / 占位。

## 成本与执行
- 采集器 + 特征约 2 个执行者工作日（下载量：季度 zip 每个几十 MB，2016 起约 40 个）；筛选与孪生单元各半天。
- 产出：`data/features/insider/`、`reports/research/iterations/h20260916_01_insider_gate/` + 复盘卡。

## 第 0 步完成后的两处修订（2026-09-16 09:40 UTC）
1. **门的定义改了。** 数据落地后发现严格意义的"机会型买入"（Cohen-Malloy-Pomorski 口径）在 top-500 池里只覆盖 1%–3% 的股票日，
   按"截面中位数"切门在 98% 的股票上都是 0，门会退化成二值。所以主门改为：**过去 60 个交易日内有公开市场买入（TRANS_CODE=P）且净买入人数 > 0**；
   强化变体：**集群买入（buyers_60d ≥ 2）**；严格机会型只作为第三个对照变体。三者都要报，每个算 1 次试验。
2. **预期下调。** 调研核实：内部人集群买入的超额 **+1.61% 发生在申报日之前**，申报当日和次日约为零
   （`reports/research/control/informed-flow-sources-and-strategy-families-2026-09-16.md` A.5）。我们只能在申报可见之后行动，所以 Form 4 是慢变量和否决位，不是"跟着买"。
   把"CAGR 变动 -3 到 +5 个百分点"的预期改为"主要看回撤与同波动超额是否改善，CAGR 持平即可"；否定判据不变。
3. **按 L-20260916-03 的规矩**：门控后按比例归一化到 100% 暴露再与门关比较；占位用 `--shift-filing-dates-days ±30`，至少 5 个种子，报分布。
数据：`data/features/insider/{年}.parquet`、`screening_panel_weekly.parquet`（2016-01 → 2026-09-15，尾段已用 EDGAR 日更补齐）；报告 `reports/research/iterations/h20260916_01_insider_gate/step0-collector-report.md`。
