# 归档清单（2026-09）

归档方式：git 分支 `archive/rounds-2026-09` 指向归档前的提交 `c632e61`，工作分支删除文件。
恢复单个文件：`git checkout archive/rounds-2026-09 -- <path>`。
每条记录：路径、行数、原用途、归档原因、残留引用。历史报告目录（`reports/`）一律保留。

## Phase A（2026-09-14）

| 路径 | 行数 | 原用途 | 归档原因 | 残留引用 |
|---|---:|---|---|---|
| `scripts/evaluate_cross_sectional_momentum_liquid500.py` | 580 | Step 10 W2：横截面动量 liquid500 正式候选评估（DuckDB 按时点宇宙 + 月度选股 + 日度盯市） | 其 `_cohort_daily_returns` 仍是 30879b4 修复前的"每日固定权重"收益公式；按时点宇宙查询已抽成 `open_composer/research/features/universe.py`；结论固化在 `reports/research/control/step10-w2-cross-sectional-liquid500-2026-09.md` | 文档字符串提及：`research/kernel/loop.py`、`research/features/universe.py`、`scripts/run_step13_m_grid.py`（均已标注归档） |
| `scripts/duckdb_survivorship_bias_comparison_liquid500.py` | 302 | Step 10 W6：幸存者偏差重测 | 同一收益公式；报告已固化于同一文件 | 无代码引用 |

## Phase B（2026-09-14 执行）

### Phase B 归档（2026-09-14）

93 个 Python 文件、123,338 行，加 4 个 systemd 单元文件。规则：`docs/codemap/codemap.json` 的 `rounds` 节点（按轮次一次性研究模块及其测试），
外加只服务这些模块的 `scripts/run_r7_forward_observation.py` 与 `deploy/systemd` 下的 r7/r23 单元。
保留：`open_composer/research/etf_structural_r9.py` 与 `tests/test_etf_structural_r9.py`（产品适配器 `etf_structural_target_weights.py` 仍导入它，等 C1 决定）；
`tests/test_iteration_dossier.py`、`tests/test_research_campaign.py` 只删去各自 1 个引用轮次模块的用例。
`open_composer/cli.py` 删除 28 条 `oc strategy *-r4…r23-*` 命令和 `target-weights` 里 r5/r7 两个按 iter_id 分支。
历史产物（`reports/research/iterations/*`、`reports/forward/*`、`strategy_specs/drafts/us_*_r*_*.yaml`）全部保留，只是不能再由代码重新生成。

