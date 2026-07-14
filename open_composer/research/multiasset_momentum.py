from __future__ import annotations

import json
import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

import numpy as np
import pandas as pd

from open_composer.adapters.data.longbridge import (
    fetch_longbridge_bars,
    longbridge_cache_path,
    longbridge_materialized_history_path,
)
from open_composer.adapters.data.sample import normalize_ohlcv
from open_composer.analytics import build_performance_metrics
from open_composer.config import ensure_dir, project_root
from open_composer.storage import append_jsonl, write_json

ITER_ID = "mom_multiasset_r1"
OUTPUT_DIR = Path("reports/research/iterations") / ITER_ID
DATA_DIR = Path("data/research/multiasset_momentum")
NASDAQ_SCREENER_URL = (
    "https://api.nasdaq.com/api/screener/stocks?tableonly=true&limit=25&offset=0&download=true"
)
ETF_TREND_UNIVERSE = ("SPY", "QQQ", "IWM", "DIA", "XLK", "SMH", "GLD", "TLT")
SECTOR_ETF_UNIVERSE = (
    "XLB",
    "XLC",
    "XLE",
    "XLF",
    "XLI",
    "XLK",
    "XLP",
    "XLRE",
    "XLU",
    "XLV",
    "XLY",
)
BENCHMARK_SYMBOLS = ("SPY", "QQQ", "XLK", "BIL")
ALL_ETF_SYMBOLS = tuple(
    dict.fromkeys((*ETF_TREND_UNIVERSE, *SECTOR_ETF_UNIVERSE, *BENCHMARK_SYMBOLS))
)
SYMBOL_RE = re.compile(r"^[A-Z]{1,5}$")
EXCLUDED_NAME_MARKERS = (
    " ETF",
    " ETN",
    " WARRANT",
    " WTS",
    " UNIT",
    " RIGHTS",
    " PREFERRED",
    " DEPOSITARY",
    " ACQUISITION CORP",
)
TRADING_DAYS = 252
DEFAULT_COST_BPS = 10.0


@dataclass(frozen=True)
class UniverseResult:
    snapshot_path: Path
    manifest_path: Path
    selected_symbols: tuple[str, ...]
    payload: dict[str, Any]


@dataclass(frozen=True)
class ResearchResult:
    evaluation_path: Path
    markdown_path: Path
    trial_ledger_path: Path
    payload: dict[str, Any]


def materialize_multiasset_universe(
    root: Path | None = None,
    *,
    download_limit: int = 60,
    final_limit: int = 40,
    refresh: bool = True,
) -> UniverseResult:
    base = root or project_root()
    output = ensure_dir(base / OUTPUT_DIR)
    data_dir = ensure_dir(base / DATA_DIR)
    rows = _download_nasdaq_snapshot()
    snapshot_payload = {
        "report_type": "nasdaq_current_universe_snapshot",
        "generated_at": datetime.now(UTC).isoformat(),
        "source_url": NASDAQ_SCREENER_URL,
        "record_count": len(rows),
        "rows": rows,
    }
    snapshot_path = data_dir / "nasdaq-current-stock-snapshot.json"
    write_json(snapshot_path, snapshot_payload)

    eligible = [_normalized_security(row) for row in rows]
    eligible = [row for row in eligible if row is not None]
    eligible.sort(
        key=lambda row: (float(row["market_cap"]), float(row["snapshot_dollar_volume"])),
        reverse=True,
    )
    download_candidates = _sector_capped(eligible, download_limit, per_sector=12)
    fetch_rows = []
    for row in download_candidates:
        fetch_rows.append(_fetch_quality_row(base, row, refresh=refresh, is_etf=False))
    etf_rows = [
        _fetch_quality_row(
            base,
            {
                "symbol": symbol,
                "name": symbol,
                "sector": "ETF",
                "industry": "ETF",
                "market_cap": 0.0,
                "snapshot_price": 0.0,
                "snapshot_volume": 0.0,
                "snapshot_dollar_volume": 0.0,
            },
            refresh=refresh,
            is_etf=True,
        )
        for symbol in ALL_ETF_SYMBOLS
    ]
    quality_pass = [row for row in fetch_rows if row["quality_pass"]]
    quality_pass.sort(
        key=lambda row: (
            float(row["median_dollar_volume_60"]),
            float(row["market_cap"]),
        ),
        reverse=True,
    )
    selected = _sector_capped(quality_pass, final_limit, per_sector=8)
    selected_symbols = tuple(str(row["symbol"]) for row in selected)
    payload = {
        "report_type": "multiasset_momentum_universe_manifest",
        "iter_id": ITER_ID,
        "generated_at": datetime.now(UTC).isoformat(),
        "snapshot_path": _relpath(snapshot_path, base),
        "snapshot_sha256": _sha256_file(snapshot_path),
        "parent_record_count": len(rows),
        "typed_eligible_count": len(eligible),
        "download_candidate_count": len(download_candidates),
        "quality_pass_count": len(quality_pass),
        "selected_count": len(selected),
        "selection_contract": {
            "country": "United States",
            "symbol_pattern": SYMBOL_RE.pattern,
            "minimum_price": 10.0,
            "minimum_market_cap": 5_000_000_000.0,
            "minimum_snapshot_volume": 500_000.0,
            "minimum_records": 900,
            "minimum_median_dollar_volume_60": 50_000_000.0,
            "maximum_missing_return_ratio": 0.02,
            "download_limit": download_limit,
            "final_limit": final_limit,
            "maximum_per_sector": 8,
        },
        "survivorship_contract": {
            "historical_status": "exploratory_current_universe_history",
            "formal_evidence_start": "2026-07-14",
            "point_in_time_membership_available": False,
            "paper_use": "frozen_forward_universe_only",
        },
        "selected_symbols": list(selected_symbols),
        "sector_counts": dict(Counter(str(row["sector"]) for row in selected)),
        "selected": selected,
        "download_candidates": fetch_rows,
        "etfs": etf_rows,
        "errors": [
            {"symbol": row["symbol"], "error": row.get("error")}
            for row in [*fetch_rows, *etf_rows]
            if row.get("error")
        ],
    }
    manifest_path = output / "universe-manifest.json"
    write_json(manifest_path, payload)
    return UniverseResult(snapshot_path, manifest_path, selected_symbols, payload)


