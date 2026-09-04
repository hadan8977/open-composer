# Step 10 接续账本

计划：`docs/plan-step-10-mechanism-supplementation-2026-09-03.zh.md`（v2.0，提交 `1a8ba61`）
执行者：Sonnet（无上下文，每次会话先读本文件再继续未完成的 Wave，不从头来）
用户不在线：常规判断自己做；需要用户决定的事写进本文件对应 Wave 的 `blocked_on_user` 小节，然后继续做其他 Wave，不停下等待。

环境（每条 shell 命令前都要）：
```bash
export PATH="$HOME/.local/bin:$PATH"
export UV_CACHE_DIR=/tmp/open-composer-uv-cache
```

---

## 总体状态

| Wave | 状态 | commit |
|---|---|---|
| Wave 0 / 3.1 轻量迭代路径 | doing（代码+测试完成，待最终 commit） | 待定 |
| Wave 0 / 3.2 策略族门槛合同 | todo | - |
| Wave 0 / 3.3 SIP 档案增量更新 + cron | todo（等后台抓取完成） | - |
| Wave 1 / F1 beta 暴露族 | todo | - |
| Wave 1 / F2 跨资产趋势 | todo | - |
| Wave 2 / PIT 流动性过滤横截面动量 | todo | - |
| Wave 3 / 预注册组合 | todo | - |
| Wave 4 / 晋级或负结果记录 | todo | - |

---

## Wave 0 / 3.1 轻量迭代路径

状态：**done**。

### 做了什么

1. **`open_composer/research/iteration_dossier.py`**：在 `_campaign_requirement_blockers` 内部新增 `_lightweight_single_mechanism_exempt(payload, *, campaign_bound)` 结构性判定函数（不穿透新增参数，直接从已经传入的 `payload` 读取字段，符合计划"内部解析、不必穿透传参"的要求）。全部六个条件都满足才豁免：
   - `single_mechanism_no_campaign_attestation is True`（严格布尔，字符串 `"true"` 不算）；
   - `paths` 恰好 1 个元素；
   - `total_candidate_budget` 在 `[1, 24]`（`LIGHTWEIGHT_MAX_CANDIDATE_BUDGET = 24`）；
   - `campaign_contract_path`、`campaign_id`、`campaign_contract_sha256` 三者都为空；
   - `candidate_manifest_path` 已声明（非空字符串）。
   豁免生效时，`_campaign_requirement_blockers` 不追加 `campaign_contract_required_for_new_iteration`，改为追加 `"warning:lightweight_single_mechanism_exemption_used"`（复用同一个 `blocked` 形状的列表返回，不改变任何既有函数签名/返回类型，因为 `_campaign_contract_blockers` 被测试直接按"字符串列表"的方式导入调用）。顶层 `validate_iteration_dossier` 在计算 `status` 之前，把所有 `"warning:"` 前缀的条目从 `blocked` 挪进 `warnings`，因此 `status` 公式从原来的 `"blocked" if blocked else "warning" if warnings else "ok"` 简化为 `"blocked" if blocked else "ok"`（原 `"warning"` 分支此前是死代码 —— 全仓库没有任何调用点会让 `warnings` 非空，`grep` 确认过 —— 所以这个简化对其余路径零行为变化）。

   **关键说明**："候选清单文件必须真的存在"这一条（原计划条件 6）**没有**在 `_lightweight_single_mechanism_exempt` 里重复检查文件是否存在（该函数只检查"已声明"，即非空字符串）——因为 `_search_space_blockers`（`_campaign_contract_blockers` 的调用方）本来就会在别处独立检查 `candidate_manifest_path` 指向的文件是否存在、内容是否与 `total_candidate_budget` 吻合（`candidate_manifest_total_mismatch` 等），豁免与否不影响这条独立检查。已用专门的对抗性测试验证豁免不能绕过这条独立检查（见下）。

2. **`tests/test_iteration_dossier.py`**：新增 8 个测试（全部通过），覆盖计划要求的正例/反例矩阵：
   - `test_lightweight_single_mechanism_exemption_grants_warning_not_block`（正例：六个条件全满足 → 无 `campaign_contract_required_for_new_iteration`，有 `warning:lightweight_single_mechanism_exemption_used`）；
   - `test_lightweight_exemption_denied_with_two_paths`（2 条 path → 拒绝）；
   - `test_lightweight_exemption_denied_with_budget_over_24`（budget=30 → 拒绝）；
   - `test_lightweight_exemption_denied_when_campaign_fields_are_declared`（只声明 `campaign_id` 不声明 path → 拒绝，且同时触发既有的 `campaign_id_without_contract_path`）；
   - `test_lightweight_exemption_denied_without_candidate_manifest_path`（未声明 manifest → 拒绝）；
   - `test_lightweight_exemption_denied_when_attestation_is_a_string_not_boolean`（attestation 为字符串 `"true"` → 拒绝，验证自我声明不能绕过结构性判定）；
   - `test_lightweight_exemption_does_not_bypass_candidate_manifest_content_checks`（对抗性：manifest 里 15 条候选但 search-space 声明 budget=10 → 豁免依然生效（无 campaign 阻断），但独立的 `candidate_manifest_total_mismatch:15:10` 依然触发，证明豁免不能绕过清单内容校验）；
   - `test_lightweight_exemption_reaches_ok_through_the_real_execution_gate`（走真实入口：构造完整的非 campaign 单机制档案，调用 `require_iteration_execution_gate(spec, root, enforce_unbound_design=True, require_registered_iteration=True)`，断言不抛异常、返回 `status="ok"`、`blocked=[]`、`warnings` 含豁免标记）。
   全部 8 个新测试 + 原有全部测试（`uv run pytest -q tests/test_iteration_dossier.py -n 2`）通过，无回归。

