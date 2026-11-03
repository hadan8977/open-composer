"""Read saved orders to audit cash and physical-unit identities; no signal/account replay."""
from pathlib import Path
from datetime import datetime,UTC
import sys,json,math,re
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT))
from engine import BASE,OUT,CAP,START,END,ARMS,STOCKS,rel,read,save
from open_composer.research.equity_book.costfn import make_cost_fn
from open_composer.research.equity_book.costs import half_spread_bp
from open_composer.research.equity_book.panel import HEDGE_ETFS
from open_composer.research.agent_workflow import Results,validate_results
from open_composer.lab.ledger import TrialLedger

def audit():
 c=pd.read_parquet(OUT/'close-with-spy.parquet').loc['2024-01-05':END];o=pd.read_parquet(OUT/'open-with-spy.parquet').reindex_like(c)
 dates=c.index;cols=c.columns;ca=c.to_numpy();oa=o.to_numpy();priced=np.isfinite(ca)&(ca>0)
 lastpos=np.where(priced.any(axis=0),len(dates)-1-np.argmax(priced[::-1],axis=0),-1)
 delist=np.where((lastpos>=0)&(lastpos<len(dates)-1),lastpos+1,-1)
 rows=[];primary={}
 for mult in [1,2]:
  for arm in ARMS:
   p=list((OUT/'accounts').glob(f'{arm}-c{mult}-s0x1_0000000000000p0*'))
   if arm=='SPY':p=[x for x in p if x.name.endswith('prices-r1')]
   p=[x for x in p if (x/'complete.json').exists()]
   assert len(p)==1,(arm,mult,p)
   primary[rel(p[0])]=(arm,mult)
 raw=make_cost_fn('open')
 for folder in sorted((OUT/'accounts').iterdir()):
  if not (folder/'complete.json').exists():continue
  receipt=folder/'read-only-audit.json'
  if receipt.exists():
   rows.append(read(receipt));continue
  native=read(folder/'native.json')
  if native['info']['unknown_symbols']:
   rows.append({'account':rel(folder),'valid':False,'reason':'Retained superseded SPY input failure, not used in economic contrasts'});continue
  d=pd.read_parquet(folder/'daily.parquet');q=pd.read_parquet(folder/'orders.parquet');ex=pd.read_parquet(folder/'executions.parquet')
  shares=np.zeros(len(cols));last=np.full(len(cols),np.nan);cash=CAP;resid=0.;cr=0.;missingmarks=[];synthetic=[];peaks=CAP;maxclosingweight=0.
  groups={pd.Timestamp(k):g for k,g in q.groupby('trade_date')};execs={} if ex.empty else {pd.Timestamp(k):g for k,g in ex.groupby('trade_date')}
  for i,date in enumerate(dates):
   # The native delisting convention releases the last marked economic value.
   # This cash bridge is visible and conditional, never a fabricated order/fill.
   jj=np.flatnonzero((delist==i)&(shares!=0))
   for j in jj:
    assert np.isfinite(last[j]);release=shares[j]*last[j];cash+=release;shares[j]=0.;synthetic.append({'date':str(date.date()),'symbol':str(cols[j]),'released_cash':float(release),'roundoff_only':bool(abs(release)<=1e-8),'basis':'Native last-mark economic entitlement, physical corporate rights unresolved'})
   g=groups.get(date)
   if g is not None:
    jj=cols.get_indexer(g.symbol);assert (jj>=0).all()
    eo=np.where(np.isfinite(oa[i])&(oa[i]>0),oa[i],last)
    assert np.allclose(eo[jj],g.price,rtol=0,atol=1e-9)
    assert pd.DatetimeIndex(g.decision_date).max()<date,'Decision must precede execution'
    # Dollar holdings observed immediately before the fill must equal saved shares.
    cr=max(cr,float(np.max(np.abs(shares[jj]*g.price.to_numpy()-g.held_before_dollars.to_numpy()))))
    shares[jj]+=g.dollar_trade.to_numpy()/g.price.to_numpy()
    costs=float(execs[date][['spread','impact','fees']].sum().sum())
    cash-=float(g.dollar_trade.sum())+costs
    if rel(folder) in primary:
     arm,mult=primary[rel(folder)];parts=raw(g)
     for k in parts:assert abs(parts[k]*mult-float(execs[date][k].sum()))<=1e-6
   last=np.where(priced[i],ca[i],last)
   held=shares!=0
   assert np.isfinite(last[held]).all()
   if (held&~priced[i]).any():missingmarks.append(str(date.date()))
   equity=cash+float(shares[held]@last[held])
   if date in d.index:
    resid=max(resid,abs(equity-float(d.loc[date,'equity'])))
    assert abs(cash-float(d.loc[date,'cash_exp']*d.loc[date,'equity']))<=1e-6
    maxclosingweight=max(maxclosingweight,float(np.max(shares[held]*last[held]/equity)) if held.any() else 0)
  assert resid<=1e-6 and cr<=1e-6,(folder.name,resid,cr)
  eq=pd.concat([pd.Series([CAP],index=[pd.Timestamp('2024-01-05')]),d.equity]);dd=eq/eq.cummax()-1;trough=dd.idxmin();peak=eq.loc[:trough].idxmax();after=eq.loc[trough:];recovered=after[after>=eq.loc[peak]-1e-8]
  recovery=None if recovered.empty else str(recovered.index[0].date())
  stock=~q.symbol.isin(HEDGE_ETFS)
  if len(q):
   px=np.where(np.isfinite(q.prior_close),q.prior_close,q.price)
   with np.errstate(all='ignore'):hs=half_spread_bp(px,q.dollar_adv_21,q.vol_21,pd.to_datetime(q.trade_date).dt.year,'open')
   fallback=stock.to_numpy()&~np.isfinite(hs)
   participation=q.dollar_trade.abs()/q.dollar_adv_21
   participation=participation[stock&np.isfinite(participation)]
   cap={'stock_fallback_cost_orders':int(fallback.sum()),'stock_fallback_order_notional_usd':float(q.loc[fallback,'dollar_trade'].abs().sum()),'stock_max_ADV_fraction':float(participation.max()) if len(participation) else None}
  else:cap={'stock_fallback_cost_orders':0,'stock_fallback_order_notional_usd':0.,'stock_max_ADV_fraction':None}
  rows.append({'account':rel(folder),'valid':True,**cap,'primary':rel(folder) in primary,'order_share_equity_max_residual_usd':resid,'held_before_order_max_residual_usd':cr,'terminal_cash':cash,'frozen_mark_dates':missingmarks,'synthetic_delist_cash_bridges':synthetic,'max_closing_weight':maxclosingweight,'drawdown_peak_date':str(peak.date()),'drawdown_trough_date':str(trough.date()),'recovery_date':recovery})
 for row in rows:
  if row.get('valid'):
   for bridge in row['synthetic_delist_cash_bridges']:bridge['roundoff_only']=abs(bridge['released_cash'])<=1e-8
   row['material_delist_bridges']=[x for x in row['synthetic_delist_cash_bridges'] if not x['roundoff_only']]
   row['material_delist_released_usd']=sum(x['released_cash'] for x in row['material_delist_bridges'])
   row['material_frozen_marks']=[]
   if row['frozen_mark_dates']:
    source=ROOT/row['account'];native=read(source/'native.json');daily=pd.read_parquet(source/'daily.parquet')
    snapshots={pd.Timestamp(k):v for k,v in native['holdings'].items()}
    for value in row['frozen_mark_dates']:
     date=pd.Timestamp(value);hh=snapshots.get(date,{})
     for symbol,w in hh.items():
      if not np.isfinite(c.loc[date,symbol]):
       dollars=w*float(daily.loc[date,'equity_open_post'])
       if abs(dollars)>1e-8:row['material_frozen_marks'].append({'date':value,'symbol':symbol,'last_mark_dollars':dollars})
  receipt=ROOT/row['account']/'read-only-audit.json'
  if not receipt.exists():
   from open_composer.lab.batch import write_evidence
   write_evidence(receipt,row)
 if '--partial' not in sys.argv:save('raw-account-audit.json',rows)
 return rows,primary