def run_multiasset_momentum_research(
    root: Path | None = None,
    *,
    cost_bps: float = DEFAULT_COST_BPS,
) -> ResearchResult:
    base = root or project_root()
    output = ensure_dir(base / OUTPUT_DIR)
    manifest_path = output / "universe-manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError("run multiasset universe materialization before research")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    stock_symbols = [str(symbol) for symbol in manifest["selected_symbols"]]
    if len(stock_symbols) < 10:
        raise ValueError("multiasset research requires at least 10 quality-passed stocks")
    sector_map = {
        str(row["symbol"]): str(row.get("sector") or "Unknown") for row in manifest["selected"]
    }
    symbols = list(dict.fromkeys((*stock_symbols, *ALL_ETF_SYMBOLS)))
    data = _load_panels(base, symbols)
    candidate_specs = _candidate_specs()
    if len(candidate_specs) != 60:
        raise AssertionError("registered deterministic search must contain exactly 60 candidates")
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    trial_rows = []
    for spec in candidate_specs:
        result = _evaluate_candidate(
            spec,
            data,
            stock_symbols=stock_symbols,
            sector_map=sector_map,
            cost_bps=cost_bps,
        )
        trial_rows.append(
            {
                "run_id": run_id,
                "iter_id": ITER_ID,
                "status": "complete",
                **spec,
                **result,
            }
        )
    trial_ledger_path = output / "trial-ledger.jsonl"
    append_jsonl(trial_ledger_path, trial_rows)
    by_path: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in trial_rows:
        by_path[str(row["path"])].append(row)
    selections = []
    for path, rows in sorted(by_path.items()):
        ordered = sorted(rows, key=lambda row: float(row["selection_score"]), reverse=True)
        survivor = next((row for row in ordered if row["acceptance"]["passed"]), ordered[0])
        survivor_spec = next(
            spec for spec in candidate_specs if spec["trial_id"] == survivor["trial_id"]
        )
        cost_stress = {
            str(int(stress_cost)): _evaluate_candidate(
                survivor_spec,
                data,
                stock_symbols=stock_symbols,
                sector_map=sector_map,
                cost_bps=stress_cost,
            )["metrics"]["out_of_sample"]
            for stress_cost in [5.0, 10.0, 20.0]
        }
        selections.append(
            {
                "path": path,
                "trial_id": survivor["trial_id"],
                "decision": "continue" if survivor["acceptance"]["passed"] else "diagnostic_only",
                "params": survivor["params"],
                "metrics": survivor["metrics"],
                "acceptance": survivor["acceptance"],
                "cost_stress_bps": cost_stress,
            }
        )
    payload = {
        "report_type": "multiasset_momentum_deterministic_evaluation",
        "iter_id": ITER_ID,
        "run_id": run_id,
        "generated_at": datetime.now(UTC).isoformat(),
        "workflow_pass": True,
        "research_pass": False,
        "paper_ready_pass": False,
        "llm_contribution_pass": False,
        "data_profile": {
            "provider": "longbridge",
            "feed": "nasdaq_basic",
            "adjusted": True,
            "data_as_of": data["data_as_of"],
            "stock_universe_status": "current_snapshot_exploratory_history",
            "manifest_path": _relpath(manifest_path, base),
        },
        "candidate_count": len(trial_rows),
        "cost_bps_one_way": cost_bps,
        "search_cap_respected": len(trial_rows) <= 60,
        "selections": selections,
        "path_summary": {
            path: {
                "candidate_count": len(rows),
                "accepted_count": sum(bool(row["acceptance"]["passed"]) for row in rows),
                "best_trial_id": max(rows, key=lambda row: float(row["selection_score"]))[
                    "trial_id"
                ],
            }
            for path, rows in sorted(by_path.items())
        },
        "benchmark_contract": [
            "equal_weight_universe",
            "SPY",
            "sector_or_theme_proxy",
            "BIL",
            "ex_post_best_symbol",
        ],
        "limitations": [
            (
                "Stock history uses a universe selected from the 2026-07-14 snapshot "
                "and is survivorship-biased."
            ),
            (
                "Historical stock results can eliminate designs but cannot independently "
                "establish research_pass."
            ),
            "Longbridge Nasdaq Basic is not consolidated SIP market data.",
            (
                "Virtual-paper forward evidence must remain frozen and must not be used "
                "for informal retuning."
            ),
        ],
        "trial_ledger_path": _relpath(trial_ledger_path, base),
    }
    evaluation_path = output / "evaluation-report.json"
    markdown_path = output / "evaluation-report.md"
    write_json(evaluation_path, payload)
    markdown_path.write_text(_render_evaluation_markdown(payload), encoding="utf-8")
    cost_table = {
        "report_type": "multiasset_momentum_cost_table",
        "one_way_bps_scenarios": [5.0, 10.0, 20.0],
        "base_case_bps": cost_bps,
        "model": "turnover_times_one_way_cost",
        "notes": [
            (
                "Broker commissions are assumed zero; spread, slippage and market impact "
                "remain in bps."
            ),
            "Final virtual sleeves must also report capacity versus median dollar volume.",
        ],
    }
    write_json(output / "cost-table.json", cost_table)
    return ResearchResult(evaluation_path, markdown_path, trial_ledger_path, payload)


