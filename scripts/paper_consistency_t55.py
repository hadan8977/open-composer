"""T-20261004-55: paper vs research consistency after the 2026-10-02 SIP repair.

Three read-only analyses; every output goes under ``--out-dir`` (default
``reports/research/program/paper-consistency-2026-10-04/``):

``s3-flip``       S3 base book and overlay at the 2026-08-31 month end on the
                  pre-repair and the current price archive (research engine),
                  plus the paper adapter's own startup replay as of the
                  2026-09-17 close on the pre-repair archive.
``s3-fragility``  how often a small price revision, or an i.i.d. 5 bp close
                  perturbation, changes S3's month-end base book, and what it
                  does to return and Sharpe.
``c2-regen``      C2 (EOM reversal + sector front-run blend) returns rebuilt on
                  the current archive with the screen lane's frozen simulator,
                  written to a NEW parquet; the old returns.parquet is only read.

The research engine is imported unedited; only its price-loading globals
(``DAILY_GLOB``, ``WARMUP_START``, ``HOLD_END``) are pointed at an archive for
the duration of one load. Archives are never written.
"""

from __future__ import annotations

import argparse
import json
import sys
from contextlib import contextmanager
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import run_h20260918_05_recent_menu as base  # noqa: E402
import run_h20260922_05_salvage as salvage  # noqa: E402

PRE_ARCHIVE = "data/live/backup-sip-daily-preswap-20261002"
CUR_ARCHIVE = "data/sip/daily"
DEFAULT_OUT_DIR = "reports/research/program/paper-consistency-2026-10-04"
PANEL_START = "2015-01-02"
PANEL_END = "2026-09-17"  # the frozen research panel end (base.HOLD_END)

S3_MENU = base.MENUS["A4_levered"]
S3_SYMBOLS = sorted({*S3_MENU, base.CASH, base.RF, salvage.DIP_ASSET})
S3_TARGET = salvage.S3_FROZEN_TARGET
S3_BOOST_TARGET = 0.60
S3_BOOST_HOLD = 10
SIGNAL_DATE = pd.Timestamp("2026-08-31")
ADAPTER_ASOF = pd.Timestamp("2026-09-17")


@contextmanager
def archive_globals(daily_dir: str, start: str, end: str):
    """Point the research engine's loader at one archive for one load."""
    saved = (base.DAILY_GLOB, base.WARMUP_START, base.HOLD_END)
    base.DAILY_GLOB = f"{(ROOT / daily_dir).as_posix()}/*/*.parquet"
    base.WARMUP_START, base.HOLD_END = start, end
    try:
        yield
    finally:
        base.DAILY_GLOB, base.WARMUP_START, base.HOLD_END = saved


def load_panel(daily_dir: str, symbols: list[str], start=PANEL_START, end=PANEL_END):
    with archive_globals(daily_dir, start, end):
        return base.load_panel(symbols)


def s3_book(
    close: pd.DataFrame,
    open_: pd.DataFrame,
    *,
    policy: str = "renormalize_survivors",
    cost_bps: float = base.COST_BPS_PRIMARY,
    overlay: bool = True,
) -> dict:
    """The S3 sleeve as the card defines it: base book, overlay scale, net returns.

    ``policy`` is the unfilled-slot rule: ``renormalize_survivors`` is the
    shipped one (the engine's own ``sleeve_weights``); ``cash`` leaves a dropped
    pick's slot in SHY (the card's defensive variant, comparison only).
    """
    leg_open, leg_close = salvage.legs(close, open_)
    weights, signal_dates = salvage.sleeve_weights(close, "s3")
    if policy == "cash":
        weights, signal_dates = cash_policy_weights(close)
    elif policy != "renormalize_survivors":
        raise ValueError(policy)
    gross, _ = salvage.simulate(weights, leg_open, leg_close, np.ones(len(close.index)), 0.0)
    if overlay:
        boost = salvage.boost_window(salvage.dip_signal(close), S3_BOOST_HOLD)
        scale = salvage.vol_scale(
            close.index, signal_dates, gross, S3_TARGET, boost, S3_BOOST_TARGET
        )
    else:
        scale = np.ones(len(close.index))
    ret, turn = salvage.simulate(weights, leg_open, leg_close, scale, cost_bps)
    return {
        "weights": weights,
        "signal_dates": signal_dates,
        "scale": pd.Series(scale, index=close.index),
        "ret": ret,
        "turn": turn,
    }


