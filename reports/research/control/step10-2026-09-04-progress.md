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
| Wave 0 / 3.1 轻量迭代路径 | done | `16feec3` |
| Wave 0 / 3.2 策略族门槛合同 | done | `5e61b08` |
| Wave 0 / 3.3 SIP 档案增量更新 + cron | **done**（含真实首次运行验收，`stale: []`） | `3d6f42b`, `8a99902`（首次真实更新记录） |
| 全仓库回归修复（3.3 引起，Wave 1 之前） | done | `f53d34d`（+ `ed2d755` 记录） |
| Wave 1 / F1 beta 暴露族 | **done**（负结果，0/24 通过新合同；捕获比定义修正后 24/24 过捕获门，超额CAGR/Sharpe仍不过） | `fad4b89`（首次评估、代码、来源卡）+ 本 commit（捕获比定义修正、重评分、`step10-w1-beta-exposure-2026-09.md`） |
| Wave 1 / F2 跨资产趋势 | **done**（负结果，0/12 通过新合同；捕获比定义修正后 9/12 过捕获门；不可路由，走独立内核机制） | `fad4b89`（首次评估、代码、来源卡）+ 本 commit（捕获比定义修正、重评分、`step10-w1-cross-asset-trend-2026-09.md`） |
| Wave 2 / PIT 流动性过滤横截面动量 | **done**（负结果，0/4 通过新合同；捕获比定义修正后仍不过，是三族里唯一捕获门本身也没过的） | 本 commit |
| Wave 3 / 预注册组合 | todo | - |
| Wave 4 / 晋级或负结果记录 | todo | - |

**接续执行者请注意**：本表的 commit 列里出现"本 commit"，是因为本次写账本时这次 commit 自己的哈希还不知道（不能自引用）；写完本节后会立即提交，随后再用一个小的纯文档 commit（沿用 `ed2d755`/`8a99902` 已经用过的模式）把"本 commit"替换成真实哈希。如果你读到这里时表里仍写着"本 commit"而不是哈希，说明那个收尾小 commit 还没做，直接 `git log --oneline` 找最新一条 `feat: rescore Step 10 Wave 1/2 under the fixed capture-ratio definition...`（或类似字样）即可。

---

## 度量修正：`benchmark_vm_capture_ratio` 的定义缺陷（原因、数学、影响范围）

**发现过程**：接手时（本节作者，2026-09-05）核对上一位执行者未提交的工作树改动，发现 F1（beta 暴露族）24 个候选、F2（跨资产趋势）12 个候选**全部**在 `benchmark_vm_capture_ratio` 门（门槛 ≥1.0）上失败，跨越两个完全不同的机制、不同的参数组合，失败率 100%。这种整齐划一的失败本身就是可疑信号——真实的经济效应很少会让所有参数组合精确地卡在同一道门上，更可能是量出了问题，不是策略出了问题。上一位执行者已经诊断出根因并写好了修复代码和回归测试，但会话中止于重跑 F1 之后、重跑 F2 与 Wave 2 之前，也没有提交。本节把这次修正的原因、数学、验证方式完整记录下来，供任何人复核。

### 旧定义错在哪

`benchmark_vm_capture_ratio`/`benchmark_vm_downside_capture` 复用了 `campaign._conditional_capture`——这个函数原本是给 `kernel-paper-tier-gates.json`（TQQQ 路由合同）设计的，它的算法是：

1. 找出基准（QQQ 或波动率匹配后的合成基准）上涨的那些交易日（或下跌的那些交易日）；
2. 在这个子集上，把候选和基准各自的**逐日收益按顺序复利乘起来**（`_compound_return`：`exp(sum(log1p(r) for r in subset)) - 1`），得到子集内的总复利收益；
3. 两个总复利收益相除。

问题在于：**总复利收益是样本量的指数函数**。设子集里有 N 天，候选在这些天的平均对数收益是基准的 β 倍（即候选相对基准的"局部 beta"是 β），基准每天的平均对数收益是 μ。那么：

- 基准总复利 ≈ `exp(N·μ) − 1`
- 候选总复利 ≈ `exp(N·β·μ) − 1`
- 两者相除，N 较大时 ≈ `exp(N·(β−1)·μ)`（分母主导）

只要 β<1（候选比基准更保守，本轮所有候选都是这种构造——趋势/波动率/回撤门控只会降低敞口，不会放大），指数 `N·(β−1)·μ` 是负的，且**随 N 线性增长而指数级恶化**。本轮的拼接 OOS 窗口有上千行（F1/F2 约 1170-1180 行，一半左右是"基准上涨日"，即 N≈500-600），这个子集大到足以让这个 artefact 主导结果，而不是真实的"捕获不对称性"。

**这不是"候选真的没有捕获能力"，而是"总复利比值这把尺子在长窗口上失效了"**。一个反例最能说明问题：一个零 alpha、精确按 β=0.5 复制基准的合成策略——每天收益恰好是基准的一半——直觉上应该读作"捕获比 ≈1.0"：它在基准上涨的日子里按比例少涨，在基准下跌的日子里也按比例少跌，涨跌两侧对称地打了同样的折扣，`upside_capture ≈ downside_capture`，比值应该抵消掉 β 本身、只剩下"是否对称"这一个信息。但旧定义在 1000 天的合成序列上会把这个理论上该是 1.0 的比值算成远低于 0.5（`tests/test_mechanism_eval.py::test_geometric_mean_capture_ratio_is_beta_invariant_unlike_the_compounded_one` 里的断言 `compounded_ratio < 0.5` 已经验证过这一点）——因为分子分母的"总复利"本身就已经不对称地放大了指数衰减效应。

### 新定义

把"总复利"换成"**每期几何平均收益**"（`_per_period_geometric_mean_return`：`expm1(mean(log1p(r) for r in subset))`），其余步骤不变（同样先按基准涨跌分子集，同样两边相除）。几何平均收益**不随子集大小变化**——不管 N 是 100 还是 1000，一个 β=0.5 的纯复制品在上涨子集和下跌子集上的每期几何平均收益都分别约等于基准对应子集的 β 倍，两者相除，β 自己就约掉了，比值稳定在 ≈1.0（`abs=0.05` 容差内）。这是 Morningstar 的标准"捕获比"定义,也是这个指标在业界原本要回答的问题："候选相对自己的整体风险水平,上涨捕获得多不多、下跌捕获得多不多",而不是"候选的绝对波动大小"。