def usage():
 run=read(BASE/'runs/mechanisms-20261102-6/run.json');phases=[]
 for name,p in run['phases'].items():
  phases.append({'phase':name,'session':p.get('session'),'status_at_capture':p['status'],'usage':p.get('usage'),'elapsed_seconds':p.get('elapsed_seconds')})
 sessions={}
 for p in phases:
  if p['usage'] is not None:
   key=p['session'] or p['phase'];prior=sessions.setdefault(key,{})
   for k,v in p['usage'].items():prior[k]=max(prior.get(k,0),v)
 observed={k:sum(v.get(k,0) for v in sessions.values()) for k in ['input_tokens','cached_input_tokens','output_tokens']}
 old=[]
 for f in sorted((OUT.parent).glob('*.resource.txt')):
  txt=f.read_text();d={'artifact':rel(f)}
  for label,key in [('User time (seconds)','user_seconds'),('System time (seconds)','system_seconds'),('Maximum resident set size (kbytes)','max_rss_KiB'),('Exit status','exit_code')]:
   m=re.search(re.escape(label)+r':\s*(\S+)',txt)
   if m:d[key]=float(m.group(1))
  old.append(d)
 save('usage-and-failures.json',{'captured_at':datetime.now(UTC).isoformat(),'all_role_records':phases,'finished_session_fieldwise_max_lower_bound':observed,'finished_session_total_token_lower_bound':observed['input_tokens']+observed['output_tokens'],'engine_process_resources':old,'failed_attempts':['Read-only path probe named a nonexistent equity_book_engine.py; system-Python probe lacked pandas. Existing .venv reused; financial jobs unchanged; event overhead retained and not separately measured','Manifest adapter KeyError before any economic account; retained failed-manifest-adapter-engine.log/resource','SPY omitted by stock-only input loader; zero-fill market account rejected, first LGBM attempt interrupted and retained; corrected ETF snapshot loaded, native order accounting resumed under explicit repair id'],'prior_lineage_provider_cost_usd':{'estimate':.21,'actual':None,'basis':'Original four Modal jobs; historical all-role token/time and debugging/failed charges incomplete'},'current_incremental_provider_compute_usd':0,'current_actual_codex_charge_usd':None,'unknown':['Worker current turn and subsequent fresh Lead usage not finalized until existing driver closes phases','Same resumed reviewer session has cumulative records: do not sum both fields as independent usage; driver fieldwise maxima / raw event accounting govern','Local CPU costs unknown; no paid provider, model fit, market refresh or remote job launched'],'scope':'Ordinary reversal research only; residual-momentum attribution and restructuring excluded; no quota percentage used as cost'})

