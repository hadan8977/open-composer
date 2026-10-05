# ruff: noqa: E501
"""T-20261004-70: spliced forward record (A1) of the live-fast-track candidates.

Three stages (run in this order, the first two are the heavy ones):

    scripts/run_capped.sh --mem 1.0G -- uv run python scripts/forward_record_t70.py shadow
    scripts/run_capped.sh --mem 1.0G -- uv run python scripts/forward_record_t70.py book   # optional
    uv run python scripts/forward_record_t70.py assemble

* ``shadow``: S1, S2, S3 (frozen overlay engine of ``run_h20260927_01_sleeve_combination``) and C2
  (screen engine, offset 0) daily net-10bp returns on the panel through the last SIP session
  (``shadow_forward.load_forward_panel``, no HOLD_END cap) -> ``/tmp/t70_etf_shadow.parquet``.
* ``book``: v1.2 F1/F2 daily net P&L of the frozen engine rerun on the live equity-book root
  (``data/live/equity_book``) -> ``/tmp/t70_book_shadow.parquet``.  Nothing under
  ``data/research`` is overwritten.
* ``assemble``: segments, statistics, forward z, tracking difference, hash chain, README inputs ->
  ``reports/research/program/forward-record-2026-10-06/``.

Everything read-only with respect to the paper pipeline and the broker.
"""

from __future__ import annotations

import hashlib
import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

OUT_DIR = ROOT / "reports/research/program/forward-record-2026-10-06"
ETF_SHADOW = Path("/tmp/t70_etf_shadow.parquet")
BOOK_SHADOW = Path("/tmp/t70_book_shadow.parquet")
ANN = 252.0
TRACK_START = "2026-09-01"
MIN_SHARPE_DAYS = 20  # below this a Sharpe is printed but flagged "not meaningful"

# ----------------------------------------------------------------------------------------
# pure statistics (unit tested)
# ----------------------------------------------------------------------------------------


def seg_stats(ret: pd.Series, rf: pd.Series | None = None) -> dict:
    """Days, cumulative return, annualised vol, Sharpe over the risk-free series, max drawdown.

    The drawdown is measured on the compounded path that starts at 1.0 on the segment's first
    day, so a one-day segment has drawdown min(0, r).  Sharpe is None below 2 days and carries
    ``sharpe_meaningful`` = False below ``MIN_SHARPE_DAYS`` days.
    """
    r = ret.dropna()
    n = int(len(r))
    if n == 0:
        return {
            "days": 0,
            "cum_return": None,
            "ann_vol": None,
            "sharpe": None,
            "sharpe_meaningful": False,
            "max_dd": None,
        }
    nav = (1.0 + r).cumprod()
    cum = float(nav.iloc[-1] - 1.0)
    dd = float((nav / np.maximum(nav.cummax(), 1.0) - 1.0).min())
    vol = float(r.std(ddof=1) * math.sqrt(ANN)) if n >= 2 else None
    sharpe = None
    if n >= 2:
        ex = r - (rf.reindex(r.index).fillna(0.0) if rf is not None else 0.0)
        sd = float(ex.std(ddof=1))
        sharpe = float(ex.mean() / sd * math.sqrt(ANN)) if sd > 0 else None
    return {
        "days": n,
        "cum_return": cum,
        "ann_vol": vol,
        "sharpe": sharpe,
        "sharpe_meaningful": n >= MIN_SHARPE_DAYS,
        "max_dd": dd,
    }


def forward_z(fwd: pd.Series, base: pd.Series) -> dict:
    """z = (mean(fwd) - mean(base)) / (std(base) / sqrt(n_fwd)); sample std (ddof=1)."""
    f = fwd.dropna()
    b = base.dropna()
    n = int(len(f))
    if n == 0 or len(b) < 2:
        return {"n_forward": n, "n_base": int(len(b)), "z": None}
    sd = float(b.std(ddof=1))
    if sd <= 0:
        return {"n_forward": n, "n_base": int(len(b)), "z": None}
    mu_b = float(b.mean())
    mu_f = float(f.mean())
    return {
        "n_forward": n,
        "n_base": int(len(b)),
        "forward_mean_daily": mu_f,
        "base_mean_daily": mu_b,
        "base_std_daily": sd,
        "z": (mu_f - mu_b) / (sd / math.sqrt(n)),
    }


def tracking_stats(diff: pd.Series) -> dict:
    d = diff.dropna()
    if d.empty:
        return {"days": 0, "mean": None, "std": None, "worst3": []}
    worst = d.nsmallest(3)
    return {
        "days": int(len(d)),
        "mean": float(d.mean()),
        "std": float(d.std(ddof=1)) if len(d) >= 2 else None,
        "worst3": [{"date": str(i.date()), "diff": float(v)} for i, v in worst.items()],
    }


def split_segments(
    index: pd.DatetimeIndex, track_start: str, last_seen: str, paper_first: str | None
) -> dict[str, pd.DatetimeIndex]:
    """Segment 1 = track_start..last_seen (inclusive), 2 = after last_seen and before the first
    paper session, 3 = paper_first and later.  Without paper: segment 2 runs to the end."""
    idx = pd.DatetimeIndex(index)
    ts, ls = pd.Timestamp(track_start), pd.Timestamp(last_seen)
    s1 = idx[(idx >= ts) & (idx <= ls)]
    if paper_first is None:
        return {"design_seen": s1, "oos_shadow": idx[idx > ls], "paper": idx[:0]}
    pf = pd.Timestamp(paper_first)
    return {
        "design_seen": s1,
        "oos_shadow": idx[(idx > ls) & (idx < pf)],
        "paper": idx[idx >= pf],
    }


# ----------------------------------------------------------------------------------------
# hash chain (unit tested)
# ----------------------------------------------------------------------------------------

GENESIS = "0" * 64


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def chain_hash(prev: str, date: str, candidate: str, path: str, sha: str) -> str:
    """chain_hash = sha256("|".join([prev_chain_hash, date, candidate, path, file_sha256]))."""
    return hashlib.sha256("|".join([prev, date, candidate, path, sha]).encode()).hexdigest()


def build_chain(entries: list[dict]) -> list[dict]:
    """entries: dicts with date, candidate, path (repo-relative), sha256.  Adds prev_hash and
    chain_hash in the given order."""
    out: list[dict] = []
    prev = GENESIS
    for e in entries:
        ch = chain_hash(prev, e["date"], e["candidate"], e["path"], e["sha256"])
        row = dict(e)
        row["prev_hash"] = prev
        row["chain_hash"] = ch
        out.append(row)
        prev = ch
    return out