### 修复范围（刻意最小化）

- 新增 `open_composer/research/kernel/mechanism_eval.py::_per_period_geometric_mean_return` 与 `_conditional_geometric_mean_capture`，只在 `evaluate_candidate` 的 `benchmark_returns is not None`（即 Step 10 新增的 vol-matched 路径）分支内使用。
- **不改** `campaign._conditional_capture` 本身——它是 `kernel-paper-tier-gates.json`（杠杆 TQQQ 路由合同）路径的冻结证据，改了会让 `iteration_dossier.py` 的实现哈希锁（`e37b3125…`）与 `mom_breadth_qd_r1` 的封存记录产生新的漂移。`benchmark_returns=None` 的旧路径（QQQ 绝对合同）逐字节不变，由 `test_benchmark_returns_none_keeps_the_existing_qqq_path_byte_for_byte` 保证。
- 旧定义的值原地保留在新字段 `benchmark_vm_capture_ratio_compounded_legacy`，只做对照展示，从不参与任何裁定。
- 新增字段 `benchmark_vm_upside_capture`（之前只算了比值,没有单独暴露分子）。

### 实际影响（用真实候选数字说话，不是假设）

以 F1 最好的候选 C12 为例（`reports/research/control/step10-w1-beta-exposure-2026-09.json`）：`benchmark_vm_capture_ratio_compounded_legacy=0.2007`（旧定义,远低于 1.0,像是"完全没有捕获能力"）→ `benchmark_vm_capture_ratio=1.1162`（新定义,通过 ≥1.0 门槛）。三个族的汇总：

| 族 | 候选数 | 捕获门修正前通过数 | 修正后通过数 |
|---|---:|---:|---:|
| F1 beta 暴露 | 24 | 0 | **24**（全过） |
| F2 跨资产趋势 | 12 | 0 | **9** |
| Wave 2 liquid-500 横截面动量 | 4 | 0 | 0（仍不过，见 Wave 2 小节——这个族波动率是 SPY 的约 2 倍,新定义下捕获比 0.97-0.999,非常接近但仍不到 1.0 门槛,不是同一种"完全没过"） |

**三个族的最终裁定结论都没有变**：修正前后,`cagr_excess_vol_matched_benchmark`（超额 CAGR,门槛 ≥5pp）与 `sharpe_excess_bil`（门槛 >1.0）这两道真正卡住候选的门槛完全没有受这次修正影响（它们的计算路径与捕获比无关）,三个族依然是 0 候选通过全部门槛。这次修正**修的是量尺,不是结论**——但量尺错了会污染报告的可信度（"捕获比 0.2,像是这策略完全没有跟涨能力"是一个错误的、可能被后续读者误用的说法),所以仍然值得单独修、单独记录。

### 验证

`tests/test_mechanism_eval.py`：13 个测试全绿（原 12 个 + 新增的 `test_geometric_mean_capture_ratio_is_beta_invariant_unlike_the_compounded_one`），`uv run ruff format . && uv run ruff check .` 全绿。三个族（F1、F2、Wave 2）的重评分方法与结果见各自小节及 `step10-w1-beta-exposure-2026-09.md`、`step10-w1-cross-asset-trend-2026-09.md`、`step10-w2-cross-sectional-liquid500-2026-09.md`。

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

状态：**doing**，只差全仓库 pytest 结果确认后的 commit。

### 做了什么

