"""Receive saved engine numbers into the finite component report; no accounts."""
from pathlib import Path
import json, sys, re, math
import pandas as pd
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from research.peer_earnings_increment_20261103.prepare import BASE,OUT,STOCKS,rel
from open_composer.research.agent_workflow import Results

def read(name):
    return json.loads((OUT/name).read_text())

def main():
    result=read('results.json')
    table=read('primary-summary.json')
    lookup={(x['arm'],x['cost_multiplier']):x for x in table}
    contrasts=read('contrasts.json')
    matches=read('matching-summary.json')
    inputs=read('inputs.json')
    coverage=pd.read_csv(OUT/'coverage.csv')
    counts=read('counts.json')
    # Preserve every actual failed/successful local invocation and unknown provider dollars.
    resources=[]
    for p in sorted(OUT.parent.glob('*.resource.txt')):
        text=p.read_text()
        def field(label):
            m=re.search(r'^\s*'+re.escape(label)+r': (.+)$',text,re.M)
            return m.group(1) if m else None
        signals=re.findall(r'Command terminated by signal (\d+)',text)
        status=field('Exit status')
        resources.append({'artifact':rel(p),'elapsed':field('Elapsed (wall clock) time (h:mm:ss or m:ss)'),
            'user_cpu_seconds':field('User time (seconds)'),'system_cpu_seconds':field('System time (seconds)'),
            'max_rss_kib':field('Maximum resident set size (kbytes)'),'exit_status':status,
            'termination_signal':signals,
            'observed_outcome':'terminated' if signals else ('unknown' if status is None else ('complete' if status=='0' else 'failed')),
            'resource_receipt_complete':bool(field('Elapsed (wall clock) time (h:mm:ss or m:ss)'))})
    original=json.loads((OUT.parent.parent/'run.json').read_text())
    recovery=read('quota-recovery-complete.json')
    costs={'local_invocations':resources,'new_remote_jobs':0,'new_paid_data_requests':0,
        'actual_provider_dollars':None,'original_worker_tokens':None,'recovery_tokens':None,
        'usage_source':'Original run.json/event logs retained. Original Worker ended at provider usage limit with no usage receipt; recovery/Lead tokens are not settled here. Repeated reviewer session usage uses fieldwise maxima, not a sum.',
        'original_driver_status':original['status'],
        'original_driver_elapsed_seconds':original['elapsed_seconds'],
        'original_usage':original['efficiency']['tokens'],
        'quota_recovery':recovery,
        'ancestor_unknown_costs':'Earlier provider dollars, failed attempts and old Modal estimate remain in predecessor Lead ledger; no reset, no duplicate addition.',
        'failed_preparation_logs':[rel(p) for p in sorted(OUT.parent.glob('prepare*.log')) if 'Traceback' in p.read_text() and 'KeyboardInterrupt' not in p.read_text()],
        'interrupted_preparation_logs':[rel(p) for p in sorted(OUT.parent.glob('prepare*.log')) if 'KeyboardInterrupt' in p.read_text()],
        'interrupted_preparation':'input-binding-interruption.json and input-binding-interruption-close.json; verified own unfinished metadata process terminated after SIGINT was ignored; original driver and Martin jobs preserved',
        'funding_probe_repair':'funding-probe-repair-reconciliation.json: prepared funding probes match original costs and 64-bisection results bitwise; actual fills still call original cost; completed accounts reused, interrupted attempt retained',
        'failed_accounts':counts['failed_accounts'],'unresolved_checkpoints':[]}
    (OUT/'cost-reconciliation.json').write_text(json.dumps(costs,ensure_ascii=False,indent=2)+'\n')
    primary=[x for x in contrasts if x['model'].startswith('ME_') and x['control'].startswith('MP_')]
    recent_robust=all(x['increment_usd']>0 and x['trailing250_increment_usd']>0 for x in primary)
    interval_robust=all(x['simultaneous95_daily_low']>0 for x in primary)
    decision='具有固定构造的正向增量，仍需独立接收后定义下一问题' if recent_robust and interval_robust else '本构造未建立稳健的近期净信息增量；建议收口这十四项固定政策'
    lines=[f'同行财报条件信息：{decision}。这是当前行业表条件下的已见窗口组件比较，尚待 fresh Lead 接收；未认证历史可交易收益。',
        '',f'在独立注资的20,000美元长仓／现金账户中比较十四项政策，固定覆盖2024-01-08至2026-09-15的674个交易日。E为同行财报反应，P为行业五日价格，M为个股252至21日动量，ME／MP分别将E／P与M等权合成，L为流动性，MX为固定跨行业旋转安慰剂。两个调仓周期从2024-01-05收盘开始，每5／20会话调仓。每档成本有16个原始账户，风险匹配另计。',
        '', '决定性比较是ME−MP，排除行业价格与个股动量联合构造的替代解释。下表美元均来自完整独立资金路径；最近250日沿用该路径，没有重置本金。区间是十项主要差额联合maxT的年化日均收益率区间，不能当作美元区间或预测。',
        '', '| 周期／成本 | ME净美元 | MP净美元 | 增量美元 | 最近250日增量 | 同波动增量美元 | 年化均值差95%联合区间 |',
        '|---|---:|---:|---:|---:|---:|---|']
    for x in primary:
        h=int(x['model'].split('_H')[1]);c=x['cost_multiplier']
        mm=next(m for m in matches if m['model']==x['model'] and m['control']==x['control'] and m['cost_multiplier']==c)
        match=f"{mm['increment_usd']:,.2f}" if mm['matched'] else '未匹配'
        lines.append(f"| {h}日／{c}x | {lookup[(x['model'],c)]['net_profit_usd']:,.2f} | {lookup[(x['control'],c)]['net_profit_usd']:,.2f} | {x['increment_usd']:,.2f} | {x['trailing250_increment_usd']:,.2f} | {match} | [{x['simultaneous95_annualized_low']:.2%}, {x['simultaneous95_annualized_high']:.2%}] |")
    lines+=['','四组ME−MP的完整、近期和同波动净差额均为负，联合区间均跨零。经济比较支持收口当前固定构造；区间宽度和行业映射条件限制了对机制真实效应的判断。']
    gross_deltas=[];cost_deltas=[]
    for x in primary:
        a,b=lookup[(x['model'],x['cost_multiplier'])],lookup[(x['control'],x['cost_multiplier'])]
        gross_deltas.append(a['gross_pnl_usd']-b['gross_pnl_usd'])
        cost_deltas.append(sum(a['costs_usd'].values())-sum(b['costs_usd'].values()))
    lines+=['','按上表行序，ME−MP毛损益差为'+ '／'.join(f'${v:,.2f}' for v in gross_deltas)+
        '，实际交易费用差为'+ '／'.join(f'${v:,.2f}' for v in cost_deltas)+
        '。费用较低已缓和账户落后，完整窗口的净差仍为负。这是不同资金路径的记账分解，不能视作独立的因果alpha。']
    lines+=['','五类预定差额全部列出。各格为完整窗口／最近250日净美元差，均以左臂减右臂；联合区间、日均差、maxT和HAC5明细保留在contrasts.json。','',
        '| 差额 | 5日1x | 5日2x | 20日1x | 20日2x |',
        '|---|---:|---:|---:|---:|']
    for a,b in [('ME','MP'),('ME','M'),('E','P'),('E','L'),('ME','MX')]:
        cells=[]
        for h,c in [(5,1),(5,2),(20,1),(20,2)]:
            x=next(x for x in contrasts if x['model']==f'{a}_H{h}' and x['control']==f'{b}_H{h}' and x['cost_multiplier']==c)
            cells.append(f"{x['increment_usd']:,.2f}／{x['trailing250_increment_usd']:,.2f}")
        lines.append('| '+a+'−'+b+' | '+' | '.join(cells)+' |')
    lines+=['','完整政策及机会成本如下。两档费用为各自重新注资、按实际成交支付的资金路径，不能把2x账本当作1x利润简单减一次费用。','',
        '| 政策 | 1x净美元 | 2x净美元 | 最近250日1x | 最近250日2x | 1x交易成本 | 2x交易成本 |',
        '|---|---:|---:|---:|---:|---:|---:|']
    for arm in [*STOCKS,'SPY','CASH']:
        a,b=lookup[(arm,1)],lookup[(arm,2)]
        ca=sum(a['costs_usd'].values());cb=sum(b['costs_usd'].values())
        lines.append(f"| {arm} | {a['net_profit_usd']:,.2f} | {b['net_profit_usd']:,.2f} | {a['trailing250_net_profit_usd']:,.2f} | {b['trailing250_net_profit_usd']:,.2f} | {ca:,.2f} | {cb:,.2f} |")
    lines+=['','所有政策的波动、回撤、现金与成交暴露见下表（1x／2x）。恢复状态、年贡献、费用分项、换手和全部成交保留在账户文件。','',
        '| 政策 | 年化夏普1x／2x | 年化波动1x／2x | 最大回撤1x／2x | 平均现金1x／2x | SPY beta 1x／2x |',
        '|---|---|---|---|---|---|']
    def num(v):return 'N/A' if v is None else f'{v:.2f}'
    for arm in [*STOCKS,'SPY','CASH']:
        a,b=lookup[(arm,1)],lookup[(arm,2)]
        lines.append(f"| {arm} | {num(a['sharpe_annual_252'])}／{num(b['sharpe_annual_252'])} | {a['annual_volatility']:.2%}／{b['annual_volatility']:.2%} | {a['max_drawdown']:.2%}／{b['max_drawdown']:.2%} | {a['mean_cash_fraction']:.2%}／{b['mean_cash_fraction']:.2%} | {num(a['beta_to_SPY'])}／{num(b['beta_to_SPY'])} |")
    lines+=['','年度分解显示两种时钟的结果并不一致。下表为1x成本ME−MP净美元；2026年只截至9月15日，不能与完整年度等长比较。','',
        '| 周期 | 2024年 | 2025年 | 2026年至9月15日 |',
        '|---|---:|---:|---:|']
    for h in [5,20]:
        a={x['year']:x['net_pnl_usd'] for x in lookup[(f'ME_H{h}',1)]['annual']}
        b={x['year']:x['net_pnl_usd'] for x in lookup[(f'MP_H{h}',1)]['annual']}
        lines.append(f"| {h}日 | "+' | '.join(f'{a[y]-b[y]:,.2f}' for y in [2024,2025,2026])+' |')
    shortfalls=[]
    for h in [5,20]:
        a=next(p.parent for p in (OUT/'accounts').glob(f'ME_H{h}-c1-s0x1_0000000000000p0*/complete.json'))
        b=next(p.parent for p in (OUT/'accounts').glob(f'MP_H{h}-c1-s0x1_0000000000000p0*/complete.json'))
        aa=json.loads((a/'attribution.json').read_text())['gross_pnl_by_symbol_usd']
        bb=json.loads((b/'attribution.json').read_text())['gross_pnl_by_symbol_usd']
        gaps=sorted(((s,aa.get(s,0)-bb.get(s,0)) for s in set(aa)|set(bb)),key=lambda x:(x[1],x[0]))[:3]
        shortfalls.append(f'{h}日差额中最大的三项个股毛贡献落后为'+ '、'.join(f'{s} ${v:,.2f}' for s,v in gaps))
    conc=pd.read_csv(OUT/'concentration.csv')
    ci=conc.loc[conc.max_issuer_weight_at_fill.idxmax()]
    cg=conc.loc[conc.max_entry_industry_weight_at_fill.idxmax()]
    lines+=['','；'.join(shortfalls)+'。这些是不同实际持仓路径的毛记账差，费用另列，不能解释为个股因果效应。',
        '',f"28个股票政策／成本视图的最大成交后发行人权重为{ci.max_issuer_weight_at_fill:.2%}（{ci.arm}、{ci.cost_multiplier}x），最大入场行业权重为{cg.max_entry_industry_weight_at_fill:.2%}（{cg.arm}、{cg.cost_multiplier}x）。固定20个5%槽位仍可能集中于一个行业；全量浓度见concentration.csv，发行人／行业毛贡献见各账户attribution.json。"]
    lines+=['',f"实际覆盖：历史U500的跨期并集{inputs['historical_U500_union']}个代码；每5会话观察{len(coverage)}个决策，{int(coverage.zero_coverage.sum())}次无覆盖而持有现金。覆盖人数中位数{coverage.covered_recipients.median():.0f}，最小{coverage.covered_recipients.min()}，最大{coverage.covered_recipients.max()}；不足两个行业、安慰剂无辨识力的决策{int(coverage.placebo_uninformative.sum())}次，其中包含无覆盖决策。当前SIC版本为{', '.join(inputs['SIC_vintage'])}，并非历史PIT；空SIC和歧义链接未进入默认Other行业，超出有界链接日期不向外猜测。行业／年／发行人覆盖、财报元数据拒绝原因均保留。",
        '',f"数据绑定了{inputs['event_rows_bound']}个财报事件，去重{inputs['duplicate_accessions_removed']}个重复accession；采用Item 2.02、有效8-K及已记录的接受来源。反应为严格晚于接受时刻的首个实际收盘，减去SPY同端点回报；在过去五会话每发行人仅留最新事件，各臂均排除自身发行人的近期事件。该信息可能晚于新闻稿，只支持filing-conditioned价格反应，不能称盈利意外。",
        '', '来源边界沿用已接受的source-notes.json：Hou研究为行业内扩散提供动机，关注点包含负面信息及大小公司差异，其全文方法仍未取得；当前高流动性长仓构造未复制该方法。已取得的日频领先衰减反证也不能直接否定现代财报条件效应。本轮没有刷新或改换来源。',
        '', '资金与价格约定：保留旧持仓隔夜收益，次日开盘按原生经济碎股单位成交；先按风险缩放，再一次性按固定初始本金过滤低于100美元的目标，所有非零差额和退出均成交。卖出固定、买入统一缩减以支付原始费用，64次二分求可行系数。开盘价差来自09:35至09:45报价快照及年度校准，缺失股票输入使用40bp价差、缺失冲击按原生约定处理。没有融资、借券、现金利息或期末强制平仓。',
        '',f"记账检查：全部完成账户的每日权益、现金、成交及费用逐项核对；32个原始账户的发行人／入场行业毛贡献以原生价格腿和已保存实际成交归因，不能称净alpha。缺失持仓标记共{sum(x['missing_mark_days'] for x in table)}条账户／标的／日记录，陈旧开盘成交{sum(x['stale_open_orders'] for x in table)}条，未认证兑付桥接{sum(x['uncertified_entitlement_bridges'] for x in table)}条（不同成本的独立账户会重复观测同一市场事件）。如存在桥接，其最后标记释放是模拟约定，真实权益没有被认证。",
        '', '风险匹配只将较高波动的一臂与独立现金混合并缩仓。区间在结果之前冻结为[0,0.1−1e−9]和[0.1,1]，各段5个节点，取最小有效根，年化波动差容差1e−6；跨100美元目标过滤跳跃的无根状态不插值。匹配账户及每次求根探测保留，属于事后描述。',
        '', '统计使用同一个63会话循环区块矩阵、1,999次抽样及固定种子20261103；每档成本联合覆盖五个差额×两个时钟。约10.7个独立区块，HAC5仅诊断；两档费用及近期视图相依。DSR／PBO为N/A：适当的完整历史候选分布与真实选择实验不足，不能据保留赢家补造分布。',
        '',f"实际执行计数：{counts['counts']['economic_comparisons']}项成本后差额，{counts['counts']['financial_accounts']}个独立账户开始，其中32个原始政策／基准视图、{counts['risk_probe_accounts']}个风险求根账户；十四个固定政策、零次拟合、零个paper候选。累计已知试验下界{result['n_trials']}，包含信号库祖先登记，另有未能完整重建的旧选择暴露。十四项政策已覆盖信息、价格、流动性、错误行业及两个传递时限；追加阈值、名单规模或种子会改变本轮问题，因此不为20至50变体参考数补格。弱结果只关闭此构造，不能否定整个信息扩散领域。",
        '',f"失败和成本：{len(costs['failed_preparation_logs'])}次准备失败已保留原日志与资源记录，涉及时间索引单位、排他证据写入和空身份集合处理；另有一次未完成的逐行绑定因性能中断。资金求解的固定报价属性改为任务内缓存，原始函数仍对实际成交收费；费用分项及64次二分结果逐位一致检查通过。{len(costs['failed_accounts'])}个失败／中断账户开始均保留。原Worker于2026-11-03 06:14 UTC因提供方额度终止，原driver的interrupted_or_failed状态与原会话保留；其后确认模型和数值进程均退出，未完成探测只以quota-repair1新ID恢复，原有99个完成账户的文件未改写。原数值进程的终止信号、完整资源和Worker用量缺收据，不能补作零。原driver已观测token下界为{original['efficiency']['tokens']['observed_total_tokens']:,}，已记录活动时间{original['elapsed_seconds']:.2f}秒；同一review会话按字段最大值去重。恢复执行资源另计，恢复和接收token尚未结算，实际提供方美元未知。此前失败支出及旧Modal估计仍沿前轮账，不移作重构成本。",
        '', '完整证据：[引擎Results及成本补记](evidence/results-complete.json)、[账户指标](evidence/primary-summary.json)、[二十项差额及联合区间](evidence/contrasts.json)、[八项风险匹配](evidence/matching-summary.json)、[输入](evidence/inputs.json)、[试验账](evidence/trials.snapshot.jsonl)、[实际资源和未知成本](evidence/cost-reconciliation.json)。paper、生产、控制和订单权限未改变。']
    lines+=['','八项同波动匹配的完整数值如下；最近250日仍沿用对应完整资金路径。','',
        '| 对照／周期／成本 | 缩放臂及比例 | 目标年化波动 | 全窗净增量美元 | 最近250日净增量 | 波动差 |',
        '|---|---|---:|---:|---:|---:|']
    for m in matches:
        cells=(f"{m['increment_usd']:,.2f} | {m['trailing250_increment_usd']:,.2f} | {m['vol_gap']:.3g}" if m['matched'] else '未匹配 | 未匹配 | N/A')
        scale=f"{m['scale']:.10f}" if m['matched'] else '无根'
        lines.append(f"| {m['model']}−{m['control']}／{m['cost_multiplier']}x | {m['scaled_arm']} × {scale} | {m['target_volatility']:.4%} | {cells} |")
    (OUT.parent/'report.zh.md').write_text('\n'.join(lines)+'\n')
    measured_adv=[x['max_ADV_fraction'] for x in table if x['arm'] in STOCKS and
                  isinstance(x['max_ADV_fraction'],(int,float)) and math.isfinite(x['max_ADV_fraction'])]
    max_adv=max(measured_adv) if measured_adv else None
    capacity=(f'Largest observed stock order/decision ADV {max_adv:.8%}' if max_adv is not None else
              'Stock order/decision ADV unknown')
    forensic={'strategy_name':BASE.name,'research_object':'conditional component, no deployable StrategySpec',
        'lookahead_check':'warning','future_leak_check':'warning','overfit_risk':'high',
        'multiple_testing_count':result['n_trials'],'pbo_proxy':None,'dsr_proxy':None,'pbo':None,'dsr':None,
        'statistical_methods':{'paired':'63-session circular block maxT,1999 draws,ten contrasts/cost,common indices',
            'risk_matching':'eight scale-down funded cash-mixture matches,predeclared support segments',
            'DSR_PBO':'N/A; incomplete appropriate historical candidate distribution and no selection experiment'},
        'sample_data_caveats':result['limitations'],'trade_count':sum(x['orders_executed'] for x in table),
        'trading_days':674,'capacity_assessment':capacity+'; SPY ADV absent from native stock attributes, ETF capacity unknown; opening-auction capacity/physical execution not certified',
        'short_sample':False,'conclusion':'warning','notes':'Event close/entry clocks and accounting checked. Current SIC and inherited retrospective native hygiene prevent strict PIT certification; accepted scope permits conditional diagnostic only.',
        'evidence':result['source_artifacts']+[rel(OUT.parent/'report.zh.md')]}
    folder=ROOT/'reports/harness/forensics';folder.mkdir(parents=True,exist_ok=True)
    (folder/f'{BASE.name}-backtest-forensics.json').write_text(json.dumps(forensic,ensure_ascii=False,indent=2)+'\n')
    (folder/f'{BASE.name}-backtest-forensics.md').write_text('条件组件回测取证结论为warning。财报反应严格晚于SEC接受时刻，下一开盘成交；当前行业版本、条件身份链接及原生回溯清洗仍不能证明历史PIT。每日现金、费用及实际成交归因已核对。完整解释和数值见[经济报告]('+str(OUT.parent/'report.zh.md')+')；DSR／PBO保持N/A，累计登记为已知下界。\n')
    # Append operational evidence without replacing the immutable engine summary.
    result['source_artifacts'] += [rel(OUT/'cost-reconciliation.json'),rel(OUT/'funding-probe-repair-reconciliation.json'),
        rel(OUT/'input-binding-interruption-close.json'),rel(OUT/'quota-recovery-start.json'),
        rel(OUT/'quota-recovery-complete.json'),rel(OUT/'affected-scientific-audit.json'),
        rel(OUT/'concentration.csv'),rel(OUT.parent/'funding-probe-checks.log'),rel(OUT.parent/'report.zh.md')]
    result['costs'] += ' Original Worker ended at provider usage limit; original driver interrupted_or_failed and its incomplete usage/resource evidence are preserved. Provider dollars and missing original Worker/recovery/Lead usage remain unknown; failed and interrupted attempts retained in cost-reconciliation.json.'
    final=Results.model_validate(result)
    (OUT/'results-complete.json').write_text(final.model_dump_json(indent=2)+'\n')
    (OUT.parent/'results.json').write_text(final.model_dump_json(indent=2)+'\n')
    (BASE/'results.json').write_text(final.model_dump_json(indent=2)+'\n')
    print(json.dumps({'report':rel(OUT.parent/'report.zh.md'),'recommendation':decision,'counts':counts['counts']},ensure_ascii=False))

if __name__=='__main__':main()