def cash_policy_weights(close: pd.DataFrame) -> tuple[pd.DataFrame, list[pd.Timestamp]]:
    """Same picks and absolute filter as ``salvage.sleeve_weights('s3')``, but a
    dropped pick's 1/top_n slot stays in SHY instead of going to the survivor."""
    cfg = salvage.SLEEVES["s3"]
    menu = [s for s in base.MENUS[cfg["menu"]] if s in close.columns]
    cols = sorted(set(menu + [base.CASH]))
    score = base.momentum_score(close, cfg["lookback"])
    cash_score = score[base.CASH]
    flags = base.rebalance_flags(close.index, cfg["rebal"])
    signal_dates = list(close.index[flags])
    pos = {d: i for i, d in enumerate(close.index)}
    change: dict[int, dict[str, float]] = {}
    for d in signal_dates:
        i = pos[d]
        if i + 1 >= len(close.index):
            continue
        row = score.loc[d, menu].dropna()
        book: dict[str, float] = {base.CASH: 1.0}
        if not row.empty:
            chosen = list(row.sort_values(ascending=False).index[: cfg["top_n"]])
            cs = cash_score.loc[d]
            if pd.notna(cs):
                chosen = [s for s in chosen if row[s] > cs]
            if chosen:
                each = 1.0 / cfg["top_n"]
                book = {s: each for s in chosen}
                rest = 1.0 - each * len(chosen)
                if rest > 1e-9:
                    book[base.CASH] = rest
        change[i + 1] = book
    rows, current = [], {base.CASH: 1.0}
    for i in range(len(close.index)):
        current = change.get(i, current)
        rows.append(dict(current))
    frame = pd.DataFrame(rows, index=close.index).reindex(columns=cols).fillna(0.0)
    return frame, signal_dates


def month_end_books(weights: pd.DataFrame, signal_dates: list[pd.Timestamp]) -> pd.DataFrame:
    """Base book live from the open after each month-end signal close."""
    idx = weights.index
    pos = {d: i for i, d in enumerate(idx)}
    rows = {}
    for d in signal_dates:
        i = pos[d] + 1
        if i < len(idx):
            rows[d] = weights.iloc[i]
    return pd.DataFrame(rows).T


def book_label(row: pd.Series) -> str:
    held = {k: round(float(v), 4) for k, v in row.items() if v > 1e-9}
    return json.dumps(dict(sorted(held.items())))


def s3_metrics(ret: pd.Series, turn: pd.Series, rf: pd.Series, start: str, end: str) -> dict:
    mask = (ret.index >= start) & (ret.index <= end)
    m = base.metrics(ret.loc[mask], rf, turn.loc[mask])
    return {"days": m.days, "cagr": m.cagr, "sharpe": m.sharpe, "max_dd": m.max_dd}


# ---------------------------------------------------------------------------
# s3-flip


