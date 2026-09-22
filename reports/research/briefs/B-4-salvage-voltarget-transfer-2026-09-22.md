# Brief B-4：抢救与迁移——波动率目标推广到 S1/S2/top50，超卖抄底信号叠加到 S3-vt40（候选 H-20260922-05）

执行者：Opus，一个会话一个交付。读本文件、工厂计划第 1、2、6 节、`reports/research/iterations/h20260922_02_s3_voltarget/report.md`、`scripts/run_h20260922_02_s3_voltarget.py`（复用其波动率目标、窗口、成本、安慰剂、G 表实现）、`reports/research/iterations/giants_sweep_20260922/report.md` 中 `f1_tqqq_rsi_no_hedge_ablation` 一行与 `config/giants_sweep/manifest.yaml` 里该 cell 的 spec。不读其它历史。

依据：H-20260922-02 证明目标波动 40%（只减不加，余额 SHY）把 S3 从 145%/−56%/1.48 变成 98%/−30%/1.66 且过 G1–G5；扫荡里唯一过安慰剂的 cell 是"QQQ 在 200 日线上且 RSI(10)<30 才持 TQQQ，否则现金"（对标窗 15.9%/−5.2%/1.37，留出窗 1.50，随机平移安慰剂 0%），问题只是空仓太多。

两个问题（同一 iteration，两个 path，各自安慰剂）：
A. **机制迁移**：目标波动 {25%, 35%} 叠到 S1（行业轮动，原 27.8%/−16.9%/1.36）、S2（成长菜单，原 49.1%/−20.3%/1.50）；目标波动 {30%, 40%} 叠到 top50 规则动量书（原 33.0%/−28.3%；用 `strategy_specs/drafts/us_recent_high_return_top50.yaml` 的权重日程，若引擎不易复现该书则写明并只做 S1/S2）。杠杆上限 1.0，21 日实现波动。≤ 6 cell。判定：夏普提升且回撤收窄、留出窗夏普 ≥ 1.0、随机挑选安慰剂 ≤ 10%；对标窗年化仍 ≥ SPMO 的 35.8%。
B. **信号叠加**：S3-vt40（冻结）+ 抄底加档：当 QQQ > SMA200 且 RSI(10) < 30 时，目标波动临时抬到 {55%, 60%}，持续 {5, 10} 个交易日后回落。4 cell。安慰剂：抄底信号随机日历平移 1–20 日 ×20 种子；判定：对标窗年化 ≥ 110% 且回撤 ≤ 35%、留出窗夏普 ≥ 2.0、平移安慰剂打赢 ≤ 10%，否则"无增量"，S3-vt40 维持原样。

流程与闸门：卡 `H-20260922-05-voltarget-transfer-and-dip-boost.md`（上一环 H-20260922-02；情报节引用 Moreira-Muir 与 giants_sweep 报告），iteration `h20260922_05_salvage`，来源快照复用 h20260922_02 的 sources（复制并注明），direction-check 与 iteration validate 通过后再跑；输出与 B-2 相同；结果文件 `reports/research/briefs/B-4-result.md`；一个 commit（Co-Authored-By 行）。约束同 B-2：不扩网格、不改门槛、不跑全量 pytest、不读 .env、回复 ≤ 300 字。