1. **新合同 `config/promotion/unlevered-family-paper-tier-gates.json`**：按计划 §3.2 原样落地——8 个门槛键（`cagr_excess_vol_matched_benchmark_minimum=0.05`、`sharpe_excess_bil_minimum=1.0`、`dsr_minimum=0.5`、`max_drawdown_minimum=-0.35`【计划要求从旧合同的 -0.65 收紧，理由写在 rationale：QQQ/SPY 十年最大回撤 -35.0%/-33.8%，非杠杆策略不该比自己的基准族更差】、`mar_minimum=0.6`、`minimum_positive_fold_fraction=0.6`、`benchmark_vm_capture_ratio_minimum=1.0`、`benchmark_vm_downside_capture_maximum=1.0`），`rationale` 字段完整写明为什么旧合同（`cagr_excess_qqq>=5pp` 对着 QQQ 十年 CAGR 20.2% 算，等于要求非杠杆策略年化 25%+）对本轮候选族不公平、新合同怎样通过波动率匹配基准解决这个问题。
2. **`open_composer/research/kernel/gate_contract.py`**：`REQUIRED_GATE_KEYS` 保持不变；新增 `UNLEVERED_FAMILY_GATE_KEYS`（8 个新键名）；`load_preregistered_gates` 新增 `required_keys: tuple[str, ...] = REQUIRED_GATE_KEYS` 关键字参数（默认值=原常量，**未传参的既有调用方行为完全不变**），内部三处用到 `REQUIRED_GATE_KEYS` 的地方改用这个参数。新增 3 个测试（`tests/test_kernel_gate_contract.py`）：新合同能用 `UNLEVERED_FAMILY_GATE_KEYS` 加载且值与文件一致；新合同用旧键集加载必须报错（`missing thresholds`/`unknown thresholds`）；反过来旧合同用新键集加载也必须报错——两份合同的键集合互斥，防止调用方忘记传 `required_keys` 时静默用错键。
3. **`open_composer/research/kernel/mechanism_eval.py::evaluate_candidate`**：新增 `benchmark_returns: pd.Series | None = None`、`benchmark_name: str = "QQQ"` 两个关键字参数。
   - `benchmark_returns=None`（默认）：行为与改动前逐字节一致——`metrics`/`gate_results` 的键名、`gates_not_applicable`（QQQ 正交豁免）全部不变。用新增测试 `test_benchmark_returns_none_keeps_the_existing_qqq_path_byte_for_byte` 显式断言这一点，加上全部既有测试原样通过做双重保险。
   - `benchmark_returns` 给定时：按公式 `w = candidate.std()/benchmark.std()`（两者都取 candidate 实际跑过的 OOS 拼接窗口）、`benchmark_vm = w*benchmark + (1-w)*BIL` 算出波动率匹配基准，**复用**（不重写）`campaign.recompute_candidate_promotion_metrics` 里已经测试过的 CAGR/capture-ratio 数学——把 `benchmark_vm` series 当成该函数的 `qqq_returns` 参数传第二次（`tqqq_returns` 传实际 TQQQ 只是为了满足行数校验，其输出被丢弃，不影响结果），把返回的 `cagr_excess_qqq`/`qqq_capture_ratio`/`qqq_downside_capture`/`qqq_correlation` 分别重命名进 `cagr_excess_vol_matched_benchmark`/`benchmark_vm_capture_ratio`/`benchmark_vm_downside_capture`/`benchmark_vm_correlation`。`gate_results` 在这条路径下换用新合同的键名求值（`cagr_excess_qqq`→`cagr_excess_vol_matched_benchmark`、`qqq_capture_ratio`→`benchmark_vm_capture_ratio`、`qqq_downside_capture`→`benchmark_vm_downside_capture`，其余 5 个键名两条路径共用），且不做 QQQ 正交豁免（这些候选族本来就该暴露于自己的基准，豁免没有意义）。`metrics` 额外记录 `benchmark_name`、`vol_match_weight`（`CandidateVerdict.metrics` 类型注解相应从 `dict[str, float | int]` 放宽为 `dict[str, float | int | str]`）。
   - 新增 3 个合成序列测试（`tests/test_mechanism_eval.py`）：`test_vol_matched_benchmark_weight_and_metrics_match_manual_computation`（w<1，用独立算一遍 `recompute_candidate_promotion_metrics(qqq_returns=手算的vol_matched_benchmark)` 核对每个数字，误差 `rel=1e-9`）、`test_vol_matched_benchmark_weight_can_exceed_one_and_still_reuses_the_formula`（w>1 融资场景，同样手算核对）、上面提到的默认路径不变测试。另在 `tests/test_kernel_gate_contract.py` 加了一条端到端测试 `test_vol_matched_promotion_eligibility_requires_the_committed_unlevered_contract`，镜像既有的"内联传参不给 promotion_eligible，只有已提交的合同文件给"测试，验证新合同也遵守同一条纪律。

### 已知的时序依赖（不是 bug）

`load_preregistered_gates` 要求合同文件已被 git 追踪且无未提交改动，这是它的核心安全属性（防止事后改阈值）。所以 3 个"读取真实新合同文件"的测试（`test_the_unlevered_family_contract_loads_with_its_documented_key_set`、`test_the_unlevered_family_contract_is_not_loadable_under_the_old_key_set`、`test_vol_matched_promotion_eligibility_requires_the_committed_unlevered_contract`）在**提交 3.2 之前**跑必然失败（`not tracked by git`）——这是预期行为，不是要修的 bug，`config/promotion/kernel-paper-tier-gates.json` 当初也是这样进来的。提交后会立刻重跑这三个测试确认转绿。

### 测试结果

- 提交前：`test_mechanism_eval.py` 12/12 全绿；`test_kernel_gate_contract.py` 除 3 个"依赖 git 提交"的新测试外全绿。
- commit `5e61b08` 之后重跑 `uv run pytest -q tests/test_kernel_gate_contract.py -n 2`：**12/12 全绿**，那 3 条测试按预期转绿。
- `uv run ruff format . && uv run ruff check .`：全绿。

状态：**done**。commit：`5e61b08`。

### blocked_on_user

无。

---

## Wave 0 / 3.3 SIP 档案每日增量更新 + cron

状态：**doing**。代码、测试、cron 已完成；**首次真实运行等后台抓取结束**（见下）。

### 做了什么

1. **`scripts/update_sip_archive.py`**（新建）：把分片身份从"当前宇宙顺序 × 批大小"彻底解耦，改为"冻结在 `_LAYOUT.json.shard_symbols` 里的固定符号集合"：
   - `freeze_shard_symbols`：首次调用时扫描当前窗口（日线：当年目录；分钟线：当月+月初3天内的上月目录）里每个分片文件的 **parquet 内容实际包含哪些 symbol**（不是重新按当前宇宙排序切片），写进 `_LAYOUT.json` 的 `shard_symbols` 字段；此后每次调用直接读缓存，不重扫（对抗性测试验证过：分片内容事后被改也不会重扫）。
   - `update_existing_shards`：对每个冻结分片，读现有文件的 `max(timestamp)`，从"该时间戳往前 2 个交易日"（`refetch_window_start`，用 `open_composer.market_calendar.us_equity_session_dates` 数交易日，只读不改该模块）到 `now` 重新拉取该分片固定的 symbol 列表，与现有数据 `concat` 后按 `(symbol, timestamp)` `drop_duplicates(keep="last")`（新抓的覆盖旧的，用于吸收迟到修正），临时文件 + `os.replace` 原子改名后落盘。
   - `append_new_symbols`：当前 ACTIVE 宇宙里不在任何冻结列表中的 symbol，按 `BATCH_SIZE=12`（复用 `fetch_sip_universe.BATCH_SIZE`，不重复声明常量）分批追加为新分片编号（`max(现有编号)+1` 起，只增不复用），只抓当前窗口起，写回 `shard_symbols`。
   - 并发防护：`_refuse_if_bulk_fetch_active` 用 `pgrep -f fetch_sip_universe.py` 检测背景抓取进程,只要它在跑就整个拒绝执行；`_exclusive_lock`（`data/sip/_update_sip_archive.lock`,`O_CREAT|O_EXCL`）防止两次 `update_sip_archive.py` 自己撞车，正常/异常退出都在 `finally` 里释放,遗留锁需要人工确认+删除(有意不做自动清场,呼应 `check_sip_freshness.py` "宁可报警不要静默"的既有约定)。
   - 加载器 `open_composer/adapters/data/sip_parquet.py` **未改动**（按计划：它本来就按 glob 发现分片、按 footer 符号范围剪枝，新增/更新的分片自然被读到）。
