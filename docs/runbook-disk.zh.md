# 磁盘管理 Runbook

机主 2026-10-02 要求：磁盘问题自己处理，保证以后不再出现，最好有动态或定期的处理和一套规则。本文是规则。

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

| 何时 | 做什么 |
|---|---|
| 每小时 :17 `disk_guard.py run` | 使用率 ≥80% 才动手，降到 75% 就停。顺序见下方。 |
| 每天 06:40 UTC `disk_guard.py run --all` | 日常卫生：不看阈值，清掉所有符合条件的项目，然后写状态文件。 |
| 重任务启动前 `scripts/run_capped.sh --min-free-gb 15 -- ...` | 空闲不足 15 GB 时先跑一次清理；仍不够就拒绝启动，退出码 75。 |

- 每小时一次的清理按这个顺序：
  1. 缓存；
  2. 超过 7 天的 `/tmp` 条目；
  3. 过期备份：先归档到 Drive，核对，再删；
  4. 温数据，只在使用率 ≥90% 时动：至少 2 年前的分钟年度目录归档后，换成指向 `/mnt/gdrive` 的符号链接。
- 不带 `--min-free-gb` 的命令（例如模拟盘定时任务）不会被拒绝；空闲低于 10 GB 时只打印警告。
- 锁文件 `/tmp/open-composer-disk-guard.lock` 防止两次运行重叠，后来的一次直接退出。
- 定时任务用 `.venv/bin/python` 直接跑，不用 `uv run`：uv 运行期间占着缓存锁，`uv cache prune` 会一直等它。每条缓存命令最多等 300–900 秒。

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

## 4. 研究任务要遵守的规则（人和代理都一样）

1. **登记大目录**：在 `data/` 下新建超过 1 GB 的目录，要在 `config/disk-policy.yaml` 里登记类别（hot、backup 或 warm）。
   - `disk_guard.py status` 会列出没登记的大目录和名字可疑的目录（tmp、backup、old、copy、failed 等）。
   - 主审轮看到后，当轮登记或处理。
2. **临时文件**：放在 `/tmp/<任务代码>/`，任务结束时自己删。不要放进 `data/`。
3. **备份目录**：命名为 `backup-<内容>-<日期>`，在配置的 `backups` 里写明 `owner` 和 `hold_task`。
   - 任务关闭且满 7 天后，自动归档并删除。
   - 要保留更久，就改登记为 hot，或者手动归档：`disk_guard.py archive <路径> --remote archive/open-composer/<路径>`。
4. **下载前先看空间**：
   - 本地放不下的数据，读 `/mnt/gdrive` 只读挂载，或用 `gdrive download --subset` 只取一部分。
   - Drive 上已有的历史数据，不要整份拉回本地。
5. **写数据的重任务**用 `run_capped.sh --min-free-gb 15`。

## 5. 升级阶梯

| 使用率 | 自动处理 | 主审轮或机主 |
|---|---|---|
| <80% | 每天 06:40 日常清理 | 不用管 |
| 80–90% | 每小时清理，到 75% 为止 | 主审轮看 `disk-status.json` 里没登记的大目录，登记或清理 |
| ≥90% | 再加上温数据归档并换成链接 | 主审轮必须处理，暂停新的写数据重任务 |
| 清理后仍 ≥90% | 日志里记退出码 3 | 通知机主。需要机主决定的只有两件：加磁盘，或删除 hot 数据 |

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