def verify_chain(rows: list[dict]) -> tuple[bool, int | None]:
    """Recompute every chain_hash from the stored fields; (ok, first_bad_line_index)."""
    prev = GENESIS
    for i, r in enumerate(rows):
        if r["prev_hash"] != prev:
            return False, i
        if chain_hash(prev, r["date"], r["candidate"], r["path"], r["sha256"]) != r["chain_hash"]:
            return False, i
        prev = r["chain_hash"]
    return True, None


# ----------------------------------------------------------------------------------------
# stage 1: ETF shadow returns
# ----------------------------------------------------------------------------------------

C2_MODULE = "scripts/screen_batches/h20260928_20_recent_opt.py"
C2_ID = "C2"
COST_BPS = 10.0


def stage_shadow() -> int:
    import run_h20260927_01_sleeve_combination as comb
    import screen_lane as lane
    import shadow_forward as sf

    c2_mod = sf.load_candidate_module(C2_MODULE)
    c2 = sf.find_candidate(c2_mod, C2_ID)
    symbols = sorted(set(comb.salvage.symbols()) | set(lane.batch_symbols([c2])))
    close, open_ = sf.load_forward_panel(symbols)
    leg_open, leg_close = comb.salvage.legs(close, open_)
    rets = comb.sleeve_returns(close, leg_open, leg_close, COST_BPS)
    c2_ret, c2_turn = lane.candidate_returns_for_offset(close, leg_open, leg_close, c2, 0, COST_BPS)
    boost = comb.salvage.boost_window(comb.salvage.dip_signal(close), comb.S3_BOOST_HOLD)
    frame = pd.DataFrame({"S1": rets["s1"], "S2": rets["s2"], "S3": rets["s3"], "C2": c2_ret})
    frame["C2_turn"] = c2_turn
    # per-day shadow diagnostics for the tracking-difference notes: gross-of-cost turnover
    for key, tgt in (("s1", None), ("s2", comb.S2_TARGET), ("s3", comb.S3_TARGET)):
        w, sig = comb.salvage.sleeve_weights(close, key)
        gross, _ = comb.salvage.simulate(w, leg_open, leg_close, np.ones(len(close.index)), 0.0)
        if key == "s3":
            sc = comb.salvage.vol_scale(close.index, sig, gross, tgt, boost, comb.S3_BOOST_TARGET)
        else:
            sc = comb.salvage.vol_scale(close.index, sig, gross, tgt)
        _, turn = comb.salvage.simulate(w, leg_open, leg_close, sc, COST_BPS)
        frame[f"{key.upper()}_turn"] = turn
        frame[f"{key.upper()}_scale"] = sc
        # top picks held on each day (non-cash weight columns > 0), as text
        names = []
        for i in range(len(w)):
            row = w.iloc[i]
            held = [f"{c}:{row[c]:.2f}" for c in w.columns if row[c] > 0]
            names.append(",".join(held))
        frame[f"{key.upper()}_book"] = names
    frame["SPY"] = (close["SPY"] / close["SPY"].shift(1) - 1.0).fillna(0.0)
    frame["RF"] = (close[lane.RF] / close[lane.RF].shift(1) - 1.0).fillna(0.0)
    frame.index.name = "date"
    frame.to_parquet(ETF_SHADOW)
    print("shadow written", ETF_SHADOW, frame.index[0].date(), frame.index[-1].date(), len(frame))
    return 0


# ----------------------------------------------------------------------------------------
# stage 2: v1.2 book rerun on a hybrid live root
# ----------------------------------------------------------------------------------------

BOOK_VARIANT = "M0_U3000"
HYBRID_ROOT = Path("/tmp/t70_book_root")
BOOK_OUT = Path("/tmp/t70_book_out")
VIX_TMP = Path("/tmp/t70_vix")


def build_hybrid_root() -> dict:
    """Live equity-book root, with the pre-2025 theme and signal files (which the live root does not
    carry) linked from the research snapshot.  Everything is symlinks; nothing is copied or edited."""
    import shutil

    live = ROOT / "data/live/equity_book"
    snap = ROOT / "data/research/equity_book"
    if HYBRID_ROOT.exists():
        shutil.rmtree(HYBRID_ROOT)
    HYBRID_ROOT.mkdir(parents=True)
    filled: dict[str, list[str]] = {}
    for child in sorted(live.iterdir()):
        if child.name in ("duck_tmp",):
            continue
        if child.name in ("alpha", "signals"):
            continue
        (HYBRID_ROOT / child.name).symlink_to(child)
    for sub in ("alpha/book_v1", "signals"):
        d = HYBRID_ROOT / sub
        d.mkdir(parents=True, exist_ok=True)
        for f in sorted((live / sub).iterdir()):
            (d / f.name).symlink_to(f)
        filled[sub] = []
        for f in sorted((snap / sub).iterdir()):
            if not (d / f.name).exists():
                (d / f.name).symlink_to(f)
                filled[sub].append(f.name)
    for f in sorted((live / "alpha").iterdir()):
        if f.name != "book_v1" and not (HYBRID_ROOT / "alpha" / f.name).exists():
            (HYBRID_ROOT / "alpha" / f.name).symlink_to(f)
    VIX_TMP.mkdir(exist_ok=True)
    for name, src in (
        ("VIXCLS.csv", ROOT / "data/live/vix/VIXCLS.csv"),
        ("VXVCLS.csv", ROOT / "data/research/vix/VXVCLS.csv"),
    ):
        link = VIX_TMP / name
        if link.is_symlink() or link.exists():
            link.unlink()
        link.symlink_to(src)
    return filled


def stage_book(limit: int | None = None) -> int:
    import os

    filled = build_hybrid_root()
    os.environ["OC_EQUITY_BOOK_DIR"] = str(HYBRID_ROOT)
    from scripts import analyze_equity_book_regimes as reg
    from scripts import book_v12_account as bva
    from scripts import realism_ladder_book_ls as t25
    from scripts import run_book_v1_stage2 as st2

    t25.EB = HYBRID_ROOT
    t25.RAW = HYBRID_ROOT / "realism_ladder"
    t25.EwmaBeta.__init__.__defaults__ = (HYBRID_ROOT / "risk",)
    st2.ThemeStore.__init__.__defaults__ = (HYBRID_ROOT / "alpha/book_v1",)
    reg.VIX_DIR = VIX_TMP
    BOOK_OUT.mkdir(exist_ok=True)
    bva.OUT_DATA = BOOK_OUT
    bva.run_account(BOOK_VARIANT, limit)
    if limit is not None:
        return 0
    cols = {}
    for f in ("F1", "F2"):
        df = pd.read_parquet(BOOK_OUT / f"A1_{BOOK_VARIANT}_{f}.parquet")
        cols[f"{f}_net_pnl"] = df["net_pnl"]
        cols[f"{f}_gross"] = df["gross"]
    out = pd.DataFrame(cols)
    out.index.name = "date"
    out.to_parquet(BOOK_SHADOW)
    (BOOK_OUT / "hybrid_root_fill.json").write_text(json.dumps(filled, indent=1))
    print("book shadow written", BOOK_SHADOW, out.index[0].date(), out.index[-1].date(), len(out))
    return 0