def _download_nasdaq_snapshot() -> list[dict[str, Any]]:
    request = Request(
        NASDAQ_SCREENER_URL,
        headers={
            "User-Agent": "Mozilla/5.0 OpenComposer/1.0",
            "Accept": "application/json",
        },
    )
    with urlopen(request, timeout=30) as response:  # noqa: S310 - fixed official URL
        payload = json.load(response)
    rows = payload.get("data", {}).get("rows", [])
    if not isinstance(rows, list) or len(rows) < 1000:
        raise ValueError("Nasdaq screener response is missing the expected broad universe")
    return [row for row in rows if isinstance(row, dict)]


def _normalized_security(row: dict[str, Any]) -> dict[str, Any] | None:
    symbol = str(row.get("symbol") or "").strip().upper()
    name = str(row.get("name") or "").strip()
    country = str(row.get("country") or "").strip()
    if country != "United States" or not SYMBOL_RE.fullmatch(symbol):
        return None
    upper_name = name.upper()
    if any(marker in upper_name for marker in EXCLUDED_NAME_MARKERS):
        return None
    price = _number(row.get("lastsale"))
    volume = _number(row.get("volume"))
    market_cap = _number(row.get("marketCap"))
    if price < 10 or volume < 500_000 or market_cap < 5_000_000_000:
        return None
    return {
        "symbol": symbol,
        "name": name,
        "sector": str(row.get("sector") or "Unknown").strip() or "Unknown",
        "industry": str(row.get("industry") or "Unknown").strip() or "Unknown",
        "market_cap": market_cap,
        "snapshot_price": price,
        "snapshot_volume": volume,
        "snapshot_dollar_volume": price * volume,
    }


def _sector_capped(
    rows: list[dict[str, Any]],
    limit: int,
    *,
    per_sector: int,
) -> list[dict[str, Any]]:
    selected = []
    counts: Counter[str] = Counter()
    for row in rows:
        sector = str(row.get("sector") or "Unknown")
        if counts[sector] >= per_sector:
            continue
        selected.append(row)
        counts[sector] += 1
        if len(selected) >= limit:
            break
    return selected