def report(rows,primary):
 table=read(OUT/'primary-summary.json');
 for row in table:
  name=next(p for p,v in primary.items() if v==(row['arm'],row['cost_multiplier']));a=next(x for x in rows if x['account']==name)
  row['max_ADV_fraction']=a['stock_max_ADV_fraction'];row['missing_cost_input_orders']=a['stock_fallback_cost_orders']
  spyname=next(p for p,v in primary.items() if v==('SPY',row['cost_multiplier']))
  d=pd.read_parquet(ROOT/name/'daily.parquet').net;spy=pd.read_parquet(ROOT/spyname/'daily.parquet').net
  row['beta_to_SPY']=float(d.cov(spy)/spy.var())
 save('primary-summary-audited.json',table)
 contrasts=read(OUT/'contrasts.json');matches=read(OUT/'matching-summary.json');counts=read(OUT/'counts.json');
 for pair in matches:
  if pair['matched']:
   ma=read(ROOT/pair['model_account']/'metrics.json');co=read(ROOT/pair['control_account']/'metrics.json')
   pair['model_max_drawdown']=ma['max_drawdown'];pair['control_max_drawdown']=co['max_drawdown']
   pair['trailing250_increment_usd']=ma['trailing250_net_profit_usd']-co['trailing250_net_profit_usd']
 save('matching-summary-audited.json',matches)
 stats={(x['arm'],x['cost_multiplier']):x for x in table};aud={r['account']:r for r in rows};auditprimary={(arm,mult):aud[p] for p,(arm,mult) in primary.items()}
 market=[x for x in matches if x['control']=='SPY']
 if all(x['matched'] and x['increment_usd']<0 for x in market):
  decision='建议封存这两组保存分数在 $20k 上的原样长仓映射，停止附近参数搜索。两模型在本窗口都能净赚钱，LightGBM还改善了冻结规则的结果；但完整674日的两档成本下，两模型均未超过实际同波动SPY账户。近期1x成本的改善与回撤下降保留为正面线索；2x成本下的反转使证据仍属混合，按已接受scope的停止条件封存当前映射。'
 else:
  decision='本轮有限经济比较已经完成，建议保留实际账户显示的条件性贡献，并停止这组冻结定义的附近搜索。模型增量、市场机会成本与回撤取舍见下表；无法精确匹配的对照保留为无法匹配。'
 recent_parts=[]
 for pair in market:
  if pair['matched']:recent_parts.append(f"{pair['model']} {pair['cost_multiplier']}x：近250日相对同风险SPY {'+' if pair['trailing250_increment_usd']>=0 else '−'}${abs(pair['trailing250_increment_usd']):,.2f}")
 recent_note='；'.join(recent_parts)+'。近期美元沿原路径计算；它们不能替代完整窗口或成本压力结果。'
 text=['# $20k 保存反转排序的长仓组件结果','', decision,'',recent_note,'','六个独立账户及两档实际成本已完成。以下结论仅适用于冻结的已见窗口和原生经济单位口径，交由 fresh Lead 接收原始账本。','', '| 政策 | 1x 净利润 | 2x 净利润 | 1x 近250日净利润 | 1x 年化波动 | 1x 最大回撤 | 1x 现金均占比 |','|---|---:|---:|---:|---:|---:|---:|']
 for arm in ARMS:
  a,b=stats[arm,1],stats[arm,2];text.append(f"| {arm} | ${a['net_profit_usd']:,.2f} | ${b['net_profit_usd']:,.2f} | ${a['trailing250_net_profit_usd']:,.2f} | {a['annual_volatility']:.1%} | {a['max_drawdown']:.1%} | {a['mean_cash_fraction']:.1%} |")
 text+=['','窗口为 2024-01-08 至 2026-09-15，共674个交易日。旧报告685日有误；未补造日期、删失亏损日或读取9月16日后的行情。每个账户起始 $20,000，保留收盘决策、次日开盘成交、旧持仓先赚隔夜收益和五批重叠。两模型沿用原始长边选择后固定翻倍，移除短股和SPY对冲，资金独立，因此不能把结果解释为仅删除旧短腿的因果效果。','', '## 模型增量及机会成本','', '| 模型/控制 | 成本 | 终值利润差 | 年化日均收益率差 | 六比较同时95%区间 | HAC5 t |','|---|---:|---:|---:|---:|---:|']
 for x in contrasts:text.append(f"| {x['model']}/{x['control']} | {x['cost_multiplier']}x | ${x['increment_usd']:,.2f} | {x['annualized_mean_difference']:.1%} | [{x['simultaneous95_annualized_low']:.1%}, {x['simultaneous95_annualized_high']:.1%}] | {x['HAC5_t']:.2f} |")
 text+=['','区间对应配对日收益率差；不表示终值美元差的区间。共同日期矩阵、63日循环区块、1,999次抽样和 seed=20261102 固定，六比较 maxT 分成本档计算。674日只约10.7个区块长度，且继承已见样本和模型选择；两成本档相互依赖。DSR/PBO 为 N/A，未从幸存结果重造独立试验数。','', '## 实际资金与风险匹配','', '| 比较 | 成本 | 缩减政策/比例 | 同风险模型利润 | 同风险控制利润 | 差额 | 模型/控制回撤 | 近250日差额 |','|---|---:|---|---:|---:|---:|---:|---:|']
 for x in matches:
  if x['matched']:text.append(f"| {x['model']}/{x['control']} | {x['cost_multiplier']}x | {x['scaled_arm']} / {x['scale']:.8f} | ${x['model_net_profit_usd']:,.2f} | ${x['control_net_profit_usd']:,.2f} | ${x['increment_usd']:,.2f} | {x['model_max_drawdown']:.1%}/{x['control_max_drawdown']:.1%} | ${x['trailing250_increment_usd']:,.2f} |")
  else:text.append(f"| {x['model']}/{x['control']} | {x['cost_multiplier']}x | 无有效根；门槛跳跃见原始匹配 | — | — | — | — | — |")
 text+=['','同风险控制逐个重新注资并对实际订单扣费，只缩减高波动一方，选择最小可行根；相同控制复用。尺度先乘目标，再按固定初始资金过滤。股票目标在 0.5、0.625、5/6 附近出现离散跳跃，不能跨跳跃插值为同风险美元。分段固定节点和根容差在收益计算前写入 definitions.json。该匹配使用整段已见数据，只作事后机会成本解释。','']
 for arm in STOCKS:
  a=stats[arm,1];text.append(f"- {arm}：目标过滤平均移除 {a['target_excluded_weight_mean']:.1%} 权重，平均持有 {a['mean_long_names']:.1f} 只；执行小于 $100 的差额订单 {a['small_orders_below100']:,} 笔，扣费资金缩减累计 ${a['funding_reduction_usd']:,.2f}。")
 text+=['','目标过滤使用固定初始 $20,000，与最小订单额不同；退出和小额调仓均执行。扣费所需资金保留全部卖单，以共同系数缩减买单，64次二分保留可行下端点，缩减后不再次过滤或归一化。现金不计息，保留原6.5%融资率用于暴露异常；实际融资和借券费用均为零。','', '## 年份贡献、成本与恢复','', '| 政策 | 年份 | 毛交易损益 | 实际交易成本 | 净损益 |','|---|---:|---:|---:|---:|']
 for arm in ARMS:
  for x in stats[arm,1]['annual']:text.append(f"| {arm} | {x['year']} | ${x['gross_pnl_usd']:,.2f} | ${x['transaction_cost_usd']:,.2f} | ${x['net_pnl_usd']:,.2f} |")
 text+=['','毛损益是该实际扣费持仓路径每日净损益加回当日成本的美元恒等式，不能当成独立免成本账户。近250日按同一财富路径取美元变化，没有重新归一化资金。完整两档逐年明细见 primary-summary-audited.json。ETF不需要股票ADV回退，股票回退计数和beta在订单审计中校正；原metrics.json保留。','']
 for arm in ARMS:
  if arm=='CASH':
   text.append('- CASH：余额维持 $20,000，利息、波动和回撤均为零。');continue
  a=stats[arm,1];au=auditprimary[arm,1];beta='N/A' if a['beta_to_SPY'] is None else f"{a['beta_to_SPY']:.3f}";adv='N/A' if not isinstance(a['max_ADV_fraction'],(int,float)) else f"{a['max_ADV_fraction']:.6%}"
  sr='N/A' if a['sharpe_annual_252'] is None else f"{a['sharpe_annual_252']:.3f}"
  text.append(f"- {arm}：原始净收益 Sharpe {sr}，beta={beta}；最长水下 {a['longest_underwater_sessions']} 会话，最大回撤峰/谷 {au['drawdown_peak_date']}/{au['drawdown_trough_date']}，恢复日 {au['recovery_date'] or '窗口末未恢复'}；最大收盘单名占比 {au['max_closing_weight']:.2%}，最大订单/ADV {adv}。")
 for arm in STOCKS:
  au=auditprimary[arm,1];names=', '.join(x['symbol'] for x in au['material_delist_bridges']) or '无'
  frozen='无' if not au['material_frozen_marks'] else '；'.join(f"{x['date']} {x['symbol']} ${x['last_mark_dollars']:,.2f}" for x in au['material_frozen_marks'])
  text.append(f"- {arm}：1x 退市最后标记转现金合计 ${au['material_delist_released_usd']:,.2f}，涉及 {names}；这些现金是条件经济权益处理，未认证公司行为兑付。有效缺价持仓记录：{frozen}。低于 $1e-8 的单位残余单列为浮点噪声。")
 text+=['','## 证据、失败和研究投入','',f"针对性验证包括 test_funding.py、test_equity_book_costs.py 和 test_equity_book_backtest.py；完成成本绑定优化后重新检查受影响行为，检查通过，未运行全套测试。引擎登记四个新政策、零新训练、12个成本视图比较；实际启动 {counts['counts']['financial_accounts']} 个资金账户，包括全部风险根探测、被否决的SPY空仓账户和中断尝试。实际完成数、失败账户及每个账户的用时以 counts.json、trials.snapshot.jsonl 和 complete/failure.json 为准，根探测不计新政策。旧暴露下界35加本轮4为39，并非39个独立成功试验。24个主格、2模型、5事后探索及6份稳健输出均保留；两份额外借券敏感性与24个重复压力窗口不混成新模型。该有限组件已经覆盖旧方向预算，无权扩展阈值、股票数、分数或成交时点。",'', '首个实现启动在价格清理清单字段上报 KeyError，发生于经济账户前。随后发现股票读取器没有加载SPY：原生引擎记录未知符号，错误市场账户的零成交结果被保留并排除。中断当时未完成的本轮股票账户，补入既存ETF快照且证明股票价格完全相同，以新修复ID继续；未重放原始研究或已完成有效账户。纯成本函数增加了固定属性绑定，64次资金根探测仍逐次计算原生变量价差/冲击/费用，只记录最终成交；受影响成本和账户检查通过。','', 'raw-account-audit.json 逐账户从保存订单换算单位持仓、累计现金和价格标记，独立核对净值与成交前持仓，不重跑信号。保留缺价冻结日和原生退市最后标记现金桥；这些是条件经济单位约定，不能认证真实公司行为权益。输入分数逐字节等于原始phase2文件；保存的年度拟合日志、训练特征截止、年度首日开盘标签结束及其后收盘预测时点一一绑定，未重新训练。新闻源行按 visible_at 检查并与保存特征逐项核对。模型拟合权重未存档、标签截尾约定、历史身份和PIT成员资格的认证限制仍在。','', '原生开盘成本来自09:35–09:45报价快照，并含2025/2026校准年效应；使用决策时ADV/波动、缺输入40bp回退和实际订单规模计算，不能称为历史实现滑点。真实碎股能力、公司行为现金和开盘执行质量是后续部署依赖。本轮没有paper、实盘、调度、市场刷新或远端作业变更。','', '全角色token/时间、失败资源与未知费用见 usage-and-failures.json。原四次Modal的 $0.21 只保留为估计；保存的成功作业回执合计约1,547.76秒，原5种模型配置实际有45次年度拟合日志，本轮零新拟合；旧调试/失败与全角色成本不完整，本轮Worker及后续Lead费用待现有driver收尾。重复review session不能累计加两遍；不把残差动量归因或重构费用算入本题，不以额度百分比替代项目成本。','', '下一项具体决策：fresh Lead 从原始订单、现金、成本和配对区间接收本轮后，决定封存该小额长仓映射。原35项已知政策暴露和本轮4项映射足以回答这一有限问题；继续扩充相邻阈值或股票数会改变已冻结的问题且增加选择暴露。该停止建议只针对当前映射，未否定反转机制、新闻信息或成本感知模型的一般研究价值。']
 p=OUT.parent/'worker-report.zh.md';content='\n'.join(text)+'\n';p.write_text(content)
 public=ROOT/'reports/research/reversal_long_side_20261102/long-side-final.zh.md';public.parent.mkdir(parents=True,exist_ok=True);public.write_text(content)