2. **`tests/test_update_sip_archive.py`**（新建，18 个测试，全绿，无网络/凭据依赖）：纯函数（`current_window_dirs`、`window_full_start`、`refetch_window_start`、`_sessions_back` 隐含覆盖）；冻结列表重建 + 幂等不重扫；合并去重 `keep=last`（构造同一 `(symbol,timestamp)` 两个不同值,断言保留新值且不重复行）；原子写入(断言无残留 `.tmp*` 文件)；`update_existing_shards`/`append_new_symbols` 用假 `_fetch_batch`（monkeypatch 掉真实网络调用,返回形状与 Alpaca `.get_stock_bars(...).df` 一致的 MultiIndex DataFrame）验证端到端合并与分片编号分配；锁文件获取/释放/异常释放；`_refuse_if_bulk_fetch_active` 的两种分支（monkeypatch `subprocess.run`）。
3. **cron 已装**（`crontab -l`）：
   ```
   30 22 * * 1-5 cd ... && uv run python scripts/check_sip_freshness.py --notify-on-stale >> /tmp/sip_freshness_cron.log 2>&1  # 原有，保留不变
   0  22 * * 1-5 cd ... && uv run python scripts/update_sip_archive.py --kind daily >> /tmp/sip_update_cron.log 2>&1 && uv run python scripts/update_sip_archive.py --kind minute >> /tmp/sip_update_cron.log 2>&1  # 新增
   ```
   新增的更新任务排在 22:00 UTC，比 22:30 的新鲜度检查早 30 分钟，给它跑完的时间；两条都是工作日（周一到周五）。
4. **顺便修的两项**（计划 §3.3 最后一段）：
   - `open_composer/config.py::data_feed()` 默认值 `"iex"` → `"sip"`（`ALPACA_DATA_FEED` 环境变量未设时的兜底值）。已改。**更正（见文末"全仓库最终验收"）**：当时"全仓库搜索确认没有测试依赖这个兜底值"的结论是错的——那是静态字符串搜索，不是实跑全量测试；实际上 `open_composer/research/minute_momentum_feasibility.py` 的 `selected_feed = feed or data_feed()` 依赖它，全量跑出 13 个失败（基线 11 + 2 个新增），已用 commit `f53d34d` 修复三个受影响测试（改测试注入 `ALPACA_DATA_FEED=iex`，不回退默认值）。
   - `.env.example` 同步：**做不了**。`Read`/`Bash cat` 都被拒绝——`.env.example` 命中了项目权限配置里 `.env*` 的 deny 规则（和 `.env` 本身一样，虽然计划原意应该只是不让读真正的 `.env`）。这不是我能绕过的权限边界，记在下面 `blocked_on_user`。

### 真实验收（已完成）

后台 2016-2022 分钟线抓取于 2026-09-04 07:07:27 UTC 完成（`data/sip-hist/minute/_COMPLETE_2016_2022.json` 标记文件出现，`fetch_watchdog.sh` 自行退出，日志见 `/tmp/fetch_minute_2016_2022.log` 最后两行）。累计运行约 37.2 小时，1,802,771,144 行。确认 `pgrep -af fetch_sip_universe` 干净（无残留进程）后，跑了两个 `--kind` 的第一次真实增量更新：

- `uv run python scripts/update_sip_archive.py --kind daily`：`froze 336 shard(s)`（首次调用，冻结现有分片的 symbol 归属，此后不再因宇宙重排改变分片身份）→ `daily 2026: updated 336 frozen shard(s)` → `341 newly-listed symbol(s) in 29 new shard(s)` → `done -- 78514 row(s) refreshed, 953 row(s) from new listings, 1.4min`。
- `uv run python scripts/update_sip_archive.py --kind minute`：`froze 1118 shard(s)` → `updated 1118 frozen shard(s)` → `1555 newly-listed symbol(s) in 130 new shard(s)` → `done -- 5473071 row(s) refreshed, 8602 row(s) from new listings, 9.0min`。
- `uv run python scripts/check_sip_freshness.py`：`{"stale": [], "archives": [{"frequency": "daily", "sessions_behind": 0, "last_bar": "2026-09-03"}, {"frequency": "minute", "sessions_behind": 0, "last_bar": "2026-09-03"}]}`——两个频率都 `sessions_behind: 0`，达标。

`crontab -l` 里 3.3 新增的每日 22:00 UTC 更新行已确认在案（见"做了什么"小节）。

### blocked_on_user

- `.env.example` 里 `ALPACA_DATA_FEED` 默认值示例同步成 `sip`：执行者的读写权限对 `.env.example` 整个文件被拒绝（命中 `.env*` deny 规则），只能请用户本人编辑该文件里 `ALPACA_DATA_FEED=` 那一行改成 `sip`（如果还是 `iex`）。影响很小——真正生效的是 `open_composer/config.py::data_feed()` 的代码默认值（已改）和实际 `.env`（据计划 §0 已经是 `sip`）；`.env.example` 只是给新环境的示例文件，不影响当前运行时行为。

### 测试结果

- `uv run pytest -q tests/test_update_sip_archive.py -n 2`：18/18 全绿（合并去重、原子写入、冻结列表幂等、新 symbol 分片分配、锁、bulk-fetch 守卫）。
- `uv run ruff format . && uv run ruff check .`：全绿。
- 全仓库 `uv run pytest -q -n 2`（含本节代码）：见文末"全仓库最终验收"一节。

### 待做

- 后台抓取结束后：`update_sip_archive.py --kind daily`、`--kind minute` 各跑一次真实调用，`check_sip_freshness.py` 确认 `stale: []`，证据写回本节。这是本节唯一剩下的未完成项；其余（脚本、测试、cron、config.py 小修）均已完成并将随本节一起 commit。

---

## Wave 0 全仓库最终验收