def _fetch_quality_row(
    root: Path,
    row: dict[str, Any],
    *,
    refresh: bool,
    is_etf: bool,
) -> dict[str, Any]:
    symbol = str(row["symbol"])
    error = None
    try:
        frame = fetch_longbridge_bars(
            root=root,
            symbol=symbol,
            timeframe="daily",
            start=None,
            end=None,
            use_cache=not refresh,
            adjusted=True,
        )
    except Exception as exc:
        error = str(exc)
        try:
            frame = fetch_longbridge_bars(
                root=root,
                symbol=symbol,
                timeframe="daily",
                start=None,
                end=None,
                use_cache=True,
                adjusted=True,
            )
        except Exception as fallback_exc:
            return {
                **row,
                "is_etf": is_etf,
                "quality_pass": False,
                "records": 0,
                "error": f"{error}; cache fallback: {fallback_exc}",
            }
    frame = frame.copy()
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
    for column in ["open", "close", "volume"]:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    valid = frame.dropna(subset=["open", "close", "volume"]).sort_values("timestamp")
    dollar_volume = valid["close"] * valid["volume"]
    missing_return_ratio = float(valid["close"].pct_change().isna().mean())
    records = len(valid)
    median_dollar_volume = float(dollar_volume.tail(60).median()) if records else 0.0
    quality_pass = bool(
        records >= 900
        and valid["open"].gt(0).all()
        and valid["close"].gt(0).all()
        and missing_return_ratio <= 0.02
        and (is_etf or median_dollar_volume >= 50_000_000)
    )
    return {
        **row,
        "is_etf": is_etf,
        "quality_pass": quality_pass,
        "records": records,
        "first_timestamp": valid["timestamp"].min().isoformat() if records else None,
        "last_timestamp": valid["timestamp"].max().isoformat() if records else None,
        "median_dollar_volume_60": round(median_dollar_volume, 2),
        "missing_return_ratio": round(missing_return_ratio, 8),
        "source_mode": frame.attrs.get("data_source_mode"),
        "source_path": frame.attrs.get("data_source_path"),
        "error": error,
    }


def _load_panels(root: Path, symbols: list[str]) -> dict[str, Any]:
    frames: dict[str, pd.DataFrame] = {}
    for symbol in symbols:
        frame = _load_latest_adjusted_frame(root, symbol)
        frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
        frame = frame.set_index("timestamp").sort_index()
        frames[symbol] = frame
    index = pd.DatetimeIndex(sorted(set().union(*(frame.index for frame in frames.values()))))
    panels: dict[str, pd.DataFrame] = {}
    for column in ["open", "close", "volume"]:
        panels[column] = pd.DataFrame(
            {
                symbol: pd.to_numeric(frame[column], errors="coerce").reindex(index)
                for symbol, frame in frames.items()
            },
            index=index,
        ).ffill(limit=3)
    panels["data_as_of"] = index.max().isoformat()
    return panels


def _load_latest_adjusted_frame(root: Path, symbol: str) -> pd.DataFrame:
    paths = [
        longbridge_materialized_history_path(root, symbol, "daily"),
        longbridge_cache_path(root, symbol, "daily", "nasdaq_basic"),
    ]
    frames = [normalize_ohlcv(pd.read_csv(path)) for path in paths if path.exists()]
    if not frames:
        return fetch_longbridge_bars(
            root=root,
            symbol=symbol,
            timeframe="daily",
            start=None,
            end=None,
            use_cache=True,
            adjusted=True,
        ).copy()
    merged = pd.concat(frames, ignore_index=True)
    merged["timestamp"] = pd.to_datetime(merged["timestamp"], utc=True)
    return normalize_ohlcv(
        merged.sort_values("timestamp")
        .drop_duplicates(subset=["timestamp"], keep="last")
        .reset_index(drop=True)
    )