def main():
 rows,primary=audit()
 if '--partial' in sys.argv:
  print('AUDITED SAVED ACCOUNTS',len(rows),flush=True);return
 events=TrialLedger(BASE/'trials.jsonl').events()
 unresolved=[e.trial_id for e in events if e.event=='started' and not any(f.event=='finished' and f.trial_id==e.trial_id for f in events)]
 assert not unresolved,unresolved
 usage();report(rows,primary)
 r=Results.model_validate(read(OUT/'results.json'))
 for x in ['raw-account-audit.json','usage-and-failures.json','prior-fit-count-clarification.json','prior-provider-receipts.json','primary-summary-audited.json','matching-summary-audited.json']:r.source_artifacts.append(rel(OUT/x))
 r.source_artifacts.append('reports/research/reversal_long_side_20261102/long-side-final.zh.md')
 save('results-audited.json',r.model_dump());(BASE/'results.json').write_text(r.model_dump_json(indent=2)+'\n')
 validate_results(ROOT,rel(BASE/'results.json'),BASE.name)
 save('final-validation.json',{'results_schema':'valid','raw_accounts_audited':sum(x.get('valid',False) for x in rows),'superseded_invalid_accounts':sum(not x.get('valid',False) for x in rows),'unresolved_account_checks':[],'production_or_paper_change':False})
 print('FINALIZED',len(rows),flush=True)
if __name__=='__main__':main()