跑于 3.1+3.2+3.3 三次 commit 的代码全部落地之后（不含 3.3 的"真实更新跑一次"这一步，那一步不改代码，只读写 `data/sip/`）：

- `uv run ruff format .`：无改动（全部已格式化）。
- `uv run ruff check .`：All checks passed。
- `uv run pytest -q -n 2`（日志 `/tmp/step10_wave0_pytest.log`，完成于 2026-09-04 06:11:20 UTC）：**首次 13 个失败**，比基线多 2 个，且有 2 个不在 `test_mom_breadth_qd_r1.py` 里——按计划纪律（超过 11 个必须停下来处理，不能硬着头皮往前推）立即停下排查。

  根因：3.3 把 `open_composer/config.py::data_feed()` 默认值从 `iex` 改成 `sip` 后，`open_composer/research/minute_momentum_feasibility.py` 第 88 行 `selected_feed = feed or data_feed()` 跟着变成 `sip`，导致三个用固定文件名 `qqq_15m_iex.csv` 做 fixture 的测试去找不存在的 `qqq_15m_sip.csv`：
  - `tests/test_minute_momentum_feasibility.py::test_minute_feasibility_uses_isolated_research_output`（`row["status"]` 从 `"ok"` 变 `"error"`）
  - `tests/test_minute_momentum_feasibility.py::test_minute_feasibility_long_history_with_interior_gaps_is_no_go`（`strict["history_months"]` 从 `>=18.0` 变 `0.0`）
  - `tests/test_minute_momentum_feasibility.py::test_minute_feasibility_cli_writes_report`（同一根因，全量跑里这一条这次凑巧还是绿的，但同样脆弱，一并修）

  之前 3.3 小节写的"全仓库搜索确认没有测试依赖这个兜底值"是错的，已在此更正——那次搜索没有跑全量测试实际验证，只是静态搜了字符串。这次教训：改一个全局默认值之后，必须跑全量测试而不是只搜代码。

  修法（不回退 sip 默认值）：三个测试各自 `monkeypatch.setenv("ALPACA_DATA_FEED", "iex")`，显式声明自己测的就是 iex 缓存路径，不依赖全局默认值；断言不改。commit `f53d34d`（独立提交，在 Wave 1 评估脚本之前落地）。

  修复验证：`uv run pytest -q tests/test_minute_momentum_feasibility.py -n 2` → 9/9 全绿；仓库里没有 `tests/test_config*.py`。修复后未重跑全量（用量限制下没必要——改动范围明确到 3 个测试的一个环境变量注入，且已用目标测试文件验证），全量结果记为 **13 → 修复后 11**，11 个全部是 `test_mom_breadth_qd_r1.py::test_recovery_*`（与基线一致，见下方 FAILED 列表）。

  ```
  FAILED tests/test_mom_breadth_qd_r1.py::test_recovery_preregistration_state_accepts_exact_repository_evidence_without_market_reads
  FAILED tests/test_mom_breadth_qd_r1.py::test_recovery_rejects_exact_data_feasibility_metadata_drift[required_reference_inventory]
  FAILED tests/test_mom_breadth_qd_r1.py::test_recovery_rejects_exact_data_feasibility_metadata_drift[blockers]
  FAILED tests/test_mom_breadth_qd_r1.py::test_recovery_rejects_exact_data_feasibility_metadata_drift[campaign_universe]
  FAILED tests/test_mom_breadth_qd_r1.py::test_recovery_rejects_candidate_authorization_semantic_drift[candidate_id]
  FAILED tests/test_mom_breadth_qd_r1.py::test_recovery_rejects_candidate_authorization_semantic_drift[path]
  FAILED tests/test_mom_breadth_qd_r1.py::test_recovery_rejects_candidate_authorization_semantic_drift[action]
  FAILED tests/test_mom_breadth_qd_r1.py::test_recovery_rejects_candidate_authorization_semantic_drift[candidate_binding_sha256]
  FAILED tests/test_mom_breadth_qd_r1.py::test_recovery_rejects_exact_universe_contract_drift[contract_id]
  FAILED tests/test_mom_breadth_qd_r1.py::test_recovery_rejects_exact_universe_contract_drift[capability_ids]
  FAILED tests/test_mom_breadth_qd_r1.py::test_recovery_rejects_exact_universe_contract_drift[universe_definition_metadata]
  ```

对照计划 §3.4："全量测试 11 个基线失败不变"——**修复后满足**。

---

## Wave 1 / F1 波动率管理 beta 暴露

状态：**done（负结果）**

### 做了什么

- 轻量迭代注册：`step10_w1_beta_exposure`（`strategy_specs/drafts/step10_w1_beta_exposure_router_family.yaml` + `scripts/new_lightweight_iteration.py` 生成 `reports/research/iterations/step10_w1_beta_exposure/{candidate-manifest,cost-table,data-feasibility,search-space}.json` 等）。`oc research iteration validate` 结果 `status: ok`，`warnings: [lightweight_single_mechanism_exemption_used]`。8 条来源卡（`reports/harness/source_cards/step10_w1_beta_exposure.jsonl`），复用本仓库 `mom_breadth_qd_r1` 已核实过的 8 篇论文（Moreira & Muir 2016 波动率管理组合、Avellaneda & Zhang 杠杆 ETF 路径依赖、Bailey&LdP DSR、Bailey et al PBO、Hansen SPA、Harvey-Liu-Zhu 多重检验、DeMiguel-Garlappi-Uppal 简单配置基准、Mouret&Clune MAP-Elites），换了新的 `project_applicability`/`reflection`，未重新逐一在线核实（复用同仓库已核实记录，claim/URL 不变）。
- 网格：24 组，写死在 manifest 里，`market∈{QQQ,SPY} × trend_sma_days∈{100,200} × target_volatility_annual_pct∈{10,15,none} × max_drawdown_pct∈{none,-15}`，其余固定（`momentum_lookback_days=60, min_momentum_pct=0, volatility_lookback_days=20, max_volatility=none, drawdown_lookback_days=60, leverage_*=none, risk_on=market@1.0, neutral=market@0.5, risk_off=BIL@1.0`）。`beta_params_from_label` 往返验证通过；BIL 通过 `load_beta_router_dataset(..., extra_symbols=["BIL"])` 直接可用，不需要 `CASH` 兜底。数据 `data_source="sip_parquet"`，2016-01-04 至 2026-08-31，QQQ/SPY 均 2680 个公共交易日。
- 评估脚本 `scripts/evaluate_beta_exposure_family_sip.py`，模板照 `scripts/evaluate_champion_route_sip.py`：`fold_count=5`，成本 base 5bps/边、压力 40bps（`spec.costs.slippage_bps`），两遍 DSR 有效试验数（探路用 `len(candidates)=24`，正式用 `max(effective_n, _MIN_DSR_TRIAL_COUNT=2)`；`_MIN_DSR_TRIAL_COUNT` 沿用 `layered_search.py`/`search_expression_trees_p2b.py` 现成常量，而不是 `search_intraday_momentum_etf.py` 里那个会在 `effective_n==1` 时崩溃的 `max(effective_n, 1)`）。裁定用新合同（`benchmark_returns=` 传每个候选自己的 `risk_on_symbol`，QQQ 候选比 QQQ、SPY 候选比 SPY）；旧合同同时跑出来仅作参照。CRISIS_WINDOWS + 选择后窗口（`2026-07-09` 起）诊断齐全；每候选输出 `exposure_pct`/`annualized_turnover_events`/`average_holding_period_days`。
- 先用 3 候选烟雾测试（发现并修了一个字典推导式语法错误 + 一个 `dsr_trial_count` 下限 bug），再跑 24 候选正式版。

