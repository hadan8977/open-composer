"""Source-linked current legal-unit/action witness; no account or model calls."""
import copy
import math
from datetime import date
import next_source_common as c
import next_input_common as ic
import next_session_source as source
import next_session_data as data

INACTIVE = {'WBA', 'PBCT', 'RE'}
SYMBOL_FIELDS = ('symbol', 'source_symbol', 'acquiree_symbol', 'old_symbol', 'new_symbol', 'acquirer_symbol')


def event_symbols(raw):
    return {raw[k] for k in SYMBOL_FIELDS if type(raw.get(k)) is str and raw[k]}


def normalize_events(value, *, retained_alias_lineage=None):
    """Normalize retained formats only; never invent a missing economic date."""
    result = []
    if type(value) is dict:
        pairs = [(kind, raw) for kind, values in value.items() for raw in values]
    else:
        assert type(value) is list
        pairs = [(r['kind'], r['raw'] if 'raw' in r else r['terms']) for r in value]
    for kind, raw in pairs:
        assert type(raw) is dict and type(raw['id']) is str and raw['id']
        economic = raw.get('ex_date') or raw.get('effective_date')
        if economic is None:
            assert kind == 'name_changes' and retained_alias_lineage is not None, 'Undated new economic/identity event remains unknown'
            source_row, review_row = retained_alias_lineage['source'], retained_alias_lineage['review']
            accepted = c.load(c.checked(source_row, c.T / 'input/BASE/output.json'))
            review = c.load(c.checked(review_row, c.T / 'independent-current-input-review-BASE.json'))
            assert review['task_id'] == c.TASK and review['policy'] == 'BASE'
            assert review['reviewer'] == c.PEER and review['independent'] is True
            assert review['verdict'] == 'accept_complete_current_input' and review['source_linked_controls_accepted'] is True
            assert review['target'] == review['derived_control_witness'] == source_row
            known = accepted['current_actions']['name_changes']
            assert raw in known, 'Changed/new undated alias is not accepted retained identity lineage'
            assert raw['old_symbol'] != raw['new_symbol'] and raw['old_cusip'] == raw['new_cusip']
            result.append(dict(id=raw['id'], kind=kind, terms=copy.deepcopy(raw), economic_date=None,
                classification='accepted_retained_alias_economic_time_unknown',
                retained_alias_lineage=copy.deepcopy(retained_alias_lineage)))
            continue
        assert type(economic) is str and date.fromisoformat(economic).isoformat() == economic
        result.append(dict(id=raw['id'], kind=kind, terms=copy.deepcopy(raw), economic_date=economic))
    return result


def merge_events(retained, current):
    """Keep all known IDs; changed terms and late old events remain explicit."""
    master, changed, late = {}, [], []
    for event in retained:
        if event['id'] in master:
            assert master[event['id']] == event, 'Conflicting retained action history'
        master[event['id']] = event
    for event in current:
        prior = master.get(event['id'])
        if prior is not None and prior != event:
            changed.append(dict(id=event['id'], retained=prior, current=event))
            continue
        if prior is None and (event['economic_date'] is None or event['economic_date'] <= '2026-10-19'):
            late.append(event['id'])
        master[event['id']] = event
    return master, changed, late


def pages(group):
    saved = source.receive_sources(group)
    context = source.receive_context(saved['context'], saved)
    objects, raw_rows = {}, {}
    for request in context['requests']:
        key = request['key']; folder = c.ROOT / c.STAGES[group] / 'captures' / key
        objs, _, _ = source.receive_capture(saved['context'], request, saved['captures'][key])
        complete = c.load(c.checked(saved['captures'][key], folder / 'complete.json'))
        pairs = []
        assert len(objs) == len(complete['pages'])
        for obj, metarow in zip(objs, complete['pages'], strict=True):
            meta = c.load(c.checked(metarow))
            assert meta['response'] in saved['consumed']
            pairs.append((obj, meta['response']))
        objects[key] = objs; raw_rows[key] = pairs
    return saved, objects, raw_rows


