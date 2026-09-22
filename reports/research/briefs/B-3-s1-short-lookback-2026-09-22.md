# Brief B-3：行业轮动短回看（候选 H-20260922-03）

执行者：Opus（在 B-2 之后）。读本文件、工厂计划第 1、2、3 节 B0、6 节，H-20260918-05 第 0、2、3、5 节，`scripts/run_h20260918_05_recent_menu.py`。

巨人：Moskowitz & Grinblatt 1999 行业动量（JF）；本地 S1 = 11 只 SPDR 行业 ETF，252 日回看，持 2，周五再平衡，对标窗 27.8% / −16.9% / 夏普 1.36，留出窗 2.22，安慰剂 2%。

问题：在 2026 这种轮动剧烈的市场里，短回看是否更好：对标窗年化 ≥ 40% 且回撤 ≤ 20%，或夏普 ≥ 2.0；留出窗夏普 ≥ 1.0；安慰剂 ≤ 10%。

预注册网格（≤ 36 cell）：回看 {21, 42, 63} × 持有 {1, 2} × 再平衡 {周五, 双周} × 绝对动量对 SHY {开, 关} × 成本 10/20 bp。安慰剂：随机挑 60 种子。基线：S1 原样、SPMO、菜单等权。

流程、闸门、产出、约束与 B-2 相同：卡 `H-20260922-03-sector-rotation-short-lookback.md`（上一环 H-20260918-05），iteration `h20260922_03_sector_short`，来源快照（Moskowitz-Grinblatt 论文页 + 本地卡），direction-check 与 iteration validate 通过后再跑，结果文件 `reports/research/briefs/B-3-result.md`，一个 commit。