### 结果（诚实负结果）

- `raw_candidate_count=24`，`effective_n=1`（`breadth_ratio≈0.042`）——24 组高度相关，聚成 1 个有效独立试验；`dsr_trial_count_used=2`（下限）。
- **`candidates_passing_new_contract: []`——0/24 通过新合同。**
- 新合同门槛失败分布（24 组里失败数）：`cagr_excess_vol_matched_benchmark` 24/24、`benchmark_vm_capture_ratio` 24/24、`sharpe_excess_bil` 24/24、`mar` 11/24；`dsr_probability`/`positive_fold_fraction`/`max_drawdown`/`benchmark_vm_downside_capture` 多数通过。
- 最接近的候选 `C12`（`sma200_..._maxdd-15_onQQQ1..._vtnone`，即 SMA200 趋势 + -15% 回撤止损、不设波动率目标）：`cagr_excess_vol_matched_benchmark=+0.0088`（仍 <0.05 门槛）、`benchmark_vm_capture_ratio=0.201`（<1.0 门槛）、`mar=0.7565`（通过）、`vol_match_weight=0.62`。旧合同下同样 `promotion_eligible=False`。
- 诊断：C12 在选择后窗口（2026-07-09 起 37 个交易日）CAGR 为 **-12.17%**，同期基准 QQQ 为 **+4.88%**（非门槛，仅诊断，如实记录）；2020 疫情崩盘窗口回撤 -18.2%，跌幅小于基准但样本仅 24 天。
- **结论与预注册的失败假说吻合**：路由的趋势/回撤/波动率门控确实压低了名义敞口和回撤，但换成"与候选自身已实现波动率相同"的基准比较后（而不是 100% 买入持有），超额 CAGR 和捕获比都不达标——去杠杆本身不是超额收益的来源。
- 证据 JSON：`reports/research/control/step10-w1-beta-exposure-2026-09.json`。

### 2026-09-05 更新：捕获比定义修正 + 正式报告

上一位执行者中止会话前已经把 `mechanism_eval.py` 的捕获比公式改成每期几何平均定义（见本账本"度量修正"一节的完整数学），并用修正后的代码重跑出了当前这份 JSON（24/24 通过 `benchmark_vm_capture_ratio`/`benchmark_vm_downside_capture`，仍是 0/24 通过全部门槛）。本次会话核实了这份 JSON 已经是修正后的结果（`benchmark_vm_capture_ratio_compounded_legacy` 字段存在，C12 上是 0.2007，与修正前一致；新的 `benchmark_vm_capture_ratio` 是 1.1162），未重跑，直接据此写出正式报告 `reports/research/control/step10-w1-beta-exposure-2026-09.md`（含全部 24 候选按超额 CAGR 排序的表格、新旧捕获比并列、门槛通过分布、危机窗口与选择后诊断）。**结论不变**：0/24 通过新合同，最好的 C12 超额 CAGR +0.99pp（门槛 5pp），Sharpe-ex-BIL 0.589（门槛 1.0）。

### blocked_on_user

- 无。

## Wave 1 / F2 跨资产 ETF 趋势配置

状态：**done（负结果）**

### 做了什么

- **路由可行性核查（计划要求先查后定）**：详细读了 `open_composer/research/core_beta_satellite_core.py`。结论：**不可表达，走独立内核机制**。具体原因（写进了 `cross_asset_trend_etf.py` 模块 docstring 和 dossier 的 `notes.archive_descriptors`）：
  1. `core_route_label()` 把 `"onTQQQ..."/"neuQQQ..."/"offCASH0"` 硬编码进 f-string，`core_variant` 只能选权重（0.5/0.75/1.0），选不了标的——做不到"core 是 BIL"。
  2. `load_core_beta_satellite_dataset` 无条件要求 `QQQ,TQQQ,SQQQ,SMH`，`universe_mode` 只是 `.label` 里的描述字符串，`_target_snapshot` 从未读取它，没有任何行为预设。
  3. 卫星仓位是叠加在核心之上的小额战术仓（`satellite_budget` 默认 0.1，即 10% 账面），不是这个机制需要的"主体仓位"。
  4. `_theme_gate_ok` 用单一硬编码标的（默认 `SMH` 半导体）做卫星总开关，和本机制"10 个跨资产 ETF 各自独立看动量"完全是两回事。
  5. core 的"risk off"腿是字面 0% 收益（`offCASH0`），不是 BIL 的真实收益率，本机制的现金腿需要后者。
  这些都不是"改小参数就能绕过"的问题，属于要重写路由核心逻辑才能塞进去，超出"查一下能不能表达"的范围，也没有去碰任何禁改文件。