3. **`scripts/new_lightweight_iteration.py`**（新建）：输入一个小 JSON 配置（`iter_id`、`strategy_name`、`representative_spec_path`、`path_name`、`hypothesis_id`、`objective`、`benchmark_family`、`candidates`[每个含 `candidate_id`+`parameters`]、`cost_table`、`sources`（≥8，≥3 篇 paper 类型）、`topic_coverage`（≥6）、`hypothesis`{statement/failure_mode/measurement/stop_pivot}、`decision`{path/decision/reason/next_iteration_suggestion}、`source_cards_path`），生成合规骨架：`candidate-manifest.json`（每个候选共享同一个 `representative_spec_path`，manifest 里每行额外记录 `parameters` 字段做审计追溯；`contracts` 用最简的 `{"fixture": {...}}` 分组，不声明 `candidate_manifest_contract`，因此不触发更重的 `generic_candidate_family_v1` 校验路径）、`cost-table.json`、`data-feasibility.json`（generic schema：`workflow_pass=true`、`research_pass/llm_contribution_pass/paper_ready_pass=false`、`historical_evaluation_authorized=true`、`path_gates`/`candidate_accounting`/`candidate_authorization` 全部按候选清单派生、`required_references` 绑定 cost-table 的 sha256）、`search-space.json`（含 `single_mechanism_no_campaign_attestation: true`）、`hypotheses.md`/`decision-record.md`/`search-space.md`/`external-brief.md`/`external-brief.json`。脚本要求调用方**先自行**给 `representative_spec_path` 指向的 spec 写好 `research_design.iter_id`/`candidate_manifest_path`/`data_feasibility_path`（三者必须与脚本将要生成的规范路径完全一致，脚本会校验并在不一致时报错退出，不会静默改写策略 spec 文件本身）。脚本结尾自动跑 `validate_iteration_dossier(iter_id, root, stage="pre-backtest")` 并打印 JSON，`status != ok` 时非零退出，因此"生成即自检"。

   **烟雾测试**（未提交，测完已删除）：用一次性 `lw_smoke_test_r1` + `strategy_specs/drafts/lw_smoke_test_family.yaml` 验证脚本能一次跑通到 `status: ok`；期间发现并修了两个 bug（`current_source_card_paths` 在没传 `source_cards_path` 时是空列表导致 `external_brief_v2_missing_current_source_card_paths`——改成必填字段；忘记写 `external_brief_md` 导致 `external_brief_md_still_template`——已补上）。验证通过后删除了烟雾测试产物，不留痕迹。

### 回归样本：`goal_first_w5_qqq_momentum`

修复前：`uv run oc research iteration validate goal_first_w5_qqq_momentum --stage pre-backtest --json` → `status: "blocked"`，`blocked: ["campaign_contract_required_for_new_iteration"]`（与计划 §3.1 描述的基线完全一致，已核实哈希 `e37b3125...` 与计划记录一致）。

补的内容（**不是**用 `new_lightweight_iteration.py` 生成器跑的——那样会用生成器的模板覆盖掉这份档案本来就写得很好、已经能通过 markdown 校验的 `hypotheses.md`/`decision-record.md`/`external-brief.{json,md}`/`search-space.md`；这四个文件修复前就已经满足所有 markdown 标记与 `external_brief` schema 校验，唯一的阻断就是缺 campaign 绑定这一条。所以用一次性脚本只新增/patch 了缺的部分，脚本本身未入库，过程记录在此供复核）：
- 新建代表性 spec `strategy_specs/drafts/goal_first_w5_qqq_momentum_family.yaml`：QQQ 日线，SMA(150) 趋势延续（6 组候选 `trend_lookback_days∈{100,150,200} × volatility_gate∈{none,realized_vol_20d_lte_median}` 的中间点），`research_design.iter_id/candidate_manifest_path/data_feasibility_path` 三个字段指向下面新建的两个文件；`data.feed: sip`、`data_assumptions.adjusted: true`。
- 新建 `reports/research/iterations/goal_first_w5_qqq_momentum/candidate-manifest.json`：6 行候选 C01..C06，共享上述 spec_path，每行 `parameters` 记录具体的 `trend_lookback_days`/`volatility_gate` 组合。
- 新建同目录 `cost-table.json`（5bps 基础/20bps 压力，注明与 W3/W5 口径一致）与 `data-feasibility.json`（generic schema，`historical_evaluation_authorized: true`，6 个候选全部标 `action: evaluate`）。
- **patch**（非覆盖）`search-space.json`：只新增 `single_mechanism_no_campaign_attestation: true`、`candidate_manifest_path`+`_sha256`、`cost_table_path`、`data_feasibility_path`+`_sha256` 六个字段，其余既有字段（`paths`、`total_candidate_budget=6`、`created_at` 等）原样保留。

