# 第一批选择规则（T-20261006-13）

写定于选择脚本 `select_first_batch.py` 运行之前，早于 `first-batch.json`。catalog.json 已建好，但没有看任何候选的回测结果（本任务不跑回测；登记簿里的旧结论只用于 `prior_*` 字段）。选择过程由脚本机械执行，人不逐条挑选。以后改规则只能新写一个版本，不能用同一个版本事后调整。

输入：`reports/research/strategy-library/catalog.json`（694 行：151 书 175、OSAP 331、QuantConnect 83、本地登记簿补充 105）。

## 1. 资格条件（全部满足才进候选池）

| 编号 | 条件 | 字段 |
|---|---|---|
| E1 | Alpaca 能交易 | `alpaca_tradable == "yes"` |
| E2 | 本地有数据，或一天内能补 | `adapter_1d == true`（`data_local == yes`，或构建时登记的一天内适配：OSAP 会计类缺不超过 2 个 Compustat 科目、一个明列的日历/行情抓取） |
| E3 | 是策略条目，不是安慰剂、被放弃项或背景章节 | `entry_type == "strategy"`，资产类别在 us_equity、etf、options、crypto |
| E4 | 没有正在进行或已在用的同一条目 | 条目本身（`prior_scope == "specific"`）对应的登记簿 status 不是 passed、testing、queued、triaged、harvested；且不是股票多空书信号表里已有的信号（`in_equity_book` 为假）。登记簿 status 为 not_executable 的剔除 |
| E5 | 没有满足五条深度规则的旧否定 | `prior_depth_ok != "yes"`。登记簿没有深度台账，目前所有旧否定都是 `unknown`，所以 E5 暂时不剔除任何条目；这类条目另受第 3 节"重测配额"限制 |
| E6 | 每个机制族（`family_key`）最多 3 个 | |
| E7 | 单一来源清单最多 24 个 | `origin_list`，防止被 OSAP 一份清单占满 |

"旧否定"指 `prior_scope == "specific"`、`prior_locally_tested == true` 且登记簿 status 为 refuted、evidence_too_weak、parked、partial。`prior_locally_tested` 的判定（启发式，写在 `build_catalog.py:_locally_tested`）：status 为 refuted 或 partial 的，除非 verdict 写了 "not tested / untested / needs_modal / primary source"，算本地测过；parked 一律不算（parked 就是没推进）；evidence_too_weak 只有当 evidence 引用了本地实验目录（`iterations/`、`screens/`、`hypotheses/`、`signal-cards/`）且 verdict 没有上述字样时才算。原因：登记簿的 evidence_too_weak 和 parked 同时包含"只看文献就放弃、没在本地测过"和"本地测过但没过"两种，不能一概当作测过。OSAP 条目只有族级旧结论（`family_level`）时，视为"从没单独测过"，不算重测。

## 2. 排序（候选池内的先后）

按下列键依次比较，机械排序，同分按 id 字母序：

1. 证据等级 `tier`，小的在前：
   - 1：OSAP 且 `Predictability in OP == 1_clear` 且 `Signal Rep Quality == 1_good`（发表后有第三方复现：OSAP 对原文的统一复现，且原文结论清楚）；
   - 2：OSAP 的其余 `1_clear`/`2_likely`（复现质量 good 或 fair）；QuantConnect 条目（有公开代码复现，来源论文可查，业绩未经独立核实），但来源写 "Quantpedia Premium" 的算 3；
   - 3：其余全部（151 一书只有公式、无经验证据；登记簿补充行；OSAP 的 indirect/4_not）。
2. 从没单独测过的在前（`prior_scope` 为 none、generic_only、family_level，或 specific 但 `prior_locally_tested` 为假，先于本地测过的 specific）。
3. 时效：证据年份（OSAP 用发表年；其他取 `original_paper` 里最大的四位年份，没有则 2010）大的在前。
4. 复杂度 S 先于 M 先于 L。

## 3. 重测配额

登记簿里单独在本地测过、被否定但没到深度的条目（`prior_scope == "specific"`、`prior_locally_tested` 为真、status 在 refuted、evidence_too_weak、parked、partial），第一批合计最多 14 个。理由：2026-10-04 的深度规则使便宜测试只能提速、不能否定；旧结论只写在登记簿，没有深度台账，所以把"补深度"当成有限的重做，并写明上次缺哪一条（`retest_reason`，取自登记簿 verdict 的前 200 字）。超过配额的不进入第一批，留给后面几批。

## 4. 覆盖配额

第一批共 50 个。先按桶填配额，再用全局排序补满：

| 桶 | 条件 | 最少 |
|---|---|---|
| 日内 | `frequency == intraday` | 8 |
| 事件 | `frequency == event` | 8 |
| 日频 | `frequency == daily` | 6 |
| 周月频 | `frequency in (weekly, monthly)` | 12 |

余下 16 个按全局排序补。每个桶内部按第 2 节排序，并遵守 E6、E7 和第 3 节配额。某个桶的合格条目不够，就如实报告缺口，不放宽资格条件去凑数。

## 5. 每项附带的信息

- `rules_met`：满足的资格条件和所属桶；
- `data_adapter`：需要的数据适配（来自 `data_local_detail` 和 `adapter_note`）；
- `template`：通道里现成的模板（lane：`scripts/screen_batches/` 里最接近的批文件；book：股票多空书信号列；intraday、options、crypto：写明没有现成通道，需要的最小新代码）；
- `cost_basis`：按 `docs/evaluation-standard.zh.md`、`config/evaluation-standard-v2.json` 和 `docs/equity-book-design.zh.md` 第 7 节选口径；日内和期权的成本口径还没冻结，写"待定"，不自造数字；
- `retest_reason`：只有重测项有。

## 6. 这一批的定位

第一批是批量筛选，不是否定程序：筛选通过的进入深度测试，没通过的只写"未到深度"，除非后续满足五条深度规则。日内条目的最低有效深度要求多信号横截面和实测价差（`docs/plan-v2-2026-10-05.zh.md` 第 3.1 节，11-02 开工），第一批里的单规则日内条目只能提速，不能用来否定日内这一类。

## 7. 修订记录

- 2026-10-06 17:1x UTC，v1：初版，早于 first-batch 第一次生成。第一次运行后发现两处不是结果问题、而是定义和数据错误：(a) 登记簿 id `dir:multi_signal_equity_book` 写错（真 id `dir:multi_signal_risk_controlled_equity_book`），已改并加断言；(b) 把登记簿 status 为 evidence_too_weak、parked 的条目一律当"测过"，而这两个状态同时包含只看文献就放弃、没在本地测过的情况（例如 `dir:end_of_day_reversal` 的 verdict 是 "Not tested this round"）。第 1、2、3 节的"旧否定"定义已按上面改为要求 `prior_locally_tested`；随后又发现 signal-cards 目录和 refuted 状态应算本地测过（insider、M&A 的否定存在 signal-cards 里），判定函数再收紧一次，这是 v2 的最终形式。第一次的输出保留在 `first-batch.v1-superseded.json`；修订发生在看过 v1 名单之后，这一点如实记录，v1 与 v2 的差别由两处定义修正造成，没有按名单内容改配额或条件。