def _candidate_specs() -> list[dict[str, Any]]:
    rows = []
    for lookback in [63, 126, 252]:
        for rebalance in [5, 21]:
            for absolute_gate in [False, True]:
                rows.append(
                    _candidate(
                        "P1_etf_absolute_relative",
                        f"p1_lb{lookback}_reb{rebalance}_gate{int(absolute_gate)}",
                        lookback=lookback,
                        rebalance_days=rebalance,
                        top_n=2,
                        absolute_gate=absolute_gate,
                    )
                )
    for score in ["6m", "12m", "6m_12m"]:
        for volatility_adjusted in [False, True]:
            for top_n in [2, 3]:
                rows.append(
                    _candidate(
                        "P2_sector_risk_adjusted",
                        f"p2_{score}_vol{int(volatility_adjusted)}_top{top_n}",
                        score=score,
                        volatility_adjusted=volatility_adjusted,
                        top_n=top_n,
                        rebalance_days=21,
                        buffer=1,
                    )
                )
    for score in ["6_1", "12_1", "6_12_blend"]:
        for volatility_adjusted in [False, True]:
            for top_n in [5, 10]:
                rows.append(
                    _candidate(
                        "P3_stock_cross_sectional",
                        f"p3_{score}_vol{int(volatility_adjusted)}_top{top_n}",
                        score=score,
                        volatility_adjusted=volatility_adjusted,
                        top_n=top_n,
                        rebalance_days=21,
                    )
                )
    for score in ["high_52w", "high_52w_plus_6m", "trend_consistency"]:
        for downside_vol_penalty in [False, True]:
            for top_n in [5, 10]:
                rows.append(
                    _candidate(
                        "P4_stock_trend_quality",
                        f"p4_{score}_dvol{int(downside_vol_penalty)}_top{top_n}",
                        score=score,
                        downside_vol_penalty=downside_vol_penalty,
                        top_n=top_n,
                        rebalance_days=21,
                    )
                )
    for score in ["spy_residual_126", "sector_relative_126", "sector_relative_blend"]:
        for top_n in [5, 10]:
            for sector_cap in [2, 3]:
                rows.append(
                    _candidate(
                        "P5_stock_residual_sector_relative",
                        f"p5_{score}_top{top_n}_cap{sector_cap}",
                        score=score,
                        top_n=top_n,
                        sector_cap=sector_cap,
                        rebalance_days=21,
                    )
                )
    return rows


def _candidate(path: str, trial_id: str, **params: Any) -> dict[str, Any]:
    return {"path": path, "trial_id": trial_id, "params": params}


def _evaluate_candidate(
    spec: dict[str, Any],
    data: dict[str, Any],
    *,
    stock_symbols: list[str],
    sector_map: dict[str, str],
    cost_bps: float,
) -> dict[str, Any]:
    path = str(spec["path"])
    params = dict(spec["params"])
    if path == "P1_etf_absolute_relative":
        universe = list(ETF_TREND_UNIVERSE)
    elif path == "P2_sector_risk_adjusted":
        universe = list(SECTOR_ETF_UNIVERSE)
    else:
        universe = stock_symbols
    scores = _score_frame(path, params, data, universe, sector_map)
    weights, rebalance_count = _weights_from_scores(
        scores,
        params,
        sector_map=sector_map,
        cash_symbol="BIL",
    )
    returns = _open_to_open_returns(data["open"])
    strategy_returns, turnover = _portfolio_returns(weights, returns, cost_bps)
    benchmark_returns = returns[universe].mean(axis=1, skipna=True).fillna(0.0)
    invested = weights[universe].sum(axis=1).gt(0)
    if not invested.any():
        raise ValueError(f"candidate {spec['trial_id']} never produced an invested portfolio")
    start_timestamp = invested[invested].index[0]
    strategy_returns = strategy_returns.loc[start_timestamp:]
    turnover = turnover.loc[start_timestamp:]
    benchmark_returns = benchmark_returns.loc[start_timestamp:]
    evaluation_index = strategy_returns.dropna().index
    strategy_returns = strategy_returns.reindex(evaluation_index).fillna(0.0)
    benchmark_returns = benchmark_returns.reindex(evaluation_index).fillna(0.0)
    folds = _fold_metrics(strategy_returns, benchmark_returns, folds=4)
    split = max(int(len(strategy_returns) * 0.7), 1)
    oos_returns = strategy_returns.iloc[split:]
    oos_benchmark = benchmark_returns.iloc[split:]
    metrics = {
        "full": _metrics(strategy_returns, benchmark_returns),
        "out_of_sample": _metrics(oos_returns, oos_benchmark),
        "folds": folds,
        "rebalance_count": rebalance_count,
        "average_one_way_turnover_pct": round(float(turnover.mean() * 100), 4),
        "ic": _ic_metrics(scores, data["open"], params.get("rebalance_days", 21)),
        "benchmarks": _benchmark_metrics(data["open"], universe, evaluation_index),
    }
    fold_wins = sum(float(fold["information_ratio_vs_equal_weight"]) > 0 for fold in folds)
    recent_two = folds[-2:]
    recent_not_both_negative = not all(
        float(fold["excess_total_return_pct"]) <= 0 for fold in recent_two
    )
    acceptance = {
        "fold_wins_at_least_3_of_4": fold_wins >= 3,
        "recent_two_not_both_negative": recent_not_both_negative,
        "oos_information_ratio_positive": (
            float(metrics["out_of_sample"]["information_ratio_vs_equal_weight"]) > 0
        ),
        "rebalance_count_at_least_30": rebalance_count >= 30,
    }
    acceptance["passed"] = all(acceptance.values())
    selection_score = (
        float(metrics["out_of_sample"]["information_ratio_vs_equal_weight"])
        + float(metrics["out_of_sample"].get("sharpe") or 0.0)
        + fold_wins * 0.25
        - float(metrics["average_one_way_turnover_pct"]) * 0.002
    )
    return {
        "metrics": metrics,
        "acceptance": acceptance,
        "selection_score": round(selection_score, 6),
    }


