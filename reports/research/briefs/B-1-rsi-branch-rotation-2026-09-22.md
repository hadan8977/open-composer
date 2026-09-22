# Brief B-1：RSI 极值分支 + 板块/杠杆轮动 + 波动率对冲腿（候选 H-20260922-04）

执行者：Opus。一个会话，一个交付。读本文件、`docs/plan-strategy-factory-2026-09-22.zh.md` 第 1、2、3 节 B0、6 节，`reports/research/intel/I-20260922-02-harvest-1.md`，`reports/research/hypotheses/H-20260918-05-recent-window-etf-menu.md` 第 0、2、3、5 节，`scripts/run_h20260918_05_recent_menu.py`（复用数据加载、窗口、成本、安慰剂）。不读其它历史。

巨人：Composer 公开 symphony 家族（`Sector Rotator MS` 年化 134.7% / 回撤 −29% / 夏普 1.7，OOS 自 2025-09-08；`Portfolio Experiment: Volatility Minimization` 年化 116.1% / −15.1% / 夏普 3.52，OOS 自 2025-06-28；`v6 Symphony Sorter` 年化 144.8% / −48.4%，OOS 自 2023-09-22）。共同结构：每日看一个 RSI(10)；过热 → 持有波动率多头（UVXY/VIXY）或现金；超卖 → 博反弹持杠杆多头；否则 → 买近 1 个月领涨板块（1 倍或 3 倍）。阈值不公开。本地已知：单一均线门控在此窗口过不了安慰剂（L-20260918-05）；新元素是 RSI 过热分支与对冲腿。

问题：这个家族在我们的协议下能否过 G1–G5（对标窗年化 ≥ 50% 且回撤 ≤ 35%，或夏普 ≥ 2 且年化 ≥ 30%；留出窗夏普 ≥ 1；安慰剂 ≤ 10%；20 bp/边下仍成立）。

预注册网格（≤ 32 cell，写进 candidate-manifest 后再跑）：
- RSI 标的 {SPY, QQQ}，RSI 窗口 10 日
- 过热阈值 {80, 85}；过热分支资产 {UVXY, BIL}
- 超卖阈值 30（固定）；超卖分支资产 TQQQ（固定）
- 正常分支：21 日收益最高的板块，菜单 {1 倍：11 只 SPDR 行业, 3 倍：TECL, FAS, ERX, CURE, DUSL}
- 再平衡 {每日, 周五}
- 成本 10 / 20 bp 每边；信号日收盘出信号、次日开盘成交
- 排除 SVXY/SVIX 等做空波动率产品（按产品类别）
安慰剂：RSI 信号随机日历平移 1–20 日 ×20 种子（分支有效性）；正常分支随机挑 1 只 ×60 种子（板块排名有效性）。基线：SPMO、TQQQ、S1 现役 sleeve、菜单等权。
必报：每日再平衡的年换手与 20 bp 下的衰减；UVXY 分支的持有天数与贡献（对冲腿到底赚没赚）；三分支各自的贡献分解。

流程与闸门：
1. 卡 `reports/research/hypotheses/H-20260922-04-rsi-branch-rotation.md`（情报节四问引用 I-20260922-02；最便宜决定性测试；否定条件；`上一环：H-20260918-05`；front-matter lane: preregistered）。
2. `oc research --help` 找新建 iteration/direction-review 命令；iteration id `h20260922_04_rsi_branch`；来源快照 ≥ 2（两个 Composer 页面用 curl 存 HTML 到 iteration 的 sources/，加短引文）；`oc research direction-check` 与 `oc research iteration validate` 通过后再跑。
3. `./scripts/run_capped.sh --mem 1.8G -- uv run python <脚本>`；输出 `reports/research/iterations/h20260922_04_rsi_branch/{candidate-manifest.json,cells.parquet,placebo.parquet,summary.json,report.md}`；report 含 SPY / MTUM / SPMO / 同波动超额 / 安慰剂五个数与 G1–G5 判定表。
4. 结果文件 `reports/research/briefs/B-1-result.md`（≤ 40 行）；否定则写 `reports/research/lessons/L-20260922-04.md`。
5. 一个 commit，末尾 `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`。

约束：不跑全量 pytest；不改门槛；不扩网格；不读 `.env`；长命令后台跑；回复 ≤ 300 字。数据缺口（某 ETF 无 2022 年前日线）写明并缩窗，不猜。
