"""Validate the independent calculations and publish one owner-readable artifact."""
from __future__ import annotations

import csv
import json
import sys
from collections import Counter,defaultdict
from datetime import UTC,date,datetime,time
from decimal import Decimal as D
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from open_composer.lab.ledger import TrialLedger
from open_composer.market_sessions import NEW_YORK,us_equity_session_dates

OUT=ROOT/'reports/owner/paper-recovery-20261103'
NAMES={
 'S1':'行业轮动','S2':'成长轮动','S3':'杠杆轮动','C2':'月末效应',
 'BASE':'基础选股','H5':'五日选股','LSTM':'跨资产模型',
 'BASE_STATE_BUDGET':'按市场状态调仓的选股','MULTI_EQUAL':'六策略等权组合','MULTI_HIERARCHICAL':'六策略分层组合',
 'Retired top50':'已停的高收益股票组合',
}


def money(x):return 'N/A'if x is None else f'{float(x):+,.2f}'
def amount(x):return 'N/A'if x is None else f'{float(x):,.2f}'
def pct(x):return 'N/A'if x is None else f'{float(x):+.2f}%'


def main():
    actual=json.loads((OUT/'actual.json').read_text());etf=json.loads((OUT/'replay_etf.json').read_text());six=json.loads((OUT/'replay_six.json').read_text())
    summaries={s['id']:s for s in actual['summaries']};histories={h['id']:h for h in actual['histories']};accounts={a['account']:a for a in actual['accounts']}
    etfs=[s for s in actual['summaries']if s['id'].startswith('legacy/us_etf')]
    sixs=[summaries['six/'+p]for p in ['BASE','H5','LSTM','BASE_STATE_BUDGET','MULTI_EQUAL','MULTI_HIERARCHICAL']]
    etf_profit=sum(D(s['profit_before_unattributed_costs_usd'])for s in etfs)
    etf_capital=sum(D(s['baseline_nav_usd'])for s in etfs)
    six_profit=sum(D(s['profit_before_unattributed_costs_usd'])for s in sixs)
    etf_fees=-D(accounts['legacy']['posted_nontrade_usd']['FEE']);six_fees=-D(accounts['six']['posted_nontrade_usd']['FEE'])
    etf_net=etf_profit-etf_fees;six_net=six_profit-six_fees
    assert etf_profit==D('-2751.21') and six_profit==D('-1831.50')
    assert not any(x['quantity_mismatch']or x['unknown_FILL_count']for x in actual['reconciliation'].values())
    assert abs(D(accounts['legacy']['profit_from_baseline_usd'])-(etf_net+D(accounts['legacy']['posted_nontrade_usd']['DIV'])))<D('.001')
    assert abs(D(accounts['six']['profit_from_baseline_usd'])-six_net)<D('.001')
    assert summaries['six/BASE']['baseline_nav_usd']=='20000'
    assert all(s['latest_valid_day']=='2026-11-02' and not s['missing_valuation_days']for s in etfs+sixs)
    assert six['new_fit_count']==0 and etf['new_fit_count']==0
    # Dated operational coverage is distinct from a no-fill day.
    sessions=[str(d)for d in us_equity_session_dates(date(2026,10,1),date(2026,11,2))]
    attempts=defaultdict(list)
    for s in etfs:
        name=s['id'].split('/')[-1]
        for p in (ROOT/'reports/paper/rehearsal').glob(name+'-2026-*.json'):
            d=json.loads(p.read_text());ds=d.get('session')
            if ds in sessions:attempts[s['id'],ds].append({'path':str(p.relative_to(ROOT)),'status':d.get('status'),'generated_at':d.get('generated_at'),'counts':d.get('counts')})
    runtime_events=defaultdict(Counter)
    for line in (OUT/'evidence/runtime-state.events.jsonl').open():
        d=json.loads(line)
        if not d.get('at')or not d.get('policy'):continue
        dt=datetime.fromisoformat(d['at'].replace('Z','+00:00')).astimezone(NEW_YORK)
        ds=str(dt.date())
        if ds in sessions and time(9,40)<=dt.time()<time(15,30):runtime_events[d['policy'],ds][d['type']]+=1
    saved_targets={(t['policy'],t['application_day']):t for t in six['targets']if not t['historical_only']}
    calendar=[]
    for s in etfs+sixs:
        identity=s['id'];h=histories[identity]
        for ds in sessions:
            fills=[x for x in h['executions']if x['session']==ds]
            p=next((p for p in h['points']if p['day']==ds),None)
            target=saved_targets.get((s['label'],ds))if identity.startswith('six/')else None
            ev=runtime_events.get((s['label'],ds),{})
            calendar.append({'strategy':NAMES[s['label']],'internal_id':identity,'day':ds,'paper_FILL_count':len(fills),'paper_close_nav_usd':p.get('nav_before_unverified_items_usd')if p else None,'scheduled_cycle_records':len(attempts[identity,ds]),'saved_dated_target':bool(target),'target_action':target.get('action')if target else None,'saved_target_is_empty':target.get('symbols')==[]if target else None,'regular_window_blocked_events':ev.get('policy_blocked',0),'regular_window_intents':ev.get('signal_and_order_intent',0),'state':'未有本策略成交'if ds<s['first_FILL_day']else'持仓与成交可核算','evidence':target.get('source')if target else ';'.join(x['path']for x in attempts[identity,ds])})
    for alias in ['quant1','quant2']:
        acts_path=OUT/'evidence'/alias/'activities-all.json';acts=json.loads(acts_path.read_text())if acts_path.exists()else[]
        for ds in sessions:
            fills=[x for x in acts if x.get('activity_type')=='FILL'and x.get('transaction_time','')[:10]==ds]
            p=ROOT/f'reports/paper/book/{alias}/daily/{ds}.json'
            calendar.append({'strategy':'股票多空账户'if alias=='quant1'else'旧SPY增强账户','internal_id':alias,'day':ds,'paper_FILL_count':len(fills)if alias=='quant1'else None,'canonical_daily_ledger':p.exists(),'state':'券商全成交已取回'if alias=='quant1'else'凭据返回401；无法确认近期状态'})
    fields=sorted({k for r in calendar for k in r})
    with (OUT/'calendar.csv').open('w')as f:
        w=csv.DictWriter(f,fields);w.writeheader();w.writerows(calendar)
    with (OUT/'account_daily.csv').open('w')as f:
        fields=['account','day','equity_usd','at','kind','missing']
        w=csv.DictWriter(f,fields);w.writeheader()
        for alias,account in accounts.items():
            for point in account['observations']:
                if alias!='legacy' and point['day']<'2026-10-01':continue
                w.writerow({'account':alias,**{k:point.get(k)for k in fields if k!='account'}})
    coverage=[]
    for s in etfs+sixs:
        identity=s['id'];policy=s['label']
        coverage.append({'id':identity,'name_zh':NAMES[policy],'first_FILL_day':s['first_FILL_day'],'last_FILL_day':s['last_FILL_day'],'first_valid_close':min(p['day']for p in histories[identity]['points']if p.get('nav_before_unverified_items_usd')is not None),'last_valid_close':s['latest_valid_day'],'window_valued_sessions':s['covered_valuation_sessions'],'cycle_days':sorted(ds for ds in sessions if attempts[identity,ds]),'missing_cycle_days':[ds for ds in sessions if not attempts[identity,ds]]if identity.startswith('legacy/')else None,'saved_dated_target_days':[ds for ds in sessions if (policy,ds)in saved_targets]if identity.startswith('six/')else None,'daily_FILL_days':s['window_FILL_days']})
    retired=[
      {'name_zh':'已停的高收益股票组合','id':'us_recent_high_return_top50','last_trade':'2026-09-23','status':'当日全部平仓，之后没有新增持仓；本期仅收到旧持仓分红2.31美元。','window_trading_pnl_usd':0,'window_dividend_usd':2.31,'return_pct':None},
      {'name_zh':'旧TQQQ路由模拟盘','id':'nasdaq_tqqq_fixed_etf_router_daily_iter11_exposure_search_paper_auto_candidate','last_snapshot':'2026-09-08','status':'旧账户已重置；重置前快照含TQQQ10235股，不能与新账户拼接。','window_pnl_usd':None},
      {'name_zh':'旧SPY增强账户','id':'quant2','last_daily_ledger':'2026-10-06','status':'保存记录为观察，未找到实成交；当前GET返回401，近期收益N/A。','window_pnl_usd':None},
      {'name_zh':'QQQ日内噪声带','id':'noiseband_qqq_obs','status':'有配置和锁文件，没有成交/每日结果记录；不计入已运行模拟盘。','window_pnl_usd':None},
      {'name_zh':'模型排名股票组合','id':'us_model_ranking_portfolio_top50','status':'最近保存观察2026-09-22，明确不下单。','window_pnl_usd':None},
      {'name_zh':'内部人买入股票组合','id':'us_insider_buy_broad_monthly','status':'2026-09-18记录明确为未授权计划演练，未下单。','window_pnl_usd':None},
      {'name_zh':'六个旧动量虚拟组合','id':'virtual_momentum_portfolio R0 R1 R2 R3 M1 M2','status':'最后记录2026-07-13，行情截至05-29，计算交易日为0；不视为十月运行。','window_pnl_usd':None},
    ]
    stock=accounts['quant1'];stock_observed=D(stock['current_broker_observed_equity_usd'])-D(1000000)
    merger_path=OUT/'quant1-merger-reconciliation.json'
    merger=json.loads(merger_path.read_text()) if merger_path.exists() else None
    if merger:
        assert D(merger['broker_latest_observed_equity_usd_unchanged']) == D(stock['current_broker_observed_equity_usd'])
        assert merger['positions_match_broker'] and merger['cash_match_broker']
    row_actual=[]
    for s in etfs+sixs:
        row_actual.append({**s,'name_zh':NAMES[s['label']],'broker_net_pnl_usd':None,'net_missing_reason':'已核所有成交，但账户实际费用没有逐策略明细；账户组总净损益可准确核算。'})
    performance={'as_of_utc':actual['generated_at'],'window':actual['window'],'expected_market_date':'2026-11-02','trading_sessions':23,'actual_strategies':row_actual,'actual_groups':{'four_etf':{'baseline_usd':str(etf_capital),'trading_pnl_usd':str(etf_profit),'posted_fee_usd':str(etf_fees),'net_after_posted_fees_usd':str(etf_net),'return_on_baseline_pct':str(etf_net/etf_capital*100)},'six_policies':{'assigned_usd':'120000','trading_pnl_usd':str(six_profit),'posted_fee_usd':str(six_fees),'net_after_posted_fees_usd':str(six_net),'return_on_assigned_pct':str(six_net/D(120000)*100)}},'broker_accounts':actual['accounts'],'quant1_latest_observation_profit_usd':str(stock_observed),'quant1_official_nov02_close_available':False,'coverage':coverage,'historical_and_observation_inventory':retired,'replay_etf':etf['results'],'replay_six':six['results'],'reconciliation':actual['reconciliation'],'known_limits':{'quant1_missing_same_day_raw_closes':stock['raw_close_coverage_missing'],'nov02_missing_BASE_dependent_replay':['BASE','BASE_STATE_BUDGET','MULTI_EQUAL','MULTI_HIERARCHICAL'],'per_sleeve_actual_fee_allocation':False,'paper_values_exclude_unposted_receivables':True,'new_fit_count':0,'parameter_search_count':0,'broker_write_count':0},'evidence':['actual.json','actual_daily.csv','calendar.csv','replay_etf.json','replay_etf_daily.csv','replay_six.json','replay_six_daily.csv','replay_six_orders.csv','lstm-frozen-series.json','evidence/']}
    if merger:
        performance['quant1_merger_receivable_estimate']=merger
        performance['evidence'].append('quant1-merger-reconciliation.json')
    (OUT/'performance.json').write_text(json.dumps(performance,ensure_ascii=False,indent=2)+'\n')
    lines=['# 10月以来模拟盘实际表现与独立补算','',f'统计区间：2026-10-01—2026-11-02，共23个美股交易日。取证时间：{actual["generated_at"]}。金额均为美元。','',
      '## 一、结论','',
      f'- 四个 ETF 合计亏 **{amount(-etf_net)}美元，-{float(-etf_net/etf_capital*100):.2f}%**，已扣截至取证时入账的{amount(etf_fees)}美元费用。主要亏损来自成长、杠杆轮动，月末效应赚钱。',
      f'- 六组新模拟盘合计投入12万美元，亏 **{amount(-six_net)}美元，-{float(-six_net/D(120000)*100):.2f}%**，已扣已入账费用{amount(six_fees)}美元。跨资产模型接近持平，其余五组均亏。它们在10月20—21日才开始成交，没有虚构10月1日以来的前向业绩。',
      f'- 股票多空账户最新券商观测比最初100万美元高 **{amount(stock_observed)}美元，+{float(stock_observed/D(1000000)*100):.2f}%**。最后正式日账是10月16日，之后持仓仍涨跌；11月2日有5只股票缺少当天收盘价，所以这笔金额是券商最新观测值，正式当日收盘净收益仍为N/A。',
      '- 可恢复原信号的连续补算已完成。补上执行缺口并不会普遍改善收益：按市场状态降低持仓的选股结果改善，基础选股和两组组合反而亏得更多。11月基础选股模型缺失，相关四组11月2日的完整策略补算仍为N/A。',
      '', '## 二、模拟盘和实盘','',
      '前三个 ETF 从9月30日收盘资金起算；月末效应从10月1日投入15,000美元起算。六组新模拟盘各按实际分配的20,000美元计算；基础选股最初分配10,000美元，10月20日在首次成交前又分配10,000美元，这笔钱没有算成盈利。表内“成交盈亏”使用本策略实际买卖价与11月2日收盘价，含闲置现金，尚未分摊同账户统一扣取的费用。','',
      '| 策略 | 本期起始资金 | 11月2日收盘资金 | 成交盈亏 | 收益率 | 区间最大回撤 |',
      '| --- | ---: | ---: | ---: | ---: | ---: |']
    for s in etfs+sixs:
        lines.append(f'| {NAMES[s["label"]]} | {amount(s["baseline_nav_usd"])} | {amount(s["latest_nav_usd"])} | {money(s["profit_before_unattributed_costs_usd"])} | {pct(s["return_pct"])} | {pct(s["max_drawdown_pct"])} |')
    lines += ['',
      f'四 ETF 的成交盈亏合计{money(etf_profit)}，扣费用后{money(etf_net)}；旧股票组合另收到分红+2.31，因此共享账户从106,067.78变为103,318.64，净变化-2,749.14。六组新模拟盘成交盈亏合计{money(six_profit)}，扣费用后{money(six_net)}；加上88万美元未分配现金，收盘重估账户为998,167.48。两个账户所有持仓数量均与券商一致，没有未归属成交。',
      '', '这些收盘资金由实际持仓加当天原始收盘价重估。券商在取证时的盘后报价余额分别为103,311.82和997,911.59，不能用盘后报价差额替代同日收盘收益。实际成交价格已经包含买卖价差，本报告没有再对真实模拟盘扣一次假设滑点。11月2日应得但尚未入账的分红未塞入这张实际现金结果；后续补记费用也需按实际到账追加。',
      '',
      '| 股票多空账户 | 资金/变化 | 解释 |',
      '| --- | ---: | --- |',
      '| 10月1日实际初始入金 | 1,000,000.00 | 原始入金，不是盈利 |',
      '| 10月30日券商日终历史净值 | 1,016,381.54 | 最后完整的券商日终记录 |',
      f'| 取证时券商余额 | {amount(stock["current_broker_observed_equity_usd"])} | 包含11月2日之后收到的最新报价，也含5只没有当天收盘价的持仓 |',
      f'| 相对初始资金的观测变化 | {money(stock_observed)} / {pct(stock_observed/D(1000000)*100)} | 已含券商记账费用11.90、分红277.35及并购现金1,455.00；没有额外入金 |',
      '| 截至10月30日日终历史最大回撤 | -0.82% | 11月2日正式收盘回撤仍缺完整价格 |',
      *([f'| 含未入账并购对价的11月2日参考估值 | 约{float(merger["estimated_economic_equity_usd"]):,.0f} / {pct(merger["estimated_return_pct"])} | 按实际100万美元本金；零股现金为估计，不是券商已入账日终 |'] if merger else []),
      '',
      *(['五只缺价股票已因并购停止交易：[CBZ][cbz-merger]、[LXP][lxp-merger]、[RAMP][ramp-merger]分别每股换55、61.20、38.50美元；[WEAV][weav-merger]每股换7.40美元；[KVUE][kvue-merger]每股换3.50美元及0.14625股KMB。原始成交与非交易活动重建的现金和全部1,503只持仓均与券商一致，这五项尚未在保存账中完成换股或入账。参考估值先去掉旧股票标值，再计并购应收，约盈利17,156美元（+1.72%），没有双计。零股条款指定Bloomberg五日VWAP，本次只用已保存SIP数据作代理估计，最终以实际到账为准。其他未入账分红继续按原报告处理，不额外加入。'] if merger else []),
      '', '账户10月5—6日只有两笔小额验证成交；正式股票多空策略从10月7日成交。以10月6日券商余额1,000,004.45为基准，最新观测变化为+16,234.94美元、+1.62%。10月19日至11月2日共11个交易日没有新成交，不能称为11天策略正常更新。当前没有实盘结果或实盘订单。',
      '', '运行日历：有保存信号或没有成交，都不能单独证明当天执行正常。逐日记录另附，下面只列会影响结论的覆盖差异。','',
      '| 策略 | 最早实际成交 | 最后实际成交 | 可核算收盘日数 | 运行覆盖与关键缺口 |',
      '| --- | --- | --- | ---: | --- |']
    for s in etfs+sixs:
        if s in etfs:
            note='22/23个执行日有计划/尝试记录，缺10月22日；11月2日确有成交'
        elif s['label']=='H5':note='10月26日产生空仓信号，27日才实际清仓；之后空仓有原信号支持'
        elif s['label']=='LSTM':note='10月26日缺完整发布；29日、11月2日有新权重但没有新成交，需结合挂单与整股差额判断'
        else:note='10月26日发布中断；11月2日缺11月基础选股模型，本期持仓仍可估值'
        lines.append(f'| {NAMES[s["label"]]} | {s["first_FILL_day"]} | {s["last_FILL_day"]} | {s["covered_valuation_sessions"]} | {note} |')
    lines += ['', '新模拟盘可复核的收盘持仓估值从10月20日的动态预算选股开始，其余五组从10月21日开始；全部最后可复核持仓估值为11月2日。股票多空只有6份正式日账，最新10月16日；旧SPY增强账户只保存至10月6日，当前读取返回401。',
      '', '## 三、研究：独立补算','',
      '四个 ETF 用原先的选股、调仓、降仓和退出规则连续计算，起始资金与实际表一致。采用原研究的“隔夜涨跌加当日涨跌”计法，主结果每买或卖1万美元估计花10美元，压力情形为20美元；费用已经从下表结果扣除。这是原规则的日线参考，不保证真实券商会按同样价格、整股数量成交。补算计入相应经济持有收益，实账尚未计入未到账分红；两者差额还包括成交时点、整股、费用假设和分红入账时点，不能全归为停跑或成交好坏。','',
      '| 策略 | 实际同期成交盈亏 / 收益率 | 连续补算净盈亏 / 收益率 | 压力费用下净盈亏 / 收益率 | 主要解释 |',
      '| --- | ---: | ---: | ---: | --- |']
    reasons={'S1':'实际约少47美元；差额未作单项归因','S2':'实际与补算只差约5美元','S3':'主要是市场持仓亏损；其原定回撤退出线为25%','C2':'实际约多55美元；差额未作单项归因'}
    for p in ['S1','S2','S3','C2']:
        a=next(x for x in etf['results']if x['strategy']==p and x['cost_bps']==10)
        b=next(x for x in etf['results']if x['strategy']==p and x['cost_bps']==20)
        s=summaries['legacy/'+a['name']]
        lines.append(f'| {NAMES[p]} | {money(s["profit_before_unattributed_costs_usd"])} / {pct(s["return_pct"])} | {money(a["net_profit_usd"])} / {pct(a["return_pct"])} | {money(b["net_profit_usd"])} / {pct(b["return_pct"])} | {reasons[p]} |')
    lines += ['', '六组新模拟盘从10月21日真实收盘持仓和现金出发，计算10月22日之后的连续执行。沿用已保存信号、原整股计算和下一交易日结算现金规则；缺失的10月26日跨资产权重由原封存模型补算，未重新训练，并逐日核对已有预测，最后一日权重完全一致。假设每天需要交易时都可在开盘完成，扣每边10或20美元/万美元。实际系统从纽约时间09:40后提交限价单，缺少停跑日期当时完整报价、逐分钟成交及盘中保护路径，因此下表是日线参考，精确模拟盘成交复现仍为N/A。','',
      '| 策略 | 补算区间 | 同期实际成交盈亏 / 收益率 | 日线参考净盈亏 / 收益率 | 压力费用下净盈亏 / 收益率 |',
      '| --- | --- | ---: | ---: | ---: |']
    for p in ['BASE','H5','LSTM','BASE_STATE_BUDGET','MULTI_EQUAL','MULTI_HIERARCHICAL']:
        a=next(x for x in six['results']if x['policy']==p and x['cost_bps']==10)
        b=next(x for x in six['results']if x['policy']==p and x['cost_bps']==20)
        lines.append(f'| {NAMES[p]} | 10月22日—{a["end"][5:].replace("-","月")}日 | {money(a["actual_matched_interval_trading_profit_usd"])} / {pct(a["actual_matched_interval_return_pct"])} | {money(a["net_profit_usd"])} / {pct(a["return_pct"])} | {money(b["net_profit_usd"])} / {pct(b["return_pct"])} |')
    lines += ['', '补算显示，动态预算选股若及时减仓，参考亏损比真实同期少约299美元；基础选股若把目标仓位补齐，参考亏损反而多约947美元，两组合计同样更差。执行中断与模型收益必须分别判断，不能把少成交带来的低仓位当成模型能力。五日选股的有效空仓延续至11月2日；11月基础选股模型没有按原截止时间形成，基础选股、动态预算和两组组合的11月2日补算保留N/A。股票多空缺少停跑期间完整、当时可得的因子、风险和组合目标，无法可信续跑原策略；仅把旧持仓往后估值不等于续跑。',
      '', '价格复权也已单独处理：11月2日短债与长债分红会改写更早的复权价格。ETF补算保留88份当日原始目标，只对缺记录的10月22日用原公式复原；成长轮动最初两天与后来复算有约0.01个百分点的权重差异，已用当日原记录校正。分红后的新价格版本只用于计量发生的持有收益，没有拿它重新决定以前的持仓。',
      '', '## 四、机主问题的答复与历史策略盘点','',
      '已完成所有能与券商成交归属对应的策略核算，并保留以下历史或仅观察项目，避免把它们漏掉或当成仍在运行。','',
      '| 项目 | 真实状态 | 本期收益处理 |',
      '| --- | --- | --- |',
      '| 已停的高收益股票组合 | 9月23日全部平仓；10月无新增成交 | 交易盈亏0；收到旧持仓分红+2.31；独立资本收益率N/A |',
      '| 旧TQQQ路由模拟盘 | 旧账户9月8日重置前已存档，之后属于另一账户 | 10月表现N/A，不与新账户拼接 |',
      '| 旧SPY增强账户 | 最后观察10月6日；当前凭据返回401 | 当前收益N/A，不能认定仍为空仓或收益为零 |',
      '| QQQ日内噪声带 | 有配置与锁文件，没有保存成交或每日结果 | 未证实进入实际模拟盘，收益N/A |',
      '| 模型排名股票组合 | 9月22日观察明确不下单 | 观察结果不计为模拟盘收益 |',
      '| 内部人买入股票组合 | 9月18日记录明确为未授权的计划演练 | 未进入实际模拟盘，收益N/A |',
      '| 六个旧动量虚拟组合 | 最后7月13日记录仍缺新行情，计算交易日数为0 | 没有可用10月业绩，收益N/A |',
      '', '下一步应先恢复有当日有效信号的策略并核实实际成交；对缺11月模型的四组保留阻断。用恢复后的真实每日记录继续比较，不能靠回填模拟成交消除停跑历史。此报告没有修改生产账本、调度、授权或发送任何订单。',
      '', '## 五、机主待决策事项','', '本专项核算没有新增机主决策。旧SPY增强账户现有凭据失效，报告已保留N/A；是否恢复该旧账户沿用主任务已有安排。',
      '', '## 附：证据、复算与限制','',
      '- 统一数据：[performance.json](performance.json)；逐策略收盘重估：[actual_daily.csv](actual_daily.csv)；账户日终历史与收盘重估：[account_daily.csv](account_daily.csv)；逐策略逐交易日日历：[calendar.csv](calendar.csv)。',
      '- 实际成交归属、每笔成交和持仓：[actual.json](actual.json)。4 ETF 与六策略的持仓差异均为空，未归属成交数均为0。',
      '- 原始券商只读回执：evidence/legacy、evidence/six、evidence/quant1；旧账户读取失败回执：evidence/quant2。保存的请求方法全部为GET，未保存凭据。',
      '- 原始行情：evidence/market/raw-*.json；已截取的六策略状态：evidence/runtime-state.json 与 evidence/runtime-state.events.jsonl。',
      '- ETF补算：[replay_etf.json](replay_etf.json)、[replay_etf_daily.csv](replay_etf_daily.csv)；六策略补算：[replay_six.json](replay_six.json)、[replay_six_daily.csv](replay_six_daily.csv)、[模拟订单](replay_six_orders.csv)。',
      '- 原模型历史推理：[lstm-frozen-series.json](lstm-frozen-series.json)。2次原模型推理、0次训练；原分数前缀误差2.38e-7和0，最后权重误差0。',
      '- 原规则：strategy_specs/drafts/us_etf_{sector_rotation_252_top2_weekly,growth_rotation_blend_top2_monthly,levered_rotation_63_top2_monthly,eom_sector_blend_monthly}.yaml；借用open_composer/lab/accounting.py、metrics.py及冻结CashState/target_quantities。',
      '- 原信号：reports/paper/diagnostics/dated-target-refresh/{日期}/targets、predecessor-targets；10月21—22日信号备份在reports/paper/diagnostics/resume-20261022/target-refresh/；每个输入的实际路径、字节数和摘要在计算JSON中。',
      '- 11月模型缺口：reports/paper/diagnostics/dated-target-refresh/2026-11-02/policy-dependencies.json；当时没有形成有效11月BASE模型。本次获批改期的模型不能回填成11月2日已经运行；当前恢复进展见[恢复报告](recovery.zh.md)。',
      '- quant1正式日账与计划：reports/paper/book/quant1/{daily,orders,plans,account-valuations}；11月2日缺原始收盘价的5只持仓：CBZ、KVUE、LXP、RAMP、WEAV。它们的取证时券商标值合计3,941.47美元，未用旧价格冒充11月2日收盘价。',
      *(['- 并购停止交易原因、现金与持仓独立重建及参考估值：[quant1-merger-reconciliation.json](quant1-merger-reconciliation.json)。[零股现金条款](https://www.sec.gov/Archives/edgar/data/55785/000114036125045609/ny20059815x4_424b3.htm)指定的Bloomberg VWAP未取回，SIP代理没有冒充正式兑付金额。'] if merger else []),
      '- 旧策略证据：reports/paper/rehearsal/us_recent_high_return_top50-authorization-revoked-20260923T140735Z.json；reports/paper/pre-reset-2026-09-08/；reports/paper/intraday/runner/quant2/；reports/paper/virtual_momentum_portfolio/latest-cycle.json。旧路由其余计划仅见reports/paper/plans/，没有本期可归属成交。',
      '- 内部标识对应：BASE=基础选股；H5=五日选股；LSTM=跨资产模型；BASE_STATE_BUDGET=按市场状态调仓的选股；MULTI_EQUAL=六策略等权组合；MULTI_HIERARCHICAL=六策略分层组合；quant1=股票多空账户；quant2=旧SPY增强账户。',
      '- 真实成交盈亏未按假设费用二次扣减；共享费用只在组总数扣一次。单策略已扣实际费用的精确净收益为N/A，不能擅自按资金比例分摊。补算费用为模型假设，已计入其净结果。',
      '- ETF采用原研究的线性收益分段记法；六策略采用原整股、资金约束、结算及分红应收规则，开盘价完整成交只是假设，不能视为错失了可保证赚到的钱。未估算新参数，也未把补算成交写回实际账。',
      '', '复算顺序：先取证，再核算实际账，再作两种补算，最后生成本报告。所有脚本均在research/paper_recovery_20261103，使用scripts/run_capped.sh顺序运行。原始证据已保存，重算实际账和补算不需要再次访问券商。',
      '', '```bash',
      'scripts/run_capped.sh --mem 450M -- .venv/bin/python research/paper_recovery_20261103/build_actual.py',
      'scripts/run_capped.sh --mem 650M -- .venv/bin/python research/paper_recovery_20261103/replay_etf.py',
      'scripts/run_capped.sh --mem 900M -- env OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 /usr/bin/python3.12 research/paper_recovery_20261103/infer_lstm_series.py',
      'scripts/run_capped.sh --mem 650M -- .venv/bin/python research/paper_recovery_20261103/replay_six.py',
      '.venv/bin/python research/paper_recovery_20261103/reconcile_quant1_mergers.py',
      'scripts/run_capped.sh --mem 450M -- .venv/bin/python research/paper_recovery_20261103/finalize.py',
      '.venv/bin/python scripts/owner_report.py lint reports/owner/paper-recovery-20261103/performance.zh.md',
      '```','']
    if merger:
        lines += [f'[{row["symbol"].lower()}-merger]: {row["source_url"]}' for row in merger['pending_mergers']]
        lines.append('')
    (OUT/'performance.zh.md').write_text('\n'.join(lines))
    ledger=TrialLedger(OUT/'trial-ledger.jsonl')
    if not ledger.events():
        for identity,evidence in [('actual','actual.json'),('fixed-etf-replay','replay_etf.json'),('fixed-six-replay','replay_six.json')]:
            ledger.start(identity,batch='paper-recovery-20261103',candidate=identity,parameters={'search':False},counts_as_trial=False,note='Fixed existing-rule reconstruction, no selection or new research trial.')
            ledger.finish(identity,status='complete',evidence=[str(OUT/evidence)])
    validation={'unknown_FILLs':0,'position_quantity_mismatches':0,'legacy_account_profit_residual_usd':'0','six_account_profit_residual_usd':'0','BASE_pre_first_trade_capital':'20000','new_fits':0,'new_parameter_trials':ledger.n_trials,'broker_writes':0,'evaluated_strategies':10,'unavailable_nov02_full_strategy_replays':4,'quant1_missing_nov02_raw_marks':5}
    (OUT/'validation.json').write_text(json.dumps(validation,indent=2)+'\n')
    print(json.dumps({'artifact':str(OUT/'performance.zh.md'),'four_etf_net':str(etf_net),'six_net':str(six_net),'validation':validation},ensure_ascii=False,indent=2))


if __name__=='__main__':main()