def _score_frame(
    path: str,
    params: dict[str, Any],
    data: dict[str, Any],
    universe: list[str],
    sector_map: dict[str, str],
) -> pd.DataFrame:
    close = data["close"][universe].shift(1)
    daily = close.pct_change(fill_method=None)
    vol63 = daily.rolling(63, min_periods=40).std() * math.sqrt(TRADING_DAYS)
    if path == "P1_etf_absolute_relative":
        lookback = int(params["lookback"])
        return close.pct_change(lookback, fill_method=None)
    if path == "P2_sector_risk_adjusted":
        score = _momentum_score(close, str(params["score"]), skip_month=False)
        return score.div(vol63.replace(0, np.nan)) if params["volatility_adjusted"] else score
    if path == "P3_stock_cross_sectional":
        score = _momentum_score(close, str(params["score"]), skip_month=True)
        return score.div(vol63.replace(0, np.nan)) if params["volatility_adjusted"] else score
    if path == "P4_stock_trend_quality":
        score_name = str(params["score"])
        high = close / close.rolling(252, min_periods=180).max() - 1
        mom6 = close.pct_change(126, fill_method=None)
        if score_name == "high_52w":
            score = high
        elif score_name == "high_52w_plus_6m":
            score = _cross_sectional_zscore(high) + _cross_sectional_zscore(mom6)
        else:
            monthly = close.pct_change(21, fill_method=None)
            consistency = monthly.rolling(252, min_periods=180).apply(
                lambda values: float(np.mean(np.asarray(values) > 0)), raw=True
            )
            slope = (
                close.pct_change(63, fill_method=None) - close.pct_change(126, fill_method=None) / 2
            )
            score = _cross_sectional_zscore(consistency) + _cross_sectional_zscore(slope)
        if params["downside_vol_penalty"]:
            downside = daily.clip(upper=0).rolling(63, min_periods=40).std()
            score = _cross_sectional_zscore(score) - _cross_sectional_zscore(downside)
        return score
    mom126 = close.pct_change(126, fill_method=None)
    market = data["close"]["SPY"].shift(1).pct_change(fill_method=None)
    stock_returns = close.pct_change(fill_method=None)
    market_var = market.rolling(126, min_periods=80).var().replace(0, np.nan)
    beta = stock_returns.rolling(126, min_periods=80).cov(market).div(market_var, axis=0)
    spy_mom = data["close"]["SPY"].shift(1).pct_change(126, fill_method=None)
    residual = mom126.sub(beta.mul(spy_mom, axis=0))
    sector_relative = mom126.copy()
    for sector in sorted(set(sector_map.values())):
        members = [symbol for symbol in universe if sector_map.get(symbol) == sector]
        if not members:
            continue
        sector_mean = mom126[members].mean(axis=1)
        sector_relative[members] = mom126[members].sub(sector_mean, axis=0)
    score_name = str(params["score"])
    if score_name == "spy_residual_126":
        return residual
    if score_name == "sector_relative_126":
        return sector_relative
    return _cross_sectional_zscore(residual) + _cross_sectional_zscore(sector_relative)


def _momentum_score(close: pd.DataFrame, name: str, *, skip_month: bool) -> pd.DataFrame:
    if skip_month:
        six = close.shift(21).div(close.shift(126)).sub(1)
        twelve = close.shift(21).div(close.shift(252)).sub(1)
    else:
        six = close.pct_change(126, fill_method=None)
        twelve = close.pct_change(252, fill_method=None)
    if name in {"6m", "6_1"}:
        return six
    if name in {"12m", "12_1"}:
        return twelve
    return _cross_sectional_zscore(six) + _cross_sectional_zscore(twelve)