# ----------------------------------------------------------------------------------------
# stage 3: assemble
# ----------------------------------------------------------------------------------------

BT_FULL_START = "2017-10-02"  # same full-window start as the T-43 allocation
BT_RECENT_START = "2024-01-08"  # anchor window start (run_h20260918_05_recent_menu.ANCHOR_START)
T43_WEIGHTS = [0.6, 0.335, 0.025, 0.12, 0.0, -0.08]  # S3, C2, F1, F2, CASH, borrow (results.json)
SPEC = "strategy_specs/drafts/{}.yaml"
PAPER_DIR = "reports/paper"
RENEWAL_LAST_PRE_OVERLAY_SESSION = "2026-09-23"

CANDIDATES: dict[str, dict] = {
    "S1": {
        "label": "S1 sector rotation (us_etf_sector_rotation_252_top2_weekly)",
        "strategy": "us_etf_sector_rotation_252_top2_weekly",
        "freeze_file": SPEC.format("us_etf_sector_rotation_252_top2_weekly"),
        "data_boundary": "2026-09-17",
    },
    "S2": {
        "label": "S2 growth rotation (us_etf_growth_rotation_blend_top2_monthly)",
        "strategy": "us_etf_growth_rotation_blend_top2_monthly",
        "freeze_file": SPEC.format("us_etf_growth_rotation_blend_top2_monthly"),
        "data_boundary": "2026-09-17",
    },
    "S3": {
        "label": "S3 levered rotation (us_etf_levered_rotation_63_top2_monthly)",
        "strategy": "us_etf_levered_rotation_63_top2_monthly",
        "freeze_file": SPEC.format("us_etf_levered_rotation_63_top2_monthly"),
        "data_boundary": "2026-09-17",
    },
    "C2": {
        "label": "C2 month-end + sector seasonality (us_etf_eom_sector_blend_monthly)",
        "strategy": "us_etf_eom_sector_blend_monthly",
        "freeze_file": C2_MODULE,
        "other_freeze_files": [SPEC.format("us_etf_eom_sector_blend_monthly")],
        "data_boundary": "2026-09-17",
    },
    "V12F1": {
        "label": "v1.2 F1 market-neutral long-short (quant1)",
        "strategy": None,
        "freeze_file": "reports/research/iterations/t20261002_book_v12/hypotheses.md",
        "data_boundary": "2026-09-15",
    },
    "V12F2": {
        "label": "v1.2 F2 SPY + overlay (quant2)",
        "strategy": None,
        "freeze_file": "reports/research/iterations/t20261002_book_v12/hypotheses.md",
        "data_boundary": "2026-09-15",
    },
    "T43": {
        "label": "T-43 program (S3 0.60, C2 0.335, F2 0.12, F1 0.025, borrowed 0.08)",
        "strategy": None,
        "freeze_file": "reports/research/program/allocation-dd30-2026-10-02/prereg.md",
        "data_boundary": "2026-09-15",
    },
}


def git_first_commit(rel: str) -> dict:
    import subprocess

    out = (
        subprocess.run(
            ["git", "log", "--diff-filter=A", "--format=%aI %h", "--", rel],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
        .stdout.strip()
        .splitlines()
    )
    if not out:
        return {"file": rel, "first_commit_utc": None, "commit": None}
    iso, sha = out[-1].split()
    ts = pd.Timestamp(iso).tz_convert("UTC").tz_localize(None)
    return {"file": rel, "first_commit_utc": str(ts), "commit": sha}


def last_seen_session(index: pd.DatetimeIndex, commit_utc: str, close_utc_hour: int = 20) -> str:
    """Last session whose close (20:00 UTC, 16:00 ET in summer time) is at or before the commit."""
    ts = pd.Timestamp(commit_utc)
    seen = [d for d in index if d + pd.Timedelta(hours=close_utc_hour) <= ts]
    return str(seen[-1].date())


def load_paper() -> dict[str, dict]:
    """Per-strategy sleeve NAV history of the paper account (read only)."""
    from datetime import UTC, datetime

    from open_composer.cockpit.data.paper import build_paper_report

    rep = build_paper_report(ROOT, now=datetime.now(UTC))
    out: dict[str, dict] = {}
    for s in rep.strategies:
        p = s.performance
        if p.status != "live" or p.history is None or p.budget is None:
            continue
        navs = [
            (pd.Timestamp(d.day), d.point.equity) for d in p.history.days if d.point is not None
        ]
        if not navs:
            continue
        idx = pd.DatetimeIndex([d for d, _ in navs])
        nav = pd.Series([v for _, v in navs], index=idx)
        prev = nav.shift(1)
        prev.iloc[0] = float(p.budget)
        out[s.name] = {
            "budget": float(p.budget),
            "nav": nav,
            "ret": nav / prev - 1.0,
            "first": idx[0],
            "prev_nav": prev,
        }
    return out


def load_fills(strategy: str) -> pd.DataFrame:
    f = ROOT / PAPER_DIR / "rehearsal" / f"{strategy}-fills.jsonl"
    if not f.exists():
        return pd.DataFrame()
    rows = [json.loads(x) for x in f.read_text().splitlines() if x.strip()]
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["session"])
    df["notional"] = df["filled_qty"].astype(float) * df["filled_avg_price"].astype(float)
    return df


def obs_idle_cash(strategy: str, d: pd.Timestamp) -> float | None:
    f = ROOT / PAPER_DIR / "daily_cycle" / f"{strategy}-observation-{d:%Y%m%d}.json"
    if not f.exists():
        return None
    data = json.loads(f.read_text())
    summ = data.get("target_weights_summary") or {}
    v = summ.get("idle_cash_fraction")
    return None if v is None else float(v)


