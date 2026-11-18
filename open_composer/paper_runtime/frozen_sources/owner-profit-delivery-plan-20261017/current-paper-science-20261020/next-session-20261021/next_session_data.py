"""Dated data/adoption helpers; not a source launcher or an execution receiver.

Import is inert. Actual source/input callers must first receive their genuinely
dated native, authority, memory, capacity, context and exact code reviews. These
helpers grant none of those permissions and never import an old stage entry.
"""

from __future__ import annotations

import ast
import copy
from datetime import date, datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import runpy
import stat
import struct
from types import SimpleNamespace
from zoneinfo import ZoneInfo

REPO = Path('/root/codex-test/open-composer')
T = REPO / 'reports/research/program/owner-profit-delivery-plan-20261017/current-paper-science-20261020'
HERE = Path(__file__).resolve().parent
PLAN = HERE / 'next-session-source-plan-M1.json'
PLAN_SHA = '2c9c1f7f645f0268b1edc301ff97be19bf8fdbc3a878dfc9acc102511754265f'
ORIGINALS = {
    'core': (T / 'current_input.py', 'd94e56b36ac7dba33f92b12e8cf59e0bd34445e69ed1d1d37544c9060920c984'),
    'ETF': (T / 'later-session-20261020/session_etf_input.py', '4ac78dd06bdbb08f924ac826d6fec34c57a56094bc308118408926e4c8272a44'),
    'math': (T / 'current_math.py', '780711676f2624594baa3e7c25afbe368eba816cdf90bf3fa21058369d5a478e'),
}
BOUNDARY = {'2026-10-19': '2026-10-20', '2026-10-20': '2026-10-21'}
CALENDAR_SHA = '7d7d641df7ac1547a77e88a20782bf58791255aabbe73ac9dacc05164041dae1'


def clock(value):
    assert type(value) is str
    d = datetime.fromisoformat(value.replace('Z', '+00:00'))
    assert d.tzinfo is not None and d.utcoffset() is not None
    return d.astimezone(timezone.utc)


def plan():
    b = PLAN.read_bytes()
    assert hashlib.sha256(b).hexdigest() == PLAN_SHA
    d = json.loads(b)
    assert d['reference_day'] == '2026-10-20' and d['application_day'] == '2026-10-21'
    return d


def expected_calendar():
    path = REPO / 'open_composer/market_sessions.py'
    assert hashlib.sha256(path.read_bytes()).hexdigest() == CALENDAR_SHA
    code = runpy.run_path(str(path))
    return [d.isoformat() for d in code['us_equity_session_dates'](date(2024, 1, 2), date(2026, 10, 20))]


class _Boundary(ast.NodeTransformer):
    def visit_Constant(self, node):
        return ast.copy_location(ast.Constant(BOUNDARY[node.value]), node) if type(node.value) is str and node.value in BOUNDARY else node


def original(group, name, *, next_boundary=False):
    """Only pinned accepted pure function AST, with documented action dates."""
    path, expected = ORIGINALS[group]
    b = path.read_bytes()
    assert hashlib.sha256(b).hexdigest() == expected
    nodes = [n for n in ast.parse(b).body if isinstance(n, ast.FunctionDef) and n.name == name]
    assert len(nodes) == 1 and not nodes[0].decorator_list
    assert not next_boundary or name in ['action_pages', 'action_rows']
    if next_boundary:
        nodes = [_Boundary().visit(nodes[0])]
    namespace = dict(math=math, date=date, ZoneInfo=ZoneInfo, clock=clock,
                     c=SimpleNamespace(clock=clock), HERE=HERE,
                     load=lambda path: dict(raw_symbols=plan()['core']['raw_symbols']))
    if group == 'ETF' and name != 'finite':
        namespace['finite'] = original('ETF', 'finite')
    exec(compile(ast.fix_missing_locations(ast.Module(body=nodes, type_ignores=[])), str(path), 'exec'), namespace)
    return namespace[name]


def core_bars(objects, symbols, *, inactive=()):
    assert set(symbols) <= set(plan()['core']['raw_symbols'])
    return original('core', 'raw_rows')(objects, symbols, ['2026-10-19', '2026-10-20'], inactive)


def core_actions(objects, symbols):
    assert set(symbols) <= set(plan()['core']['raw_symbols'])
    return original('core', 'action_pages', next_boundary=True)(objects, symbols)


def ETF_actions(objects):
    return original('ETF', 'action_rows', next_boundary=True)(objects, plan()['ETF']['symbols'])


def _bits(value):
    assert type(value) in [int, float] and math.isfinite(value) and value > 0
    return struct.pack('>d', value)


