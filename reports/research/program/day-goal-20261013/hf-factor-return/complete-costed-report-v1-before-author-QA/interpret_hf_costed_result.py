"""Author interpretation of completed frozen outputs; no repricing or selection."""
# Report paragraphs/table rows intentionally remain intact as presentation literals.
# ruff: noqa: E501

import json
from collections import Counter

from hf_completion_resources import snapshot
from hf_features import P, bind, save

R = P / "economic/results"


def pct(value):
    return "N/A" if value is None else f"{100 * value:.3f}%"


def num(value):
    return "N/A" if value is None else f"{value:,.3f}"


def main():
    path = P / "complete-costed-result.json"
    result = json.loads(path.read_text())
    funded = json.loads((R / "funded-results.json").read_text())
    host = json.loads((R / "host-results.json").read_text())
    diagnostic = json.loads((R / "fractional-diagnostic-results.json").read_text())
    assert host["ready"] and result["inventory"]["independent4k_model_books"] == 40
    ids = list(result["fee_panels"]["20"]["candidates"])
    panel20 = result["fee_panels"]["20"]
    assert not panel20["positive_terminal_profit"]
    best = panel20["sorted_terminal_diagnostic_only"][0]
    primary = result["six_primary_common_All_target_contrasts"]["All_primary"]
    host_sharpe_comparisons = {}
    for fee in [20, 40]:
        for control in ["CASH", "BIL", "SPY", "PLS_IDX_MKT"]:
            deltas = {}
            unknown = []
            for key, row in host["results"].items():
                host_name, candidate, cost = key.split("__")
                if candidate not in ids or cost != str(fee):
                    continue
                left = row["metrics"].get("Sharpe_netstd")
                right = host["results"][f"{host_name}__{control}__{fee}"]["metrics"].get("Sharpe_netstd")
                if left is None or right is None:
                    unknown.append(key)
                else:
                    deltas[key] = left - right
            host_sharpe_comparisons[f"{fee}__{control}"] = dict(
                higher={k: v for k, v in deltas.items() if v > 0},
                equal=[k for k, v in deltas.items() if v == 0],
                lower={k: v for k, v in deltas.items() if v < 0},
                unavailable=unknown,
            )
    diag_summary = {}
    for fee in [0, 1, 5, 20, 40]:
        for lag in [0, 1]:
            rows = {
                k: v
                for k, v in diagnostic.items()
                if k.split("__")[1] == str(fee) and k.endswith("lag" + str(lag))
            }
            valid = {k: v for k, v in rows.items() if v.get("terminal_NAV") is not None}
            maximum = max(valid, key=lambda k: valid[k]["terminal_NAV"])
            diag_summary[f"{fee}__lag{lag}"] = dict(
                books=len(rows),
                valid=len(valid),
                positive_terminal=sum(v["terminal_NAV"] > 1 for v in valid.values()),
                expost_max_terminal_id=maximum,
                expost_max_terminal=valid[maximum]["terminal_NAV"],
                expost_max_terminal_CAGR=valid[maximum]["CAGR"],
                expost_max_terminal_Sharpe=valid[maximum]["Sharpe_netstd"],
                selection_or_deployment=False,
            )
    trial_rows = [
        json.loads(x) for x in (P / "economic/model-trial-ledger.jsonl").read_text().splitlines()
    ]
    result["inventory"].update(
        model_files_by_extension=dict(Counter(q.suffix for q in (P / "economic/models").iterdir())),
        trial_status_counts=dict(
            Counter(x.get("status", "linear_validation_candidate") for x in trial_rows)
        ),
        HGB_refits=8,
        HGB_logical_configurations=96,
        HGB_completed_prefixes=96,
        HGB_started_plus_continuation_rows=97,
        HGB_warm_chains=32,
        selected_linear_fold_files=272,
        mean_model_files=17,
        source_model_test_years=17,
        actual_physical_ledger_files=159,
        funded_controls=15,
        host_physical_controls=4,
        host_combined_paths=92,
        DSR_effective_count=4453,
        counts_are_not_interchangeable=True,
    )
    result["economic_judgment"] = dict(
        decision="stop_current_application_defer_deployment",
        reason=(
            "All20 primary20bp physical accounts lose capital and trail SPY/BIL/cash. "
            "The lower-cost physical accounts do not establish the desired substantial "
            "absolute return; no model or cost view is selected after seeing results."
        ),
        highest20bp_terminal_expost_id=best,
        highest20bp_terminal_USD=panel20["candidates"][best]["terminal_NAV"],
        source_full_mechanism_refuted=False,
        source_original_replication_pass=False,
        near_term_2026_profitability_demonstrated=False,
        matched_host_terminal_comparisons=result["matched_host_terminal_comparisons"],
        lower_cost_stale_winner_not_real_time_factor_information_proof=True,
        next_allocation=(
            "Stop this APP allocation and deployment. Do not rescue an observed "
            "cost/window/model. A future source-native15m/PIT or forward study "
            "requires a separately justified plan, actual friction/funding inputs "
            "and fixed matched controls; no new allocation is made here."
        ),
    )
    result["mechanism_judgment"] = dict(
        width="PLS full beats market-only point estimate, maxT p=.6067; increment unproven.",
        algorithm="HGB has higher common All MSE than PLS, maxT p=.9725; no nonlinear credit.",
        measurement="INV is worse on common All target, maxT p=.0050; transform sensitivity, not proof of contamination or no factor mechanism.",
        keys="Removing five groups worsens MSE; nominal p=.0100 but family maxT p=.0850.",
        stale="Twenty-packetday stale features worsen loss, maxT p=.0010; supports timing sensitivity, not standalone funded Alpha.",
        jump_training="CTS vs All training does not improve common All loss, maxT p=.9995.",
        power="Report each HAC SE/MDE and bootstrap interval; nonsignificance is not equivalence.",
        nonlinear_cross_factor_identification=False,
        source_aggregation_and_cleaning_ambiguity_retained=True,
    )
    result["diagnostic_summary"] = diag_summary
    result["host_netstd_Sharpe_comparisons"] = host_sharpe_comparisons
    result["host_leading_availability_resolution"] = bind(P / "host-leading-availability-diff.json")
    result["execution_explanations"] = dict(
        fee_views=(
            "Each cost changes SSignal threshold, affordable integer lot and funding "
            "path; not the same order list repriced. Nonmonotone low-fee returns "
            "are not evidence of negative transaction costs."
        ),
        SPY40="The one scheduled benchmark buy fails cash-gap check, remains20000cash; not a continuously invested SPY40bp result.",
        BIL="Only20bp primary20k BIL book has complete integer-share path; 0/1/5/40 have actual odd-share reverse-split unknown CIL from2017-11-30. Those dependent metrics remain N/A.",
        overnight="Fixed +1 overnight rule dominates20bp threshold books; 18/20 model NAVs equal overnight-only, one higher and one lower.",
        funding="Cash proxy, whole-buy skips and unavailable reference windows preserved; no certified broker settlement, quote or fill.",
        attribution="Additive daily overnight/intraday gross attribution on the same book, not separately reinvested strategies.",
    )
    result["resources_before_independent_result_review"] = snapshot()
    result["author_interpretation_pending"] = False
    result["independent_result_acceptance_pending"] = True
    result["workflow_pass"] = True
    result["workflow_pass_scope"] = (
        "Complete conditional computation and gates; independent final acceptance recorded separately."
    )
    save(path, result)

    lines = [
        "# HF 因子完整条件实测与投资判断",
        "",
        "结论：停止当前应用投入，暂缓部署。研究完成不计合格 Alpha。原20条预测管线、800个四规则诊断、100个独立20k资金账及40个独立4k组合袖套已完成；模型、资金账和组合的收益口径分别保留。",
        "",
        f"主成本为单侧20bp。20条管线全部亏损；事后最高终值为 {best} 的 ${num(panel20['candidates'][best]['terminal_NAV'])}，初始$20,000，CAGR {pct(panel20['candidates'][best]['CAGR'])}、净标准差Sharpe {num(panel20['candidates'][best]['Sharpe_netstd'])}。这只是完整结果中的最大值，不是新选定策略。匹配SPY实物对照终值$39,621.121，BIL$20,943.390，现金$20,000。",
        "",
        "作者300个月、272因子的真实公开1分钟档案已取得。这里是已独立批准的IDX/SUM/INV条件重建；公开净组合1分钟收益不能被声称等同原作者15分钟持仓腿，整日清理、插值、未来因子筛选与PIT风险未消除。固定公共FF市场目标再映射SPY，HGB是明确APP算法。作者19.89%/26.73%年算术均值及以毛二阶矩为分母的Sharpe，均不等于本报告净CAGR/净标准差Sharpe。未恢复原TAQ逐笔报价成本，1bp等成本只是预注册敏感性，不称原论文净收益复现。",
        "",
        "完整源方法评价为2004–2020，六主配对共同93,297窗口/4,280日；资金账为2016-01-04收盘初始化至2020-12-31，共1,259日。所有历史已见，年度时序测试不被改称未经触碰OOS，2020末252/126/63日也不是2026近期。",
        "",
        "**绝对收益与成本**",
        "",
        "|单侧成本|20条中盈利数|事后最高终值管线|最高终值|该管线CAGR|该管线净Sharpe|匹配SPY终值|",
        "|---|---:|---|---:|---:|---:|---:|",
    ]
    for fee, panel in result["fee_panels"].items():
        name = panel["sorted_terminal_diagnostic_only"][0]
        v = panel["candidates"][name]
        lines.append(
            f"|{fee}bp|{len(panel['positive_terminal_profit'])}|{name}|${num(v['terminal_NAV'])}|{pct(v['CAGR'])}|{num(v['Sharpe_netstd'])}|${num(panel['references']['SPY_BH']['terminal_NAV'])}|"
        )
    lines += [
        "",
        "40bp的SPY对照因固定首次整股买入遭遇cash-gap而完全未成交，$20,000是现金路径，不能称成功买入持有。BIL在0/1/5/40bp账本于2017-11-30发生真实奇数旧股反向拆股，未知碎股兑现金额使其连续账及依赖指标N/A；20bp偶数旧股账可用。没有事后改整股数量或填造CIL。",
        "",
        "低成本并未形成足够大的实物资金收益。1bp最优实物终值来自STALE对照，CAGR5.31%；它主要在2020获利，不能由此证明实时宽因子信息增量。SPositive费用阈值和整股资金路径会随成本变动，成本视图不是同一订单序列机械加减费用。",
        "",
        "|管线|20bp终值|20bp CAGR|20bp净Sharpe|20bp超BIL Sharpe|20bp SPY beta|40bp终值|",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for name in ids:
        v = funded[name + "__20"]["full"]
        v40 = funded[name + "__40"]["full"]
        lines.append(
            f"|{name}|{num(v['terminal_NAV'])}|{pct(v['CAGR'])}|{num(v['Sharpe_netstd'])}|{num(v['primary_physical_Sharpe_ex_BIL'])}|{num(v['SPY_beta'])}|{num(v40['terminal_NAV'])}|"
        )
    core = funded["PLS_IDX_CTS__20"]
    lines += [
        "",
        f"PLS主线20bp累计参考费用${num(core['fees'])}，成交{core['filled']}次，{core['unsettled_cash_wait_sessions']}个收盘存在待结算销售现金，平均可用现金${num(core['mean_available_cash'])}。20bp下18/20管线终值等于隔夜规则对照，模型区分大幅消失；HGB_IDX只比它多$244.706，仍亏损超过$11,000。现金到账为已冻结代理规则，不是实际券商结算证明或收益下界。",
        "",
        "**信息与模型贡献**",
        "",
        "|共同All目标配对；正值代表treatment更好|损失差|HAC SE|80%功效MDE|联合maxT p|",
        "|---|---:|---:|---:|---:|",
    ]
    for row in primary["paired"]:
        lines.append(
            f"|{row['contrast']['contrast_id']}|{row['loss_control_minus_treatment']:.9g}|{row['SE']:.9g}|{row['MDE80_two_sided_normal']:.9g}|{row['joint_two_sided_maxT_p']:.6f}|"
        )
    lines += [
        "",
        "宽PLS的All R²为0.158%，市场滞后PLS为0.060%，HGB为0.008%；宽度与HGB增量都没有通过共同六检验的maxT。INV的PLS R²为−0.181%，相对IDX显著变差；这既可能反映测量处理，也可能反映首窗噪声及有效信息被移除，不能单独证明原资料污染。STALE在共同目标上显著较差，说明时效有作用；删除关键五组仅名义p显著，maxT后不显著；CTS训练对共同All目标未展示改善。MDE和区间保留，不把不显著当等效或全机制反证。未加入同HGB市场-only，故不声称识别非线性跨因子贡献。",
        "",
        "**800个诊断与隔夜贡献**",
        "",
        "|成本|延迟窗口|有效诊断|终值>1数|事后最高终值CAGR|该诊断净Sharpe|",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for key, row in diag_summary.items():
        fee, lag = key.split("__lag")
        lines.append(
            f"|{fee}bp|{lag}|{row['valid']}|{row['positive_terminal']}|{pct(row['expost_max_terminal_CAGR'])}|{num(row['expost_max_terminal_Sharpe'])}|"
        )
    lines += [
        "",
        "无资金限制的零成本诊断仍有较大毛收益：一窗口延迟下PLS_IDX_CTS/SPositive CAGR19.79%、Sharpe1.196；IDX HGB为17.65%/1.090，INV PLS为10.06%/0.696。1bp同规则分别降至9.92%、10.50%、4.65%；5bp起全部诊断终值小于1。这不是$20k可实现收益：诊断允许分数持仓，短仓借券仅APP成本，没有ETB与资金证明。",
        "",
        "同账本加总的隔夜毛日收益贡献约0.542；零成本PLS IDX日内部分约0.426，INV日内约−0.002，HGB IDX约0.335。它们是逐日加法归因，不能相加当CAGR或独立复投策略。隔夜持仓、时钟与资金约束在利润转换中起决定作用；不能只用预测R²或毛收益宣称账户Alpha。",
        "",
        "**匹配宿主组合**",
        "",
        f"首次运行发现宿主前段缺值并实际返回N/A；旧输出保留。经独立差异验收，固定第一个五个宿主列都可用的共同收盘{host['first_common_close']}初始化，至{host['last_common_close']}共{host['rows']}日；只处理leading不可用前段，内部缺日/值仍阻断。40个4k资金账独立执行，16k原F1/net10和五分量EW初始后漂移；未把20k路径缩放、未每日80/20再平衡。",
        "",
        "|成本/4k替换对照|可比较40对|终值更高|相同|更低|N/A|",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for key, row in result["matched_host_terminal_comparisons"].items():
        lines.append(
            f"|{key}|{row['compared']}|{len(row['positive_terminal_difference'])}|{len(row['zero_terminal_difference'])}|{len(row['negative_terminal_difference'])}|{row['unknown']}|"
        )
    lines += ["", "以下Sharpe比较与美元比较分开；净Sharpe略高不自动构成有用投资角色。", "",
              "|成本/替换对照|净Sharpe更高|相同|更低|N/A|", "|---|---:|---:|---:|---:|"]
    for key, row in host_sharpe_comparisons.items():
        lines.append(f"|{key}|{len(row['higher'])}|{len(row['equal'])}|{len(row['lower'])}|{len(row['unavailable'])}|")
    lines += [
        "",
        "每对仅删其共同初始化行计算日收益差；host原net10不冒充20bp。完整host-results保留每项净Sharpe、beta、终值差和HAC；host HAC是逐对描述，不能套用六个预测损失检验的联合校正。低相关或Sharpe局部改善须与美元损益一起判断。",
        "",
        "**试验、资源与可主张边界**",
        "",
        "实际3,513个唯一逻辑模型配置/3,610行试验记录；272个线性选中fold文件、17个历史均值文件、96个HGB前缀文件，共385个文件。32条HGB warm chain、8次五年重拟合、96个完成配置；96个started和1个continuation_started保留旧350失败暴露。共享矩计算不等于每个CV配置独立重训。DSR的4,453包含所有配置和940个经济视图，为已见历史的描述性独立零假设近似；PBO/SPA及未见OOS晋级N/A，不以DSR替代严格20bp超BIL>1门。",
        "",
        "两次Agent断流没有停止原计算。原PID1418348账户进程在700预约不足时于同一36,000总池内改为1,200预约，实际退出0、750.98 CPU秒；无重复启动或账户重跑。旧450失败、未知暴露、全部source/prep费用与旧预约保留；本次无新付费、source、market、云或下单。报告中的资源快照为独立终验之前，最终唯一结算见完成回执。",
        "",
        "停止的是这个公开输入重建与现金代理应用，不是否定作者完整机制。未来若有原生15分钟腿/PIT形成资料、实际低摩擦与融资执行证据，可另按完整计划检验；本次不追加已见窗口、改参数或挑事后获利成本救结果。research_pass、ml_contribution_pass、paper_ready_pass均false，原论文原数值复现未通过，真实fill/结算/借券与2026当前收益未证明。",
        "",
        "独立结果验收尚待本包review；所有数值直接绑定economic/results，旧结果、失败和批准版本原字节保留。",
    ]
    (P / "complete-costed-result.md").write_text("\n".join(lines) + "\n")
    print(json.dumps(dict(result=bind(path), report=bind(P / "complete-costed-result.md"))))


if __name__ == "__main__":
    main()