def tracking_rows(
    cand: str,
    strategy: str,
    paper: dict,
    shadow: pd.DataFrame,
    column: str,
) -> list[dict]:
    """Per paper day: paper return - shadow return and a mechanical decomposition."""
    fills = load_fills(strategy)
    rows = []
    book_col = f"{column}_book"
    for d, pr in paper["ret"].items():
        sr = float(shadow.loc[d, column])
        diff = float(pr - sr)
        nav_prev = float(paper["prev_nav"].loc[d])
        fd = fills[fills["date"] == d] if len(fills) else fills
        n_f = int(len(fd))
        notional = float(fd["notional"].sum()) if n_f else 0.0
        slip_cost_bp_nav = (
            float((fd["notional"] * fd["slippage_vs_open_bps"].astype(float)).sum() / nav_prev)
            if n_f
            else 0.0
        )
        times = sorted(str(t)[11:16] for t in fd["filled_at"]) if n_f else []
        turn = float(shadow.loc[d, f"{column}_turn"]) if f"{column}_turn" in shadow else 0.0
        if column == "C2":
            turn = float(shadow.loc[d, "C2_turn"])
        refund_bp = turn * COST_BPS  # shadow charges COST_BPS per unit turnover, paper does not
        idle = obs_idle_cash(strategy, d)
        round_bp = 0.0 if idle is None else -idle * sr * 1e4
        explained_bp = -slip_cost_bp_nav + refund_bp + round_bp
        resid_bp = diff * 1e4 - explained_bp
        book = str(shadow.loc[d, book_col]) if book_col in shadow else ""
        parts = []
        if n_f:
            parts.append(
                f"fill price: {n_f} orders, {notional:,.0f} USD, adverse slippage vs official open "
                f"{-slip_cost_bp_nav:+.1f} bp of NAV; timing: executed {times[0]}-{times[-1]} UTC "
                "(day_market after the open) while the shadow earns the official open"
            )
        else:
            parts.append("no orders that day (fill price / timing: none)")
        if turn > 0:
            parts.append(
                f"shadow turnover {turn:.2f} charges {refund_bp:.1f} bp that paper does not pay explicitly"
            )
        if idle is not None:
            parts.append(
                f"whole-share rounding / idle cash {idle:.2%} of equity: estimate {round_bp:+.1f} bp"
            )
        parts.append(f"residual {resid_bp:+.1f} bp (holdings/data/mark differences)")
        tag = ""
        if cand == "S3" and book == "SHY:1.00" and abs(diff) > 5e-4:
            tag = (
                "T-55 data flip: shadow on the repaired SIP archive holds SHY, the paper sleeve holds"
                " UPRO (chosen on the pre-repair archive); not an execution error"
            )
            parts.append(tag)
        pre_overlay = cand in ("S2", "S3") and d <= pd.Timestamp(RENEWAL_LAST_PRE_OVERLAY_SESSION)
        if pre_overlay:
            parts.append(
                "paper ran the pre-renewal rule without the volatility overlay until the 09-23 renewal"
                " (overlay trades filled 09-24, spec commit 97c992c 2026-09-23 07:35 UTC); the shadow engine"
                " applies the frozen overlay from the start"
            )
        rows.append(
            {
                "date": str(d.date()),
                "pre_renewal_paper_rule": bool(pre_overlay),
                "paper_return": float(pr),
                "shadow_return": sr,
                "diff": diff,
                "shadow_book": book,
                "n_fills": n_f,
                "fill_slippage_cost_bp_of_nav": slip_cost_bp_nav,
                "shadow_modeled_cost_bp": refund_bp,
                "rounding_estimate_bp": round_bp,
                "residual_bp": resid_bp,
                "t55_flip": bool(tag),
                "reason": "; ".join(parts),
            }
        )
    return rows


def seg_block(ret: pd.Series, spy: pd.Series, rf: pd.Series, idx: pd.DatetimeIndex) -> dict:
    r = ret.reindex(idx)
    return {
        "range": [str(idx[0].date()), str(idx[-1].date())] if len(idx) else None,
        "strategy": seg_stats(r, rf),
        "spy": seg_stats(spy.reindex(idx), rf),
    }


def candidate_block(
    name: str,
    shadow_ret: pd.Series,
    spliced: pd.Series,
    paper_first: str | None,
    last_seen: str,
    spy: pd.Series,
    rf: pd.Series,
    bt_end_cap: str | None = None,
) -> dict:
    """Segments, forward z and splice for one boundary."""
    idx = pd.DatetimeIndex(spliced.dropna().loc[TRACK_START:].index)
    segs = split_segments(idx, TRACK_START, last_seen, paper_first)
    out: dict = {"last_seen_session": last_seen, "segments": {}}
    for seg, ix in segs.items():
        out["segments"][seg] = seg_block(spliced, spy, rf, ix)
    out["segments"]["total"] = seg_block(spliced, spy, rf, idx)
    fwd_idx = segs["oos_shadow"].append(segs["paper"])
    out["segments"]["forward_oos_plus_paper"] = seg_block(spliced, spy, rf, fwd_idx)
    out["segments"]["forward_shadow_engine_only"] = seg_block(shadow_ret, spy, rf, fwd_idx)
    bt_end = last_seen if bt_end_cap is None else min(last_seen, bt_end_cap)
    base_full = shadow_ret.loc[BT_FULL_START:bt_end]
    base_recent = shadow_ret.loc[BT_RECENT_START:bt_end]
    out["z"] = {
        "backtest_full": {
            "window": [BT_FULL_START, bt_end],
            **forward_z(spliced.reindex(fwd_idx), base_full),
        },
        "backtest_recent": {
            "window": [BT_RECENT_START, bt_end],
            **forward_z(spliced.reindex(fwd_idx), base_recent),
        },
        "backtest_full_shadow_only": {
            "window": [BT_FULL_START, bt_end],
            **forward_z(shadow_ret.reindex(fwd_idx), base_full),
        },
        "backtest_recent_shadow_only": {
            "window": [BT_RECENT_START, bt_end],
            **forward_z(shadow_ret.reindex(fwd_idx), base_recent),
        },
        "note": "z = (mean forward daily return - mean backtest daily return) / (backtest daily std / sqrt(n_forward)); "
        "sample std; the shadow-only variants use the shadow engine on the same days. Daily returns are not iid; "
        "with n_forward below about 20 a z is descriptive only.",
    }
    return out