| 路径 | 行数 | 类型 |
|---|---:|---|
| `open_composer/research/multiasset_forward_multimodal_r5.py` | 8959 | 研究模块 |
| `open_composer/research/multiasset_forward_multimodal_r4.py` | 4903 | 研究模块 |
| `open_composer/research/mom_breadth_qd_r1.py` | 4672 | 研究模块 |
| `open_composer/research/high_beta_sleeve_ensemble_r1.py` | 3490 | 研究模块 |
| `open_composer/research/vix_term_structure_overlay_r1.py` | 3369 | 研究模块 |
| `open_composer/research/pit_semantic_theme_r23_forward.py` | 3048 | 研究模块 |
| `open_composer/adapters/execution/multiasset_forward_multimodal_r5_target_weights.py` | 2609 | 适配器 |
| `open_composer/research/pit_semantic_theme_forward.py` | 2507 | 研究模块 |
| `open_composer/research/core_satellite_r7.py` | 2493 | 研究模块 |
| `scripts/prepare_mom_breadth_qd_r1.py` | 2443 | 脚本 |
| `scripts/prepare_vix_term_structure_overlay_r1.py` | 2331 | 脚本 |
| `open_composer/research/pit_semantic_theme_r22_forward.py` | 2305 | 研究模块 |
| `open_composer/research/pit_semantic_theme_r11.py` | 2263 | 研究模块 |
| `open_composer/research/pit_semantic_theme_r24.py` | 2134 | 研究模块 |
| `open_composer/research/multiasset_forward_multimodal_r6.py` | 2108 | 研究模块 |
| `scripts/prepare_pit_semantic_theme_r24.py` | 2019 | 脚本 |
| `open_composer/research/multiscale_low_turnover_r6.py` | 1973 | 研究模块 |
| `open_composer/research/robust_momentum_r4.py` | 1957 | 研究模块 |
| `scripts/prepare_pit_semantic_theme_r23.py` | 1906 | 脚本 |
| `open_composer/research/dynamic_theme_chain_r8.py` | 1779 | 研究模块 |
| `open_composer/research/pit_semantic_theme_r22.py` | 1744 | 研究模块 |
| `open_composer/research/pit_semantic_theme_r21.py` | 1727 | 研究模块 |
| `open_composer/research/pit_semantic_theme_r20.py` | 1726 | 研究模块 |
| `open_composer/research/pit_semantic_theme_r19.py` | 1669 | 研究模块 |
| `open_composer/research/pit_semantic_theme_r17.py` | 1657 | 研究模块 |
| `open_composer/research/pit_semantic_theme_r18.py` | 1657 | 研究模块 |
| `open_composer/research/pit_semantic_theme_r16.py` | 1582 | 研究模块 |
| `open_composer/research/pit_semantic_theme_r15.py` | 1580 | 研究模块 |
| `open_composer/research/pit_semantic_theme_r14.py` | 1577 | 研究模块 |
| `open_composer/research/dynamic_theme_chain_r8_ml.py` | 1554 | 研究模块 |
| `scripts/prepare_high_beta_sleeve_ensemble_r1.py` | 1554 | 脚本 |
| `open_composer/research/pit_semantic_theme_r13.py` | 1527 | 研究模块 |
| `open_composer/research/multiscale_event_r5.py` | 1467 | 研究模块 |
| `scripts/prepare_pit_semantic_theme_r20.py` | 1394 | 脚本 |
| `scripts/prepare_pit_semantic_theme_r22.py` | 1354 | 脚本 |
| `scripts/prepare_pit_semantic_theme_r18.py` | 1343 | 脚本 |
| `scripts/prepare_pit_semantic_theme_r21.py` | 1341 | 脚本 |
| `scripts/prepare_pit_semantic_theme_r17.py` | 1327 | 脚本 |
| `scripts/prepare_pit_semantic_theme_r19.py` | 1298 | 脚本 |
| `scripts/prepare_pit_semantic_theme_r14.py` | 1295 | 脚本 |
| `scripts/prepare_pit_semantic_theme_r16.py` | 1263 | 脚本 |
| `scripts/prepare_pit_semantic_theme_r13.py` | 1262 | 脚本 |
| `scripts/prepare_pit_semantic_theme_r15.py` | 1256 | 脚本 |
| `open_composer/research/dynamic_theme_stock_r9_evaluation.py` | 1200 | 研究模块 |
| `open_composer/research/pit_semantic_theme_r12.py` | 1179 | 研究模块 |
| `open_composer/research/event_seeded_theme_stock_r10.py` | 1145 | 研究模块 |
| `open_composer/research/multiasset_paper_control_r7.py` | 1114 | 研究模块 |
| `open_composer/adapters/execution/multiasset_paper_control_r7_target_weights.py` | 939 | 适配器 |
| `open_composer/research/dynamic_theme_stock_r9.py` | 900 | 研究模块 |
| `open_composer/research/spy_dual_trend_r8.py` | 817 | 研究模块 |
| `scripts/prepare_pit_semantic_theme_r12.py` | 780 | 脚本 |
| `open_composer/research/event_seeded_theme_stock_r10_evaluation.py` | 604 | 研究模块 |
| `open_composer/adapters/data/multiasset_paper_control_r7_snapshot.py` | 257 | 适配器 |
| `open_composer/research/pit_semantic_theme_r24_forward.py` | 147 | 研究模块 |
| `tests/test_multiasset_forward_multimodal_r5.py` | 3353 | 测试 |
| `tests/test_mom_breadth_qd_r1.py` | 2667 | 测试 |
| `tests/test_vix_term_structure_overlay_r1.py` | 1377 | 测试 |
| `tests/test_multiasset_forward_multimodal_r4.py` | 1002 | 测试 |
| `tests/test_multiasset_forward_multimodal_r5_target_weights.py` | 1530 | 测试 |
| `tests/test_high_beta_sleeve_ensemble_r1.py` | 561 | 测试 |
| `tests/test_pit_semantic_theme_r24.py` | 630 | 测试 |
| `tests/test_pit_semantic_theme_r21.py` | 472 | 测试 |
| `tests/test_pit_semantic_theme_r22.py` | 480 | 测试 |
| `tests/test_pit_semantic_theme_r20.py` | 451 | 测试 |
| `tests/test_pit_semantic_theme_r17.py` | 401 | 测试 |
| `tests/test_pit_semantic_theme_r18.py` | 403 | 测试 |
| `tests/test_pit_semantic_theme_r19.py` | 403 | 测试 |
| `tests/test_core_satellite_r7.py` | 239 | 测试 |
| `tests/test_dynamic_theme_chain_r8.py` | 295 | 测试 |
| `tests/test_event_seeded_theme_stock_r10.py` | 311 | 测试 |
| `tests/test_multiscale_event_r5.py` | 170 | 测试 |
| `tests/test_multiscale_low_turnover_r6.py` | 207 | 测试 |
| `tests/test_pit_semantic_theme_r11.py` | 204 | 测试 |
| `tests/test_pit_semantic_theme_r23_forward.py` | 624 | 测试 |
| `tests/test_robust_momentum_r4.py` | 171 | 测试 |
| `tests/test_multiasset_forward_multimodal_r6.py` | 244 | 测试 |
| `tests/test_pit_semantic_theme_forward.py` | 455 | 测试 |
| `tests/test_pit_semantic_theme_r13.py` | 332 | 测试 |
| `tests/test_pit_semantic_theme_r14.py` | 312 | 测试 |
| `tests/test_pit_semantic_theme_r15.py` | 312 | 测试 |
| `tests/test_pit_semantic_theme_r16.py` | 314 | 测试 |
| `tests/test_dynamic_theme_chain_r8_ml.py` | 414 | 测试 |
| `tests/test_pit_semantic_theme_r22_forward.py` | 462 | 测试 |
| `tests/test_dynamic_theme_stock_r9.py` | 249 | 测试 |
| `tests/test_pit_semantic_theme_r12.py` | 157 | 测试 |
| `tests/test_high_beta_sleeve_ensemble_r1_semantic.py` | 118 | 测试 |
| `tests/test_multiasset_paper_control_r7_forward_snapshot.py` | 88 | 测试 |
| `tests/test_multiasset_paper_control_r7_target_weights.py` | 272 | 测试 |
| `tests/test_spy_dual_trend_r8.py` | 65 | 测试 |
| `tests/test_dynamic_theme_stock_r9_evaluation.py` | 50 | 测试 |
| `tests/test_event_seeded_theme_stock_r10_evaluation.py` | 102 | 测试 |
| `tests/test_pit_semantic_theme_features_labels_and_embargo_use_registered_timing.py` | 906 | 测试 |
| `scripts/run_r7_forward_observation.py` | 31 | 脚本 |
| `deploy/systemd/open-composer-r7-forward-observation.service` | - | systemd 单元（本机已 masked/disabled） |
| `deploy/systemd/open-composer-r7-forward-observation.timer` | - | systemd 单元（本机已 masked/disabled） |
| `deploy/systemd/open-composer-r23-tier0-observation.service` | - | systemd 单元（本机已 masked/disabled） |
| `deploy/systemd/open-composer-r23-tier0-observation.timer` | - | systemd 单元（本机已 masked/disabled） |
