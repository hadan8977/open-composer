"""Prefix expressions over dated fields. Window lengths count exchange sessions."""

import json
import math

import polars as pl

# The registry is the boundary between score inputs and future execution outcomes.
FIELDS = set(
    """
sector return_1 return_5 return_21 return_63 return_126 return_252 volatility_21 adr_pct_20 gap
volume_ratio_5 volume_ratio_20 median_dollar_volume_20 days_since_earnings earnings_gap
earnings_volume_ratio insider_purchase_count_30d insider_purchase_shares_30d
insider_purchase_reports_30d short_interest_shares days_to_cover off_exchange_short_ratio
shares_outstanding raw_close raw_volume dollar_volume
sales_growth_yoy operating_margin_change_yoy operating_margin iv_current
iv_week_ago iv_month_ago revenue operating_income
""".split()
)
WINDOWS = {"lag", "mean", "std", "min", "max", "sum"}


def key(expr):
    return json.dumps(expr, separators=(",", ":"))


def walk(expr):
    yield expr
    if isinstance(expr, list):
        for child in expr[1:]:
            yield from walk(child)


def point_op(op, args):
    a = args[0]
    if op == "log":
        return pl.when(a > 0).then(a.log())
    if op == "neg":
        return -a
    if op == "abs":
        return abs(a)
    b = args[1]
    if op == "ratio":
        return pl.when(b != 0).then(a / b)
    if op == "diff":
        return a - b
    if op == "add":
        return a + b
    if op == "mul":
        return a * b
    if op == "gt":
        return a > b
    if op == "mask":
        return pl.when(a).then(b)
    if op == "fill":
        return a.fill_null(b)
    raise ValueError(f"Unknown operator {op}")


def compile_score(expr, fields, windows):
    if isinstance(expr, str):
        if expr not in fields:
            raise ValueError(f"Unregistered score field {expr}")
        return pl.col(expr)
    if isinstance(expr, (int, float)) and math.isfinite(expr):
        return pl.lit(expr)
    op, *children = expr
    if op in WINDOWS:
        return pl.col(windows[key(expr)])
    args = [compile_score(child, fields, windows) for child in children]
    a = args[0]
    if op == "rank":
        result = a.rank().over("ix") / a.count().over("ix")
    elif op == "z":
        result = ((a - a.mean().over("ix")) / a.std().over("ix")).fill_nan(None)
    elif op == "neutral":
        result = pl.when(pl.col("sector").is_not_null()).then(a - a.mean().over("ix", "sector"))
    else:
        result = point_op(op, args)
    return result


def daily_sql(expr, fields, names):
    """DuckDB analytic stages. A session gap invalidates a full trailing window."""
    if isinstance(expr, str):
        if expr not in fields:
            raise ValueError(f"Unregistered daily input {expr}")
        return '"' + expr + '"'
    if isinstance(expr, (float, int)) and math.isfinite(expr):
        return str(expr)
    op, *children = expr
    if key(expr) in names:
        return names[key(expr)]
    a = daily_sql(children[0], fields, names)
    if op in WINDOWS:
        n = children[1]
        if type(n) is not int or n < 1:
            raise ValueError("Session window must be a positive integer")
        frame = (
            f"partition by security_id order by ix range between {n - 1} preceding and current row"
        )
        if op == "lag":
            return f"first({a}) over (partition by security_id order by ix range between {n} preceding and {n} preceding)"
        fn = {"mean": "avg", "std": "stddev_samp"}.get(op, op)
        return f"case when count({a}) over ({frame})={n} then {fn}({a}) over ({frame}) end"
    if op == "neg":
        return f"(-{a})"
    if op == "abs":
        return f"abs({a})"
    b = daily_sql(children[1], fields, names)
    if op == "ratio":
        return f"({a}/nullif({b},0))"
    if op == "mask":
        return f"(case when {a} then {b} end)"
    symbol = {"add": "+", "mul": "*", "diff": "-", "gt": ">"}[op]
    return f"({a}{symbol}{b})"


def window_plan(expressions, fields):
    """Group same-depth windows to share one security/date sort."""
    pending = {
        key(n): n
        for expr in expressions
        for n in walk(expr)
        if isinstance(n, list) and n[0] in WINDOWS
    }
    names, stages = {}, []
    while pending:
        ready = {
            k: n
            for k, n in pending.items()
            if all(key(child) not in pending for child in walk(n[1]) if isinstance(child, list))
        }
        stage = {}
        for k, n in ready.items():
            name = f"window_{len(names)}"
            stage[name] = daily_sql(n, fields, names)
            names[k] = name
            del pending[k]
        stages.append(stage)
    return names, stages