def previous_inputs():
    _, plan = c.receive_definition()
    result = {}
    for policy in ['BASE', 'H5', 'LSTM', 'ETF-input']:
        if policy == 'ETF-input':
            row, rr = plan['ETF']['prior_input'], plan['ETF']['prior_input_review']
        else:
            row = c.binding(c.T / 'input' / policy / 'output.json')
            rr = c.binding(c.T / f'independent-current-input-review-{policy}.json')
        value = c.load(c.checked(row)); review = c.load(c.checked(rr))
        assert review['task_id'] == c.TASK and review['policy'] == policy
        assert review['reviewer'] == c.PEER and review['independent'] is True
        assert review['verdict'] == 'accept_complete_current_input' and review['source_linked_controls_accepted'] is True
        assert review['target'] == review['derived_control_witness'] == row
        result[policy] = (value, row, rr)
    return result


def raw_prior_inventory(previous):
    rows = {}
    for policy, (value, _, _) in previous.items():
        bars = value['raw_reference_bars'] if policy == 'ETF-input' else value['controls']['bars']
        for symbol, days in bars.items():
            if '2026-10-19' in days:
                raw = days['2026-10-19']
                if symbol in rows: assert rows[symbol] == raw, 'Retained raw overlap conflicts'
                rows[symbol] = raw
    return rows


def build_records(symbols, raw, events, *, group_for, raw_bindings, action_bindings,
                  retained_bindings, late_events, breaks):
    records = {}
    for symbol in symbols:
        relevant = [v for v in events.values() if symbol in event_symbols(v['terms'])]
        unresolved = [v['id'] for v in relevant if v['id'] in late_events]
        boundary = [v for v in relevant if v['economic_date'] is not None and '2026-10-20' < v['economic_date'] <= '2026-10-21']
        unresolved += [v['id'] for v in boundary if v['kind'] != 'cash_dividends']
        if symbol in breaks: unresolved.append('default_raw_price_hygiene_break')
        row = raw.get((symbol, '2026-10-20'))
        supported = row is not None and symbol not in INACTIVE and not unresolved
        records[symbol] = dict(symbol=symbol, source_group=group_for[symbol],
            reference_day='2026-10-20', application_day='2026-10-21', raw_unit_symbol=symbol,
            raw_adjustment='raw', process_query_window=['2026-09-30', '2026-11-14'],
            complete_action_page_chain_received=True, retained_known_events_merged_without_revision=True,
            no_prior_dividend_entitlement_inferred=True,
            unit_transition='identity' if supported else ('unsupported' if symbol in INACTIVE else 'unknown'),
            supported=supported, raw_open=None if row is None else row['o'], raw_close=None if row is None else row['c'],
            unresolved_event_ids=sorted(set(unresolved)),
            boundary_right_event_ids=sorted(v['id'] for v in boundary if v['kind'] == 'cash_dividends'),
            known_event_ids=sorted(v['id'] for v in relevant),
            accepted_alias_events=[copy.deepcopy(v) for v in relevant if v.get('classification') == 'accepted_retained_alias_economic_time_unknown'],
            raw_unit_source_rows=raw_bindings[symbol], action_source_rows=action_bindings[group_for[symbol]],
            retained_action_bindings=retained_bindings[symbol])
    return records


