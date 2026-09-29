# 自动研究轮日志

每行一轮，由 `scripts/autonomous_preflight.py log` 追加，跳过的轮也记。用量来自本机会话记录：本轮会话及其子代理的 fresh token（输入 + 缓存写入 + 输出），是下限，不是订阅百分比。执行手册：`docs/runbook-autonomous-round.zh.md`。

| 开始 (UTC) | 结束 (UTC) | 状态 | 任务 | 摘要 | fresh / cache-read tokens |
|---|---|---|---|---|---|
| 2026-09-28T01:07 | 2026-09-28T01:19 | done | T-20260927-02 | S3 分批调仓否定 0/4；月末调仓日在选择窗和对标窗都是 21 个日子里最好的，不挑日子的对标窗预期约 86%/夏普 1.5/回撤 -35%（H-20260928-01） | 237,511 / 8,029,988 |
| 2026-09-28T07:07 | 2026-09-28T07:07 | skipped | - | skip_quota: 5h window 95% >= 50% line (resets 10:59 UTC); owner sessions active | n/a |
| 2026-09-28T13:07 | 2026-09-28T14:41 | failed | T-20260928-14 (trust gate) + gap search | 13:07 round dispatched two background subagents and ended its turn at 13:10; Paseo archived the round and both subagents were killed with no output. Lock released and the task reset to ready by the interactive session at 14:5x; the runbook now requires foreground subagents and foreground waits. | n/a |
| 2026-09-28T16:07 | 2026-09-28T16:07 | skipped | - | wait_owner_active: owner interactive sessions wrote at 15:59 UTC and quota reading unavailable (token expired -- re-login); skipped, next round 19:07 UTC | n/a |
| 2026-09-28T19:07 | 2026-09-28T20:13 | done | T-20260928-14 + gap search | T-14 训练置信度门否定 0/3（AUROC 0.52，半仓版夏普比同波动账本只高 0.05，不如安慰剂；Modal $0.04）；缺口搜索加 T-40（因子风格+细分行业 ETF 菜单 24 候选）和 T-41（国家 ETF，等机主确认，blocked）；模拟盘值守正常 | 1,898,749 / 50,130,931 |
| 2026-09-28T22:07 | 2026-09-28T22:36 | done | T-20260928-40 + gap search | T-40 因子风格+细分行业 ETF 轮动 0/24 保留（因子菜单 5 条近期观察：对标窗夏普 1.25-1.44、压力期 0.15-0.40，DSR≤0.64；K2 全不过）；缺口搜索加 T-42 期权到期周、T-43 国会交易 ETF、T-44 ETF 对切换 | 1,010,275 / 42,005,743 |
| 2026-09-29T01:07 | 2026-09-29T02:16 | done | T-20260928-42 + T-20260928-43 + T-20260928-44 + gap search | T-42 期权到期周 0/8（对标窗夏普全负，第 2 周五安慰剂反而更好）；T-43 政治交易 ETF 轮动 0/12（最好 0.90<1.19）；T-44 ETF 对切换 0/12（SMH/QQQ 过 K1 但不如静态 50/50）；缺口搜索加 T-20260929-01 大跌日反弹+重判抄底规则、-02 小盘节前效应；模拟盘值守正常；额度读数不可用（token 过期） | 2,506,992 / 78,835,353 |
