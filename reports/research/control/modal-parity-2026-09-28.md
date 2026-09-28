# Modal 运行器一致性检查（2026-09-28）

**结论：通过。** 在 Modal 上原样重跑 H-20260928-01（S3 分批调仓，21 个调仓日偏移 + T4），`results.json` 的 1326 个数值字段和本机提交的结果最大绝对差 2.2e-16（浮点舍入量级），唯一不同的字段是生成时间 `generated_at`。以后经 `scripts/modal_run.py` 跑出的结果可以直接当本机结果使用。

| 项目 | 内容 |
|---|---|
| 命令 | `python3 scripts/modal_run.py --job h20260928-01-parity --cpu 2 --memory-gib 4 --timeout-min 20 --data data/sip/daily --data <manifest> --data <search-space> --out reports/research/iterations/h20260928_01_s3_rebalance_tranching --fetch-to <scratch> -- uv run python -u scripts/run_h20260928_01_s3_rebalance_tranching.py` |
| 资源 | 2 核 / 4 GiB，无 GPU |
| 容器内耗时 | 约 23–42 秒（第一次读卷上 3,734 个日线分片约 110 秒，之后有缓存） |
| 花费 | 每次约 $0.001–0.04；到 06:10 UTC 本月累计已出账单 $0.07 |
| 比对方法 | 递归比对两份 JSON 的每个数值字段；NaN 视为相等 |

## 过程中修掉的问题

1. **第一次运行 20 分钟超时，看不到进度**：原来的写法只在命令结束后才回传输出。已改成边跑边输出（带秒数），超时时也能看到卡在哪一步。那次超时之后，同一命令在 42 秒内跑完，推测是第一次读卷上数据很慢。
2. **打包结果时报错**：`TarFile.add()` 没有 `dereference` 参数，应该在 `tarfile.open()` 上设置。已修正。

## 使用要点

- 数据按需同步到卷 `oc-data`（本地清单 `reports/research/control/modal-data-manifest.json`，大小和修改时间不变就跳过）；卷存储每 GiB 每月 $0.09，一轮测试结束后删除大数据。
- 代码按白名单上传，不含 `.env`、密钥、`data/`、`reports/`；上传前扫描密钥。
- 容器内线程数设为申请核数的两倍（1 个 Modal 核 = 2 vCPU）。
- 所有启动都先过 `scripts/modal_budget.py check`（本月上限 $25）。