def produce():
    native, claim = ic.start('CURRENT_CONTROLS'); ic.computing('CURRENT_CONTROLS')
    started = c.now(); _, plan = c.receive_definition()
    previous = previous_inputs(); retained = []
    alias_lineage = dict(source=previous['BASE'][1], review=previous['BASE'][2])
    for value, _, _ in previous.values(): retained += normalize_events(value['current_actions'], retained_alias_lineage=alias_lineage)
    saved, objects, page_rows = {}, {}, {}
    for group in ['core', 'ETF']:
        saved[group], objects[group], page_rows[group] = pages(group)
    core_symbols, etf_symbols = plan['core']['raw_symbols'], plan['ETF']['symbols']
    core = data.core_bars(objects['core']['raw-bars'], core_symbols, inactive=sorted(INACTIVE))
    etf = data.original('ETF', 'bar_rows')(objects['ETF']['raw-reference'], etf_symbols, ['2026-10-19', '2026-10-20'])
    assert all(core[key] == value for key, value in etf.items() if key in core), 'Core/ETF current raw overlap differs'
    raw = {**core, **etf}; old_raw = raw_prior_inventory(previous)
    conflicts = [dict(symbol=s, old=r, current=raw.get((s, '2026-10-19')))
                 for s, r in old_raw.items() if raw.get((s, '2026-10-19')) != r]
    ca = data.core_actions(objects['core']['actions'], core_symbols)
    ea = data.ETF_actions(objects['ETF']['actions'])
    current = normalize_events(ca[0]['corporate_actions'], retained_alias_lineage=alias_lineage) + normalize_events(ea, retained_alias_lineage=alias_lineage)
    master, revisions, late = merge_events(retained, current)
    caprows = {k: native['capacity'][k] for k in ['context', 'review']}
    if conflicts or revisions:
        c.save(c.ROOT / 'controls/changed-source-inventory.json', dict(raw_changes=conflicts, action_changes=revisions,
               complete_inventory=True, inputs_admissible=False, source_retry_permitted=False), capacity_rows=caprows)
        raise ValueError('Changed accepted prior source retained for saved-source reception')
    import numpy as np
    import pandas as pd
    from open_composer.research.features.price_hygiene import sanitize_price_matrices
    symbols = list(dict.fromkeys(core_symbols + etf_symbols)); dates = ['2026-10-19', '2026-10-20']
    matrices = [pd.DataFrame([[raw.get((s, d), {}).get(k, np.nan) for s in symbols] for d in dates],
                 index=pd.to_datetime(dates), columns=symbols, dtype=float) for k in ['c', 'o']]
    _, _, qa = sanitize_price_matrices(*matrices)
    breaks = {r.symbol for r in qa.breaks if str(r.first_session_after.date()) == '2026-10-20'}
    group_for = {s: ('core' if s in core_symbols else 'ETF') for s in symbols}
    raw_bindings = {s: [row for obj, row in page_rows[group_for[s]][
        'raw-bars' if group_for[s] == 'core' else 'raw-reference'] if s in obj['bars']] for s in symbols}
    action_bindings = {g: [row for _, row in page_rows[g]['actions']] for g in ['core', 'ETF']}
    retained_bindings = {}
    for s in symbols:
        retained_bindings[s] = [row for p, (v, row, _) in previous.items()
                               if s in (set(v['symbols']) | (set() if p == 'ETF-input' else set(v['controls']['bars'])))]
        assert retained_bindings[s], 'No retained current unit/action lineage'
    records = build_records(symbols, raw, master, group_for=group_for, raw_bindings=raw_bindings,
                action_bindings=action_bindings, retained_bindings=retained_bindings, late_events=late, breaks=breaks)
    consumed = [r for value, row, rr in previous.values() for r in [row, rr]]
    for obj in saved.values(): consumed += obj['consumed']
    for group in ['core', 'ETF']:
        consumed += [native['source_inputs'][group]['output'], native['source_inputs'][group]['completed']]
    unique = {r['path']: r for r in consumed}; assert all(unique[r['path']] == r for r in consumed)
    return ic.finish('CURRENT_CONTROLS', dict(kind='current_legal_unit_action_controls', symbols=records,
        consumed=list(unique.values()), current_actions_by_group={g: [dict(kind=k, terms=r) for page in objects[g]['actions']
            for k, values in page['corporate_actions'].items() for r in values] for g in ['core', 'ETF']},
        late_old_event_ids=sorted(set(late)), hygiene=dict(defaults=True, raw=qa.manifest()),
        valid_until='2026-10-22T00:00:00Z', provider_ex_date_coverage_certified=False,
        historical_dividend_entitlement_certified=False, account_funding_or_risk_go=False,
        computed_started_at=started, computed_completed_at=c.now()))


if __name__ == '__main__':
    produce()
