# Brief B-2：S3 杠杆轮动加波动率目标与回撤刹车（候选 H-20260922-02）

执行者：Opus。一个会话，一个交付。读本文件、`docs/plan-strategy-factory-2026-09-22.zh.md` 第 1、2、3 节 B0、6 节，`reports/research/hypotheses/H-20260918-05-recent-window-etf-menu.md` 第 0、2、3、5 节，`scripts/run_h20260918_05_recent_menu.py`（复用其数据加载、窗口、成本、安慰剂）。不读其它历史。

巨人：Moreira & Muir 2017《Volatility-Managed Portfolios》(Journal of Finance)：按上月实现方差倒数缩放敞口，提高夏普并降低回撤；被多次复现。本地：S3 = 菜单 {TQQQ, SOXL, UPRO, USD, TECL}，63 日回看，持 2，月末再平衡，绝对动量对 SHY；对标窗年化 145.4% / 回撤 −56.4% / 夏普 1.48，安慰剂 25%。

问题：加波动率目标和回撤刹车后，能否把对标窗回撤压到 ≤ 35% 而年化仍 ≥ 50%，留出窗夏普 ≥ 1.0，安慰剂 ≤ 10%。

预注册网格（≤ 48 cell，跑之前写进 candidate-manifest.json）：
- 波动率目标：目标年化波动 {40%, 60%, 无} × 实现波动窗口 {21 日} × 杠杆上限 1.0（只减不加，余额进 SHY）
- 回撤刹车：{无, 从 sleeve 权益最高点回撤 ≥ 25% 时减半仓、创新高或 21 个交易日后恢复}
- 回看 {63, blend(21/63/126/252)} × 持有 {2} × 月末
- 成本 10 / 20 bp 每边；信号日收盘出信号、次日开盘成交（与引擎一致）
安慰剂：同菜单随机挑 2 只 60 种子；刹车信号随机日历平移 1–20 日 ×20 种子（刹车有效性）。
基线：S3 原样；SPMO、TQQQ 买入持有；菜单等权。

流程与闸门：
1. 写卡 `reports/research/hypotheses/H-20260922-02-s3-voltarget-drawdown-brake.md`（含情报节四问、最便宜决定性测试、否定条件；`上一环：H-20260918-05`；YAML front-matter lane: preregistered）。
2. 用 `oc research --help` 找到新建 iteration 与 direction-review 的命令；iteration id `h20260922_02_s3_voltarget`；来源至少两条并有快照与短引文：Moreira-Muir 2017 论文页（SSRN 2659431 或 JF DOI 10.1111/jofi.12513，用 curl 保存 HTML 到 iteration 目录的 sources/），以及本地 H-20260918-05 卡片。`oc research direction-check <path>` 与 `oc research iteration validate <id>` 必须通过后再跑。
3. 跑：`./scripts/run_capped.sh --mem 1.8G -- uv run python <你的脚本>`；输出到 `reports/research/iterations/h20260922_02_s3_voltarget/{candidate-manifest.json,cells.parquet,placebo.parquet,summary.json,report.md}`。report 必报：每 cell 的 select/holdout/anchor 夏普、年化、回撤；SPY / MTUM / SPMO / 同波动超额 / 安慰剂五个数；G1–G5 判定表。
4. 结果文件 `reports/research/briefs/B-2-result.md`（≤ 40 行）：结论一句话、最佳 cell、G1–G5 逐项、否定或通过、下一步。教训卡 `reports/research/lessons/L-20260922-02.md` 若否定。
5. 提交一个 commit（消息末尾 `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`）。

约束：不跑全量 pytest；不改门槛；不扩网格；不读 `.env`；≤ 25 次工具调用外的长命令用后台；回复我 ≤ 300 字。
