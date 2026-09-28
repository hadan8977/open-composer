"""T-20260928-15: does "an LLM proposes hypotheses, writes factor code, gets IC
feedback" beat our existing factor zoo on our own US data?

Dossier: ``reports/research/iterations/h20260928_15_claude_factor_batch/``
(``direction-review.json`` + ``candidate-manifest.json`` frozen, ``direction-
check`` and ``iteration validate --stage pre-backtest`` pass before this
script computed any result). Reuses ``open_composer.research.signal_card``
(``load_market``, ``load_signal``, ``composite_signal``, ``rank_ic``,
``masked_ranks``, ``rank_corr``, ``topk_cohorts``, ``hold``, ``book_returns``,
``equal_weight``) unmodified; no new simulator.

Method
------
Batch: the 8 (Round 1) + 4 (Round 2, frozen 2026-09-28) Claude-authored
factors, one small parquet per factor in ``data/features/
h20260928_15_claude_factors/`` (built by ``scripts/
build_h20260928_15_claude_factors.py``).

Zoo (symmetric): every numeric column of ``data/features/{alpha101,alpha191,
osap_price}_broad`` plus ``data/features/alpha158`` (the full, 154-column
store; added 2026-09-28 after a coordinator review found the originally-
checked ``alpha158_broad`` incomplete -- that path is a ``_scratch`` build
that never finished past 2016 and stays excluded) plus the existing 27
rank-mode signal cards in ``reports/research/signal-cards/`` (event-mode
cards excluded; a "rank-mode signal" here means a dense cross-sectional
score, matching the brief's "existing rank cards").

For every candidate, both sets alike: sign is fixed from the SELECT window's
own mean rank IC (``sign(mean IC over SELECT)``) -- the zoo cards' own
pre-existing ``direction`` metadata is deliberately ignored, so neither side
gets a head start from having "seen" more than its own SELECT window.

    --window select   Screen everything on SELECT (2016-06-01..2023-12-29)
                       only; writes select-results.json. Never reads or
                       writes anything about the TEST window.
    --window test      Run exactly once, after Round 2 is frozen. Computes
                       TEST (2024-01-02..2026-09-08, aligned to alpha158's
                       coverage ceiling) rank IC/ICIR and the
                       10/20bp top-50 monthly book for the two SELECT-chosen
                       winners (batch, zoo), each set's TEST oracle-best with
                       deflated_sharpe_probability, and max |rank corr| of
                       each batch factor against the whole zoo+cards.

Usage
-----
    scripts/run_capped.sh --mem 1.8G -- uv run python \\
        scripts/run_h20260928_15_factor_batch.py --window select
    scripts/run_capped.sh --mem 1.8G -- uv run python \\
        scripts/run_h20260928_15_factor_batch.py --window test
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from open_composer.research.campaign_statistics import (  # noqa: E402
    deflated_sharpe_probability,
)
from open_composer.research.signal_card import (  # noqa: E402
    Market,
    book_returns,
    composite_signal,
    equal_weight,
    hold,
    load_market,
    load_signal,
    masked_ranks,
    rank_corr,
    topk_cohorts,
)

ITER_ID = "h20260928_15_claude_factor_batch"
OUT_DIR = ROOT / "reports" / "research" / "iterations" / ITER_ID
FEATURES = ROOT / "data" / "features"
BATCH_DIR = FEATURES / "h20260928_15_claude_factors"


def _batch_path(candidate_id: str) -> Path:
    """Each batch factor is its own small parquet (see build_h20260928_15_
    claude_factors.build_all): memory-safe, no wide merge held in memory."""
    return BATCH_DIR / f"{candidate_id}.parquet"


SELECT_WINDOW = ("2016-06-01", "2023-12-29")
# End date aligned to alpha158's coverage ceiling (2026-09-08, one session
# short of the other stores' 2026-09-17) once alpha158 joined the zoo
# (coordinator correction 2026-09-28), so every candidate -- batch and zoo
# alike -- is compared on the identical TEST window, not a per-candidate one.
TEST_WINDOW = ("2024-01-02", "2026-09-08")
TOP_N = 1000
PRIMARY_H = 21
SECONDARY_H = 5
BOOK_TOP_K = 50
BOOK_H = 20  # signal_card's closest built-in horizon to "21d monthly"
BOOK_COST_BPS = (10.0, 20.0)
DSR_HAC_LAG = 21

BATCH_CANDIDATES = [
    "F01_insider_short_confluence",
    "F02_opportunistic_insider_signal",
    "F03_trading_activity_surge",
    "F04_sue_short_confirmation",
    "F05_quality_liquidity_trend",
    "F06_momentum_short_confirmation",
    "F07_accruals_cashflow_confirmation",
    "F08_earnings_recency_gated_insider_buying",
    # Round 2 (preregistered from Round-1 SELECT-only feedback, frozen
    # 2026-09-28 before any TEST number was computed).
    "F09_insider_short_confluence_dollar_weighted",
    "F10_quality_composite_roe_profitability_accruals",
    "F11_momentum_activity_surge_confirmation",
    "F12_post_earnings_insider_buying_bad_news_gate",
]

ZOO_STORES = {
    "alpha101_broad": FEATURES / "alpha101_broad",
    "alpha191_broad": FEATURES / "alpha191_broad",
    "osap_price_broad": FEATURES / "osap_price_broad",
    # data/features/alpha158/ (NOT alpha158_broad, which is the incomplete,
    # 2016-only _scratch build) is the full store: yearly parquet 2016-2026,
    # 154 numeric columns, coverage ends 2026-09-08 -- one session short of
    # the other stores' 2026-09-17. Coordinator correction 2026-09-28: the
    # zoo baseline was missing this, the largest library (154 cols vs 79
    # raw cols across the other three); added before SELECT is fixed.
    "alpha158": FEATURES / "alpha158",
}

# Existing rank-mode signal cards (reports/research/signal-cards/index.jsonl),
# event-mode cards excluded. Each entry reproduces the card's own frozen spec
# exactly (reports/research/signal-cards/*-manifest.json), but WITHOUT the
# card's own preregistered `direction` -- sign is refixed from SELECT here,
# symmetrically with the batch.
ZOO_CARDS: dict[str, dict] = {
    "card_mom_12_1": {"source": "data/features/daily_broad", "column": "momentum_252_21"},
    "card_rev_5d": {"source": "data/features/daily_broad", "column": "ret_5"},
    "card_rev_21d": {"source": "data/features/daily_broad", "column": "ret_21"},
    "card_high_52w": {"source": "data/features/daily_broad", "column": "dist_from_252d_high"},
    "card_idio_vol_63": {"source": "data/features/daily_broad", "column": "idio_vol_63"},
    "card_max_ret_21": {"source": "data/features/daily_broad", "column": "max_ret_1_21"},
    "card_overnight_mom_21": {
        "source": "data/features/daily_broad",
        "column": "overnight_return_21d_mean",
    },
    "card_intraday_rev_21": {
        "source": "data/features/daily_broad",
        "column": "intraday_return_21d_mean",
    },
    "card_resid_mom": {"source": "data/features/osap_price_broad", "column": "residualmom_252_21"},
    "card_season_2_5": {"source": "data/features/osap_price_broad", "column": "momseason_2_5"},
    "card_days_to_cover": {"source": "data/features/short_interest", "column": "days_to_cover"},
    "card_short_vol_z21": {
        "source": "data/features/short_volume_broad",
        "column": "short_volume_ratio_zscore_21",
    },
    "card_news_attention": {
        "source": "data/features/news_attention",
        "column": "attention_surge_5d",
    },
    "card_news_hf_reaction_raw": {
        "source": "data/features/news_hf_reaction",
        "column": "news_return",
    },
    "card_news_hf_reaction_5d_sum": {
        "sql": (
            "WITH r AS (SELECT symbol, trade_date, news_return FROM "
            "read_parquet('data/features/news_hf_reaction/*.parquet')), "
            "cal AS (SELECT DISTINCT symbol, trade_date FROM "
            "read_parquet('data/features/daily_broad/*.parquet')), "
            "dense AS (SELECT cal.symbol, cal.trade_date, COALESCE(r.news_return, 0) "
            "AS news_return FROM cal LEFT JOIN r USING (symbol, trade_date)) "
            "SELECT symbol, trade_date, SUM(news_return) OVER (PARTITION BY symbol "
            "ORDER BY trade_date ROWS BETWEEN 4 PRECEDING AND CURRENT ROW) AS value FROM dense"
        )
    },
    "card_sue_eps_rank_recent": {
        "source": "data/features/sec_fundamentals_daily",
        "column": "sue_eps",
        "where": "days_since_report <= 5",
    },
    "card_sue_rev_rank_recent": {
        "source": "data/features/sec_fundamentals_daily",
        "column": "sue_rev",
        "where": "days_since_report <= 5",
    },
    "card_gross_profitability": {
        "source": "data/features/sec_fundamentals_daily",
        "column": "gross_profitability",
    },
    "card_asset_growth": {
        "source": "data/features/sec_fundamentals_daily",
        "column": "asset_growth",
    },
    "card_accruals": {"source": "data/features/sec_fundamentals_daily", "column": "accruals"},
    "card_roe": {"source": "data/features/sec_fundamentals_daily", "column": "roe"},
    "card_mom_12_1_roe_universe": {
        "sql": (
            "SELECT d.symbol, d.trade_date, d.momentum_252_21 AS value FROM "
            "read_parquet('data/features/daily_broad/*.parquet') d JOIN "
            "read_parquet('data/features/sec_fundamentals_daily/*.parquet', "
            "union_by_name=true) f USING (symbol, trade_date) WHERE f.roe IS NOT NULL"
        )
    },
    "card_comp_c1_mom_quality": {
        "components": [
            {"source": "data/features/daily_broad", "column": "momentum_252_21", "direction": 1},
            {"source": "data/features/daily_broad", "column": "idio_vol_63", "direction": -1},
            {"source": "data/features/daily_broad", "column": "max_ret_1_21", "direction": -1},
            {
                "source": "data/features/daily_broad",
                "column": "dist_from_252d_high",
                "direction": 1,
            },
        ]
    },
    "card_comp_c2_mom_quality_insider": {
        "components": [
            {"source": "data/features/daily_broad", "column": "momentum_252_21", "direction": 1},
            {"source": "data/features/daily_broad", "column": "idio_vol_63", "direction": -1},
            {"source": "data/features/daily_broad", "column": "max_ret_1_21", "direction": -1},
            {
                "source": "data/features/daily_broad",
                "column": "dist_from_252d_high",
                "direction": 1,
            },
            {
                "sql": (
                    "SELECT d.symbol, d.trade_date, CASE WHEN i.buyers_60d >= 2 AND "
                    "i.open_market_buy_count_60d > 0 THEN 1.0 ELSE 0.0 END AS value FROM "
                    "read_parquet('data/features/daily_broad/*.parquet') d LEFT JOIN "
                    "read_parquet('data/features/insider_broad/*.parquet', union_by_name=true) "
                    "i USING (symbol, trade_date)"
                ),
                "direction": 1,
            },
        ]
    },
    "card_comp_c3_mom_52w": {
        "components": [
            {"source": "data/features/daily_broad", "column": "momentum_252_21", "direction": 1},
            {
                "source": "data/features/daily_broad",
                "column": "dist_from_252d_high",
                "direction": 1,
            },
        ]
    },
    "card_comp_c4_mom_roe": {
        "components": [
            {"source": "data/features/daily_broad", "column": "momentum_252_21", "direction": 1},
            {"source": "data/features/sec_fundamentals_daily", "column": "roe", "direction": 1},
        ]
    },
    "card_comp_c5_mom_roe_insider": {
        "components": [
            {"source": "data/features/daily_broad", "column": "momentum_252_21", "direction": 1},
            {"source": "data/features/sec_fundamentals_daily", "column": "roe", "direction": 1},
            {
                "sql": (
                    "SELECT d.symbol, d.trade_date, CASE WHEN i.buyers_60d >= 2 AND "
                    "i.open_market_buy_count_60d > 0 THEN 1.0 ELSE 0.0 END AS value FROM "
                    "read_parquet('data/features/daily_broad/*.parquet') d LEFT JOIN "
                    "read_parquet('data/features/insider_broad/*.parquet', union_by_name=true) "
                    "i USING (symbol, trade_date)"
                ),
                "direction": 1,
            },
        ]
    },
}


def _log(msg: str) -> None:
    print(f"[h20260928_15] {msg}", flush=True)


def _zoo_raw_columns(store: str) -> list[str]:
    con = duckdb.connect()
    con.execute("SET memory_limit='600MB'")
    try:
        glob = str(ZOO_STORES[store] / "*.parquet")
        cols = (
            con.execute(
                f"DESCRIBE SELECT * FROM read_parquet('{glob}', union_by_name=true) LIMIT 0"
            )
            .df()["column_name"]
            .tolist()
        )
    finally:
        con.close()
    return [c for c in cols if c not in ("symbol", "trade_date")]


def _window_mask(dates: pd.DatetimeIndex, window: tuple[str, str]) -> np.ndarray:
    start, end = pd.Timestamp(window[0]), pd.Timestamp(window[1])
    return (dates >= start) & (dates <= end)


def _ic_stats(ic: np.ndarray, dates: pd.DatetimeIndex, window: tuple[str, str]) -> dict:
    m = _window_mask(dates, window)
    s = pd.Series(ic, index=dates)[m].dropna()
    if len(s) < 30:
        return {"n": int(len(s)), "mean": None, "icir": None}
    mean = float(s.mean())
    sd = float(s.std(ddof=1))
    return {"n": int(len(s)), "mean": mean, "icir": (mean / sd) if sd > 0 else None}


def _candidate_signal(market: Market, spec: dict) -> np.ndarray:
    if "components" in spec:
        return composite_signal(market, spec["components"])
    if "sql" in spec:
        return load_signal(market, sql=spec["sql"])
    return load_signal(
        market, source=spec["source"], column=spec["column"], where=spec.get("where")
    )


def _load_candidate(market: Market, cid: str) -> np.ndarray:
    """Dispatch a candidate id to its signal, one of the three families."""
    if cid in BATCH_CANDIDATES:
        return load_signal(market, source=str(_batch_path(cid)), column=cid)
    if cid in ZOO_CARDS:
        return _candidate_signal(market, ZOO_CARDS[cid])
    store, col = cid.removeprefix("zoo_").split("__", 1)
    return load_signal(market, source=str(ZOO_STORES[store]), column=col)


def _simple_book_test_window(
    market: Market,
    signal: np.ndarray,
    direction: int,
    member: np.ndarray,
    ret: np.ndarray,
) -> dict:
    """Lean top-K monthly book (signal_card primitives, no deciles/placebo):
    10bp/20bp Sharpe and the raw daily excess-return series, TEST window only."""
    sig = signal * direction
    cohorts = topk_cohorts(sig, member, BOOK_TOP_K)
    held = hold(cohorts, BOOK_H)
    bench = equal_weight(member, ret)
    mask = _window_mask(market.dates, TEST_WINDOW)
    out: dict = {}
    excess_20bp = None
    for bps in BOOK_COST_BPS:
        net, _turn = book_returns(held, ret, bps)
        net_s = pd.Series(net, index=market.dates)[mask]
        bench_s = pd.Series(bench, index=market.dates)[mask]
        excess = (net_s - bench_s).to_numpy()
        sd = net_s.std()
        years = len(net_s) / 252.0
        cum = (1.0 + net_s).cumprod()
        out[f"{int(bps)}bp"] = {
            "cagr": float(cum.iloc[-1] ** (1.0 / years) - 1.0)
            if cum.iloc[-1] > 0 and years > 0
            else None,
            "sharpe": float(net_s.mean() / sd * math.sqrt(252.0)) if sd > 0 else None,
            "excess_ann": float(excess.mean() * 252.0),
        }
        if bps == 20.0:
            excess_20bp = excess
    out["excess_series_20bp"] = excess_20bp.tolist() if excess_20bp is not None else []
    return out


def scan(market: Market, window: str) -> dict:
    ret = market.next_open_returns()
    member = market.member()
    t0 = time.monotonic()
    fwd21 = market.forward_returns(PRIMARY_H)
    fwd5 = market.forward_returns(SECONDARY_H)
    rf21 = masked_ranks(fwd21, member)
    rf5 = masked_ranks(fwd5, member)
    _log(f"forward-return ranks ready ({time.monotonic() - t0:.0f}s)")

    results: dict[str, dict] = {}
    batch_rank_cache: dict[str, np.ndarray] = {}
    store_coverage: dict[str, list[float]] = {}
    member_count = float(member.sum())

    def evaluate(name: str, signal: np.ndarray) -> dict:
        rs = masked_ranks(signal, member)
        ic21 = rank_corr(rs, rf21, member)
        ic5 = rank_corr(rs, rf5, member)
        select21 = _ic_stats(ic21, market.dates, SELECT_WINDOW)
        row = {"select_21d": select21, "select_5d": _ic_stats(ic5, market.dates, SELECT_WINDOW)}
        sign = 1
        if select21["mean"] is not None and select21["mean"] < 0:
            sign = -1
        row["sign_from_select"] = sign
        if window == "test":
            row["test_21d"] = _ic_stats(ic21, market.dates, TEST_WINDOW)
            row["test_5d"] = _ic_stats(ic5, market.dates, TEST_WINDOW)
        if name in BATCH_CANDIDATES:
            batch_rank_cache[name] = rs
        return row

    # Batch
    for name in BATCH_CANDIDATES:
        sig = load_signal(market, source=str(_batch_path(name)), column=name)
        results[name] = evaluate(name, sig)
        _log(f"batch {name} done ({time.monotonic() - t0:.0f}s)")

    # Zoo raw columns
    for store in ZOO_STORES:
        for col in _zoo_raw_columns(store):
            cid = f"zoo_{store}__{col}"
            try:
                sig = load_signal(market, source=str(ZOO_STORES[store]), column=col)
            except Exception as exc:  # a bad/incompatible column must not kill the scan
                _log(f"zoo {cid} FAILED: {exc!r}")
                continue
            coverage = float(np.isfinite(np.where(member, sig, np.nan)).sum()) / member_count
            store_coverage.setdefault(store, []).append(coverage)
            row = evaluate(cid, sig)
            row["coverage_share_of_universe_name_days"] = coverage
            if window == "test":
                # info-only: max |rank corr| of this zoo column vs every batch factor
                rs = masked_ranks(sig, member)
                corrs = []
                for bname, brs in batch_rank_cache.items():
                    c = rank_corr(brs, rs, member)
                    v = float(np.nanmean(c)) if np.isfinite(c).any() else None
                    if v is not None:
                        corrs.append((bname, abs(v)))
                row["max_abs_corr_vs_batch"] = max(corrs, key=lambda p: p[1]) if corrs else None
            results[cid] = row
            del sig
        mean_cov = float(np.mean(store_coverage.get(store, [0.0])))
        _log(
            f"zoo store {store} done ({time.monotonic() - t0:.0f}s), "
            f"mean coverage {mean_cov:.1%} of universe name-days"
        )

    # Zoo cards
    for name, spec in ZOO_CARDS.items():
        try:
            sig = _candidate_signal(market, spec)
        except Exception as exc:
            _log(f"zoo {name} FAILED: {exc!r}")
            continue
        results[name] = evaluate(name, sig)
        del sig
    _log(f"zoo cards done ({time.monotonic() - t0:.0f}s)")

    store_coverage_mean = {k: float(np.mean(v)) for k, v in store_coverage.items()}
    return {
        "results": results,
        "member": member,
        "ret": ret,
        "store_coverage_mean": store_coverage_mean,
    }


def pick_best(results: dict, ids: list[str], horizon: str = "select_21d") -> str | None:
    scored = [
        (cid, abs(results[cid][horizon]["icir"]))
        for cid in ids
        if cid in results and results[cid][horizon]["icir"] is not None
    ]
    if not scored:
        return None
    return max(scored, key=lambda p: p[1])[0]


def run(window: str) -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    missing = [c for c in BATCH_CANDIDATES if not _batch_path(c).exists()]
    if missing:
        raise SystemExit(
            f"missing batch factor files {missing}; run build_h20260928_15_claude_factors.py first"
        )
    _log(f"loading market top_n={TOP_N} ...")
    market = load_market(top_n=TOP_N, memory_limit="1200MB")
    scanned = scan(market, window)
    results = scanned["results"]

    batch_ids = [c for c in BATCH_CANDIDATES if c in results]
    zoo_ids = [c for c in results if c not in BATCH_CANDIDATES]

    batch_winner = pick_best(results, batch_ids)
    zoo_winner = pick_best(results, zoo_ids)
    _log(f"SELECT-chosen: batch={batch_winner} zoo={zoo_winner}")

    payload = {
        "iter_id": ITER_ID,
        "window": window,
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "universe_top_n": TOP_N,
        "select_window": list(SELECT_WINDOW),
        "test_window": list(TEST_WINDOW),
        "batch_ids": batch_ids,
        "zoo_ids": zoo_ids,
        "batch_select_chosen": batch_winner,
        "zoo_select_chosen": zoo_winner,
        "zoo_store_coverage_mean": scanned["store_coverage_mean"],
        "results": results,
    }

    if window == "test":
        member = scanned["member"]
        ret = scanned["ret"]
        books = {}
        for label, cid in (("batch", batch_winner), ("zoo", zoo_winner)):
            if cid is None:
                continue
            sign = results[cid]["sign_from_select"]
            sig = _load_candidate(market, cid)
            books[label] = {
                "candidate_id": cid,
                **_simple_book_test_window(market, sig, sign, member, ret),
            }
            del sig
        payload["select_chosen_test_books"] = books

        # Oracle-best per set on TEST rank IC, with DSR deflated by set size.
        oracle = {}
        for label, ids in (("batch", batch_ids), ("zoo", zoo_ids)):
            best = pick_best(results, ids, horizon="test_21d")
            if best is None:
                continue
            sign = results[best]["sign_from_select"]
            sig = _load_candidate(market, best)
            book = _simple_book_test_window(market, sig, sign, member, ret)
            excess = np.asarray(book["excess_series_20bp"])
            dsr = None
            if len(excess) > max(DSR_HAC_LAG, 3) and np.isfinite(excess).all() and excess.std() > 0:
                try:
                    dsr = float(
                        deflated_sharpe_probability(
                            excess, trial_count=len(ids), hac_lag=DSR_HAC_LAG
                        )
                    )
                except ValueError:
                    dsr = None
            oracle[label] = {
                "candidate_id": best,
                "test_21d": results[best]["test_21d"],
                "book_20bp": book["20bp"],
                "trial_count": len(ids),
                "dsr_probability": dsr,
            }
            del sig
        payload["oracle_best_per_set"] = oracle

    out_path = OUT_DIR / f"{window}-results.json"
    out_path.write_text(json.dumps(payload, indent=1, default=str) + "\n", encoding="utf-8")
    _log(f"wrote {out_path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--window", choices=("select", "test"), required=True)
    args = ap.parse_args(argv)
    return run(args.window)


if __name__ == "__main__":
    raise SystemExit(main())
