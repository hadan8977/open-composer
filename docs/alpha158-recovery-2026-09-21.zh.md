# Alpha158 宽池特征构建恢复（2026-09-21）

目标是恢复可重复、内存有界的特征构建，供后续既有研究使用。这里不是新策略实验，没有训练、回测、晋升或模拟下单。

## 先查外部依据

联网核查时间：2026-09-21 13:39 UTC。DuckDB 官网 HTML 在本次请求返回 403，转读其官方 GitHub 文档源；未将访问失败伪装为证据。

| 官方来源 | 获取结果与具体依据 | 内容 SHA-256 |
| --- | --- | --- |
| https://raw.githubusercontent.com/duckdb/duckdb-web/main/docs/current/sql/statements/copy.md | `COPY (SELECT ...) TO ...` 可直接将查询结果写入 Parquet；`ROW_GROUP_SIZE` 控制写出分组大小。 | `6470f80a942a081f21e971b02609cc37a58b89336b8901c5ca1333b967f7008a` |
| https://raw.githubusercontent.com/duckdb/duckdb-web/main/docs/current/guides/performance/how_to_tune_workloads.md | 大于内存的数据可借助磁盘 spill；显式设置临时目录和线程数；排序属于阻塞算子，不能声称所有操作天然恒定内存。 | `4f2fca991da3c0d8e532f6465558615e8731e8aeda339af50a00def7c3cb3588` |
| https://raw.githubusercontent.com/microsoft/qlib/main/qlib/contrib/data/loader.py | `Alpha158DL` 默认滚动窗口为 5/10/20/30/60，另有 OPEN/HIGH/LOW/VWAP 的 PRICE 项。本项目原先只实现 154 个特征，本次保留此定义，没有声称完整复刻 158 列。 | `814b7f7ab3d418ae3c87ce352220080b239eba2670eac9e38376b794be4075cb` |

## 实际故障和修复边界

原程序把每批 DataFrame 放入 `batch_frames`，续跑又把所有 checkpoint 读回内存，最后整年 concat+sort。31 个分片已经算完，但每次恢复仍在合并时触发同一内存风险；仅称其“分片运行”不能解决问题。

现在每批最多 100 个符号，默认 DuckDB 缓冲预算 600 MB；已有公式加载连接固定 2 个线程，合并连接固定 1 个线程。合并通过 DuckDB 磁盘 spill 排序并 COPY 输出，小行组 4096；不把全年结果或全部 checkpoint 放回 pandas。外部 `run_capped.sh --mem 1.8G` 仍是进程级硬上限，DuckDB 设置不是 Python 全进程内存保证。

每轮按数据文件内容 SHA-256、精确符号集、批大小、窗口、公式和构建代码版本建立 checkpoint 身份；计算只读取显式冻结的文件清单，完成前再次校验输入哈希。分片、输出、manifest、完成标志分别原子替换；完成标志最后发布。文件锁阻止同一输出目录并发写入。中断留下的无标志分片会重新计算，已验证分片可恢复；损坏分片拒绝复用。

老的无身份分片保留在原目录，不把其来源猜测成已验证身份。新分片在 `_scratch/<year>/<identity_sha256>/` 内。有效分片保留供中断恢复，后续可在确认完成之后单独清理，当前不自动删除。

## 当前真实状态

2026-09-21 13:39 UTC：`data/features/alpha158_broad` 无已完成年度 Parquet；`_scratch/2016` 有 31 个旧分片，合计 1,152,395,894 字节，序号 000–030；没有运行中的构建进程。这些文件仍保留。尚未运行整池特征重建，也未验证真实年度规模的峰值 RSS。

## 已停用的旧定时任务

只删除 `alpha158_broad_nightly.sh` 与 `etf_pool_placebo_nightly.sh` 的 start/stop 四行，保留另外 19 行的字节内容和顺序；未修改任何模拟盘任务。

- 备份：`/root/.local/state/open-composer/cron-backups/crontab-before-alpha158-recovery-20260921T134220Z.txt`，权限 0600。
- 原 crontab SHA-256：`7edcbc629aa99215032b7e9e584cfdbf1083cb6856608ba15a79c3e815d84cb1`。
- 删除目标四行后的其余内容 SHA-256：`2339673817b484fca3c8e3fa5b47dd593ac86538f8b64e6cb9e53ca60dd37bb7`。
- 安装后重新读回，逐字节一致；没有创建替代 cron。

## 验收与下一步

聚焦测试：`uv run pytest tests/test_alpha158_build_streaming.py tests/test_alpha158_features.py`。
覆盖 154 列数值与旧 concat/sort 路径的精确比较、空分片、键重复拒绝、数据内容更改（文件大小和 mtime 不变）、分片损坏、模拟中断恢复、旧分片保留、超限批大小拒绝。本次聚焦验证 15 passed（17.70 秒），两个 Python 文件的 ruff format/check 与夜间脚本 bash -n 均通过；全仓测试由集成方另行运行。

真实数据的下一项有界验收建议只运行 2016 年，并记录峰值 RSS、退出码、行数和完成身份：

```bash
./scripts/run_capped.sh --mem 1.8G -- /usr/bin/time -v uv run python scripts/build_alpha158_features.py --years 2016 --universe-root data/features/universe_broad --out-dir data/features/alpha158_broad --extra-daily-root data/sip-delisted/by_year --symbol-batch-size 100 --memory-limit 600MB
```

本次实现者没有启动此命令。应先由集成方完成测试，再在已有长任务资源预算和研究优先级下执行；不能将特征表构建完成误报为策略有收益或可模拟交易。

## 集成方的真实分片试验

2026-09-21 使用两个现有旧分片，仅验证新合并器的资源行为，输出在临时目录生成后丢弃，未当成可研究的正式特征表：输入 73,785,891 bytes，71,492 行；DuckDB 256 MB，进程硬帽 900 MB；合并 3.45 秒，进程总耗时 4.46 秒，峰值 RSS 304,816 KiB，退出码 0。机读记录：`reports/research/control/alpha158-merge-pilot-20260921.json`。

这个结果验证了真实分片可以在有限内存中合并；它不证明整年构建完成，也不为无来源身份的旧分片补造 provenance。整年/全历史重建仍未启动。