def audit_ETF_prefix(objects, previous_panel, expected_dates):
    """Return COMPLETE changes/issues. Caller must retain report before refusal.

    No panel decoding/writing, source calls, scaling or tolerance is hidden here.
    A rejected report is never an admissible input or a target/cash decision.
    """
    symbols = plan()['ETF']['symbols']
    assert type(expected_dates) is list and len(expected_dates) == 703
    assert expected_dates == expected_calendar()
    assert expected_dates[0] == '2024-01-02' and expected_dates[-2:] == ['2026-10-19', '2026-10-20']
    assert set(previous_panel) == {'dates', 'symbols', 'opening', 'closing'}
    assert previous_panel['dates'] == expected_dates[:-1] and previous_panel['symbols'] == symbols
    assert len(previous_panel['opening']) == len(previous_panel['closing']) == 702
    assert all(len(row) == 23 for field in ['opening', 'closing'] for row in previous_panel[field])
    finite = original('ETF', 'finite')
    allowed_dates, allowed_symbols = set(expected_dates), set(symbols)
    rows, issues = {}, []
    for page_index, page in enumerate(objects):
        if type(page) is not dict or type(page.get('bars')) is not dict:
            issues.append(dict(page=page_index, reason='malformed_bars_page'))
            continue
        for symbol, values in page['bars'].items():
            if symbol not in allowed_symbols or type(values) is not list:
                issues.append(dict(page=page_index, symbol=symbol, reason='foreign_symbol_or_malformed_rows'))
                continue
            for row_index, raw in enumerate(values):
                where = dict(page=page_index, symbol=symbol, row=row_index)
                try:
                    assert type(raw) is dict
                    stamp = clock(raw['t']).astimezone(ZoneInfo('America/New_York'))
                    assert (stamp.hour, stamp.minute, stamp.second, stamp.microsecond) == (0, 0, 0, 0)
                    day = stamp.date().isoformat()
                    assert day in allowed_dates
                    for field in ['o', 'h', 'l', 'c']:
                        finite(raw[field], positive=True)
                    finite(raw['v']); finite(raw['n'], integer=True)
                    assert raw['l'] <= min(raw['o'], raw['c']) <= max(raw['o'], raw['c']) <= raw['h']
                    assert raw['v'] > 0 or raw['n'] > 0
                    key = (symbol, day)
                    if key in rows:
                        issues.append(dict(**where, day=day, reason='duplicate_or_conflicting_bar'))
                    else:
                        rows[key] = raw
                except (AssertionError, KeyError, TypeError, ValueError, OverflowError):
                    # Exact rejected raw values stay in the bound source page;
                    # do not duplicate invalid/NaN source bodies into JSON.
                    issues.append(dict(**where, reason='invalid_daily_bar'))
    changes, missing = [], []
    for i, day in enumerate(expected_dates):
        for j, symbol in enumerate(symbols):
            raw = rows.get((symbol, day))
            if raw is None:
                missing.append([i, j])
            if i == 702:
                continue
            for field_index, (old_field, new_field) in enumerate([('opening', 'o'), ('closing', 'c')]):
                old = previous_panel[old_field][i][j]
                old_bits = _bits(old)
                new = None if raw is None else raw[new_field]
                if new is None or old_bits != _bits(new):
                    # Full compact inventory: flat(cell = day,symbol,O/C),
                    # original value, received value (None means missing).
                    changes.append([(i * 23 + j) * 2 + field_index, old, new])
    accepted = not issues and not missing and not changes
    if accepted:
        strict_rows = original('ETF', 'bar_rows')(objects, symbols, expected_dates)
        assert strict_rows == rows
    return dict(accepted=accepted, ordered_dates=expected_dates, symbols=symbols,
                prior_cells_compared=32292, changes=changes, missing=missing, source_issues=issues,
                changed_cells=len(changes), tolerance_used=False, scaling_used=False,
                complete_change_inventory=True, panel_or_signal_admissible=accepted)


def pinned_bytes(frozen):
    """Receive one actual prebound inode, allowing later atomic path replacement.

    Call only inside the admitted source stage. This is a memory read, never a
    durable copy or a claim that today's pathname still represents old bytes.
    """
    path = Path(frozen['path'])
    assert path.is_absolute() and path.resolve() == path and not path.is_symlink()
    assert str(path) in [row['path'] for row in plan()['core']['local_file_inventory']], 'Foreign local source file'
    assert set(['device', 'inode', 'bytes', 'mtime_ns', 'sha256']) <= set(frozen)
    started = datetime.now(timezone.utc).isoformat()
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        before = os.fstat(fd)
        assert stat.S_ISREG(before.st_mode) and before.st_nlink == 1
        def identity(s):
            return (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns)
        assert identity(before) == tuple(frozen[k] for k in ['device', 'inode', 'bytes', 'mtime_ns'])
        with os.fdopen(fd, 'rb', closefd=False) as stream:
            data = stream.read()
            assert len(data) == frozen['bytes']
            digest = hashlib.sha256(data).hexdigest()
            assert digest == frozen['sha256']
            stream.seek(0)
            assert hashlib.sha256(stream.read()).hexdigest() == digest
        after = os.fstat(fd)
        assert identity(before) == identity(after), 'Received inode mutated in place'
        try:
            current = path.lstat()
            replaced = (current.st_dev, current.st_ino) != (before.st_dev, before.st_ino)
        except FileNotFoundError:
            replaced = True
    finally:
        os.close(fd)
    return data, dict(origin=copy.deepcopy(frozen), read_started_at=started,
                      read_completed_at=datetime.now(timezone.utc).isoformat(),
                      sha256=digest, pinned_inode_stable=True, pathname_replaced_after_open=replaced,
                      future_publication_requires_live_path_hash=False)


