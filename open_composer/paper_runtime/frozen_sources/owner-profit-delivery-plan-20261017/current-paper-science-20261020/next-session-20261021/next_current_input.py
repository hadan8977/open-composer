"""Fixed Oct21 input producers; source/model/account entry is never implicit."""
import copy
import io
import sys
from contextlib import contextmanager
from pathlib import Path
import next_source_common as c
import next_input_common as ic
import next_control_input as controls
import next_session_data as data

FUTURE = c.REPO / 'reports/research/program/owner-profit-delivery-plan-20261017/candidate-contribution/future-input-receiver'
BASE = FUTURE.parent / 'current-initialization-20261019'
LSTM = c.REPO / 'reports/research/program/return-line-replenishment-20261016/direct-position-learning-20261016'


@contextmanager
def future_modules():
    names = ['receiver_common', 'source_contract', 'retained_sources', 'features', 'source_writer']
    previous = {n: sys.modules.pop(n, None) for n in names}
    sys.path.insert(0, str(FUTURE))
    try: yield
    finally:
        sys.path.pop(0)
        for n in names:
            sys.modules.pop(n, None)
            if previous[n] is not None: sys.modules[n] = previous[n]


def digest(value):
    import numpy as np
    return c.hashlib.sha256(np.ascontiguousarray(value).tobytes()).hexdigest()


def optional(value):
    if type(value).__module__.startswith('numpy'): return optional(value.tolist())
    if type(value) is float and not c.math.isfinite(value): return None
    if type(value) is dict: return {k: optional(v) for k, v in value.items()}
    if type(value) in [list, tuple]: return [optional(v) for v in value]
    return value


def write_npz(policy, name, arrays):
    native, _ = ic.computing(policy)
    import numpy as np
    stream = io.BytesIO(); np.savez_compressed(stream, **arrays)
    return c.save_bytes(c.ROOT / ic.STAGES[policy] / name, stream.getvalue(),
                        capacity_rows={k: native['capacity'][k] for k in ['context', 'review']})


def base_input(control, source, objects, previous):
    """Only the accepted daily eligibility bridge; frozen design is referenced."""
    import numpy as np
    old = previous['BASE'][0]
    seed = c.load(FUTURE / 'accepted-seed.json')
    input_manifest = c.load(c.checked(seed['accepted_input_manifest']))
    for row in seed['files'].values():
        c.checked(row); assert row in input_manifest['files']
    # Select only the accepted causal price/return/support arrays. No monthly
    # label, training matrix, old prediction or account history is decoded.
    selected = {}
    keys = dict(daily=['dates', 'symbols', 'raw_close', 'raw_open', 'raw_volume', 'returns'],
                raw_units=['dates', 'symbols', 'raw_close', 'raw_open'], inherited=['symbols', 'eligible'])
    for name, names in keys.items():
        with np.load(c.checked(seed['files'][name]), allow_pickle=False) as z:
            selected[name] = {key: z[key] for key in names}
            if name == 'daily' and 'all_raw_volume' in z.files: selected[name]['all_raw_volume'] = z['all_raw_volume']
    inherited = selected['inherited']
    permutation = [inherited['symbols'].tolist().index(s) for s in old['symbols']]
    inherited['eligible'] = inherited['eligible'][:, permutation]
    units = old['controls']['raw_units']
    current = data.core_bars(objects['raw-bars'], units, inactive=['WBA'])
    with future_modules():
        features = c.module('next_base_action_rules', FUTURE / 'features.py')
        actions = features.merge_actions(old['current_actions'], data.core_actions(objects['actions'], units), '2026-10-19')
        retained = c.module('next_base_retained', FUTURE / 'retained_sources.py')
        capture = c.load(BASE / 'prospective-contract.json')['current_source']['retained_raw_capture']
        historical = retained.receive_retained([capture], '2026-10-19T13:30:00Z', seed['prefix_end'], '2026-10-16')
        bars = {s: {} for s in units}
        from zoneinfo import ZoneInfo
        for page in historical['raw']:
            for symbol, values in page['bars'].items():
                for row in values:
                    day = c.clock(row['t']).astimezone(ZoneInfo('America/New_York')).date().isoformat()
                    assert day not in bars[symbol]; bars[symbol][day] = row
        for symbol, dates in old['controls']['bars'].items():
            for day, row in dates.items():
                if day in bars[symbol]: assert bars[symbol][day] == row
                bars[symbol][day] = row
        for (symbol, day), row in current.items():
            if day in bars[symbol]: assert bars[symbol][day] == row
            bars[symbol][day] = row
        bridge = c.module('next_base_original_daily_bridge', BASE / 'bridge.py')
        daily, triggers = bridge.extend_daily(selected['daily'], selected['raw_units'], inherited,
            dict(manifest=dict(reference_day='2026-10-20', prefix_end=seed['prefix_end']),
                 objects={'raw-bars': [dict(bars={s: list(v.values()) for s, v in bars.items()})]}, actions=actions))
    assert str(daily['dates'][-1]) == '2026-10-20'
    current_eligible = daily['eligible'][-1]
    marks = {s: control['symbols'][s]['raw_close'] for s in units}
    assert optional({s: float(daily['all_raw_close'][-1, j]) for j, s in enumerate(units)}) == marks
    ages = copy.deepcopy(old['count_ages'])
    for row in ages:
        if row['current_calendar_age'] is not None: row['current_calendar_age'] += 1
    fields = ['symbols', 'observation_month', 'feature_observation_end', 'primitive', 'flags', 'turnover',
              'formation_eligible', 'model_design', 'model_design_sha256', 'historical_model_provenance']
    value = {k: copy.deepcopy(old[k]) for k in fields}
    value.update(current_daily_eligible=current_eligible,
        eligible=np.asarray(old['formation_eligible'], dtype=bool) & current_eligible,
        current_split_jump_triggers=triggers[-1], count_ages=ages, raw_reference_marks=marks,
        current_actions=control['current_actions_by_group']['core'],
        consumed=[*historical['bindings'], *seed['files'].values(), c.binding(FUTURE / 'accepted-seed.json')],
        no_new_fit_labels_or_accounts=True, frozen_model_design_recomputed=False)
    return value


