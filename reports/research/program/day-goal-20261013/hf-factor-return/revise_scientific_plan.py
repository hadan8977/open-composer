# ruff: noqa: E501
"""Apply the four independently requested scientific corrections; no economics."""

import hashlib
import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from open_composer.market_sessions import _early_closes, us_equity_session_close

P = Path(__file__).parent
ROOT = Path.cwd()


def bind(path):
    return {
        "path": str(path.resolve().relative_to(ROOT)),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "bytes": path.stat().st_size,
    }


def save(path, obj):
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n")


def archive(name, version):
    original, saved = P / name, P / version
    if not saved.exists():
        saved.write_bytes(original.read_bytes())


def main():
    archive("scientific-plan.json", "scientific-plan-v1.json")
    archive("execution-contract.json", "execution-contract-v1.json")
    archive("independent-plan-review.json", "independent-plan-review-v1.json")
    old = json.loads((P / "scientific-plan-v1.json").read_text())
    assert (
        bind(P / "scientific-plan-v1.json")["sha256"]
        == "e8681f8c8ea2e38c23c5ecdc381604940aaac41724d4cf3dab6e08f1fcb6b3e9"
    )
    plan = json.loads(json.dumps(old))
    f, v, e, inference, resource = (
        plan[k]
        for k in (
            "feature_and_label",
            "validation_and_models",
            "execution_and_capital",
            "inference_and_contribution",
            "resources_and_gates",
        )
    )

    rows = []
    day = date(1996, 1, 1)
    while day <= date(2020, 12, 31):
        if day.weekday() < 5:
            rows.append(
                {
                    "date": str(day),
                    "nominal_source_open": "09:30:00",
                    "nominal_source_close": "13:00:00"
                    if day in _early_closes(day.year)
                    else "16:00:00",
                    "activation": "only after actual source09:30 row is observed; no future file/date/tail lookup",
                }
            )
        day += timedelta(days=1)
    calendar = {
        "schema_version": 1,
        "role": "fixed_conditional_source_clock_not_verified_venue_history",
        "timezone": "America/New_York wallclock APP assumption",
        "rows": rows,
        "primitive": bind(ROOT / "open_composer/market_sessions.py"),
        "rules": "Monday-Friday decision grid. Helper _early_closes independent dateformula supplies13:00 dates, others16:00. Helper holiday/specialclosures are NOT used to reject observedsourcepacket dates. Actual09:30 row activates currentpacketday whenobserved; no calendar may be inferredfromthatday's futuretail.",
        "limits": "This conditional grid is deliberately not called actualNYSE calendar. Earlydateexceptions not in primitive and lateauction/cleaning tails can remain uncertain. Postdeclaredcutoff rows quarantined, missinggrid rows not filled. Observedfuturetail cannot select currentwindows. ActualSPYfundedscope has separatecalendar/providerclock QA.",
    }
    save(P / "source-conditional-clock.json", calendar)
    funded_rows = []
    day = date(2016, 1, 1)
    while day <= date(2020, 12, 31):
        close = us_equity_session_close(day)
        if close is not None:
            funded_rows.append(
                {
                    "date": str(day),
                    "open": "09:30:00",
                    "close": str(close),
                    "regular15_windows": 14 if close.hour == 13 else 26,
                }
            )
        day += timedelta(days=1)
    save(
        P / "funded-SPY-clock-proposed.json",
        {
            "schema_version": 1,
            "role": "separate2016_2020SPYclock_inputgate_not_actual_observations",
            "calendar_primitive": bind(ROOT / "open_composer/market_sessions.py"),
            "timezone": "America/New_York",
            "rows": funded_rows,
            "gate": "Match independently with actualSPY SIP15Min UTC/regularstart/end andrawdaily dates/close evidence. Calendar/clock conflicts retained andresolvedbeforeeconomicgo, no futurereturn screens. No accurate1996 venuehistory claim.",
            "actual_market_clock_accepted": False,
        },
    )

    f["calendar"] = (
        "唯一 sourceconditionalclock：绑定source-conditional-clock.json，Mon-Fri固定09:30开盘/16:00名义截止，固定helper _early_closes日期公式的日期13:00截止；不以helper holiday/specialclosures删source09:30已观测packet日期。1996/97MLK等实际source09:30可激活，不宣称NYSE全历史verified。当前09:30观测激活packetday，不能按当日未来文件存在/尾时间回推。规则cutoff后行隔离；缺行不补。原行与每条异常保留。2016..2020资金账独立绑定funded-SPY-clock-proposed与实际SPY intraday/daily输入QA，不能把source条件时钟用于证明可成交。"
    )
    f["windows"] = (
        "Fixed15 grids09:30+15*k, target按固定名义cutoff最多14/26。每格仅消费截至signal已成熟的15行09:31..，09:30隔夜单列。hour严格四个同日成熟格。当前packet是否可用只看当时及过去格，不能看当前日最后一行、未来label/收盘完整性；target缺失仅在事后统计评价记N/A，不能撤销当时signal/order。source日内cutoff不随未来尾行改变。"
    )
    f["IDX"] = (
        "Mature15窗口L=sum(log1p(rminute))，hour=last4L平均。上一sourcepacketday channel=其已成熟固定网格窗口L之和+单列已观测09:30 overnight log；至少4格且首格/overnight有效，部分尾格不入、完整性/缺格数量保留。不是完整close-to-close在缺行短日时已恢复，也不是原腿15m。当前日不能以未来完整性筛选。"
    )
    f["SUM"] = (
        "Mature15窗口simple SUM，hour last4SUM平均；上一packetday channel=已成熟固定grid simpleSUM之和+已观测09:30值，min4格且首格/overnight有效。target保持同一FF_IDX log格，不随SUM改变。"
    )
    f["INV"] = (
        "B[j,k]=SUM15[j,k]-SUM15[j,1]，首成熟基准之后才用；hour最后4B平均，prevchannel为上一packetday所有已成熟固定等长格B之和（min4格且首格有效），无overnight。上一日可用已完成格数量是已知过去；不以本日未来尾行筛信号。每个被消费格严格15观察，同日加c的假设下每个B消15c；不是log不变量，不恢复pricecleaning/PIT。FFmarket不假设带c，INV marketchannel是显式信息变换，target仍FF_IDX。"
    )
    f["common_prediction_clock"] = (
        "同一固定sourcegrid，k=4..nominal_n-1（full10:30..15:45，conditional13:00日10:30..12:45）。只用当时packet成熟条件：current/hour/previouspacketday/firstanchor/20pastpacketdaystale输入均有效的共同定义，signal不受未来target是否有值影响。无packet记录N/A forecast与账户zero-risk fallback，不能把missing m=0后在band内错误保留旧desired。所有来源统计报告coverage和calendar不确定；actualSPY交易clock只在其真实资金scope中另裁切。"
    )
    f["feature_sets"] = (
        "ALL272、MKT ff__mkt、KEY6=market+source5、MINUS5、STALE保持市场当前而其他factorHAR取20个已激活source09:30packetday之前的同clock packet。这里20packetdays不是verifiedexchange-session标签。STALE/INV使用同一因果过去索引/共同可用时钟，不读取futurelabels。sourcecatalogue符号只做来源注释，使用已发布实际return不再乘orientation sign。"
    )
    f["jump"] += (
        " 修订clock：tau仅取之前已激活packetdays中按绑定固定grid有完整26格的252日/min52，全天冻结；非完整/conditional14格日不当完整26日，当前日没有futuretail筛选。当前短日已有格仍以26nominal Delta为source推导APP惯例。"
    )

    v["Ridge"] = (
        "原OA.3.2.2：min SSE/n_train+lambda||b||²；100自然loglambda点[-1,8]，beta=(XTX/n_train+lambda I)^-1 XTy/n_train。未归一化solver必须alpha=n_train*exp(grid_value)，或Gram直接n_train*lambda。n_train是共同成熟特征/已成熟训练label的训练80%实际行数，非fulltrain+valid/全期/predictor数。X/y仅训练中心/scale，截距不惩罚，常量列beta0；恢复y训练mean/std。独立同syntheticdata closedform vsnormalized objective vs sklearn Ridge(alpha=n*lambda)数值等价验收，不把遗漏n称普通数值差。"
    )
    e["signal_rules"] = (
        "冻结APP FFlog forecast score m -> SPY target启发式：SSign m>h:+1，m<-h:-1，其余保持v；SPositive m>h:+1，m<-h:0，其余保持v。理论OA5.2是score*m*w-h|w-v|的数学解，并不是已证明FFlog m等于SPY条件simpleexpectedreturn或wealth最优。原printedEq6/7负号歧义依附录重建，不声称作者actualcode已修。fractional诊断v是上次理想已执行target；funded v为本时刻pending执行后真实heldq>0的0/1，不能用未成交desired。Sign/Positive只在诊断层固定显示；20k仅SPositive。"
    )
    e["cost_map"] = [
        {
            "bps_each_side": b,
            "cost_c": b / 10000,
            "threshold_h": b / 10000,
            "h_not_divided_again": True,
        }
        for b in (0, 1, 5, 20, 40)
    ]
    e["cost_views"] = (
        "每侧成交单位名义费用c=0/.0001/.0005/.002/.004，h=c；20bp h=.002，不再/2。只有当某观测fullspread存在时c=spread/2。未知TAQ不推造原费用，1/5bp明确假设。0/1/5/20/40各自threshold/orderpath与现金账、40fundedstress自己affordability；固定20orders加40费用仅unfunded诊断。Source short fractional仅2%annualborrow假设，无ETB/资金资格。手续费计每次opening/closing/overnight变更，idlecash0，无真实impact校准。"
    )
    e["initial_and_open"] = (
        "初始化firstcommonclose全20k cash，无初始化夜间买入，所有paired comparison只删自己的初始化行。之后每个SPY真实session09:30确定intraday目标0：先依据priorclose-heldq登记exdate应收/实际split及proxy到期现金，再执行上一closing后已知heldq的opening清仓参考单，手续费和sale待结计入；没有openbar则no-fill并过期。首小时无forecast固定zero-risk，不隐含09:30买入。SPY/BILBH controls在首个初始化后09:30单独按priorclose冻结lots买入，同成本/现金proxy；overnightonly用同night/opening规则。"
    )
    e["event_order"] = [
        {
            "rank": 1,
            "at": "09:30 before open reference",
            "action": "Dueproxycash/dividendpay conversion and corporateexdate entitlement frompriorcloseholding; actualsplit applied. Freezeopeningexit sellquantity fromknownheldq.",
        },
        {
            "rank": 2,
            "at": "09:30 open reference",
            "action": "Executeopeningtarget0 ifactualSPYopen available, otherwiseexpire/no-fill. No forecast/firsthourbuy. availablecash excludesunsettledsales.",
        },
        {
            "rank": 3,
            "at": "each interior15minute start t",
            "action": "Execute pending fromt-15 usingactualbaropen t; pre-frozenquantity neverusesnewbarclose; gap/cash failure skipswholebuy. Pending expires afterthissingleattempt; updateactualheldq, cash,待结 andfees.",
        },
        {
            "rank": 4,
            "at": "t after precedingbar completion is processed",
            "action": "Observe only precedingregularbarclose endingt/source rows<=t; formmaturepacket. validm computes targetusingv=actualheldstate AFTERrank3. missingpacket hasexplicitfallback0, notnumericm0/in-bandhold.",
        },
        {
            "rank": 5,
            "at": "t new pending",
            "action": "Freeze lot usingknownpreviousbarclose endingt andactualavailablecash afterpriorfill; scheduleonlynextfullbaropen t+15 strictlybeforeactualclose. No retry/rollover; sameactualheldtarget hasno rebalance/dividendtopup.",
        },
        {
            "rank": 6,
            "at": "close-15 after priorpending execution and precedingbar observed",
            "action": "Closingnighttarget+1 supersedeslateintradayforecast. Cancelpending dueclose. Ifalreadyheld maintainq; ifflat freezewholebuy floor(availablecash/(knownprecedingbarclose*(1+c))). Thisis lastregularbarSTART, not futurelastbarclose.",
        },
        {
            "rank": 7,
            "at": "actualclosingbell",
            "action": "Executefrozennightlot atlastregularbarclose reference onlyifactualprice+cost<=availablecash; otherwisewholebuy skip/expire. Nofutureclose sizing. CloseNAV thenheldq*boundclosingmark+cash+pendingnetsales+dividendreceivable. Freezeknownheldq openingexit fornextactualsession.",
        },
    ]
    e["funded_clock"] = (
        "以独立SPY actual2016..2020固定日历+rawbars clock执行上述event_order。来源score m预测下一格，但fundedorder下一完整baropen才执行，形成一格延迟，不重新训练/改变target掩盖滞后。每次下单用本时刻实际holding，非理想desired。缺包fallback0在下一允许baropen尝试清仓；开盘/执行bar缺失均不填价、不强制成交，单次pending过期。lategrid/收盘由night单覆盖。rawbar open/close均研究参考而非实际ask/bid/fill/auctionproof。"
    )
    e["integer_gap_cash"] = (
        "flat->long冻lot floor(availablecash/(known precedingbarclose*(1+c)))，下一允许open或nightclose实际参考价+fees超cash则wholebuy skip，不能用actualfutureprice当时downsize。long->flat仅sell实际heldq。No-fill不会改变q/v、不会保留旧desired当新holding；后续新packet重新从实际v判断。每单仅一次到期；缺bar、cashgap、invalidlot各自reason保存。matchedheldtarget无dailyresize，divcash不自动加仓。sale进入待结，positivecash longonly无借贷。"
    )
    e["overnight"] = (
        "Fractional source-like诊断夜间+1、firsthour0和opening/closingturnover均报。资金账户night+1只是已知lastbarstart目标：close-15参考previousbarclose冻lot，close单次affordability；cash不足夜间0/部分整股risk真实保留，不forcednegativecash。夜间收益归market exposure而非预测Alpha。opening退出与收盘重新入场分开计费。"
    )
    e["pending_policy"] = {
        "validity": "single scheduled referenceclock attempt only; no rollover/retry",
        "no_fill": "q unchanged, pending clears; nextdecision usesactualv",
        "missing_packet": "forecastN/A; explicitdesired0 exit atnextpermittedopen ifheld, otherwisecash",
        "night_priority": "atclose-15 cancel close-due intradaypending; frozennightlot soleclosingorder",
        "position_in_band": "keepactualv; never infer q fromunfilleddesired",
    }

    contrasts = [
        ("C1_PLS_WIDTH", "PLS_IDX_CTS", "PLS_IDX_MKT", "同PLS模型的宽信息增量"),
        (
            "C2_FULL_ALGORITHM",
            "HGB_IDX_CTS",
            "PLS_IDX_CTS",
            "同全信息算法增量；不识别nonlinear crossfactor attribution",
        ),
        ("C3_MEASUREMENT", "PLS_INV_CTS", "PLS_IDX_CTS", "相同市场target下测量/adjustment敏感性"),
        (
            "C4_DELETE_KEYS",
            "PLS_IDX_MINUS5",
            "PLS_IDX_CTS",
            "删五组后MSE改善/恶化，不是全因子科学否定",
        ),
        ("C5_STALE", "PLS_IDX_STALE", "PLS_IDX_CTS", "20过去packetdays的时效对照"),
        (
            "C6_JUMP_TRAIN",
            "PLS_IDX_CTS",
            "PLS_IDX_ALL",
            "不同训练label对同一All实际target的预测损失增量",
        ),
    ]
    inference["primary_contrasts"] = [
        {
            "contrast_id": ident,
            "treatment_id": a,
            "control_id": b,
            "evaluation_target": "All public ff__mkt IDX realisedlog15window",
            "loss": "squared_error",
            "positive_direction": "L_control-L_treatment;positive means lower treatment loss",
            "interpretation": meaning,
        }
        for ident, a, b, meaning in contrasts
    ]
    inference["statistical"] = (
        "全部20管线都在同All实现target及同Cts实现target各报告uncenteredR2/RMSE，训练label不是各自评价label。6主对比exact IDs见primary_contrasts，全部共同Alltarget；Cts共同target相同6对比仅预注册描述诊断，未新增primarymaxTfamily。paired使用事前maturepacket clock+两个预测有限且target事后已成熟的交集；共同六家族用全部六对共有时间戳/日，不按loss择行/范围。futuretarget缺失只在评价计N/A，并报告forecast/order当时是否已发，不回改policy。先报pooledwindowMSE；inference聚合每日lossdifferenceSUM和commonwindowcount，delta=sumdiff/sumcount，HAC lag5对中心化daily sumscore，20packetday blocks2000draws seed20261013使用sumdiff/sumcount比例，jointmaxT6、相同draws、sign如表。年段/覆盖/缺失交集逐项披露；CTS-vsALL不比较各自不同target的loss。"
    )
    inference["nonlinear_claim_boundary"] = (
        "保持20候选和原资源，不追加HGBmarket-only。HGBfullvsPLSfull只证明同全信息算法增量（若显著），不能单独证明非线性跨因子贡献；宽信息增量仅相同PLS full-vsMKT/缺组/stale支持。INV配对也是PLS信息变换证据。"
    )
    plan["decision_rule"] += (
        " HGB任何改善仅按同全信息算法增量解释，未识别非线性跨因子贡献；不会事后拿不同label的MSE作jump收益证据。"
    )
    resource["calibration_cell"] = {
        "candidate_id": "HGB_IDX_CTS",
        "test_block_start_year": 2019,
        "training_end_year": 2018,
        "depth": 6,
        "learning_rate": 0.1,
        "max_iter_checkpoints": [50, 150, 350],
        "random_state": 20261013,
        "cpu_termination_coreseconds": 450,
        "memory_cap_MiB": 900,
        "economics_and_test_performance_hidden_until_resource_projection": True,
        "retention": "actualsuccessful50/150/350 fittedcheckpoints retained; failed/incompleteCPU counted. Nativefullgates first, notsourceQA fit.",
    }

    plan["bindings"]["source_conditional_clock"] = bind(P / "source-conditional-clock.json")
    plan["bindings"]["funded_SPY_clock_proposed"] = bind(P / "funded-SPY-clock-proposed.json")
    plan["bindings"]["calendar_findings_at_independent_review"] = bind(
        P / "calendar-source-clock-findings-at-plan-review.json"
    )
    plan["created_at_utc"] = datetime.now(UTC).isoformat()
    plan["status"] = "complete_R1_R4_scientific_revision_economic_closed"
    assert plan["candidates"] == old["candidates"]
    save(P / "scientific-plan.json", plan)
    contract = {
        "schema_version": 1,
        "task_id": plan["task_id"],
        "author": plan["author"],
        "scientific_plan": bind(P / "scientific-plan.json"),
        "status": "proposed_R1_R4_full_contract_economic_closed",
    }
    for key in (
        "feature_and_label",
        "validation_and_models",
        "execution_and_capital",
        "inference_and_contribution",
        "resources_and_gates",
    ):
        contract[key] = plan[key]
    save(P / "execution-contract.json", contract)
    changed = {
        key: {"old": old.get(key), "new": plan.get(key)}
        for key in plan
        if plan.get(key) != old.get(key)
    }
    save(
        P / "scientific-plan-revision.json",
        {
            "schema_version": 1,
            "task_id": plan["task_id"],
            "author": plan["author"],
            "reviewer": plan["reviewer"],
            "binding": {
                "old_plan": bind(P / "scientific-plan-v1.json"),
                "old_contract": bind(P / "execution-contract-v1.json"),
                "old_review": bind(P / "independent-plan-review-v1.json"),
                "new_plan": bind(P / "scientific-plan.json"),
                "new_contract": bind(P / "execution-contract.json"),
                "source_clock": bind(P / "source-conditional-clock.json"),
                "funded_clock": bind(P / "funded-SPY-clock-proposed.json"),
            },
            "addressed": [
                "R1_sample_normalized_ridge",
                "R2_fixed_conditional_clock",
                "R3_cost_cash_known_order_clock",
                "R4_common_target_exact_contrasts",
            ],
            "candidate_inventory_unchanged": True,
            "new_fit_source_market_economic": 0,
            "changed_top_level": sorted(changed),
            "diff": changed,
            "source_and_budget_scope_unchanged": True,
            "input_implementation_native_resource_economic_ready": False,
        },
    )
    print(
        json.dumps(
            {
                "plan": bind(P / "scientific-plan.json"),
                "contract": bind(P / "execution-contract.json"),
                "revision": bind(P / "scientific-plan-revision.json"),
            }
        )
    )


if __name__ == "__main__":
    main()