def BASE_adoption(old_input, old_forecast, current_input):
    """Frozen design/scores; only the original admissibility allocator can vary."""
    assert old_forecast['policy'] == 'BASE'
    assert old_forecast['reference_day'] == '2026-10-19' and old_forecast['application_day'] == '2026-10-20'
    assert current_input['reference_day'] == '2026-10-20' and current_input['application_day'] == '2026-10-21'
    assert old_forecast['symbols'] == old_input['symbols']
    for key in ['symbols', 'primitive', 'flags', 'turnover', 'formation_eligible', 'historical_model_provenance']:
        assert current_input[key] == old_input[key], 'Frozen BASE design/provenance changed'
    for rows in [old_input['model_design'], current_input['model_design']]:
        assert len(rows) == 28 and all(len(row) == 14 for row in rows)
    assert all(struct.pack('>d', a) == struct.pack('>d', b)
               for arow, brow in zip(old_input['model_design'], current_input['model_design'], strict=True)
               for a, b in zip(arow, brow, strict=True))
    daily, formation = current_input['current_daily_eligible'], old_input['formation_eligible']
    assert len(daily) == len(formation) == 28 and all(type(v) is bool for v in daily + formation)
    eligible = [a and b for a, b in zip(formation, daily, strict=True)]
    assert current_input['eligible'] == eligible
    allocation = original('math', 'base_allocation')(old_forecast['scores'], eligible, old_forecast['symbols'])
    return dict(policy='BASE', scores=copy.deepcopy(old_forecast['scores']), allocation=allocation,
                new_prediction=False, original_computed_started_at=old_forecast['computed_started_at'],
                original_computed_completed_at=old_forecast['computed_completed_at'],
                reference_day='2026-10-20', application_day='2026-10-21',
                raw_reference_marks=copy.deepcopy(current_input['raw_reference_marks']),
                current_actions=copy.deepcopy(current_input['current_actions']),
                current_eligible=eligible, original_definition_preserved=True)


def H5_adoption(old_forecast, current_controls):
    """Hold the exact original scientific episode; never initialize a funded book."""
    import sys
    assert sys.version_info[:2] == (3, 11), 'Original H5 arithmetic runtime required'
    assert old_forecast['policy'] == 'H5'
    assert old_forecast['reference_day'] == '2026-10-19' and old_forecast['application_day'] == '2026-10-20'
    assert current_controls['reference_day'] == '2026-10-20' and current_controls['application_day'] == '2026-10-21'
    symbols = old_forecast['symbols']
    assert current_controls['symbols'] == symbols and len(symbols) == 32
    eligible = current_controls['current_eligible']
    assert len(eligible) == 32 and all(type(v) is bool for v in eligible)
    allocation = old_forecast['allocation']
    assert len(allocation['weights']) == 32 and 0 <= allocation['K'] <= 5
    for symbol, weight, yes in zip(symbols, allocation['weights'], eligible, strict=True):
        if weight > 0:
            assert yes, 'Held H5 selection lost required current support'
            mark = current_controls['raw_reference_marks'][symbol]
            assert type(mark) in [int, float] and math.isfinite(mark) and mark > 0
    assert current_controls['unsupported_current_unit_or_action'] is False
    return dict(policy='H5', scores=copy.deepcopy(old_forecast['scores']), allocation=copy.deepcopy(allocation),
                new_prediction=False, original_signal_observation='2026-10-19',
                original_signal_application='2026-10-20', reference_day='2026-10-20',application_day='2026-10-21',
                phase_anchor='2024-01-02',next_regular_observation='2026-10-23',next_regular_application='2026-10-26',
                original_computed_started_at=old_forecast['computed_started_at'],
                original_computed_completed_at=old_forecast['computed_completed_at'],
                raw_reference_marks=copy.deepcopy(current_controls['raw_reference_marks']),
                current_actions=copy.deepcopy(current_controls['current_actions']),
                current_eligible=eligible, funded_initialization_granted=False)