def h5_input(control, previous):
    old = previous['H5'][0]; carriers = old['controls']['carriers']
    symbols = old['symbols']; records = control['symbols']
    eligible = [carriers[s] is not None and records[carriers[s]]['supported'] is True for s in symbols]
    marks = {carrier: records[carrier]['raw_close'] for carrier in carriers.values() if carrier is not None}
    marks['SPY'] = records['SPY']['raw_close']
    forecast = c.load(c.T / 'inference/H5/output.json')
    selected_support = all(yes for yes, weight in zip(eligible, forecast['allocation']['weights'], strict=True) if weight > 0)
    relevant = set(marks)
    return dict(symbols=symbols, current_eligible=eligible, raw_reference_marks=marks,
        current_actions=[e for e in control['current_actions_by_group']['core'] if controls.event_symbols(e['terms']) & relevant],
        episode_carriers=copy.deepcopy(carriers),
        unsupported_current_unit_or_action=not selected_support, selected_support_received=selected_support,
        held_original_input=previous['H5'][1], held_original_forecast=c.binding(c.T / 'inference/H5/output.json'),
        historical_model_provenance=copy.deepcopy(old['historical_model_provenance']),
        original_observation_day='2026-10-19', original_application_day='2026-10-20',
        next_regular_observation='2026-10-23', next_regular_application='2026-10-26',
        no_current_feature_builder=True, no_new_scores_K_phase_or_funded_initialization=True, consumed=[])


