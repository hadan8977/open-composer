# 磁盘管理 Runbook

机主 2026-10-02 要求：磁盘问题自己处理，保证以后不再出现；同日又要求处理要轻，不能影响研究效率。所以现在只有每小时一次、最低优先级的自动检查，研究任务和自动轮不用做任何磁盘相关的事。本文只作参考。

- 执行：`scripts/disk_guard.py`
- 配置：`config/disk-policy.yaml`
- 台账：`reports/ops/disk-ledger.jsonl`，每次清理、归档、删除记一行
- 最新状态：`reports/ops/disk-status.json`
- 日志：`logs/disk_guard.log`

## 1. 为什么要管

- 根分区 `/dev/vda1` 共 217 GB，同时承载机主的线上服务 `/opt/quantcheck`。磁盘写满会让它挂掉（`/opt/gdrive-agent/README.md`）。
- 2026-10-02 早上使用率到了 96%，原因有四个：
  - 2016–2022 年分钟原始归档 `data/sip-hist`（31 GB）早已在 Drive 上，本地还留着一份；
  - pip、uv、npm 缓存和系统日志约 16 GB；
  - `/tmp` 里积了 864 个超过 7 天没动的旧文件，共 2.5 GB；
  - 任务备份 6.4 GB。
- 当时既没有定期清理，也没有"大目录要登记"的规则。
- 已用的 155 GB 里，本仓库占 78 GB，其余是机主或系统的：`/usr` 12 GB、`/root/.hermes` 11 GB、`/root/.cache` 9 GB、`/opt/openwebui-venv` 7.6 GB、`/root/.codex` 4.1 GB、交换文件 4.1 GB 等（2026-10-02 07:14–07:26 UTC 实测）。这些不归本工具清理；配置的 `watch` 清单只报告它们的大小，增长了由机主决定。

## 2. 自动机制

- 每小时 :17 跑一次 `nice -n 19 ionice -c3 .venv/bin/python scripts/disk_guard.py run`。
  - 使用率低于 80% 时，只读一次磁盘用量就结束，不扫目录。
  - 达到 80% 时按顺序清理，降到 75% 就停：
    1. 缓存；
    2. 超过 7 天的 `/tmp` 条目；
    3. 过期备份：先归档到 Drive，核对，再删；
    4. 使用率 ≥90% 时才动温数据：至少 2 年前的分钟年度目录归档后，换成指向 `/mnt/gdrive` 的链接。
- 清理结束只写一份轻量状态（使用率）。全面扫描（`status`）只在需要时手动跑。
- 锁文件 `/tmp/open-composer-disk-guard.lock` 防止两次运行重叠。

## 3. 删除规则（在代码里强制，不只写在配置里）

1. **范围**：只删允许范围（仓库 `data/` 和 `/tmp`）内的路径。
   - 保护清单里的路径不删，包含保护路径的上级目录也不删。
   - 保护清单：`/opt`、`/etc`、`/var/lib`、`/root/.config`、`/root/backup`、`/root/.claude`、`/root/.paseo`、研究快照 `data/research/equity_book`、`data/live/equity_book`、`data/sip/daily`、`data/sec`、`/tmp/claude-0`。
2. **符号链接**：不跟随，也不删除。
3. **正在用的不删**：有进程的工作目录或打开的文件在里面，就不删。
4. **备份先归档**。适用于两类条目：
   - `data/` 下名字像 `backup-*`、`*_backup_*`、`failed-*`、`_*_tmp` 的目录；
   - `/tmp` 里名字像备份或压缩包的条目。

   删除前必须先满足三条：
   - 上传到 Drive 的 `archive/open-composer/...`，逐文件保持原样，不打包；
   - `rclone check --one-way` 退出码为 0，并且报告"0 differences found"；
   - 所属任务在队列里已标为 done 或 cancelled。任务还开着，就不删。
5. **`/tmp` 按年龄删**：看整棵目录树里最新的修改时间，7 天没动才删。`claude-*`、系统目录、socket、锁文件和 uv 缓存永远不按年龄删。
6. **留痕**：每个动作都写一行台账。项目设置里禁止 `rm -rf` 的规则保持不变，删除只走这个工具。

## 4. 研究任务

不用做任何事：不登记目录，不加参数，不查状态。`data/` 下名字像备份的目录会自动保护 7 天，满 7 天后要清理时，也先归档到 Drive 再删。`scripts/run_capped.sh --min-free-gb N` 还在，按需选用，不是必须。

## 5. 升级

清理后使用率仍 ≥90% 时，日志记退出码 3，由交互会话处理。需要机主决定的只有两件：加磁盘，或删除仍在用的数据。

## 6. 恢复

- **归档的备份**：`gdrive download archive/open-composer/<路径> --local <目标>`（会先检查本地空间），或直接读 `/mnt/gdrive/archive/open-composer/<路径>`。
- **温数据**：符号链接指向 `/mnt/gdrive`，读取不用改代码，只是慢一些。要搬回本地，先删掉链接，再 `gdrive download datasets/sip/minute/<年> --local data/sip/minute/<年>`。
- **读 Drive 挂载也占本地盘**：`/mnt/gdrive` 读过的文件缓存在 `/root/.cache/rclone`，最多 20 GB，闲置 1 小时后清掉。大批量读历史数据时要把这 20 GB 算进去。
- **`data/sip-hist`**：2016–2022 年分钟原始归档，从 2026-10-02 起是指向 `/mnt/gdrive/datasets/sip-hist` 的链接。读它的有三处：`scripts/cache_minute_panel.py`、`scripts/build_intraday_daily_features.py`、`open_composer/research/features/intraday_daily.py`。

## 7. 查看

- 状态：`.venv/bin/python scripts/disk_guard.py status`
- 演练，不删任何东西：`.venv/bin/python scripts/disk_guard.py run --all --dry-run`
- 日志：`logs/disk_guard.log`
- 台账：`reports/ops/disk-ledger.jsonl`

## 8. 记录

- **2026-10-02（首次清理）**：共释放 50.95 GB，使用率 96% → 72.3%（07:30 UTC，空闲 61.0 GB）。明细如下（数字出自台账）：
  - `data/sip-hist` 32.40 GB：Drive 上已有完整副本，`rclone check` 0 差异，93,914 个文件一致，本地换成链接。
  - 缓存 9.57 GB：pip 5.46、npm 2.38、journald 1.24、uv 0.49。
  - 过期备份 6.36 GB，共 5 个：先归档到 `archive/open-composer/data/...`，核对后删除。
  - `/tmp` 2.61 GB，864 个条目。其中 6 个像备份的条目先归档到 `archive/open-composer/tmp/`，包括 09-15 的整机状态备份（git bundle、状态包、crontab）。
  - T-20261002-01 的两个备份（共 1.1 GB）在任务关闭前保留。