def score_table(close: pd.DataFrame, when: pd.Timestamp) -> dict:
    score = base.momentum_score(close, "63")
    row = score.loc[when]
    cash = float(row[base.CASH])
    pos = close.index.get_loc(when)
    table = {}
    for s in [*S3_MENU, base.CASH, salvage.DIP_ASSET]:
        if s not in close.columns:
            continue
        table[s] = {
            "close_signal": float(close.loc[when, s]),
            "close_t_minus_63": float(close.iloc[pos - 63][s]),
            "score_63": float(row[s]),
            "margin_vs_shy": float(row[s] - cash),
        }
    ranked = sorted(
        ((s, table[s]["score_63"]) for s in S3_MENU if np.isfinite(table[s]["score_63"])),
        key=lambda x: -x[1],
    )
    top2 = [s for s, _ in ranked[:2]]
    survivors = [s for s in top2 if table[s]["score_63"] > cash]
    return {
        "rank": [s for s, _ in ranked],
        "top2": top2,
        "survivors": survivors,
        "dropped_by_filter": [s for s in top2 if s not in survivors],
        "third_minus_second": (ranked[2][1] - ranked[1][1]) if len(ranked) > 2 else None,
        "table": table,
    }


def price_diffs(pre: pd.DataFrame, cur: pd.DataFrame, lo: pd.Timestamp, hi: pd.Timestamp) -> dict:
    cols = [c for c in pre.columns if c in cur.columns]
    only_pre = sorted(
        d.date().isoformat() for d in pre.index.difference(cur.index) if lo <= d <= hi
    )
    only_cur = sorted(
        d.date().isoformat() for d in cur.index.difference(pre.index) if lo <= d <= hi
    )
    a = pre.loc[lo:hi, cols]
    b = cur.loc[lo:hi, cols].reindex(a.index)
    rel = (b / a - 1.0).abs()
    items = []
    for s in cols:
        bad = rel[s][rel[s] > 1e-9]
        for d in bad.index:
            items.append(
                {
                    "symbol": s,
                    "date": d.date().isoformat(),
                    "pre": float(a.loc[d, s]),
                    "cur": float(b.loc[d, s]),
                    "rel_diff": float(b.loc[d, s] / a.loc[d, s] - 1.0),
                }
            )
    items.sort(key=lambda r: -abs(r["rel_diff"]))
    return {
        "window": [lo.date().isoformat(), hi.date().isoformat()],
        "dates_only_in_pre": only_pre,
        "dates_only_in_cur": only_cur,
        "n_differing_closes": len(items),
        "max_abs_rel_diff": items[0]["rel_diff"] if items else 0.0,
        "by_symbol": {s: sum(1 for r in items if r["symbol"] == s) for s in cols},
        "largest": items[:25],
    }