def hash_entries(has_book_dirs: bool = True) -> list[dict]:
    """Existing per-day artifacts of the paper/shadow pipeline, hashed (nothing is changed)."""
    ents: list[dict] = []

    def add(date: str, cand: str, rel: str, note: str = "") -> None:
        p = ROOT / rel
        if p.exists():
            ents.append(
                {
                    "date": date,
                    "candidate": cand,
                    "path": rel,
                    "sha256": file_sha256(p),
                    "note": note,
                }
            )

    for cand, cfg in CANDIDATES.items():
        st = cfg.get("strategy")
        if not st:
            continue
        for f in sorted((ROOT / PAPER_DIR / "daily_cycle").glob(f"{st}-observation-*.json")):
            ds = f.stem.rsplit("-", 1)[1]
            add(
                f"{ds[:4]}-{ds[4:6]}-{ds[6:]}",
                cand,
                str(f.relative_to(ROOT)),
                "daily observation log (target-weight summary)",
            )
        for f in sorted((ROOT / PAPER_DIR / "rehearsal").glob(f"{st}-????-??-??-??????.json")):
            parts = f.stem[len(st) + 1 :].split("-")
            add(
                "-".join(parts[:3]),
                cand,
                str(f.relative_to(ROOT)),
                "paper cycle snapshot (session date in file name)",
            )
        tw = ROOT / "reports/execution" / f"{st}-target-weights.json"
        if tw.exists():
            mtime = pd.Timestamp(tw.stat().st_mtime, unit="s").strftime("%Y-%m-%d")
            add(
                mtime,
                cand,
                str(tw.relative_to(ROOT)),
                "target-weights file is overwritten daily; hash attests the latest state only",
            )
    for cand, acct in (("V12F1", "quant1"), ("V12F2", "quant2")):
        for sub in ("targets", "plans"):
            for f in sorted((ROOT / PAPER_DIR / "book" / acct / sub).glob("20??-??-??.json")):
                add(
                    f.stem,
                    cand,
                    str(f.relative_to(ROOT)),
                    f"book v1.2 {sub[:-1]} file of that date",
                )
    add(
        "2026-10-02",
        "T43",
        "reports/research/program/allocation-dd30-2026-10-02/results.json",
        "frozen T-43 allocation result (weights)",
    )
    ents.sort(key=lambda e: (e["date"], e["candidate"], e["path"]))
    return ents


def build_series() -> tuple[pd.DataFrame, dict]:
    """Daily shadow returns S1,S2,S3,C2,F1,F2,T43 plus SPY and RF; consistency checks."""
    import run_program_dd30_allocation as alloc

    etf = pd.read_parquet(ETF_SHADOW)
    etf.index = pd.to_datetime(etf.index)
    checks: dict = {}
    # F1/F2: stored research files, realised-dated, extended by the live-root rerun if present
    books = {}
    for f in ("F1", "F2"):
        d = pd.read_parquet(ROOT / f"data/research/book_v12/A1_M0_U3000_{f}.parquet")
        books[f] = alloc.realization_dated(d["net_pnl"] / 1e6)
        books[f].index = pd.to_datetime(books[f].index)
    book_last = books["F1"].index[-1]
    book_src = pd.Series("research_book_v12_parquet", index=books["F1"].index)
    if BOOK_SHADOW.exists():
        nb = pd.read_parquet(BOOK_SHADOW)
        nb.index = pd.to_datetime(nb.index)
        for f in ("F1", "F2"):
            rer = alloc.realization_dated(nb[f"{f}_net_pnl"] / 1e6)
            checks[f"{f}_rerun_vs_stored_max_abs_diff"] = float(
                (rer.reindex(books[f].index).dropna() - books[f].reindex(rer.index).dropna())
                .abs()
                .max()
            )
            new = rer.loc[rer.index > book_last]
            books[f] = pd.concat([books[f], new])
        book_src = pd.concat(
            [
                book_src,
                pd.Series(
                    "book_v12_live_root_rerun",
                    index=books["F1"].index[books["F1"].index > book_last],
                ),
            ]
        )
    frame = pd.DataFrame(
        {
            "S1": etf["S1"],
            "S2": etf["S2"],
            "S3": etf["S3"],
            "C2": etf["C2"],
            "V12F1": books["F1"],
            "V12F2": books["F2"],
            "SPY": etf["SPY"],
            "RF": etf["RF"],
        }
    )
    frame = frame.loc[BT_FULL_START:]
    # T-43 program path
    eng = pd.DataFrame(
        {"S3": etf["S3"], "C2": etf["C2"], "F1": books["F1"], "F2": books["F2"], "CASH": etf["RF"]}
    ).loc[BT_FULL_START:]
    eng = eng.dropna()
    prog = alloc.path(np.array(T43_WEIGHTS), eng.to_numpy(), eng.index, 0)
    frame["T43"] = prog
    stored = pd.read_parquet(
        ROOT / "reports/research/program/allocation-dd30-2026-10-02/program_returns.parquet"
    )
    stored = stored["program_ret"]
    stored.index = pd.to_datetime(stored.index)
    j = pd.concat([prog.rename("mine"), stored.rename("stored")], axis=1).dropna()
    checks["T43_path_vs_stored_program_returns"] = {
        "overlap_days": int(len(j)),
        "last_overlap_date": str(j.index[-1].date()),
        "max_abs_diff": float((j["mine"] - j["stored"]).abs().max()),
    }
    checks["T43_path_vs_stored_program_returns"]["max_abs_diff_since_2026_01_01"] = float(
        (j["mine"] - j["stored"]).loc["2026-01-01":].abs().max()
    )
    # the stored T-43 run read the pre-repair C2 file; rebuild with it to show the path engine matches
    old = pd.read_parquet(
        ROOT / "reports/research/screens/h20260928_20_recent_opt/returns.parquet"
    )["C2__o00__net10"]
    old.index = pd.to_datetime(old.index)
    eng_old = eng.copy()
    eng_old["C2"] = old.reindex(eng.index).fillna(eng["C2"])
    prog_old = alloc.path(np.array(T43_WEIGHTS), eng_old.to_numpy(), eng_old.index, 0)
    j2 = pd.concat([prog_old.rename("mine"), stored.rename("stored")], axis=1).dropna()
    checks["T43_path_prerepair_C2_vs_stored_program_returns_max_abs_diff"] = float(
        (j2["mine"] - j2["stored"]).abs().max()
    )
    checks["T43_note"] = (
        "stored T-43 program_returns used the pre-repair C2 file (T-55: repaired C2 differs by up to "
        "1.005% on 2019-01-02); this record uses the repaired C2 series."
    )
    checks["F_book_last_stored_date"] = str(book_last.date())
    checks["F_book_last_date_used"] = str(books["F1"].index[-1].date())
    return frame, {"checks": checks, "book_src": book_src, "etf": etf}


def _p(x: float | None, nd: int = 2) -> str:
    return "n/a" if x is None else f"{x * 100:.{nd}f}%"


def _n(x: float | None, nd: int = 2) -> str:
    return "n/a" if x is None else f"{x:.{nd}f}"


SEG_ZH = {
    "design_seen": "设计时看过",
    "oos_shadow": "样本外影子",
    "paper": "模拟盘",
    "total": "合计",
    "forward_oos_plus_paper": "前向（影子+模拟盘拼接）",
    "forward_shadow_engine_only": "前向（同日仅影子引擎）",
}