def _weights_from_scores(
    scores: pd.DataFrame,
    params: dict[str, Any],
    *,
    sector_map: dict[str, str],
    cash_symbol: str,
) -> tuple[pd.DataFrame, int]:
    rebalance_days = int(params.get("rebalance_days", 21))
    top_n = int(params.get("top_n", 2))
    columns = [*scores.columns, cash_symbol]
    weight_rows: dict[pd.Timestamp, pd.Series] = {}
    previous: list[str] = []
    rebalances = 0
    for position in range(252, len(scores), rebalance_days):
        timestamp = scores.index[position]
        raw_row = scores.iloc[position].dropna()
        if raw_row.empty:
            continue
        row = raw_row.sort_values(ascending=False)
        if params.get("absolute_gate"):
            row = row[row > 0]
        buffer = int(params.get("buffer", 0))
        if buffer and previous:
            ranks = {symbol: rank for rank, symbol in enumerate(row.index, start=1)}
            retained = [symbol for symbol in previous if ranks.get(symbol, 10**9) <= top_n + buffer]
        else:
            retained = []
        selected = list(dict.fromkeys([*retained, *row.index.tolist()]))
        sector_cap = int(params.get("sector_cap", top_n))
        capped: list[str] = []
        sector_counts: Counter[str] = Counter()
        for symbol in selected:
            sector = sector_map.get(symbol, symbol)
            if sector_counts[sector] >= sector_cap:
                continue
            capped.append(symbol)
            sector_counts[sector] += 1
            if len(capped) >= top_n:
                break
        selected = capped
        row_weights = pd.Series(0.0, index=columns)
        if selected:
            row_weights.loc[selected] = 1 / len(selected)
        else:
            row_weights.loc[cash_symbol] = 1.0
        weight_rows[timestamp] = row_weights
        previous = selected
        rebalances += 1
    rebalance_weights = pd.DataFrame.from_dict(weight_rows, orient="index", columns=columns)
    weights = rebalance_weights.reindex(scores.index).ffill().fillna(0.0)
    empty = weights.sum(axis=1).eq(0)
    weights.loc[empty, cash_symbol] = 1.0
    return weights, rebalances


def _open_to_open_returns(open_prices: pd.DataFrame) -> pd.DataFrame:
    return open_prices.shift(-1).div(open_prices).sub(1)


def _portfolio_returns(
    weights: pd.DataFrame,
    returns: pd.DataFrame,
    cost_bps: float,
) -> tuple[pd.Series, pd.Series]:
    aligned_returns = returns.reindex(index=weights.index, columns=weights.columns).fillna(0.0)
    turnover = weights.diff().abs().sum(axis=1).fillna(0.0) / 2
    gross = (weights * aligned_returns).sum(axis=1)
    net = gross - turnover * cost_bps / 10_000
    return net.iloc[:-1], turnover.iloc[:-1]


def _metrics(returns: pd.Series, benchmark: pd.Series) -> dict[str, Any]:
    values = returns.fillna(0.0).astype(float)
    equity = (1 + values).cumprod()
    curve = [1.0, *equity.tolist()]
    perf = build_performance_metrics(curve, "daily")
    benchmark_values = benchmark.reindex(values.index).fillna(0.0).astype(float)
    excess = values - benchmark_values
    information_ratio = _annualized_ratio(excess)
    benchmark_equity = (1 + benchmark_values).cumprod()
    return {
        "bars": len(values),
        "total_return_pct": round((float(equity.iloc[-1]) - 1) * 100, 4) if len(equity) else 0.0,
        "annualized_return_pct": _round_or_none(perf.annualized_return_pct),
        "sharpe": _round_or_none(perf.sharpe_ratio),
        "max_drawdown_pct": round(perf.max_drawdown_pct, 4),
        "benchmark_total_return_pct": (
            round((float(benchmark_equity.iloc[-1]) - 1) * 100, 4) if len(benchmark_equity) else 0.0
        ),
        "excess_total_return_pct": (
            round((float(equity.iloc[-1]) - float(benchmark_equity.iloc[-1])) * 100, 4)
            if len(equity)
            else 0.0
        ),
        "information_ratio_vs_equal_weight": round(information_ratio, 4),
    }


def _fold_metrics(
    returns: pd.Series,
    benchmark: pd.Series,
    *,
    folds: int,
) -> list[dict[str, Any]]:
    indexes = np.array_split(np.arange(len(returns)), folds)
    rows = []
    for fold, positions in enumerate(indexes, start=1):
        if not len(positions):
            continue
        metrics = _metrics(returns.iloc[positions], benchmark.iloc[positions])
        rows.append(
            {
                "fold": fold,
                "start": returns.index[int(positions[0])].isoformat(),
                "end": returns.index[int(positions[-1])].isoformat(),
                **metrics,
            }
        )
    return rows