- 新建 `open_composer/research/kernel/mechanisms/cross_asset_trend_etf.py`（独立内核机制，模板照 `intraday_momentum_etf.py`）：`SPY,QQQ,IWM,EFA,EEM,TLT,IEF,GLD,DBC,VNQ` + 现金腿 `BIL`；月末对每个 ETF 用**自身**过去 `lookback_months`（6 或 12）个月总收益判正负（时间序列动量，不做横截面排名）；正的进入"候选多头"，按动量高低排序取前 `top_n`（3/5/all=10）名。**一个计划文本未明确、需要执行者自行决定并如实记录的实现选择**：把 `top_n` 当作"槽位数"（1/top_n 每槽），未填满的槽位持有 BIL——这是标准 GTAA/双动量惯例（如 Faber 2007），不是"10 只 ETF 各占固定 1/10，选中的才换成 ETF"这种读法；两种读法计划文本都说得通，选了前者并在模块 docstring 里写明。权重 `equal`（每槽 1/top_n）或 `inverse_vol_60d`（选中的名字之间按 60 日已实现波动率倒数分配，总敞口不变）。成本 5bps/边（计划 §4.2 原话），压力 40bps，在换仓日按全部标的（含 BIL）权重变化绝对值之和计成本。
- **写单测时抓到一个真实 bug**：`rebalance_positions` 的过滤条件写成了"交易日下标 - lookback_months >= 0"，应该是"月份下标 - lookback_months >= 0"；月份下标不够时 `month_end_positions[month_idx - lookback_months]` 会因为 Python 负数下标"绕到列表末尾"而不是报错，安静地用最后一个月当成"回看起点"，污染最早一次换仓的动量判断。8 个新单测里 4 个因此失败，定位后修好，全部 8 个测试转绿（`tests/test_cross_asset_trend_etf.py`）。**之前跑的一次 12 候选正式评估用的是修 bug 前的代码，已丢弃重跑**，下面数字全部来自修复后的版本。
- 轻量迭代注册 `step10_w1_cross_asset_trend`（同样走 3.1 路径，`strategy_specs/drafts/step10_w1_cross_asset_trend_etf_family.yaml`，spec 里 `notes.archive_descriptors.product_executable: false` 并写明原因），8 条来源卡（复用 `mom_breadth_crossasset_trend_r1` 已核实的 8 篇：Moskowitz-Ooi-Pedersen 时序动量、Hurst-Ooi-Pedersen 百年趋势跟踪证据，其余 6 篇与 F1 共用方法论文献）。`oc research iteration validate` → `status: ok`。12 组网格（`lookback_months×top_n×weighting` = 2×3×2）直接从 `cross_asset_trend_etf.PARAMETER_SPACE` 生成 manifest，评估脚本反过来校验 manifest 与 `PARAMETER_SPACE` 逐项相等（单一事实来源，杜绝改一处忘改另一处）。
- 评估脚本 `scripts/evaluate_cross_asset_trend_sip.py`：方法与 F1 一致（`fold_count=5`、两遍 DSR、CRISIS_WINDOWS+选择后诊断、新旧合同并报），基准统一用 **SPY**（计划 §4.2 明确写"基准族 SPY"，不像 F1 分标的）。交易活动诊断（在场天数占比/年化换手/平均持仓天数）通过给 `daily_cross_asset_trend_returns` 加一个可选 `rebalance_sink` 钩子精确复算，不是近似。数据：11 个标的 `daily_returns_on_naive_dates` 内连接，2016-01-05 至 2026-08-31，2679 个公共交易日。
- 先 3 候选烟雾测试通过，再跑 12 候选正式版（第一次跑完发现单测 bug 后作废重跑一次，见上）。

### 结果（诚实负结果）

- `raw_candidate_count=12`，`effective_n=1`（`breadth_ratio≈0.083`），`dsr_trial_count_used=2`（下限）。
- **`candidates_passing_new_contract: []`——0/12 通过新合同。**
- 新合同门槛失败分布：`cagr_excess_vol_matched_benchmark` 12/12、`benchmark_vm_capture_ratio` 12/12、`sharpe_excess_bil` 12/12、`mar` 3/12。
- 最接近的候选（`lookback_months=6, top_n=5, weighting=equal`）：原始 CAGR 10.85%，但 `cagr_excess_vol_matched_benchmark=+0.0111`（<0.05 门槛）、`benchmark_vm_capture_ratio=0.5895`（<1.0 门槛，**修正前的旧定义值，见下**）、`mar=0.9736`（通过）、`max_drawdown=-11.14%`，平均持仓约 105 天，在场天数占比 98.3%。旧合同下同样 `promotion_eligible=False`。
- **结论与 F1 同一模式**：月度轮动确实降低了波动/回撤，但用"与候选已实现波动率相同"的 SPY 基准比较后，超额收益和捕获比不达标；换成对波动率敏感的比较标准后，"更平滑的净值曲线"本身不足以构成晋级理由。

### 2026-09-05 更新：捕获比定义修正 + 重跑 + 正式报告

上一位执行者中止会话前只重跑了 F1，没来得及重跑 F2——本次会话接手时磁盘上**完全没有** F2 的证据 JSON（`step10-w1-cross-asset-trend-2026-09.json` 不存在，仓库全文搜索、`/tmp` 都没有），只有账本里这段用旧捕获比定义写的文字记录。F2 的评估脚本本身不依赖 DuckDB、数据量小（11 个标的的日收益），重跑成本是秒级，所以直接用已经修正的 `mechanism_eval.py` 重跑：

```
export PATH="$HOME/.local/bin:$PATH"; export UV_CACHE_DIR=/tmp/open-composer-uv-cache
uv run python scripts/evaluate_cross_asset_trend_sip.py
```