def adapter_replay(daily_dir: str, asof: pd.Timestamp) -> dict:
    """The paper adapter's own startup path, on ``daily_dir`` as of ``asof``'s close."""
    import tempfile

    from open_composer.adapters.execution import rotation_target_weights as rtw
    from open_composer.models.strategy_spec import load_strategy_spec

    spec = load_strategy_spec(
        ROOT / "strategy_specs/drafts/us_etf_levered_rotation_63_top2_monthly.yaml"
    )
    cfg = spec.portfolio.etf_rotation
    symbols = sorted({*cfg.menu, cfg.cash_symbol, cfg.vol_target.dip_boost.signal_symbol})
    # load_price_panel reads <root>/data/sip/daily; give it a root whose daily dir
    # is a symlink to the requested archive (read-only use; nothing is written to it).
    with tempfile.TemporaryDirectory(prefix="t55root-") as tmp:
        daily = Path(tmp) / "data" / "sip"
        daily.mkdir(parents=True)
        (daily / "daily").symlink_to((ROOT / daily_dir).resolve(), target_is_directory=True)
        years = list(range(2015, asof.year + 1))
        panel = rtw.load_price_panel(Path(tmp), symbols, years)
    panel = panel.loc[panel["trade_date"] <= asof.date()]
    series = {s: rtw._symbol_series(panel, s) for s in symbols}
    sessions = sorted(
        set(panel.loc[panel["symbol"].isin(sorted({*cfg.menu, cfg.cash_symbol})), "trade_date"])
    )
    weights, signal_sessions = rtw.replay_books(
        series,
        sessions,
        menu=cfg.menu,
        cash_symbol=cfg.cash_symbol,
        lookbacks=cfg.lookbacks,
        top_n=cfg.top_n,
        rebalance=cfg.rebalance,
        absolute_momentum_filter=cfg.absolute_momentum_filter,
        min_history_sessions=cfg.min_history_sessions,
        unfilled_slot_policy=cfg.unfilled_slot_policy,
    )
    last = weights.iloc[-1]
    decision = rtw._decide_overlay(
        panel,
        series,
        menu=cfg.menu,
        cash_symbol=cfg.cash_symbol,
        latest_session=asof.date(),
        lookbacks=cfg.lookbacks,
        top_n=cfg.top_n,
        rebalance=cfg.rebalance,
        absolute_momentum_filter=cfg.absolute_momentum_filter,
        min_history_sessions=cfg.min_history_sessions,
        unfilled_slot_policy=cfg.unfilled_slot_policy,
        vol_cfg=cfg.vol_target,
    )
    aug = pd.Timestamp("2026-09-01").date()
    book_aug = weights.loc[aug] if aug in weights.index else None
    return {
        "archive": daily_dir,
        "asof_close": asof.date().isoformat(),
        "last_signal_session": signal_sessions[-1].isoformat(),
        "base_book_now": {k: round(float(v), 6) for k, v in last.items() if v > 1e-9},
        "base_book_after_08_31": None
        if book_aug is None
        else {k: round(float(v), 6) for k, v in book_aug.items() if v > 1e-9},
        "overlay": {
            "multiplier": decision.multiplier,
            "target_annual_vol": decision.target_annual_vol,
            "realized_annual_vol": decision.realized_annual_vol,
            "boost_active": decision.boost_active,
            "decision_session": str(decision.decision_session),
        },
    }


def run_s3_flip(out_dir: Path) -> dict:
    pre_c, pre_o = load_panel(PRE_ARCHIVE, S3_SYMBOLS)
    cur_c, cur_o = load_panel(CUR_ARCHIVE, S3_SYMBOLS)
    result: dict = {"signal_date": SIGNAL_DATE.date().isoformat(), "panel_end": PANEL_END}
    books: dict[str, dict] = {}
    for name, (close, open_) in {"pre_repair": (pre_c, pre_o), "current": (cur_c, cur_o)}.items():
        run = s3_book(close, open_)
        weights = run["weights"]
        after = weights.iloc[weights.index.get_loc(SIGNAL_DATE) + 1]
        sep = close.index[(close.index >= "2026-09-01") & (close.index <= PANEL_END)]
        books[name] = {
            "scores": score_table(close, SIGNAL_DATE),
            "base_book_from_09_01": json.loads(book_label(after)),
            "overlay_scale_09_01_to_09_17": {
                d.date().isoformat(): round(float(run["scale"].loc[d]), 4) for d in sep
            },
            "weights_09_17": json.loads(book_label(weights.loc[sep[-1]])),
        }
    result["research_engine"] = books
    pos = pre_c.index.get_loc(SIGNAL_DATE)
    result["price_diffs_lookback"] = price_diffs(pre_c, cur_c, pre_c.index[pos - 63], SIGNAL_DATE)
    result["price_diffs_whole_s3_panel"] = {
        "n_pre_dates": len(pre_c),
        "n_cur_dates": len(cur_c),
        **{
            k: v
            for k, v in price_diffs(pre_c, cur_c, pre_c.index[0], pre_c.index[-1]).items()
            if k
            in (
                "n_differing_closes",
                "max_abs_rel_diff",
                "by_symbol",
                "dates_only_in_pre",
                "dates_only_in_cur",
            )
        },
    }
    result["adapter_replay_pre_repair"] = adapter_replay(PRE_ARCHIVE, ADAPTER_ASOF)
    result["adapter_replay_current"] = adapter_replay(CUR_ARCHIVE, ADAPTER_ASOF)
    (out_dir / "s3_flip.json").write_text(json.dumps(result, indent=2, default=float) + "\n")
    return result


