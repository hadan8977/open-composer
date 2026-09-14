# 归档清单（2026-09）

归档方式：git 分支 `archive/rounds-2026-09` 指向归档前的提交 `c632e61`，工作分支删除文件。
恢复单个文件：`git checkout archive/rounds-2026-09 -- <path>`。
每条记录：路径、行数、原用途、归档原因、残留引用。历史报告目录（`reports/`）一律保留。

## Phase A（2026-09-14）

| 路径 | 行数 | 原用途 | 归档原因 | 残留引用 |
|---|---:|---|---|---|
| `scripts/evaluate_cross_sectional_momentum_liquid500.py` | 580 | Step 10 W2：横截面动量 liquid500 正式候选评估（DuckDB 按时点宇宙 + 月度选股 + 日度盯市） | 其 `_cohort_daily_returns` 仍是 30879b4 修复前的"每日固定权重"收益公式；按时点宇宙查询已抽成 `open_composer/research/features/universe.py`；结论固化在 `reports/research/control/step10-w2-cross-sectional-liquid500-2026-09.md` | 文档字符串提及：`research/kernel/loop.py`、`research/features/universe.py`、`scripts/run_step13_m_grid.py`（均已标注归档） |
| `scripts/duckdb_survivorship_bias_comparison_liquid500.py` | 302 | Step 10 W6：幸存者偏差重测 | 同一收益公式；报告已固化于同一文件 | 无代码引用 |

## Phase B（待 W2 提交后执行）

按 `docs/codemap/codemap.json` 中 `rounds` 节点的 `files` 与 `tests` 列表归档，届时补记于此。