def lstm_input(control, source, objects, previous):
    import numpy as np
    import pandas as pd
    import next_source_local as local
    from open_composer.research.features.price_hygiene import sanitize_price_matrices
    old = previous['LSTM'][0]; symbols = local.SYMBOLS
    projection = local.receive_projection(source['local_projection'])
    tail = local.sessions('2026-10-01', '2026-10-20')
    adjusted = {k: v for k, v in projection['rows'].items() if v['day'] in tail}
    if projection['missing']:
        overlap = local.sessions('2026-09-28', '2026-10-20')
        fetched = data.original('core', 'raw_rows')(objects['adjusted-tail'], symbols, overlap)
        for key, row in projection['rows'].items():
            if row['day'] in overlap:
                for field, name in [('o', 'open'), ('c', 'close')]:
                    assert np.isclose(fetched[(row['symbol'], row['day'])][field] / row[name], 1, rtol=1e-7, atol=1e-8)
        adjusted.update({s + ':' + day: dict(symbol=s, day=day, open=r['o'], close=r['c'])
                         for (s, day), r in fetched.items() if day in tail})
    assert set(adjusted) == {s + ':' + d for s in symbols for d in tail}
    accepted = old['original_accepted']
    closing = pd.read_parquet(c.checked(accepted['ETF-sanitized-close.parquet']))[symbols]
    opening = pd.read_parquet(c.checked(accepted['ETF-sanitized-open.parquet']))[symbols]
    prefix = len(closing)
    for day in tail:
        closing.loc[pd.Timestamp(day)] = [adjusted[s + ':' + day]['close'] / projection['adjustment_factors'][s]['multiplier'] for s in symbols]
        opening.loc[pd.Timestamp(day)] = [adjusted[s + ':' + day]['open'] / projection['adjustment_factors'][s]['multiplier'] for s in symbols]
    clean, clean_open, qa = sanitize_price_matrices(closing, opening)
    assert np.array_equal(clean.to_numpy(), closing.to_numpy(), equal_nan=True)
    assert np.array_equal(clean_open.to_numpy(), opening.to_numpy(), equal_nan=True)
    assert not any(str(v.first_session_after.date()) >= '2026-10-01' for v in qa.breaks)
    features = c.module('next_lstm_original_features', LSTM / 'prepare_features.py')
    x, vol, _ = features.features(clean)
    with np.load(c.checked(accepted['source-features.npz']), allow_pickle=False) as z:
        assert prefix == 2701 and np.array_equal(x[:prefix], z['features'], equal_nan=True)
        assert np.array_equal(vol[:prefix], z['vol'], equal_nan=True)
    dates = clean.index.strftime('%Y-%m-%d').to_numpy(dtype='U10')
    assert dates.tolist() == local.sessions('2016-01-04', '2026-10-20')
    first = int(np.flatnonzero(dates == '2026-01-02')[0]); lo = first - 63
    assert len(dates[first:]) == 201 and len(dates[lo:]) == 264
    valid = np.isfinite(x).all(-1) & np.isfinite(vol) & (vol > 1e-8)
    assert valid[lo:].all() and all(control['symbols'][s]['supported'] is True for s in symbols)
    arrays = dict(dates=dates[lo:], features=x[lo:], vol=vol[lo:], valid=valid[lo:], first_2026=np.array(63))
    sequence = write_npz('LSTM', 'sequence.npz', arrays)
    with np.load(c.checked(old['sequence']), allow_pickle=False) as prior:
        changes = {key: np.argwhere(arrays[key][:-1] != prior[key]).tolist()
                   for key in ['features', 'vol', 'valid']}
        assert arrays['dates'][:-1].tolist() == prior['dates'].tolist()
    if any(changes.values()):
        native, _ = ic.computing('LSTM')
        c.save(c.ROOT / 'input/LSTM/changed-prior-sequence.json', dict(sequence=sequence,
            previous=old['sequence'], complete_changed_indices=changes, input_admissible=False,
            source_or_forward_replay_permitted=False), capacity_rows={k: native['capacity'][k] for k in ['context', 'review']})
        raise ValueError('Changed accepted recurrent prefix requires saved-input reception')
    return dict(symbols=symbols, sequence=sequence, sequence_feature_sha256=digest(arrays['features']),
        sequence_vol_sha256=digest(arrays['vol']), sequence_valid_sha256=digest(arrays['valid']),
        original_accepted=accepted, original_prefix_rows=2701, original_prefix_bitexact=True,
        prior_263_sequence_bitexact=True, model_context=copy.deepcopy(old['model_context']),
        historical_model_provenance=copy.deepcopy(old['historical_model_provenance']),
        recurrent_burnin_sessions=63, annual_sessions=201, current_vol=vol[-1], current_features=x[-1],
        current_eligible=[True] * 10, raw_reference_marks={s: control['symbols'][s]['raw_close'] for s in symbols},
        current_actions=[e for e in control['current_actions_by_group']['core'] if controls.event_symbols(e['terms']) & set(symbols)],
        adjustment_factors=projection['adjustment_factors'],
        hygiene=qa.manifest(), raw_hygiene=control['hygiene'], new_labels=0, fits=0,
        consumed=[*accepted.values(), old['sequence'], source['local_projection']])