# ---------------------------------------------------------------------------
# s3-fragility

FULL_SPAN = ("2016-01-04", "2026-09-16")
ANCHOR_SPAN = ("2024-01-08", "2026-09-16")


def _book_array(weights: pd.DataFrame, signal_dates: list[pd.Timestamp]) -> tuple[list, np.ndarray]:
    """Base books live after each month-end signal that has a next session."""
    idx = weights.index
    pos = {d: i for i, d in enumerate(idx)}
    keep = [d for d in signal_dates if pos[d] + 1 < len(idx) and d >= pd.Timestamp("2016-01-01")]
    arr = np.stack([weights.iloc[pos[d] + 1].to_numpy(dtype=float) for d in keep])
    return keep, arr


def decision_margins(close: pd.DataFrame, dates: list[pd.Timestamp]) -> pd.DataFrame:
    """Score-unit distance of each month-end decision from its nearest boundary:
    the 2nd/3rd rank gap and each pick's gap to SHY (the absolute filter)."""
    score = base.momentum_score(close, "63")
    menu = [s for s in S3_MENU if s in close.columns]
    rows = []
    for d in dates:
        r = score.loc[d, menu].dropna().sort_values(ascending=False)
        cash = score.loc[d, base.CASH]
        gap23 = float(r.iloc[1] - r.iloc[2]) if len(r) > 2 else np.nan
        gaps = [abs(float(r.iloc[i] - cash)) for i in range(min(2, len(r)))]
        rows.append(
            {"date": d, "gap_rank2_rank3": gap23, "gap_pick_vs_shy": min(gaps) if gaps else np.nan}
        )
    out = pd.DataFrame(rows).set_index("date")
    out["margin"] = out.min(axis=1)
    return out


def _summ(x: np.ndarray) -> dict:
    x = np.asarray(x, dtype=float)
    return {
        "mean": float(np.mean(x)),
        "std": float(np.std(x, ddof=1)) if len(x) > 1 else float("nan"),
        "min": float(np.min(x)),
        "p05": float(np.percentile(x, 5)),
        "median": float(np.median(x)),
        "p95": float(np.percentile(x, 95)),
        "max": float(np.max(x)),
    }


