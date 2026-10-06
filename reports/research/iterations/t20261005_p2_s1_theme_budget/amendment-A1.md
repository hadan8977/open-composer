# 修正案 A1（结果之前写，不改任何规则、窗口、门槛、配置或候选）

2026-10-06 01:20 UTC，10-06 01:07 主审轮（Opus）。写入时本合同没有任何结果（`results.json` 不存在，T-20261005-32 状态 ready）。

## 原因

T-20261005-31（10-06 01:07 主审轮审核，接受）：C2 的 DSR 近期 0.566（试验数取上界 47；取下界 25 时 0.691），全期 0.342，低于 P1 档的 0.70；S3 近期 0.815、全期 0.916，过。来源 `reports/research/program/etf-dsr-2026-10-08/results.json`。第二版计划第 9 节写定"DSR < 0.70 的不进试点提议"。所以按现有证据，L1 实盘试点只能是 S3 一条；O1（0.642 S3 + 0.358 C2）仍是模拟盘组合（四条 sleeve 授权到 11-01）的决策对象。

## 改动：只多算一个决策对象

- 第 5 节和简报"Decision"一节的判定（`cost_ok`、`benefit`、`monotone`、`selected`、`pilot_limit`、`mechanical_status`）原样对对象 S3（5 个偏移等权的序列）再算一次，写成 `decision_s3`、`pilot_limit_s3`、`pilot_limit_alternatives_s3`、`mechanical_status_s3`。阈值、窗口、成本、配置、回放日期都不变。
- 需要的数字（`configs["S3"][config_id][window]` 和 `replay[R1..R3]`）本来就在原合同的交付里，所以不加回测路径，试验数不变。
- 执行轮如果已按原简报跑完，这几个字段由脚本从 `results.json` 机械补算，规则以本文件为准，不许看结果后再改。
- O1 的 `pilot_limit` 仍是 T-58 模拟盘组合比较的输入；`pilot_limit_s3` 是 L1 试点（只有 S3）的输入，见 `t20261005_p4_alloc_v2/amendment-A2.md`。
