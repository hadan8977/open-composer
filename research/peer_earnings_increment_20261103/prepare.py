"""Bind the accepted, finite peer-information experiment to saved inputs only."""
from pathlib import Path
from datetime import datetime
import sys, json, time
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts import t22_run as R
from open_composer.market_sessions import us_equity_session_close, NEW_YORK, us_equity_session_dates
from open_composer.research.features.price_hygiene import sanitize_price_matrices
from open_composer.lab.batch import write_evidence
from open_composer.lab.ledger import TrialLedger
from open_composer.research.agent_workflow import require_research

BASE = Path(__file__).resolve().parent
OUT = BASE / 'runs/mechanisms-20261102-7/worker/evidence'
ROLES = ['E', 'P', 'M', 'ME', 'MP', 'L', 'MX']
STOCKS = [f'{role}_H{h}' for h in [5, 20] for role in ROLES]
START, END, DECISION = '2024-01-08', '2026-09-15', '2024-01-05'

def save(name, value):
    p = OUT / name
    p.parent.mkdir(parents=True, exist_ok=True)
    if p.exists():
        normalized = json.loads(json.dumps(value, default=str))
        if json.loads(p.read_text()) != normalized:
            raise RuntimeError(f'Immutable evidence differs: {p}')
        return
    write_evidence(p, value)

def rel(p):
    return str(p.relative_to(ROOT))

def reaction_positions(accepted, closes):
    return closes.searchsorted(pd.DatetimeIndex(accepted), side='right')

def identity_rows(sic, date):
    """Covering dated links or explicitly unbounded current links; never nearest-link guessing."""
    f = sic.loc[(sic.link_first_date.isna() | (sic.link_first_date <= date)) &
                (sic.link_last_date.isna() | (sic.link_last_date >= date))].copy()
    unique = f[['symbol','cik','sic','ff48']].drop_duplicates()
    count = unique.groupby('symbol',sort=False).size()
    bad = set(count[count.ne(1)].index) | set(unique.loc[unique.sic.isna(),'symbol'])
    bounds = f.groupby('symbol',sort=False)[['link_first_date','link_last_date']].count()
    unbounded = bounds.eq(0).any(axis=1)
    result = f.loc[~f.symbol.isin(bad)].drop_duplicates('symbol').set_index('symbol')
    result['conditional_unbounded_link'] = unbounded.reindex(result.index)
    return result, sorted(bad)

def rank_roles(frame):
    r = frame[['E', 'P', 'M', 'L']].rank(pct=True, method='average')
    groups = sorted(frame.ff48.unique())
    values = frame.groupby('ff48').E.first().reindex(groups)
    # Rotate numeric group codes once; this is a fixed descriptive falsifier.
    rotated = dict(zip(groups, np.roll(values.to_numpy(), 1)))
    x = frame.ff48.map(rotated).rank(pct=True, method='average')
    r['ME'] = (r.E + r.M) / 2
    r['MP'] = (r.P + r.M) / 2
    r['MX'] = (x + r.M) / 2
    return r, len(groups) < 2

