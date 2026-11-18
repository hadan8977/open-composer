# OpenComposer 运行与分工

| 工作 | 位置和入口 |
|---|---|
| 研究、代码、数据和知识维护 | Windows `C:\OpenComposer\repo`。研究流程见 [研究入口](../research/README.md)，行情见 [本地行情目录](local-data-catalog.zh.md)。 |
| 重型计算 | Windows 通过 `scripts/modal_run.py` 使用 Vault 档案 `modal-zhoucehuang`，回收结果后在同一研究目录继续。额度规则见 [项目约束](rules.md)。 |
| 纸盘、刷新、对账和网站 | VPS `/root/codex-test/open-composer`，股书刷新和六策略推理使用 `/root/codex-test/oc-paper-recovery-20261103` 中绑定的输入。 |
| 主机状态、工具和恢复收据 | `C:\OpenComposer\ops`，状态见 `STATUS.zh.md`，SSH 入口为 `ssh.cjs`。 |

## 本机研究

本机沿用原任务、原会话和冻结输入。第四轮按机主要求暂停，`control.json`
中 `research=false`。当前轮次、证据和恢复方法见
[研究入口](../research/README.md)及[知识工具](research-tools.md)。新研究暂停期间，
行情维护和纸盘运行仍按各自既有权限执行。2026 年 9 月 1 日后的行情供 OOS 使用。

Windows 数值作业用 `scripts/run_capped.py`：每个作业一个原生 Job Object，限制提交内存，
超时、中断或控制进程退出时整棵进程树一起结束；内存预算读取 `config/memory-budget.json`。
需要 Nautilus 撮合扩展或更大计算时使用 Modal，Windows 本地受阻的原生扩展保留系统保护。Hadan 的现有独立契约仍由
`config/windows-paseo-worker.json` 和 [项目约束](rules.md)管理。

## VPS 运行

- 网站由 `quant.service` 和 `cloudflared-quant.service` 提供。
  用 `systemctl is-active` 及网站 `/`、`/healthz`、`/paper` 检查。
- 六策略由 `oc-six-paper-validation.service` 运行，输入绑定在
  `config/paper/six-service.json` 和目标收据，复现代码在
  `research/paper_recovery_20261103` 及 `open_composer/paper_runtime`。
- ETF 与股书的原时钟由实际 crontab 定义。股书输入可用
  `scripts/refresh_book_v12_current_units.py --check-ready --equity-basis 300000`
  检查，`scripts/run_book_v12_daily.py --plan --accounts quant1 --equity-basis 300000`
  生成计划。已授权的运行命令由原调度执行。
- VPS 运行使用原 Git 检出及各服务现有环境。纸盘命令用
  `scripts/run_capped.sh --class paper`。网站、服务及调度的近期结果以服务器日志和纸盘回执为准。
  磁盘巡检由 `scripts/disk_guard.py` 按 `config/disk-policy.yaml` 执行，日志在 `logs`。
- 日报仍由原邮件计划发送。发送权限、内容和读者见 [汇报规则](owner-reporting.zh.md)。

## 恢复

使用 [私有快照恢复说明](private-checkpoint-backup.zh.md)中的明确快照和
`C:\OpenComposer\opsackup` 下的原收据。私有研究和账本保留在本机，
公开 GitHub 的发布范围须由机主决定。研究输入、策略模型和纸盘授权根据其原绑定恢复。