def etf_input(control, source, objects, previous):
    import numpy as np
    import pandas as pd
    from open_composer.research.features.price_hygiene import sanitize_price_matrices
    _, plan = c.receive_definition(); old = previous['ETF-input'][0]
    with np.load(c.checked(plan['ETF']['prior_panel']), allow_pickle=False) as z:
        prior = {key: z[key].tolist() for key in ['dates', 'symbols', 'opening', 'closing']}
    dates = data.expected_calendar(); symbols = plan['ETF']['symbols']
    audit = data.audit_ETF_prefix(objects['adjusted-history'], prior, dates)
    native, _ = ic.computing('ETF-input')
    auditrow = c.save(c.ROOT / 'input/ETF/full-adjusted-basis-audit.json', audit,
                     capacity_rows={k: native['capacity'][k] for k in ['context', 'review']})
    assert audit['accepted'], 'Full changed source retained; no scaling/tolerance/reGET/ranking rescue'
    rows = data.original('ETF', 'bar_rows')(objects['adjusted-history'], symbols, dates)
    raw = data.original('ETF', 'bar_rows')(objects['raw-reference'], symbols, ['2026-10-19', '2026-10-20'])
    opening, closing = [pd.DataFrame([[rows[(s, d)][key] for s in symbols] for d in dates],
                         index=pd.to_datetime(dates), columns=symbols, dtype=float) for key in ['o', 'c']]
    clean, clean_open, qa = sanitize_price_matrices(closing, opening)
    assert not qa.breaks and np.isfinite(clean.to_numpy()).all() and np.isfinite(clean_open.to_numpy()).all()
    assert np.array_equal(clean.to_numpy(), closing.to_numpy()) and np.array_equal(clean_open.to_numpy(), opening.to_numpy())
    assert all(control['symbols'][s]['supported'] is True for s in symbols)
    arrays = dict(dates=np.asarray(dates, dtype='U10'), symbols=np.asarray(symbols, dtype='U4'),
                  opening=clean_open.to_numpy(dtype=np.float64), closing=clean.to_numpy(dtype=np.float64))
    panel = write_npz('ETF-input', 'panel.npz', arrays)
    return dict(symbols=symbols, panel=panel, full_basis_audit=auditrow, prior_panel=plan['ETF']['prior_panel'],
        session_count=703, first_session=dates[0], last_session=dates[-1], hashes={k: digest(v) for k, v in arrays.items()},
        raw_reference_marks={s: raw[(s, '2026-10-20')]['c'] for s in symbols},
        raw_reference_bars={s: {d: raw[(s, d)] for d in ['2026-10-19', '2026-10-20']} for s in symbols},
        current_actions=data.ETF_actions(objects['actions']),
        hygiene=dict(defaults=True, trigger_count=0, missing_required_support=False),
        signal_units=old['signal_units'], order_units=old['order_units'],
        dividends_not_credited_twice=True, process_dates_are_not_exdate_coverage_or_PIT=True,
        new_fit_count=0, new_label_count=0, new_backtest_count=0, new_historical_funded_account_count=0,
        consumed=[plan['ETF']['prior_panel'], previous['ETF-input'][1], previous['ETF-input'][2], auditrow])


def produce(policy):
    assert policy in ['BASE', 'H5', 'LSTM', 'ETF-input']
    native, _ = ic.start(policy); ic.computing(policy); started = c.now()
    control = ic.receive_stage('CURRENT_CONTROLS')
    previous = controls.previous_inputs()
    group = 'ETF' if policy == 'ETF-input' else 'core'
    saved, objects, _ = controls.pages(group)
    if policy == 'H5': value = h5_input(control, previous)
    else: value = {'BASE': base_input, 'LSTM': lstm_input, 'ETF-input': etf_input}[policy](control, saved, objects, previous)
    consumed = value.pop('consumed') + saved['consumed']
    consumed += [r for item in previous.values() for r in item[1:]]
    consumed += [native['current_controls']['output'], native['current_controls']['completed'],
                 native['input'], native['source_inputs'][group]['completed']]
    unique = {r['path']: r for r in consumed}; assert all(unique[r['path']] == r for r in consumed)
    value.update(source=native['input'], source_complete=native['source_inputs'][group]['completed'],
        source_completed_at=c.load(native['source_inputs'][group]['completed']['path'])['completed_at'],
        source_plan=c.binding(c.ROOT / 'next-session-source-plan-M1.json'),
        consumed=list(unique.values()), computed_started_at=started, computed_completed_at=c.now())
    return ic.finish(policy, optional(value))


if __name__ == '__main__':
    assert len(sys.argv) == 2
    produce(sys.argv[1])