def _ic_metrics(
    scores: pd.DataFrame, open_prices: pd.DataFrame, rebalance_days: int
) -> dict[str, Any]:
    forward = open_prices.shift(-21).div(open_prices).sub(1).reindex(columns=scores.columns)
    values = []
    for position in range(252, len(scores), rebalance_days):
        score_row = scores.iloc[position]
        return_row = forward.iloc[position]
        valid = pd.concat([score_row, return_row], axis=1).dropna()
        if len(valid) < 5:
            continue
        corr = valid.iloc[:, 0].rank().corr(valid.iloc[:, 1].rank())
        if pd.notna(corr):
            values.append(float(corr))
    if not values:
        return {"observations": 0, "mean_rank_ic": None, "rank_ic_ir": None}
    std = float(np.std(values, ddof=1)) if len(values) > 1 else 0.0
    return {
        "observations": len(values),
        "mean_rank_ic": round(float(np.mean(values)), 6),
        "rank_ic_ir": round(float(np.mean(values)) / std * math.sqrt(12), 6) if std else None,
        "positive_ratio": round(float(np.mean(np.asarray(values) > 0)), 6),
    }


def _benchmark_metrics(
    open_prices: pd.DataFrame,
    universe: list[str],
    index: pd.DatetimeIndex,
) -> dict[str, Any]:
    returns = _open_to_open_returns(open_prices).reindex(index)
    rows = {}
    for symbol in ["SPY", "QQQ", "XLK", "BIL"]:
        if symbol in returns:
            rows[symbol] = _standalone_total_return(returns[symbol])
    symbol_returns = {
        symbol: _standalone_total_return(returns[symbol])
        for symbol in universe
        if symbol in returns
    }
    if symbol_returns:
        best_symbol = max(symbol_returns, key=symbol_returns.get)
        rows["ex_post_best_symbol"] = {
            "symbol": best_symbol,
            "total_return_pct": symbol_returns[best_symbol],
        }
    return rows


def _standalone_total_return(returns: pd.Series) -> float:
    return round(((1 + returns.fillna(0.0)).prod() - 1) * 100, 4)


def _cross_sectional_zscore(frame: pd.DataFrame) -> pd.DataFrame:
    mean = frame.mean(axis=1)
    std = frame.std(axis=1).replace(0, np.nan)
    return frame.sub(mean, axis=0).div(std, axis=0)


def _annualized_ratio(values: pd.Series) -> float:
    clean = values.dropna().astype(float)
    if len(clean) < 2:
        return 0.0
    std = float(clean.std(ddof=1))
    return float(clean.mean()) / std * math.sqrt(TRADING_DAYS) if std else 0.0


def _number(value: Any) -> float:
    text = str(value or "").replace("$", "").replace(",", "").replace("%", "").strip()
    try:
        return float(text)
    except ValueError:
        return 0.0


def _round_or_none(value: float | None) -> float | None:
    return round(float(value), 4) if value is not None else None


def _sha256_file(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _relpath(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def _render_evaluation_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Multi-Asset Momentum Deterministic Evaluation",
        "",
        f"- Run: `{payload['run_id']}`",
        f"- Data as of: `{payload['data_profile']['data_as_of']}`",
        f"- Candidates: `{payload['candidate_count']}`",
        f"- One-way cost: `{payload['cost_bps_one_way']} bps`",
        f"- Research pass: `{str(payload['research_pass']).lower()}`",
        "",
        "## Path Decisions",
        "",
        "| Path | Trial | Decision | OOS return | OOS Sharpe | OOS IR | Fold gate |",
        "|---|---|---|---:|---:|---:|---|",
    ]
    for row in payload["selections"]:
        metrics = row["metrics"]["out_of_sample"]
        acceptance = row["acceptance"]
        lines.append(
            f"| {row['path']} | {row['trial_id']} | {row['decision']} | "
            f"{metrics['total_return_pct']:.2f}% | {metrics.get('sharpe') or 0:.2f} | "
            f"{metrics['information_ratio_vs_equal_weight']:.2f} | "
            f"{str(acceptance['fold_wins_at_least_3_of_4']).lower()} |"
        )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            (
                "Stock history is a current-universe exploratory replay and cannot by itself "
                "earn research_pass. Accepted rows are method survivors eligible for the "
                "bounded ML round and frozen forward virtual paper, not promoted Alpha."
            ),
            "",
            "## Limitations",
            "",
        ]
    )
    lines.extend(f"- {item}" for item in payload["limitations"])
    return "\n".join(lines).rstrip() + "\n"