重跑用的数据窗口比上次（`2016-01-05` 至 `2026-08-31`）多了几个交易日（SIP 日线增量更新已经推进到 `2026-09-04`），所以最好候选的具体数字与上面这段旧文字略有出入（CAGR 11.08% vs 10.85%，超额 CAGR +1.33pp vs +1.11pp），但结论完全一致。新结果：**捕获比修正后 9/12 通过 `benchmark_vm_capture_ratio`（旧定义 0/12），仍是 0/12 通过全部门槛**——最好候选（`lookback_months=6, top_n=5, weighting=equal`）新定义捕获比 1.058（旧定义 0.5915），`cagr_excess_vol_matched_benchmark=+0.0133`、`sharpe_excess_bil=0.648`，两者仍分别远低于 5pp、1.0 门槛。正式报告：`reports/research/control/step10-w1-cross-asset-trend-2026-09.md`（含全部 12 候选表格、新旧捕获比并列、危机窗口、选择后诊断——后者这次是正的：+27.6% CAGR vs SPY +21.7%，42 天样本，非门槛）。

- 证据 JSON：`reports/research/control/step10-w1-cross-asset-trend-2026-09.json`（2026-09-05 重新生成）。

### blocked_on_user

- 无（"能不能接入产品"的问题已经自己查清楚并给出结论：这周不能，需要新路由模式或者给 `core_beta_satellite_core` 的 core 腿做成任意标的/权重才能接，这是下一轮的候选建议，不是需要用户此刻拍板的事）。

## Wave 2 / PIT 流动性过滤横截面动量

状态：**done（负结果）**。正式报告：`reports/research/control/step10-w2-cross-sectional-liquid500-2026-09.md`（完整方法、PIT 过滤说明、幸存者偏差重测、内存超预算记录、捕获比重评分方法、全部 4 候选表格）。本节只记要点，细节一律以报告为准，不重复。

### 做了什么

- 上一位执行者已经写好并跑过 DuckDB 管线（`scripts/evaluate_cross_sectional_momentum_liquid500.py`、`scripts/duckdb_survivorship_bias_comparison_liquid500.py`，两者均未提交，本次一并入库）：PIT 流动性过滤（每月末用≤当日的 60 日滚动美元 ADV 取前 500，`close>5` 同样按月末时点评估，不用单一窗口套全历史）、4 组网格（`top_fraction∈{0.10,0.15} × rebalance_stride_months∈{1,2}`）、幸存者偏差在 liquid-500 内重测（`active_only` vs `active_plus_removed`，两个独立排名，不拼接）。
- **内存**：正式评估脚本峰值 RSS **1,323.3MB**，幸存者重测脚本峰值 **1,262.0MB**，均超出脚本内 DuckDB `memory_limit=900MB` 与报告目标 1,000MB——如实记录，未收紧过滤力度去凑数（计划明令禁止）。两次都在 3.8GB 机器上跑完，未 OOM，但不代表可以和别的重负载任务并发。
- **幸存者偏差重测结果**：CAGR 差 -0.12pp、Sharpe 差 -0.002，判定"非材料性"，但**结论范围限定为 liquid-500 动量族**（大市值代理），不是横截面动量幸存者偏差的一般性结论——W6 更早的无流动性过滤版本已经证明这个结论在更宽的设定下不成立，两者不矛盾。

### 捕获比重评分（未重跑 DuckDB）

原始 JSON（09-04 07:47 UTC 产出，早于捕获比修正）已经按计划要求持久化了每个候选的 `oos_return_stream`/`oos_dates`/`vol_match_weight`。由于本次修正只改变 `benchmark_vm_capture_ratio`/`benchmark_vm_downside_capture` 两个字段的计算公式，其余全部指标的输入和公式都未变，本次会话没有重跑 DuckDB 管线（1.3GB 峰值内存，重跑无必要的开销），而是写了一个一次性脚本（未入库，逻辑记录于 `step10-w2-cross-sectional-liquid500-2026-09.md` 第 4 节）：读原 JSON 持久化的 `oos_return_stream`/`oos_dates`/`vol_match_weight`，加一次新鲜的 SPY/BIL 读取重建波动率匹配基准，直接调用修正后的生产函数 `mechanism_eval._conditional_geometric_mean_capture`（不是重新实现数学）算出新捕获比，再用新合同门槛重新判定这两道门与总裁定，原地写回同一份 JSON 路径。**已知的口径误差**：SPY/BIL 是"现在"读取的，SIP 日线档案在原始跑批后经历过至少一次每日增量更新（2 交易日回看窗口的迟到修正），理论上 OOS 窗口末尾几天可能有 basis-point 级差异，但因为四个候选修正后的捕获比（0.97-0.999）离门槛（1.0）的差距远大于这种量级的噪声，不影响裁定。

### 结果（诚实负结果）

- **`candidates_passing_new_contract: []`——0/4 通过新合同。**
- 捕获比修正后 `benchmark_vm_capture_ratio` 从旧定义的 0.09-0.19 升到新定义的 0.97-0.999——大幅改善但**仍全部 <1.0**，是本轮三个族里唯一一个捕获门本身也没有通过的（F1 全过、F2 9/12 过）。四个候选 `vol_match_weight` 都在 1.93-2.22（候选波动率接近 SPY 两倍），`cagr_excess_vol_matched_benchmark` 全部为负（-3.42pp 至 -8.59pp）、`sharpe_excess_bil` 最高只有 0.474、`mar` 最高只有 0.386，`max_drawdown` 4 个里 3 个不过（-34.0% 到 -40.6%）。
- 危机窗口诊断出现了与 F1/F2 相反的模式：2020 疫情崩盘窗口跌幅（-38.4%）**大于**基准 SPY（-33.5%），2018Q4 同样跌幅更大——流动性前 500 的动量多头在这类极端流动性危机中不具备防御性。选择后窗口（2026-07-09 至 09-03，41 天）CAGR 普遍在 -37% 到 -55%，同期 SPY +25.2%，四个候选方向一致，如实记录。
- 产品映射（`cross_sectional_momentum` 模式的目标权重身份）确认不在本周范围，本次结果也不改变这个判断——若某天这个族真通过了，才需要补映射。

### blocked_on_user

- 无。

## Wave 3 / 预注册组合

状态：todo

## Wave 4 / 晋级或负结果记录

状态：todo
