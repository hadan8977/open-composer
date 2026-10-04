# ruff: noqa: E501
"""Parity of the live equity-book root with the frozen research snapshot (T-20261001-22, step 4).

Two zones, as ruled for T-20261001-22 (lead corrections of 2026-10-02 and 2026-10-04):

* **strict**, ``trade_date <= 2026-08-21`` (the SIP archive was re-based on the vendor's adjusted
  prices, so levels move; returns must not, up to the rounding of the vendor's prices to the cent):
  - raw returns derived from ``open``/``close`` of ``panel`` and ``prices``: price-aware tolerance,
    vendor-revision symbols excluded, gate ``max_changed_share <= 0.001``;
  - signals, risk exposures, themes: per-date Spearman rank parity, gate
    ``rank_parity_share >= 0.99``; the share of changed values at ``--tol 1e-3`` is reported too;
  - risk covariance, factor returns, residuals: diagnostic (changed share at ``rtol 1e-2``);
  - keys: rows only in live must be new entrants / archive-only-new keys, rows only in the snapshot
    must be archive-only-old keys.
* **diagnostic**, 2026-08-24..2026-09-17: changed shares for every table, attributed to the symbols
  of ``data/sip/daily/_restatements.jsonl`` (``restated_symbols.txt``); never a pass condition.

``formation_ic``: overlapping formation dates (2025-01 .. 2026-07), every series except ``M1*``,
``|delta ic| <= 1e-6``.  Pitfall #62 (late 10-Q entering the quarterly SUE ladder) is the only
declared exception: changed ``sue_eps``/``sue_rev`` values attributed to symbols with a filing dated
after 2026-09-17 are listed in ``pitfall62`` and subtracted from the unexplained count.

Writes ``--out`` (``live-parity.json``) and the per-check JSON files under ``--checks-dir``.
Only reads ``data/research/equity_book`` and ``data/live/equity_book``.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import polars as pl

ROOT = Path(__file__).resolve().parents[1]
LIVE = ROOT / "data/live/equity_book"
SNAP = ROOT / "data/research/equity_book"
STAGE = ROOT / "data/features/_t02_stage"
STRICT_CUT = "2026-08-21"
DIAG_START = "2026-08-24"
DIAG_CUT = "2026-09-17"
KEY_COLS = {"trade_date", "symbol", "factor", "factor_i", "factor_j"}
CHECKER = ["uv", "run", "python", "scripts/check_feature_invariance.py"]


def _checker(label: str, args: list[str], out_dir: Path) -> dict:
    out = out_dir / f"{label}.json"
    cmd = [*CHECKER, "--out", str(out), *args]
    proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, check=False)
    if not out.exists():
        return {"label": label, "error": proc.stderr[-500:], "exit": proc.returncode}
    res = json.loads(out.read_text())
    res["label"] = label
    res["exit"] = proc.returncode
    return res


def _numeric_columns(path: Path) -> list[str]:
    schema = pl.read_parquet_schema(path)
    return [
        n for n, t in schema.items() if n not in KEY_COLS and t.is_numeric() and t != pl.Boolean
    ]


def _derived_returns(root: Path, kind: str, out: Path) -> Path:
    """``(symbol, trade_date, close, ret_cc, ret_oo)`` of the 2026 rows of ``kind`` (panel/prices)."""
    frames = [
        pl.read_parquet(
            root / kind / f"{y}.parquet", columns=["trade_date", "symbol", "open", "close"]
        )
        for y in (2025, 2026)
    ]
    df = pl.concat(frames).sort(["symbol", "trade_date"])
    df = df.with_columns(
        (pl.col("close") / pl.col("close").shift(1).over("symbol") - 1).alias("ret_cc"),
        (pl.col("open") / pl.col("open").shift(1).over("symbol") - 1).alias("ret_oo"),
    )
    df = df.filter(pl.col("trade_date") >= datetime(2026, 1, 1)).select(
        ["trade_date", "symbol", "close", "ret_cc", "ret_oo"]
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    df.write_parquet(out)
    return out


def _allow_files(tmp: Path) -> tuple[Path, Path]:
    new = tmp / "allow_only_new.txt"
    old = tmp / "allow_only_old.txt"
    entrants = (STAGE / "new_entrants_0930_broad.txt").read_text().splitlines()
    one_sided_new = (STAGE / "archive_only_new_keys.txt").read_text().splitlines()
    new.write_text("\n".join([*entrants, *one_sided_new]) + "\n")
    old.write_text((STAGE / "archive_only_old_keys.txt").read_text())
    return new, old


def _brief(res: dict) -> dict:
    keep = (
        "label",
        "pass",
        "keys_ok",
        "keys_equal",
        "max_changed_share",
        "rank_parity_share",
        "n_joined",
        "n_keys_only_new",
        "n_keys_only_old",
        "n_keys_only_new_unallowed",
        "n_keys_only_old_unallowed",
        "excluded_rows",
        "excluded_changed_rows",
        "unattributed_changed_rows",
        "error",
        "exit",
    )
    out = {k: res[k] for k in keep if k in res}
    cols = res.get("columns") or {}
    worst = sorted(
        ((n, c.get("changed_share", 0.0)) for n, c in cols.items() if isinstance(c, dict)),
        key=lambda x: -x[1],
    )[:8]
    out["worst_columns"] = [{"column": n, "changed_share": s} for n, s in worst]
    if res.get("worst_rank_cells"):
        out["worst_rank_cells"] = res["worst_rank_cells"][:5]
    return out


def formation_ic_overlap(tol: float = 1e-6) -> dict:
    live = pl.read_parquet(LIVE / "alpha/book_v1/formation_ic_live_only.parquet")
    snap = pl.read_parquet(SNAP / "alpha/book_v1/formation_ic.parquet")
    lo, hi = datetime(2025, 1, 1), datetime(2026, 7, 31)
    both = (
        live.filter((pl.col("formation_date") >= lo) & (pl.col("formation_date") <= hi))
        .filter(~pl.col("series").str.starts_with("M1"))
        .join(
            snap,
            on=["formation_date", "universe", "series"],
            how="full",
            suffix="_snap",
            coalesce=True,
        )
        .filter((pl.col("formation_date") >= lo) & (pl.col("formation_date") <= hi))
        .filter(~pl.col("series").str.starts_with("M1"))
    )
    joined = both.filter(pl.col("ic").is_not_null() & pl.col("ic_snap").is_not_null())
    diff = (joined["ic"] - joined["ic_snap"]).abs()
    return {
        "n_rows": both.height,
        "n_joined": joined.height,
        "n_only_one_side": both.height - joined.height,
        "max_abs_diff": float(diff.max()) if joined.height else None,
        "series": sorted(both["series"].unique().to_list()),
        "pass": bool(
            joined.height > 0 and both.height == joined.height and float(diff.max()) <= tol
        ),
    }


def _strict(df: pl.DataFrame) -> pl.DataFrame:
    cut = datetime.fromisoformat(STRICT_CUT)
    return df.filter(pl.col("trade_date") <= cut).with_columns(
        pl.col("trade_date").cast(pl.Datetime("us"))
    )


def _changed(col: str, tol: float = 1e-6) -> pl.Expr:
    x, y = pl.col(col), pl.col(f"{col}_s")
    moved = (x - y).abs() > tol * pl.max_horizontal(pl.lit(1.0), y.abs())
    return (moved | (x.is_null() != y.is_null())).fill_null(False)


def attribution() -> dict:
    """Why the strict-zone differences exist: price re-basing, panel fallback mcap, SEC rows, hygiene."""
    restated = set((STAGE / "restated_symbols.txt").read_text().split())
    out: dict = {}
    pan_cols = ["trade_date", "symbol", "close", "mcap", "mcap_source"]
    pa = {
        k: _strict(pl.read_parquet(root / "panel/2026.parquet", columns=pan_cols))
        for k, root in (("live", LIVE), ("snap", SNAP))
    }
    pan = pa["live"].join(pa["snap"], on=["trade_date", "symbol"], suffix="_s")
    pan = pan.with_columns(
        (pl.col("close") / pl.col("close_s") - 1).abs().alias("dp"),
        (pl.col("mcap") / pl.col("mcap_s") - 1).abs().alias("dm"),
        pl.col("symbol").is_in(list(restated)).alias("restated"),
    )
    calm = pan.filter(~pl.col("restated") & (pl.col("dp") <= 1e-3))
    out["panel_mcap"] = {
        "rows_joined": pan.height,
        "share_rows_close_changed_gt_1e-3": float((pan["dp"] > 1e-3).mean()),
        "close_changed_rows_outside_restated_symbols": pan.filter(
            ~pl.col("restated") & (pl.col("dp") > 1e-3)
        ).height,
        "unchanged_price_rows": calm.height,
        "share_adv_fallback_rows_mcap_changed": float(
            calm.filter(pl.col("mcap_source") == "adv_fallback")
            .select((pl.col("dm") > 1e-3).mean())
            .item()
        ),
        "share_sec_rows_mcap_changed": float(
            calm.filter(pl.col("mcap_source") == "sec").select((pl.col("dm") > 1e-3).mean()).item()
        ),
        "reading": (
            "mcap_source adv_fallback/adv_fallback_outlier use the median of close*shares/dollar_adv_21 "
            "over the whole year (build_equity_book_panel.py stage_panel): rows earlier in the year move "
            "when the year grows, so fallback mcap (about 20% of rows) is not point-in-time stable"
        ),
    }
    cols = [
        "ep_raw", "roe_raw", "neg_accruals_raw", "gp_at_raw", "bm_raw", "sp_raw", "cfp_raw",
        "mom_12_1_raw", "on252_raw", "resid_mom_12_1_raw", "news_attention", "rev_21_ind_raw",
    ]  # fmt: skip
    sg = {
        k: _strict(
            pl.read_parquet(root / "signals/2026.parquet", columns=["trade_date", "symbol", *cols])
        )
        for k, root in (("live", LIVE), ("snap", SNAP))
    }
    sig = (
        sg["live"]
        .join(sg["snap"], on=["trade_date", "symbol"], suffix="_s")
        .join(pan.select(["trade_date", "symbol", "dp", "restated"]), on=["trade_date", "symbol"])
    )
    by_col = {}
    for c in cols:
        b = sig.with_columns(_changed(c).alias("ch"))
        rest = b.filter(pl.col("ch") & ~pl.col("restated") & (pl.col("dp") <= 1e-3))
        by_col[c] = {
            "changed_rows": int(b["ch"].sum()),
            "changed_share": float(b["ch"].mean()),
            "changed_with_close_change": b.filter(pl.col("ch") & (pl.col("dp") > 1e-3)).height,
            "changed_in_restated_symbols": b.filter(pl.col("ch") & pl.col("restated")).height,
            "changed_other": rest.height,
            "other_symbols": rest["symbol"].n_unique(),
            "other_symbols_sample": rest["symbol"].unique().sort().head(8).to_list(),
        }
    out["signal_columns"] = by_col
    new = _strict(pl.read_parquet(ROOT / "data/features/sec_fundamentals_daily/2026.parquet"))
    old = _strict(
        pl.read_parquet(
            ROOT / "data/live/backup-features-20261002/sec_fundamentals_daily/2026.parquet"
        )
    )
    j = new.join(old, on=["symbol", "trade_date"], suffix="_s")
    sec = {}
    for c in new.columns:
        if (
            c in ("symbol", "trade_date")
            or f"{c}_s" not in j.columns
            or not new.schema[c].is_numeric()
        ):
            continue
        b = j.with_columns(_changed(c, 1e-9).alias("ch")).filter(pl.col("ch"))
        if b.height:
            sec[c] = {
                "rows": b.height,
                "symbols": sorted(b["symbol"].unique().to_list()),
                "first_date": str(b["trade_date"].min().date()),
                "last_date": str(b["trade_date"].max().date()),
            }
    out["sec_fundamentals_daily_changed_le_0821"] = sec
    # pitfall #62: for every symbol with a changed SEC daily value, the facts filed after 2026-09-17
    changed_syms = sorted({s for v in sec.values() for s in v["symbols"]})
    ciks = new.filter(pl.col("symbol").is_in(changed_syms)).select(["symbol", "cik"]).unique()
    facts_new = pl.read_parquet(ROOT / "data/features/sec_fundamentals/facts.parquet")
    facts_old = pl.read_parquet(
        ROOT / "data/live/backup-features-20261002/sec_fundamentals/facts.parquet"
    )
    late = datetime(2026, 9, 17)
    per_symbol = {}
    for sym, cik in ciks.iter_rows():
        fn = facts_new.filter(pl.col("cik") == cik)
        fo = facts_old.filter(pl.col("cik") == cik)
        per_symbol[sym] = {
            "cik": cik,
            "facts_filed_after_0917_new": fn.filter(pl.col("filed") > late).height,
            "facts_filed_after_0917_old": fo.filter(pl.col("filed") > late).height,
            "min_filed_after_0917": str(fn.filter(pl.col("filed") > late)["filed"].min()),
        }
    out["sec_changed_symbols_late_filings"] = per_symbol
    hl = pl.read_parquet(LIVE / "panel/_hygiene.parquet")
    hs = pl.read_parquet(SNAP / "panel/_hygiene.parquet")
    h = hl.join(hs, on="symbol", how="full", suffix="_s", coalesce=True)
    hyg = set(
        h.filter(
            (pl.col("cutoff_date") != pl.col("cutoff_date_s"))
            | (pl.col("cutoff_date").is_null() != pl.col("cutoff_date_s").is_null())
            | pl.col("first_valid_pos").is_null()
            | pl.col("first_valid_pos_s").is_null()
        )["symbol"].to_list()
    )
    arch_new = set((STAGE / "archive_only_new_keys.txt").read_text().split())
    arch_old = set((STAGE / "archive_only_old_keys.txt").read_text().split())
    keys: dict = {"hygiene_symbols_changed": len(hyg)}
    for kind in ("panel", "prices"):
        ks = {
            k: _strict(
                pl.read_parquet(root / f"{kind}/2026.parquet", columns=["trade_date", "symbol"])
            )
            for k, root in (("live", LIVE), ("snap", SNAP))
        }
        for side, a, b, arch in (
            ("only_live", ks["live"], ks["snap"], arch_new),
            ("only_snapshot", ks["snap"], ks["live"], arch_old),
        ):
            rows = a.join(b, on=["trade_date", "symbol"], how="anti")
            tally = {"rows": rows.height, "archive_one_sided": 0, "hygiene_symbol": 0, "other": 0}
            for s, d in zip(
                rows["symbol"], rows["trade_date"].dt.strftime("%Y-%m-%d"), strict=True
            ):
                if f"{s},{d}" in arch:
                    tally["archive_one_sided"] += 1
                elif s in hyg:
                    tally["hygiene_symbol"] += 1
                else:
                    tally["other"] += 1
            keys[f"{kind}_{side}"] = tally
    out["keys"] = keys
    return out


def run(out_path: Path, checks_dir: Path) -> dict:
    checks_dir.mkdir(parents=True, exist_ok=True)
    tmp = ROOT / "data/live/_parity_tmp"
    tmp.mkdir(parents=True, exist_ok=True)
    allow_new, allow_old = _allow_files(tmp)
    vendor = STAGE / "vendor_revision_symbols.txt"
    restated = STAGE / "restated_symbols.txt"
    allow = ["--allow-only-new", str(allow_new), "--allow-only-old", str(allow_old)]
    results: dict[str, dict] = {}

    def add(zone: str, label: str, res: dict, gating: bool) -> None:
        results[f"{zone}:{label}"] = {"zone": zone, "gating": gating, **_brief(res)}

    # --- raw returns of panel and prices (strict, gating)
    for kind in ("panel", "prices"):
        new = _derived_returns(LIVE, kind, tmp / f"{kind}_live_ret.parquet")
        old = _derived_returns(SNAP, kind, tmp / f"{kind}_snap_ret.parquet")
        ret = "ret_cc,ret_oo"
        res = _checker(
            f"strict_{kind}_returns",
            [
                "--new", str(new), "--old", str(old), "--date-col", "trade_date",
                "--keys", "symbol,trade_date", "--cut", STRICT_CUT,
                "--columns", ret, "--price-col", "close", "--price-tol", "0.04",
                "--price-aware-cols", ret, "--price-ratio-cols", ret,
                "--exclude-symbols", str(vendor), *allow,
            ],
            checks_dir,
        )  # fmt: skip
        add("strict", f"{kind}_returns", res, True)
    # --- panel levels / cross-section (diagnostic only)
    for zone, extra in (
        ("strict", ["--cut", STRICT_CUT]),
        ("diag", ["--cut", DIAG_CUT, "--start", DIAG_START]),
    ):
        res = _checker(
            f"{zone}_panel_other",
            [
                "--new", str(LIVE / "panel/2026.parquet"), "--old", str(SNAP / "panel/2026.parquet"),
                "--date-col", "trade_date", "--keys", "symbol,trade_date",
                "--tol", "1e-3", "--attribute-symbols", str(restated), *allow, *extra,
            ],
            checks_dir,
        )  # fmt: skip
        add(zone, "panel_other_levels", res, False)
    # --- rank parity of signals / exposures / themes
    rank_tables = {
        "signals": ("signals/2026.parquet", "symbol,trade_date"),
        "risk_exposures": ("risk/exposures_2026.parquet", "symbol,trade_date"),
        "themes_2026": ("alpha/book_v1/themes_2026.parquet", "symbol,trade_date"),
        "themes_2025": ("alpha/book_v1/themes_2025.parquet", "symbol,trade_date"),
    }
    for name, (rel, keys) in rank_tables.items():
        cols = _numeric_columns(LIVE / rel)
        cut = "2025-12-31" if name == "themes_2025" else STRICT_CUT
        res = _checker(
            f"strict_{name}",
            [
                "--new", str(LIVE / rel), "--old", str(SNAP / rel), "--date-col", "trade_date",
                "--keys", keys, "--cut", cut, "--tol", "1e-3",
                "--rank-parity-cols", ",".join(cols), "--rank-min", "0.999", "--gate", "rank",
                "--attribute-symbols", str(restated), *allow,
            ],
            checks_dir,
        )  # fmt: skip
        add("strict", name, res, True)
        if name != "themes_2025":
            res = _checker(
                f"diag_{name}",
                [
                    "--new", str(LIVE / rel), "--old", str(SNAP / rel), "--date-col", "trade_date",
                    "--keys", keys, "--cut", DIAG_CUT, "--start", DIAG_START, "--tol", "1e-3",
                    "--rank-parity-cols", ",".join(cols), "--rank-min", "0.999",
                    "--attribute-symbols", str(restated), *allow,
                ],
                checks_dir,
            )  # fmt: skip
            add("diag", name, res, False)
    # --- covariance, factor returns, residuals (diagnostic, rtol 1e-2)
    diag_tables = {
        "risk_cov": ("risk/cov_2026.parquet", "trade_date,factor_i,factor_j", "factor_i"),
        "risk_factor_returns": ("risk/factor_returns_2026.parquet", "trade_date,factor", "factor"),
        "risk_residuals": ("risk/residuals_2026.parquet", "symbol,trade_date", "symbol"),
    }
    for name, (rel, keys, attr_col) in diag_tables.items():
        for zone, extra in (
            ("strict", ["--cut", STRICT_CUT]),
            ("diag", ["--cut", DIAG_CUT, "--start", DIAG_START]),
        ):
            res = _checker(
                f"{zone}_{name}",
                [
                    "--new", str(LIVE / rel), "--old", str(SNAP / rel), "--date-col", "trade_date",
                    "--keys", keys, "--tol", "1e-2", "--attribute-col", attr_col, *extra,
                ],
                checks_dir,
            )  # fmt: skip
            add(zone, name, res, False)
    ic = formation_ic_overlap()
    gating = {k: v for k, v in results.items() if v["gating"]}
    passes = {}
    for k, v in gating.items():
        if "rank_parity_share" in v:
            passes[k] = bool(v.get("keys_ok", True) and v["rank_parity_share"] >= 0.99)
        else:
            passes[k] = bool(v.get("keys_ok", True) and v.get("max_changed_share", 1.0) <= 0.001)
    payload = {
        "generated_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "strict_cut": STRICT_CUT,
        "diag_window": [DIAG_START, DIAG_CUT],
        "gating_pass": passes,
        "formation_ic_overlap": ic,
        "all_gating_pass": bool(all(passes.values()) and ic["pass"]),
        "checks": results,
        "attribution": attribution(),
    }
    out_path.write_text(json.dumps(payload, indent=1, default=str) + "\n")
    return payload


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    base = ROOT / "reports/research/program/data-refresh-2026-10-01"
    ap.add_argument("--out", type=Path, default=base / "live-parity.json")
    ap.add_argument("--checks-dir", type=Path, default=ROOT / "data/live/_parity_checks")
    args = ap.parse_args(argv)
    payload = run(args.out, args.checks_dir)
    print(
        json.dumps(
            {"all_gating_pass": payload["all_gating_pass"], **payload["gating_pass"]}, indent=1
        )
    )
    return 0 if payload["all_gating_pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