def main():
    require_research(ROOT)
    OUT.mkdir(parents=True, exist_ok=True)
    if (OUT / 'inputs-complete.json').exists():
        print('REUSE completed inputs; no recomputation', flush=True)
        return
    repairing = '--repair-calendar-unit' in sys.argv
    if (OUT / 'inputs-started.json').exists() and not repairing:
        raise RuntimeError('Unresolved input attempt: inspect and preserve before repair')
    begun = time.monotonic()
    save(f'inputs-repair-started-{time.time_ns()}.json' if repairing else 'inputs-started.json', {'at': pd.Timestamp.now(tz='UTC').isoformat()})
    ledger = TrialLedger(BASE / 'trials.jsonl')
    prior = [json.loads(x) for x in (ROOT / 'reports/research/trials.jsonl').read_text().splitlines()
             if 't20261001_book_v1"' in x]
    # Whole ancestor inventory, not just the industry signal or successful policies.
    existing = {e.trial_id for e in ledger.events()}
    if 'book_v1_registered_ancestry' not in existing:
      ledger.import_prior('book_v1_registered_ancestry', count=len(prior),
        evidence=['reports/research/trials.jsonl', 'reports/research/iterations/t20261001_book_v1/results.json',
                  'open_composer/research/equity_book/signals.py'],
        note='Known registered Book v1 configurations including industry momentum; broader later starts/failed debug unknown. No exact peer experiment found; not independent-trial count.')
    for arm in STOCKS:
        if 'policy:'+arm in existing:
            continue
        ledger.start('policy:' + arm, batch='fixed-information-roles', candidate=arm,
                     parameters={'capital': 20000, 'cost_multipliers': [1, 2]},
                     note='Seven fixed roles times two clocks; no search or fitting')
    save('trial-reconciliation.json', {'ancestor_registered_rows': prior, 'known_prior_floor': len(prior),
        'earlier_exact_peer_comparison_found': False,
        'saved_signal_library': 'ind_mom_12_1 and mom_12_1 in Book v1; no peer-earnings term in signal inventory',
        'old_queue': 'T-20260930-02 superseded 2026-10-01; old ten-cell grid not run here',
        'unknown': 'Later related signal-library policy selection and failed/debug starts not fully reconstructible; no defensible complete historical candidate distribution.',
        'new_policies': 14, 'new_model_fits': 0})
    save('definitions.json', {'roles': ROLES, 'policies': STOCKS, 'capital': 20000,
        'calendar': [START, END], 'decision_origin': DECISION, 'clocks': [5, 20],
        'cost_multipliers': [1, 2], 'target_filter': 'fixed initial capital*0.05*scale>=100; apply once; no order minimum',
        'matching': {'segments': [[0., .1-1e-9], [.1, 1.]], 'nodes_per_segment': 5,
                     'root_choice': 'smallest valid bracketed root, scale down only', 'xtol': 1e-10, 'vol_tolerance': 1e-6},
        'bootstrap': {'seed': 20261103, 'draws': 1999, 'block': 63, 'contrasts_per_cost': 10},
        'clock_details': 'First actual exchange close STRICTLY after acceptance, including early closes; latest accession per CIK in t-4..t; recipients with own issuer event excluded in all roles',
        'identity': 'Unique covering symbol/CIK/SIC identity; current unbounded links labeled conditional; no nearest-link extrapolation or null-SIC Other bucket',
        'event_eligibility': 'Other issuers must be in decision-time eligible U500, have a saved event ticker with unambiguous same CIK and current industry, and finite reaction endpoints; one latest event per issuer',
        'P': 'Mean five-session simple excess return of other eligible industry stocks with finite endpoints; missing observations unavailable, never zero',
        'scope': 'Conditional initial component diagnostic; frozen seen window, no held partition or later return rows'})
    s = R.Store()
    a, b = s.pos(pd.Timestamp(DECISION)), s.pos(pd.Timestamp(END))
    # Read only admitted feature rows. The master symbol union is not a current roster.
    positions = range(a-4, b+1)
    eligible = {}
    union = set()
    for t in positions:
        adv = np.asarray(s.m('dollar_adv_21')[t], float)
        ok = R.candidates(s, t, 500, 'none', adv) & (adv > 0)
        names = s.symbols[ok]
        eligible[s.dates[t]] = names
        union.update(names)
    hist_start = s.dates[a-252]
    print('LOAD', len(union), 'historical U500 union', hist_start, END, flush=True)
    if (OUT/'history-close.parquet').exists() and (OUT/'history-open.parquet').exists() and (OUT/'hygiene.json').exists():
        c, o = pd.read_parquet(OUT/'history-close.parquet'), pd.read_parquet(OUT/'history-open.parquet')
        print('REUSE bound price matrices and hygiene receipt', flush=True)
    else:
        p = R.PricePanel.from_dir(symbols=sorted(union), start=str(hist_start.date()), end=END,
                                 include_etfs=True, load_open=True)
        # Arrow-backed parquet calendars can be microsecond indexes.
        p.dates = p.dates.as_unit('ns')
        c, o, hygiene = sanitize_price_matrices(p.frame('close'), p.frame('open'))
        save('hygiene.json', hygiene.manifest())
    assert o is not None
    # SPY is in the ETF source, not in the stock-only price file.
    assert 'SPY' in c and c.SPY.loc[DECISION:END].notna().all() and o.SPY.loc[DECISION:END].notna().all()
    expected = pd.DatetimeIndex(us_equity_session_dates(pd.Timestamp(START).date(), pd.Timestamp(END).date()))
    idx = c.loc[START:END].index
    assert idx.equals(expected) and len(idx) == 674
    assert c.index[-1] == pd.Timestamp(END) and c.index[0] == hist_start
    for name,frame in [('history-close',c),('history-open',o),('close',c.loc[DECISION:END]),('open',o.loc[DECISION:END])]:
        if not (OUT/f'{name}.parquet').exists():
            frame.to_parquet(OUT/f'{name}.parquet')
    closes = pd.DatetimeIndex([pd.Timestamp(datetime.combine(d.date(), us_equity_session_close(d.date())), tz=NEW_YORK).tz_convert('UTC') for d in c.index])
    sic = pd.read_parquet(ROOT / 'data/features/sic_map/sic_map.parquet')
    events = pd.concat([pd.read_parquet(ROOT / f'data/features/earnings_events/{y}.parquet',
                       filters=[('acceptance_utc', '<=', closes[-1].strftime('%Y-%m-%dT%H:%M:%SZ'))]) for y in [2024, 2025, 2026]], ignore_index=True)
    input_n = len(events)
    events['cik'] = events.cik.astype(int)
    events['accepted'] = pd.to_datetime(events.acceptance_utc, utc=True)
    invalid = ~(events.form.eq('8-K') & events['items'].str.split(',').apply(lambda x: '2.02' in [v.strip() for v in x]) & events.acceptance_source.isin(['edgar_index', 'formula']))
    rejected = events.loc[invalid].copy()
    events = events.loc[~invalid].copy()
    conflict = events.groupby('accession')[['cik','accepted']].nunique().max(axis=1).gt(1)
    ambiguous_acc = conflict[conflict].index
    rejected = pd.concat([rejected, events.loc[events.accession.isin(ambiguous_acc)]])
    duplicates = int(events.accession.duplicated().sum())
    events = events.loc[~events.accession.isin(ambiguous_acc)].sort_values(['accepted', 'ticker']).drop_duplicates('accession').copy()
    events['reaction_pos'] = reaction_positions(events.accepted, closes)
    events = events.loc[events.reaction_pos.between(1, len(c)-1)].copy()
    ef = events[['accession','ticker','cik','accepted','reaction_pos','acceptance_source']].rename(columns={'acceptance_source':'source'}).reset_index(drop=True)
    ts = ef.reaction_pos.to_numpy(int)
    ef['reaction_date'] = c.index[ts]
    ef['reaction_close_utc'] = closes[ts]
    ef['previous_close_date'] = c.index[ts-1]
    linked = ef.reset_index(names='_event').merge(sic,left_on='ticker',right_on='symbol',how='left',suffixes=('','_link'))
    covering = linked.loc[(linked.link_first_date.isna() | linked.link_first_date.le(linked.reaction_date)) &
                         (linked.link_last_date.isna() | linked.link_last_date.ge(linked.reaction_date))]
    unique = covering[['_event','cik_link','sic','ff48']].drop_duplicates()
    sizes = unique.groupby('_event').size()
    good = unique.loc[unique._event.map(sizes).eq(1) & unique.sic.notna()].set_index('_event')
    same_issuer = ef.cik.eq(good.cik_link.reindex(ef.index))
    ef['reason'] = pd.Series('ambiguous_or_uncovered_issuer_link',index=ef.index,dtype=object)
    ef.loc[same_issuer,'reason'] = None
    js = c.columns.get_indexer(ef.ticker)
    ef.loc[same_issuer & (js<0),'reason'] = 'not_in_historical_U500_union'
    safe = np.maximum(js,0)
    prices = c.to_numpy()
    v0,v1 = prices[ts-1,safe],prices[ts,safe]
    finite = np.isfinite(v0)&np.isfinite(v1)&(v0>0)&(v1>0)
    ef.loc[ef.reason.isna() & ~finite,'reason'] = 'missing_reaction_endpoint'
    with np.errstate(invalid='ignore',divide='ignore'):
        reaction = v1/v0-c.SPY.to_numpy()[ts]/c.SPY.to_numpy()[ts-1]
    ef['reaction_excess'] = np.where(ef.reason.isna(),reaction,np.nan)
    print('EVENTS BOUND',len(ef),flush=True)
    assert (ef.accepted < ef.reaction_close_utc).all()
    ef.to_parquet(OUT / 'events.parquet', index=False)
    rejected.to_parquet(OUT / 'rejected-events.parquet', index=False)
    targets = {arm: pd.DataFrame(0., index=c.loc[DECISION:END].index[:-1], columns=c.columns) for arm in STOCKS}
    scored, coverage, membership = [], [], []
    decisions = c.loc[DECISION:END].index[:-1]
    for j, date in enumerate(decisions):
        if j % 5:
            continue
        t = c.index.get_loc(date)
        idf, ambiguous = identity_rows(sic, date)
        native = pd.Index(eligible[date]).intersection(c.columns)
        valid = native.intersection(idf.index)
        valid = valid[c.loc[date, valid].notna()]
        f = idf.loc[valid, ['cik', 'ff48', 'conditional_unbounded_link']].copy()
        momentum = c.iloc[t-21].reindex(valid) / c.iloc[t-252].reindex(valid) - 1
        f['M'] = momentum
        p5 = c.iloc[t].reindex(valid) / c.iloc[t-5].reindex(valid) - c.SPY.iloc[t]/c.SPY.iloc[t-5]
        f['p5'] = p5
        st = s.pos(date)
        f['L'] = pd.Series(np.asarray(s.m('dollar_adv_21')[st], float), index=s.symbols).reindex(valid)
        window = ef.loc[ef.reaction_pos.between(t-4, t)].sort_values(['accepted', 'accession']).drop_duplicates('cik', keep='last')
        own = set(window.cik)
        # Keep the latest event even if its reaction is unavailable; never fall back to an older valid event.
        pe = window.loc[window.reason.isna() & window.ticker.isin(valid)].copy()
        pe['ff48'] = pe.ticker.map(f.ff48)
        pe = pe.loc[pe.cik.eq(pe.ticker.map(f.cik))]
        group_events = pe.groupby('ff48').agg(E=('reaction_excess', 'mean'), peer_issuers=('cik', 'nunique'))
        n_group = f.groupby('ff48').size()
        f['industry_n'] = f.ff48.map(n_group)
        f['peer_issuers'] = f.ff48.map(group_events.peer_issuers)
        f['E'] = f.ff48.map(group_events.E)
        sums = f.groupby('ff48').p5.transform('sum')
        counts = f.groupby('ff48').p5.transform('count')
        f['P'] = (sums - f.p5.fillna(0)) / (counts - f.p5.notna().astype(int))
        f['own_event'] = f.cik.isin(own)
        covered = f.loc[(f.industry_n >= 15) & (f.peer_issuers >= 2) & ~f.own_event &
                        np.isfinite(f[['E', 'P', 'M', 'L']]).all(axis=1)].copy()
        ranks, placebo_uninformative = rank_roles(covered)
        cov = {'date': date, 'native_eligible': len(native), 'identity_covered': len(valid),
               'ambiguous_symbols': len(native.intersection(ambiguous)), 'own_event_excluded': int(f.own_event.sum()),
               'covered_recipients': len(covered), 'covered_industries': int(covered.ff48.nunique()),
               'placebo_uninformative': placebo_uninformative, 'zero_coverage': len(covered) == 0}
        coverage.append(cov)
        for group, g in f.groupby('ff48'):
            membership.append({'date': date, 'ff48': int(group), 'eligible_n': len(g),
                               'covered_n': int((covered.ff48 == group).sum()), 'peer_issuers': int(group_events.peer_issuers.get(group, 0))})
        sf = covered.join(ranks.add_suffix('_rank')).reset_index(names='symbol')
        sf.insert(0, 'decision_date', date)
        scored.append(sf)
        for h in [5, 20]:
            if j % h:
                continue
            for role in ROLES:
                order = pd.DataFrame({'symbol': ranks.index, 'rank': ranks[role].to_numpy()}).sort_values(['rank', 'symbol'], ascending=[False, True])
                picked = order.symbol.head(20)
                targets[f'{role}_H{h}'].loc[date, picked] = .05
    for arm, target in targets.items():
        h = int(arm.split('_H')[1])
        target = target.iloc[::h]
        target.to_parquet(OUT / f'targets-{arm}.parquet')
    pd.concat(scored, ignore_index=True).to_parquet(OUT / 'scores.parquet', index=False)
    pd.DataFrame(coverage).to_csv(OUT / 'coverage.csv', index=False)
    pd.DataFrame(membership).to_csv(OUT / 'industry-coverage.csv', index=False)
    save('inputs.json', {'admitted_event_rows': input_n, 'duplicate_accessions_removed': duplicates,
        'conflicting_accessions': list(ambiguous_acc), 'invalid_metadata_rows': len(rejected),
        'event_rows_bound': len(ef), 'event_reason_counts': ef.reason.fillna('usable').value_counts().to_dict(),
        'acceptance_sources': ef.source.value_counts().to_dict(), 'history': [str(c.index[0].date()), END],
        'n_sessions': len(idx), 'price_union_columns': len(c.columns), 'historical_U500_union': len(union),
        'SIC_vintage': sorted(sic.fetched_at_utc.dropna().unique()), 'SIC_PIT_certified': False,
        'data_mode': 'saved native SIP adjusted equity-book panel; ETF SPY explicit; no provider fallback',
        'native_manifest': 'data/research/equity_book/panel/_manifest.json',
        'existing_event_QA': 'reports/research/program/earnings-events-timing-fix-2026-10-04/checks.json',
        'limitations': ['Current SIC only; unbounded links conditional; no extrapolation beyond dated link intervals',
            'Native panel prebuilt retrospective price hygiene and pre-hygiene ADV attributes inherited',
            'Conditional adjusted economic units, last-mark/freeze/delist release; entitlements uncertified']})
    save('inputs-complete.json', {'seconds': time.monotonic()-begun, 'policies': len(targets),
        'coverage_decisions': len(coverage), 'zero_coverage': sum(x['zero_coverage'] for x in coverage)})
    print('INPUTS COMPLETE', time.monotonic()-begun, flush=True)

if __name__ == '__main__':
    main()