def seg_table(summary: dict, key: str) -> list[str]:
    lines = [
        "| 候选 | 段 | 区间 | 天数 | 累计收益 | 年化波动 | 夏普 | 最大回撤 | SPY 同期累计 |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for name, c in summary["candidates"].items():
        blk = c.get(key)
        if blk is None:
            continue
        for seg, v in blk["segments"].items():
            st, sp = v["strategy"], v["spy"]
            rng = "-" if v["range"] is None else f"{v['range'][0]}..{v['range'][1]}"
            sh = _n(st["sharpe"])
            if st["sharpe"] is not None and not st["sharpe_meaningful"]:
                sh += "（<20天，仅描述）"
            lines.append(
                f"| {name} | {SEG_ZH[seg]} | {rng} | {st['days']} | {_p(st['cum_return'])} |"
                f" {_p(st['ann_vol'])} | {sh} | {_p(st['max_dd'])} | {_p(sp['cum_return'])} |"
            )
    return lines


def z_table(summary: dict, key: str) -> list[str]:
    lines = [
        "| 候选 | n 前向 | z（回测全期） | z（回测近期窗口） | z（仅影子，全期） | z（仅影子，近期） |",
        "|---|---|---|---|---|---|",
    ]
    for name, c in summary["candidates"].items():
        blk = c.get(key)
        if blk is None:
            continue
        z = blk["z"]
        lines.append(
            f"| {name} | {z['backtest_full']['n_forward']} | {_n(z['backtest_full']['z'])} |"
            f" {_n(z['backtest_recent']['z'])} | {_n(z['backtest_full_shadow_only']['z'])} |"
            f" {_n(z['backtest_recent_shadow_only']['z'])} |"
        )
    return lines


def tracking_table(summary: dict) -> list[str]:
    lines = [
        "| 候选 | 子集 | 天数 | 日均差(bp) | 日标准差(bp) | 最差 3 天 |",
        "|---|---|---|---|---|---|",
    ]
    for name, c in summary["candidates"].items():
        t = c.get("tracking_difference")
        if not t:
            continue
        for lab, key in (
            ("全部模拟盘日", "all_paper_days"),
            ("T-55 数据翻转日", "t55_flip_days"),
            ("其余日", "other_days"),
            ("09-23 前（模拟盘尚无波动率叠加层）", "pre_renewal_paper_rule_days"),
            ("09-24 起", "post_renewal_days"),
        ):
            st = t.get(key)
            if not st or st["days"] == 0:
                continue
            worst = "; ".join(f"{w['date']} {w['diff'] * 1e4:+.1f}" for w in st["worst3"])
            sd = "n/a" if st["std"] is None else f"{st['std'] * 1e4:.1f}"
            lines.append(
                f"| {name} | {lab} | {st['days']} | {st['mean'] * 1e4:+.1f} | {sd} | {worst} |"
            )
    return lines


def tracking_daily_lines(summary: dict) -> list[str]:
    lines = []
    for name, c in summary["candidates"].items():
        t = c.get("tracking_difference")
        if not t:
            continue
        lines += [
            "",
            f"### {name} 逐日（模拟盘 − 影子，bp）",
            "",
            "| 日期 | 模拟盘 | 影子 | 差 | 成交价 | 影子成本 | 整股取整(估) | 残差 | 说明 |",
            "|---|---|---|---|---|---|---|---|---|",
        ]
        for r in t["daily"]:
            lines.append(
                f"| {r['date']} | {r['paper_return'] * 1e4:+.1f} | {r['shadow_return'] * 1e4:+.1f} |"
                f" {r['diff'] * 1e4:+.1f} | {-r['fill_slippage_cost_bp_of_nav']:+.1f} |"
                f" {r['shadow_modeled_cost_bp']:+.1f} | {r['rounding_estimate_bp']:+.1f} |"
                f" {r['residual_bp']:+.1f} | {r['reason']} |"
            )
    return lines


DECAY_RULE = """\
## 衰减规则草案（供 A5 提议使用；所有阈值和天数均为 **待主审校准**，本任务没有拍数）

输入：每个候选的前向日净收益（影子+模拟盘拼接，见上）、前向 z（相对回测近期窗口）、前向最大回撤相对该候选冻结时回测回撤分布的分位、
以及 `config/evaluation-standard-v2.json` 的 `forward_monitoring` 里已有的硬停止（回撤 95% 分位减半、99% 分位停用、
21 日 beta 绝对值上限、成本超支比、后验 P(SR>0) 低于 0.5 停用）。下列四档与这些已有条目对齐，不改动它们。

| 档 | 进入条件（任一） | 动作 | 回到上一档的条件 |
|---|---|---|---|
| 健康 | z ≥ Z_OK 且回撤分位 < Q_WARN | 按计划规模运行 | - |
| 警告 | z < Z_WARN 连续 N_WARN 个交易日；或回撤分位 ≥ Q_WARN | 不加仓；每日复核，日报标红 | z ≥ Z_OK 且回撤分位 < Q_WARN 连续 M_UP 个交易日 |
| 衰减 | z < Z_DECAY 连续 N_DECAY 个交易日；或回撤分位 ≥ 0.95（已有 halve_dd_percentile）；或 21 日 beta 越界 / 成本超支触发既有规则 | 规模减半，提请主审复核 | z ≥ Z_WARN 且回撤分位 < Q_WARN 连续 M_UP 个交易日 |
| 停用 | z < Z_STOP 连续 N_STOP 个交易日；或回撤分位 ≥ 0.99（已有 stop_dd_percentile）；或后验 P(SR>0) < 0.5（已有）| 停止新开仓并平仓到现金，写失效原因 | 只能由主审重新批准，不自动回升 |

约定：
- 往下转移需要"连续 N 个交易日"（N_WARN < N_DECAY < N_STOP，防止一天噪声触发）；往上回升需要更长的 M_UP（滞回），M_UP > N_DECAY。N_*、M_UP、Z_*、Q_WARN 全部待主审校准。
- 前向样本少于 n_min 个交易日时（待校准，与评判标准的"短窗口不单独一票否决"一致）z 不触发降档，只触发回撤分位和已有硬停止。
- z 的前提是日收益近似独立同分布；日收益有自相关和厚尾，校准时应改用块自助法的 z 或按有效样本数缩放，并用本记录的跟踪差检验"模拟盘 vs 影子"的偏差是否单独构成降档理由。
- 模拟盘与影子的跟踪差持续偏离（日均差或其 z 超限，阈值待校准）时，先按"执行偏差"处理（检查成交价、成交时点、整股取整、现金、数据源），不直接按策略衰减处理。
"""


def render_readme(summary: dict, notes: str) -> str:
    L: list[str] = []
    L += [
        "# 前向记录拼接（T-20261004-70，A1）",
        "",
        f"生成：`scripts/forward_record_t70.py assemble`，数据最后一个交易日 {summary['last_session_in_record']}。"
        "本记录只做记账：不下结论，不改设计，不改评判标准；所有数字由脚本写入 `summary.json`，本文件的表格由同一脚本从 `summary.json` 渲染。",
        "",
        "## 方法",
        "",
        "- 记录起点 2026-09-01。每个候选分三段：**设计时看过**（起点到冻结日）、**样本外影子**（冻结日次日到模拟盘首个成交日的前一天，用冻结规则重算）、**模拟盘**（模拟盘子策略的真实净值收益）。",
        "- 冻结日 = 冻结规则文件首次提交时间之前最后一个已收盘的交易日（收盘按 20:00 UTC 计）。用的文件见下表。另报一版“回测所用数据边界”（回测面板的最后一个交易日）作对照，两者不同的候选在 `summary.json` 的 `alt_boundary_backtest_data` 里。",
        "- 影子引擎：S1/S2/S3 用 `run_h20260927_01_sleeve_combination.sleeve_returns`（冻结的叠加层引擎，与 T-43 同一份），C2 用筛选通道 offset 0（`screen_lane.candidate_returns_for_offset`，与 `returns.sip-repaired-20261002.parquet` 在 2026-09-17 之前逐日一致，最大差 0.0）；成本每单位换手 10 bp，收盘信号、次日开盘成交；面板 `shadow_forward.load_forward_panel`（不设 HOLD_END 上限），数据为 10-02 之后修复过的 SIP 档案。",
        "- v1.2 F1/F2：研究文件 `data/research/book_v12/A1_M0_U3000_F*.parquet`（按 T-43 的口径换成按实现日索引，除以 100 万）。T-43 组合：`run_program_dd30_allocation.path`，权重 S3 0.60 / C2 0.335 / F2 0.12 / F1 0.025 / 借款 0.08，偏移 0，每月第 1 个交易日再平衡，5 bp。",
        "- 模拟盘：`open_composer.cockpit.data.paper.build_paper_report` 的子策略净值（20:00 UTC 标记），第一天相对子策略预算 15000 美元。",
        "- 夏普 = 日超额收益（减 BIL）均值 / 标准差 × √252；不足 20 天只作描述。最大回撤在各段内从 1.0 起复利计算。SPY 为同日期收盘到收盘。",
        "- **前向 z** = (前向日均收益 − 回测日均收益) / (回测日标准差 / √n前向)；回测基准用同一引擎在 2017-10-02..冻结日（全期）和 2024-01-08..冻结日（近期窗口，即冻结合同的 anchor 窗口起点）两版；另报“仅影子”版（同一批前向日只用影子引擎，去掉执行差异）。",
        "- **跟踪差** = 模拟盘日收益 − 同日影子收益；逐日拆为 成交价（成交文件里 `slippage_vs_open_bps` 加权）、成交时点（成交时间 UTC）、影子成本（影子每单位换手扣 10 bp，模拟盘没有）、整股取整（观察日志的闲置现金比例 × 影子收益，估计值）、残差。",
        "- **哈希链** `hash_chain.jsonl`：每行 日期、候选、文件路径、文件 SHA-256、前一行 `chain_hash`、本行 `chain_hash = sha256('|'.join([prev_hash, date, candidate, path, sha256]))`，第一行 prev 为 64 个 0。只登记现有文件；复核命令见文末。",
        "",
        "## 冻结日与依据",
        "",
        "| 候选 | 冻结规则文件（首次提交） | 首次提交时间 UTC | 最后一个已见收盘（提交口径） | 回测数据边界 | 模拟盘首日 |",
        "|---|---|---|---|---|---|",
    ]
    for name, c in summary["candidates"].items():
        f = c["freeze"]
        c0 = c["primary_boundary_commit"]
        L.append(
            f"| {name} | `{f['file']}`（{f['commit']}） | {f['first_commit_utc']} | {c0['last_seen_session']} |"
            f" {c['data_boundary_of_backtest']} | {c['paper']['first_session'] or '无'} |"
        )
    L += [
        "",
        "S1–S3 的提交口径与回测留出边界（`HOLD_END` 2026-09-17）一致。C2 另有规格文件 `strategy_specs/drafts/us_etf_eom_sector_blend_monthly.yaml`（首次提交 2026-09-30 03:48 UTC，最后一个已见收盘 09-29）；主口径取规则模块 `h20260928_20_recent_opt.py`（kept.jsonl 记录 09-28 06:43 UTC），保守版见 `summary.json`。",
        "",
        "## 每候选三段与合计（提交口径）",
        "",
    ]
    L += seg_table(summary, "primary_boundary_commit")
    L += ["", "## 回测数据边界口径（两者不同的候选）", ""]
    L += seg_table(summary, "alt_boundary_backtest_data")
    L += ["", "## 前向 z（提交口径）", ""]
    L += z_table(summary, "primary_boundary_commit")
    L += ["", "## 前向 z（回测数据边界口径）", ""]
    L += z_table(summary, "alt_boundary_backtest_data")
    L += [
        "",
        "z 的前向样本很短（见 n 前向），日收益也不独立，这一列只用来记录，不构成通过或否定的依据。",
        "",
        "## 跟踪差（模拟盘 − 影子）",
        "",
    ]
    L += tracking_table(summary)
    L += tracking_daily_lines(summary)
    L += [
        "",
        "## 一致性核对",
        "",
        "```json",
        json.dumps(summary["consistency_checks"], indent=1, ensure_ascii=False),
        "```",
    ]
    L += [
        "",
        "## 哈希链",
        "",
        f"{summary['hash_chain']['lines']} 行，写入时校验通过={summary['hash_chain']['verified_on_write']}，链头 `{summary['hash_chain']['head']}`。",
    ]
    L += ["", notes.strip(), "", DECAY_RULE]
    L += [
        "## 复现与复核",
        "",
        "```",
        "scripts/run_capped.sh --mem 1.0G -- uv run python scripts/forward_record_t70.py shadow",
        "scripts/run_capped.sh --mem 1.0G -- uv run python scripts/forward_record_t70.py book     # 可选，v1.2 影子重跑",
        "uv run python scripts/forward_record_t70.py assemble /tmp/t70_notes.md",
        "uv run python scripts/forward_record_t70.py verify   # 重算 hash_chain.jsonl",
        "```",
        "",
    ]
    return "\n".join(L)


def stage_assemble(notes_path: str | None) -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    frame, aux = build_series()
    etf = aux["etf"]
    paper = load_paper()
    spy = frame["SPY"]
    rf = frame["RF"]
    last_day = frame.index[-1]
    summary: dict = {
        "task": "T-20261004-70",
        "track_start": TRACK_START,
        "last_session_in_record": str(last_day.date()),
        "engine_note": (
            "S1/S2/S3: run_h20260927_01_sleeve_combination.sleeve_returns (frozen overlay engine), "
            "net 10 bp per unit turnover, close signal -> next open fill; C2: screen_lane offset 0, same cost; "
            "panel = shadow_forward.load_forward_panel (no HOLD_END cap)."
        ),
        "consistency_checks": aux["checks"],
        "candidates": {},
        "calibration_pending": "all thresholds in the decay rule draft are 待主审校准",
    }
    rec_rows = []
    for name, cfg in CANDIDATES.items():
        shadow_ret = frame[name] if name in frame else None
        fz = git_first_commit(cfg["freeze_file"])
        cand: dict = {
            "label": cfg["label"],
            "freeze": {
                **fz,
                "rule": "last session closed (20:00 UTC) at or before the first commit of the frozen rule file",
                "other_files": [git_first_commit(x) for x in cfg.get("other_freeze_files", [])],
            },
            "data_boundary_of_backtest": cfg["data_boundary"],
        }
        shadow_ret = shadow_ret.dropna()
        last_seen = last_seen_session(frame.index, fz["first_commit_utc"])
        # paper
        pap = paper.get(cfg["strategy"]) if cfg.get("strategy") else None
        paper_first = str(pap["first"].date()) if pap is not None else None
        spliced = shadow_ret.copy()
        source = pd.Series("shadow", index=spliced.index, dtype=object)
        if pap is not None:
            pr = pap["ret"]
            spliced.loc[pr.index] = pr
            source.loc[pr.index] = "paper_sleeve_nav"
        cand["paper"] = {
            "first_session": paper_first,
            "last_session": str(pap["ret"].index[-1].date()) if pap is not None else None,
            "start_budget": pap["budget"] if pap is not None else None,
            "first_day_return_basis": "first sleeve NAV against the sleeve budget"
            if pap is not None
            else None,
        }
        primary = candidate_block(name, shadow_ret, spliced, paper_first, last_seen, spy, rf)
        cand["primary_boundary_commit"] = primary
        if cfg["data_boundary"] != last_seen:
            cand["alt_boundary_backtest_data"] = candidate_block(
                name, shadow_ret, spliced, paper_first, cfg["data_boundary"], spy, rf
            )
        # shadow source label per day for record.csv
        shadow_src = "shadow_etf_engine_net10bp"
        if name.startswith("V12"):
            shadow_src = "research_book_v12_parquet"
        if name == "T43":
            shadow_src = "program_path_offset0_5bp_rebalance"
        # record rows
        segs = split_segments(
            pd.DatetimeIndex(spliced.loc[TRACK_START:].index), TRACK_START, last_seen, paper_first
        )
        for seg, ix in segs.items():
            for d in ix:
                src = shadow_src
                if name.startswith("V12"):
                    src = str(aux["book_src"].get(d, shadow_src))
                if source.loc[d] == "paper_sleeve_nav":
                    src = "paper_sleeve_nav"
                rec_rows.append(
                    {
                        "date": str(d.date()),
                        "candidate": name,
                        "segment": seg,
                        "net_return": float(spliced.loc[d]),
                        "source": src,
                        "shadow_return": float(shadow_ret.loc[d]),
                    }
                )
        # tracking difference
        if pap is not None and name in ("S1", "S2", "S3", "C2"):
            rows = tracking_rows(name, cfg["strategy"], pap, etf, name)
            diffs = pd.Series({pd.Timestamp(r["date"]): r["diff"] for r in rows})
            cand["tracking_difference"] = {
                "definition": "paper sleeve NAV return minus same-day shadow engine return",
                "all_paper_days": tracking_stats(diffs),
                "daily": rows,
            }
            if name in ("S2", "S3"):
                pre = pd.Series(
                    {
                        pd.Timestamp(r["date"]): r["diff"]
                        for r in rows
                        if r["pre_renewal_paper_rule"]
                    }
                )
                post = pd.Series(
                    {
                        pd.Timestamp(r["date"]): r["diff"]
                        for r in rows
                        if not r["pre_renewal_paper_rule"]
                    }
                )
                cand["tracking_difference"]["pre_renewal_paper_rule_days"] = tracking_stats(pre)
                cand["tracking_difference"]["post_renewal_days"] = tracking_stats(post)
            if name == "S3":
                sub = pd.Series({pd.Timestamp(r["date"]): r["diff"] for r in rows if r["t55_flip"]})
                oth = pd.Series(
                    {pd.Timestamp(r["date"]): r["diff"] for r in rows if not r["t55_flip"]}
                )
                cand["tracking_difference"]["t55_flip_days"] = tracking_stats(sub)
                cand["tracking_difference"]["other_days"] = tracking_stats(oth)
        summary["candidates"][name] = cand
    # hash chain
    chain = build_chain(hash_entries())
    ok, bad = verify_chain(chain)
    with (OUT_DIR / "hash_chain.jsonl").open("w") as fh:
        for r in chain:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    summary["hash_chain"] = {
        "lines": len(chain),
        "verified_on_write": ok,
        "head": chain[-1]["chain_hash"] if chain else None,
        "formula": "chain_hash = sha256('|'.join([prev_hash, date, candidate, path, sha256]))",
    }
    rec = pd.DataFrame(rec_rows).sort_values(["candidate", "date"])
    rec.to_csv(OUT_DIR / "record.csv", index=False, float_format="%.8f")
    (OUT_DIR / "summary.json").write_text(
        json.dumps(summary, indent=1, default=float, ensure_ascii=False)
    )
    notes = Path(notes_path).read_text() if notes_path and Path(notes_path).exists() else ""
    (OUT_DIR / "README.md").write_text(render_readme(summary, notes))
    print("written", OUT_DIR, "rows", len(rec), "chain", len(chain), ok)
    return 0


if __name__ == "__main__":
    stage = sys.argv[1] if len(sys.argv) > 1 else ""
    if stage == "shadow":
        raise SystemExit(stage_shadow())
    if stage == "book":
        lim = int(sys.argv[2]) if len(sys.argv) > 2 else None
        raise SystemExit(stage_book(lim))
    if stage == "verify":
        rows = [json.loads(x) for x in (OUT_DIR / "hash_chain.jsonl").read_text().splitlines()]
        ok, bad = verify_chain(rows)
        print("chain ok" if ok else f"chain BROKEN at line {bad}", len(rows))
        raise SystemExit(0 if ok else 1)
    if stage == "assemble":
        raise SystemExit(stage_assemble(sys.argv[2] if len(sys.argv) > 2 else None))
    raise SystemExit(f"unknown stage {stage!r}")