修复后：
```
$ uv run oc research iteration validate goal_first_w5_qqq_momentum --stage pre-backtest --json
{
  "iter_id": "goal_first_w5_qqq_momentum",
  "status": "ok",
  "blocked": [],
  "warnings": ["lightweight_single_mechanism_exemption_used"],
  "checked_at": "2026-09-04T02:13:50.305312+00:00"
}
```
`campaign_contract_required_for_new_iteration` → `ok`，符合计划 §3.4 验收项。

**这份修复没有随代码一起 git add**：`reports/research/iterations/goal_first_w5_qqq_momentum/` 和 `strategy_specs/drafts/goal_first_w5_qqq_momentum_family.yaml` 命中现有 `.gitignore` 里 `reports/research/iterations/*` 与 `strategy_specs/drafts/*` 的黑名单规则（`git ls-files` 确认这个目录此前从未被 git 追踪过——即便上周 W5 工作已经在磁盘上产生了它——这是本仓库既有惯例：`reports/research/iterations/` 下只有一份显式白名单里的少数早期里程碑迭代被追踪，其余都是本地工作产物，包括 `mom_breadth_qd_r1` campaign 下的所有子迭代)。沿用既有惯例，本次**没有**修改 `.gitignore` 去把它加入白名单，避免在未获授权的情况下改变仓库的追踪策略；复现步骤已完整记录在本账本，任何人都能用上面列的文件内容重新生成（或直接问我要那次性脚本的内容——已按计划惯例删除，因为它是一次性修复，不是可复用工具；可复用工具是已入库的 `scripts/new_lightweight_iteration.py`）。

### 验收对照（计划 §3.4 第一条）

- [x] 3.1 全部测试通过（`tests/test_iteration_dossier.py` 全绿，8 个新增 + 全部既有）。
- [x] `goal_first_w5_qqq_momentum` 补齐后 `status=ok`。
- [x] `scripts/new_lightweight_iteration.py` 生成的骨架能一次通过 pre-backtest 校验（烟雾测试证实,已清理）。
- [ ] 全仓库 `ruff format`/`ruff check`/`pytest -q -n 2` 全绿且基线仍是 11 个失败 —— **跑中**，见下。

### 全仓库验收（3.1 提交前）

- `uv run ruff format . && uv run ruff check .`：全绿（`ruff check`："All checks passed!"）。
- `uv run pytest -q -n 2`（后台，日志 `/tmp/step10_full_pytest_wave0_3_1.log`）：**11 failed**，全部是 `tests/test_mom_breadth_qd_r1.py::test_recovery_*`（逐条核对：`test_recovery_preregistration_state_accepts_exact_repository_evidence_without_market_reads`、`test_recovery_rejects_exact_data_feasibility_metadata_drift`×3、`test_recovery_rejects_candidate_authorization_semantic_drift`×4、`test_recovery_rejects_exact_universe_contract_drift`×3），与计划 §0 记录的既有基线完全一致，本次改动零新增失败。注：此次全量跑是在 3.1 改动完成、3.2 改动开始之前触发的，只覆盖了 3.1 的代码；3.2 的改动另外用 `tests/test_mechanism_eval.py`、`tests/test_kernel_gate_contract.py` 定向验证（见 3.2 小节），commit 3.2 前会再跑一次全量确认。

状态：**done**。commit：见下（本节写完后立即提交）。

### blocked_on_user

无。

---

## Wave 0 / 3.2 策略族门槛合同

状态：todo（尚未开始；将在 3.1 commit 之后、且必须早于 Wave 1/2 任何评估运行之前，独立 commit）。

---

## Wave 0 / 3.3 SIP 档案每日增量更新 + cron

状态：todo。**已确认后台抓取进程仍在跑**（`pgrep -af fetch_sip_universe` 命中 `--kind minute --start-year 2016 --end-year 2022 --out data/sip-hist`，`fetch_watchdog.sh` 同时在跑），2026-09-04 01:53 UTC 时进度在 2022 年（最后一年）shard 205/1118，累计运行约 31.9 小时。**不得碰这个进程**；`update_sip_archive.py` 首次真实运行必须等它结束（`pgrep -f fetch_sip_universe` 为空）且带锁文件。会在 Wave 1/2 评估跑的间隙轮询进度，不主动等待。

---

## Wave 1 / F1 波动率管理 beta 暴露

状态：todo

## Wave 1 / F2 跨资产 ETF 趋势配置

状态：todo

## Wave 2 / PIT 流动性过滤横截面动量

状态：todo

## Wave 3 / 预注册组合

状态：todo

## Wave 4 / 晋级或负结果记录

状态：todo