def perturb_close(close: pd.DataFrame, bp: float, seed: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    noise = rng.normal(0.0, bp / 10_000.0, size=close.shape)
    return close * (1.0 + noise)


def fragility_for_policy(
    close: pd.DataFrame, open_: pd.DataFrame, rf: pd.Series, policy: str, seeds: int, bp: float
) -> dict:
    ref = s3_book(close, open_, policy=policy)
    dates, ref_books = _book_array(ref["weights"], ref["signal_dates"])
    margins = decision_margins(close, dates)
    ref_metrics = {
        "anchor": s3_metrics(ref["ret"], ref["turn"], rf, *ANCHOR_SPAN),
        "full": s3_metrics(ref["ret"], ref["turn"], rf, *FULL_SPAN),
    }
    changed = np.zeros(len(dates))
    anchor_cagr, anchor_sharpe, full_cagr, full_sharpe = [], [], [], []
    for k in range(seeds):
        run = s3_book(perturb_close(close, bp, 20261004 + k), open_, policy=policy)
        d2, books = _book_array(run["weights"], run["signal_dates"])
        assert d2 == dates
        changed += np.abs(books - ref_books).max(axis=1) > 1e-9
        a = s3_metrics(run["ret"], run["turn"], rf, *ANCHOR_SPAN)
        f = s3_metrics(run["ret"], run["turn"], rf, *FULL_SPAN)
        anchor_cagr.append(a["cagr"])
        anchor_sharpe.append(a["sharpe"])
        full_cagr.append(f["cagr"])
        full_sharpe.append(f["sharpe"])
    share = changed / seeds
    unstable = share >= 0.10
    per_date = pd.DataFrame({"flip_share": share, "margin": margins["margin"]}, index=dates)
    return {
        "policy": policy,
        "n_month_ends": len(dates),
        "seeds": seeds,
        "bp": bp,
        "month_ends_changing_in_ge_10pct_of_seeds": int(unstable.sum()),
        "share_month_ends_changing_in_ge_10pct_of_seeds": float(unstable.mean()),
        "share_month_ends_never_changing": float((share == 0).mean()),
        "mean_flip_share_per_month_end": float(share.mean()),
        "month_ends_with_decision_margin_lt_10bp": int((margins["margin"] < 0.001).sum()),
        "month_ends_with_decision_margin_lt_25bp": int((margins["margin"] < 0.0025).sum()),
        "month_ends_with_decision_margin_lt_50bp": int((margins["margin"] < 0.005).sum()),
        "unstable_month_ends": [
            {
                "date": d.date().isoformat(),
                "flip_share": float(per_date.loc[d, "flip_share"]),
                "margin_score_units": float(per_date.loc[d, "margin"]),
            }
            for d in per_date.index[unstable]
        ],
        "unperturbed": ref_metrics,
        "perturbed": {
            "anchor_cagr": _summ(anchor_cagr),
            "anchor_sharpe": _summ(anchor_sharpe),
            "full_cagr": _summ(full_cagr),
            "full_sharpe": _summ(full_sharpe),
        },
    }


def archive_comparison(pre: tuple, cur: tuple, rf: pd.Series, policy: str) -> dict:
    run_pre = s3_book(*pre, policy=policy)
    run_cur = s3_book(*cur, policy=policy)
    dates, b_pre = _book_array(run_pre["weights"], run_pre["signal_dates"])
    d_cur, b_cur = _book_array(run_cur["weights"], run_cur["signal_dates"])
    assert dates == d_cur
    diff = np.abs(b_pre - b_cur).max(axis=1) > 1e-9
    cols = list(run_pre["weights"].columns)
    margins = decision_margins(pre[0], dates)
    differing = [
        {
            "date": d.date().isoformat(),
            "pre": json.loads(book_label(pd.Series(b_pre[i], index=cols))),
            "cur": json.loads(book_label(pd.Series(b_cur[i], index=cols))),
            "margin_pre_score_units": float(margins["margin"].iloc[i]),
        }
        for i, d in enumerate(dates)
        if diff[i]
    ]
    per_year = {}
    for year in range(2016, 2027):
        sel = [d.year == year for d in dates]
        end = min(pd.Timestamp(f"{year}-12-31"), pd.Timestamp(FULL_SPAN[1]))
        r_pre = run_pre["ret"].loc[f"{year}-01-01" : end]
        r_cur = run_cur["ret"].loc[f"{year}-01-01" : end]
        per_year[str(year)] = {
            "month_ends": int(sum(sel)),
            "month_ends_differing": int(sum(diff[i] for i, s in enumerate(sel) if s)),
            "ret_pre": float((1 + r_pre).prod() - 1),
            "ret_cur": float((1 + r_cur).prod() - 1),
            "ret_diff_cur_minus_pre": float((1 + r_cur).prod() - (1 + r_pre).prod()),
        }
    return {
        "policy": policy,
        "n_month_ends": len(dates),
        "month_ends_differing": int(diff.sum()),
        "differing": differing,
        "per_year": per_year,
        "metrics_pre": {
            "anchor": s3_metrics(run_pre["ret"], run_pre["turn"], rf, *ANCHOR_SPAN),
            "full": s3_metrics(run_pre["ret"], run_pre["turn"], rf, *FULL_SPAN),
        },
        "metrics_cur": {
            "anchor": s3_metrics(run_cur["ret"], run_cur["turn"], rf, *ANCHOR_SPAN),
            "full": s3_metrics(run_cur["ret"], run_cur["turn"], rf, *FULL_SPAN),
        },
    }


def run_s3_fragility(out_dir: Path, seeds: int, bp: float) -> dict:
    pre_c, pre_o = load_panel(PRE_ARCHIVE, S3_SYMBOLS)
    cur_c, cur_o = load_panel(CUR_ARCHIVE, S3_SYMBOLS)
    rf_pre = (pre_c[base.RF] / pre_c[base.RF].shift(1) - 1.0).fillna(0.0)
    rf_cur = (cur_c[base.RF] / cur_c[base.RF].shift(1) - 1.0).fillna(0.0)
    result: dict = {
        "note": "Perturbation multiplies every CLOSE by (1+e), e~N(0, bp) i.i.d. per symbol-day; "
        "opens, the BIL risk-free series and all rules stay as in the frozen engine. "
        "Base archive for perturbation: the current one. Descriptive only; no rule change.",
        "spans": {"anchor": ANCHOR_SPAN, "full": FULL_SPAN},
    }
    result["archive_vs_archive"] = {
        p: archive_comparison((pre_c, pre_o), (cur_c, cur_o), rf_cur, p)
        for p in ("renormalize_survivors", "cash")
    }
    result["perturbation"] = {
        p: fragility_for_policy(cur_c, cur_o, rf_cur, p, seeds, bp)
        for p in ("renormalize_survivors", "cash")
    }
    del rf_pre
    (out_dir / "s3_fragility.json").write_text(json.dumps(result, indent=2, default=float) + "\n")
    return result


# ---------------------------------------------------------------------------
# c2-regen

C2_LANE_DIR = "reports/research/screens/h20260928_20_recent_opt"
C2_OLD_RETURNS = f"{C2_LANE_DIR}/returns.parquet"
C2_NEW_RETURNS = f"{C2_LANE_DIR}/returns.sip-repaired-20261002.parquet"
C2_COLUMNS = ["C2__o00__net10", "C2__o00__net20"]


def run_c2_regen(out_dir: Path, new_path: str = C2_NEW_RETURNS) -> dict:
    """Rebuild C2's offset-0 net10/net20 returns on the current archive with the
    screen lane's frozen simulator; write them to a NEW parquet."""
    if Path(new_path).name == Path(C2_OLD_RETURNS).name:
        raise SystemExit("refusing to write over the old returns.parquet")
    sys.path.insert(0, str(ROOT / "scripts" / "screen_batches"))
    import h20260928_20_recent_opt as batch
    import screen_batch
    import screen_lane as lane

    candidates = screen_batch.candidates_from_module(batch)
    c2 = next(c for c in candidates if c.id == "C2")
    with archive_globals(CUR_ARCHIVE, lane.PANEL_START, base.HOLD_END):
        close, _open, leg_open, leg_close, rf = lane.load_batch_panel(
            candidates, getattr(batch, "extend_panel", None)
        )
    # The stored (old) file used the pre-repair BIL for its risk-free series, so the
    # old Sharpe ratios need the pre-repair archive too. Rebuilding the old returns
    # from that archive also shows whether the backup is the data that made the file.
    with archive_globals(PRE_ARCHIVE, lane.PANEL_START, base.HOLD_END):
        pre_close, _o, pre_lo, pre_lc, rf_old = lane.load_batch_panel(
            candidates, getattr(batch, "extend_panel", None)
        )
    pre10, _t = lane.candidate_returns_for_offset(
        pre_close, pre_lo, pre_lc, c2, 0, lane.COST_BPS_PRIMARY
    )
    ret10, turn10 = lane.candidate_returns_for_offset(
        close, leg_open, leg_close, c2, 0, lane.COST_BPS_PRIMARY
    )
    ret20, turn20 = lane.candidate_returns_for_offset(
        close, leg_open, leg_close, c2, 0, lane.COST_BPS_STRESS
    )
    new = pd.DataFrame({C2_COLUMNS[0]: ret10, C2_COLUMNS[1]: ret20})
    old = pd.read_parquet(ROOT / C2_OLD_RETURNS)[C2_COLUMNS]
    target = ROOT / new_path
    target.parent.mkdir(parents=True, exist_ok=True)
    new.to_parquet(target)
    common = old.index.intersection(new.index)
    first_valid = lane.first_valid_signal_date(close, c2)
    windows: dict[str, dict] = {}
    for name, window in lane.WINDOWS.items():
        start = lane.window_actual_start(window[0], first_valid)
        row = {}
        for label, frame, turn_a, turn_b, rf_used in (
            ("old", old, None, None, rf_old),
            ("new", new, turn10, turn20, rf),
        ):
            t10 = turn_a if turn_a is not None else pd.Series(0.0, index=frame.index)
            t20 = turn_b if turn_b is not None else pd.Series(0.0, index=frame.index)
            metrics, _ = lane.evaluate_offset_window(
                frame[C2_COLUMNS[0]], t10, frame[C2_COLUMNS[1]], t20, rf_used, window, first_valid
            )
            row[label] = {
                "sharpe_net10": metrics["net10"]["sharpe"],
                "cagr_net10": metrics["net10"]["cagr"],
                "max_dd_net10": metrics["net10"]["max_dd"],
                "sharpe_net20": metrics["net20"]["sharpe"],
            }
        row["sharpe_net10_diff_new_minus_old"] = (
            row["new"]["sharpe_net10"] - row["old"]["sharpe_net10"]
        )
        row["window"] = list(window)
        row["actual_start"] = str(start.date())
        windows[name] = row
    diffs = {}
    for col in C2_COLUMNS:
        d = (new[col].loc[common] - old[col].loc[common]).abs()
        diffs[col] = {
            "sessions_compared": int(len(common)),
            "max_abs_diff": float(d.max()),
            "date_of_max": str(d.idxmax().date()),
            "mean_abs_diff": float(d.mean()),
            "median_abs_diff": float(d.median()),
            "p95_abs_diff": float(np.percentile(d, 95)),
            "days_diff_gt_1e-6": int((d > 1e-6).sum()),
            "days_diff_gt_1e-4": int((d > 1e-4).sum()),
            "days_diff_gt_1e-3": int((d > 1e-3).sum()),
        }
    result = {
        "new_returns": new_path,
        "old_returns_untouched": C2_OLD_RETURNS,
        "archive": CUR_ARCHIVE,
        "panel_end": base.HOLD_END,
        "rows_new": int(len(new)),
        "rows_old": int(len(old)),
        "index_equal": bool(new.index.equals(old.index)),
        "old_stored_vs_rebuilt_on_preswap_archive_max_abs_diff": float(
            (pre10.loc[old.index.intersection(pre10.index)] - old[C2_COLUMNS[0]]).abs().max()
        ),
        "windows": windows,
        "daily_return_diff": diffs,
    }
    (out_dir / "c2_regen.json").write_text(json.dumps(result, indent=2, default=float) + "\n")
    return result


# ---------------------------------------------------------------------------
# main


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("cmd", choices=["s3-flip", "s3-fragility", "c2-regen"])
    ap.add_argument("--out-dir", default=DEFAULT_OUT_DIR)
    ap.add_argument("--seeds", type=int, default=50)
    ap.add_argument("--bp", type=float, default=5.0)
    args = ap.parse_args(argv)
    out_dir = ROOT / args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    if args.cmd == "s3-flip":
        res = run_s3_flip(out_dir)
        print(json.dumps(res, indent=2, default=float)[:3000])
    elif args.cmd == "c2-regen":
        res = run_c2_regen(out_dir)
        print(json.dumps(res, indent=2, default=float)[:5000])
    elif args.cmd == "s3-fragility":
        res = run_s3_fragility(out_dir, args.seeds, args.bp)
        print(json.dumps(res["perturbation"], indent=2, default=float)[:6000])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
