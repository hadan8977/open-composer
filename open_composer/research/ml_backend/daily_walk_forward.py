"""Expanding yearly stock-rank fits and fixed monthly daily-screen calibration."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter
from uuid import uuid4

import lightgbm as lgb
import numpy as np
import pandas as pd
import pyarrow.parquet as pq
from threadpoolctl import threadpool_limits

from open_composer.adapters.data.sip_parquet import OOS_START
from open_composer.expressions import validate_expression
from open_composer.lab.ledger import TrialLedger
from open_composer.market_sessions import NEW_YORK, us_equity_session_dates
from open_composer.models.strategy_spec import StrategySpec
from open_composer.research.agent_workflow import require_research
from open_composer.research.equity_book.backtest import signal_positions
from open_composer.research.equity_book.daily_screen import ScreenData, run_daily_screen
from open_composer.research.equity_book.panel import PricePanel
from open_composer.research.features.decision_daily import (
    FEATURE_COLUMNS,
    FEATURES,
    KEY,
    MARKET,
)
from open_composer.research.features.panel import _connect
from open_composer.research.ml_backend.daily_labels import LABEL_COST_BP
from open_composer.research.ml_backend.model_factory import create_model

ROOT = Path(__file__).resolve().parents[3]
TRAIN_FIRST = 2016
REPORT_FIRST = 2024
DEVELOPMENT_LAST = 2025
EMBARGO = 5
MARKET_INPUTS = tuple(field for field in MARKET if field != "universe_count")
STOCK_INPUTS = tuple(field for field in FEATURE_COLUMNS if field not in MARKET)
LEVEL_NAMES = {
    "median_dollar_volume_20": "log_median_dollar_volume_20",
    "shares_outstanding": "log_shares_outstanding",
    "short_interest_shares": "short_interest_fraction",
}
STOCK_RANKS = tuple(LEVEL_NAMES.get(field, field) for field in STOCK_INPUTS)
EVENT_FIELDS = {
    "earnings_missing": ("days_since_earnings", "earnings_gap", "earnings_volume_ratio"),
    "insider_missing": tuple(field for field in STOCK_INPUTS if field.startswith("insider_")),
    "finra_missing": ("short_interest_fraction", "days_to_cover", "off_exchange_short_ratio"),
    "shares_missing": ("log_shares_outstanding",),
}
MATRIX_FIELDS = (*EVENT_FIELDS, *STOCK_RANKS, *MARKET_INPUTS)
STOCK_END = len(EVENT_FIELDS) + len(STOCK_RANKS)
MODEL_COLUMNS = {
    "linear": slice(STOCK_END),
    "lightgbm": slice(len(EVENT_FIELDS), None),
    "lightgbm-stock": slice(len(EVENT_FIELDS), STOCK_END),
}
TARGET = "net_return_20_percentile"
INPUTS = (*STOCK_INPUTS, *MARKET_INPUTS)
DECISION_FIELDS = [*KEY, "trade_date", "decision_at", "known_at"]


def _spec(name):
    """Validate the inputs and reference trading rule before fitting or replay."""
    hyperparameters = (
        {"alpha": 10_000}
        if name == "linear"
        else {
            "n_estimators": 60,
            "n_jobs": 2,
            "max_bin": 63,
            "force_col_wise": True,
        }
    )
    fields = MATRIX_FIELDS[MODEL_COLUMNS[name]]
    factors = {
        field: {"source": "feature_packet", "path": FEATURES.as_posix(), "field": field}
        for field in (*fields, "top_or_bottom_decile", "monthly_rebalance")
    }
    spec = StrategySpec(
        name=f"daily-{name}",
        description="Monthly top and bottom stock deciles at the next open",
        timeframe="daily",
        universe=["DAILY_US_STOCK_UNIVERSE"],
        lifecycle="draft",
        position_direction="long_short",
        entry={"all": ["top_or_bottom_decile"]},
        exit={"all": ["monthly_rebalance"]},
        risk={},
        execution={},
        costs={"slippage_bps": LABEL_COST_BP},
        required_capabilities=[
            "market.alpaca_bars",
            "events.sec_filings",
            "events.sec_form4_insider",
            "market.finra_short_interest",
            "reference.sec_disclosed_common_shares",
        ],
        factors=factors,
        model={
            "kind": "ridge_regressor" if name == "linear" else "lightgbm_regressor",
            "features": fields,
            "hyperparameters": hyperparameters,
            "label": {"horizon_bars": 20, "one_way_cost_bps": LABEL_COST_BP},
            "training": {"embargo_bars": EMBARGO},
        },
    )
    for expression in spec.all_expressions():
        validate_expression(expression, spec.factors)
    return spec


def _cutoff(year):
    prior = us_equity_session_dates(
        pd.Timestamp(year - 1, 12, 1).date(), pd.Timestamp(year - 1, 12, 31).date()
    )
    return pd.Timestamp(prior[-EMBARGO], tz=NEW_YORK) + pd.Timedelta(hours=9, minutes=30)


def _session_blocks(batches):
    # Both inputs are ordered by session, but a batch can split the last one.
    pending = None
    for batch in batches:
        frame = pd.concat([pending, batch.to_pandas()], ignore_index=True)
        stop = frame.session.searchsorted(frame.session.iloc[-1])
        if stop:
            yield frame.iloc[:stop]
        pending = frame.iloc[stop:]
    if pending is not None:
        yield pending


def _training_files(root, year, temp):
    cutoff = _cutoff(year)
    # Keep all eligible peers in the feature ranks, including censored outcomes.
    fields = ", ".join("f." + field for field in INPUTS)
    rows = 0
    with _connect("450MB") as con, (temp / "x").open("wb") as x, (temp / "y").open("wb") as y:
        con.execute("SET temp_directory = ?", [str(temp / "duckdb")])
        for history in range(TRAIN_FIRST, year):
            features = root / f"{history}.parquet"
            labels = root / "labels" / f"{history}.parquet"
            batches = con.execute(
                f"""
                SELECT f.session, {fields}, l.net_return_20
                FROM read_parquet(?) f LEFT JOIN read_parquet(?) l
                    ON l.security_id = f.security_id AND l.session = f.session
                   AND l.matures_at_20 < ? AND isfinite(l.net_return_20)
                WHERE f.known_at < f.decision_at AND f.decision_at < ?
                ORDER BY f.session, f.security_id
            """,
                [str(features), str(labels), cutoff, cutoff],
            ).to_arrow_reader(65_536)
            for frame in _session_blocks(batches):
                target = frame.groupby("session").net_return_20.rank(pct=True)
                valid = target.notna()
                _matrix(frame)[valid].tofile(x)
                target[valid].to_numpy(dtype="float32").tofile(y)
                rows += int(valid.sum())
    return rows, cutoff


def _matrix(frame):
    stock = frame.loc[:, STOCK_INPUTS].replace([np.inf, -np.inf], np.nan)
    shares = stock.shares_outstanding.where(stock.shares_outstanding > 0)
    dollars = stock.median_dollar_volume_20.where(stock.median_dollar_volume_20 > 0)
    stock["short_interest_shares"] = stock.short_interest_shares / shares
    stock["shares_outstanding"] = np.log(shares)
    stock["median_dollar_volume_20"] = np.log(dollars)
    stock = stock.rename(columns=LEVEL_NAMES)
    missing = pd.DataFrame(
        {name: stock.loc[:, fields].isna().any(axis=1) for name, fields in EVENT_FIELDS.items()}
    )
    ranks = stock.groupby(frame.session).rank(method="average", pct=True)
    market = frame.loc[:, MARKET_INPUTS].replace([np.inf, -np.inf], np.nan)
    return pd.concat([missing, ranks, market], axis=1).to_numpy(dtype="float32")


def _linear(model, x, y, predict):
    # Fit the factory's standardized ridge via sufficient statistics so the
    # full expanding sample never needs a second, standardized memory copy.
    scaler = model.named_steps["scale"]
    alpha = model.named_steps["model"].alpha
    width = x.shape[1]
    gram, rhs = np.zeros((width, width)), np.zeros(width)
    mean = y.mean(dtype="float64")
    with threadpool_limits(limits=2):
        for start in range(0, len(x), 65_536):
            scaler.partial_fit(np.nan_to_num(x[start : start + 65_536], nan=0.5))
        for start in range(0, len(x), 65_536):
            stop = start + 65_536
            z = scaler.transform(np.nan_to_num(x[start:stop], nan=0.5)).astype("float64")
            gram += z.T @ z
            rhs += z.T @ (y[start:stop] - mean)
        weights = np.linalg.solve(gram + alpha * np.eye(width), rhs)
    return scaler.transform(np.nan_to_num(predict, nan=0.5)) @ weights + mean, weights


class _MappedRows(lgb.Sequence):
    batch_size = 65_536

    def __init__(self, data):
        self.data = data

    def __len__(self):
        return len(self.data)

    def __getitem__(self, key):
        # LightGBM's sampling interface requires doubles for individual rows.
        values = self.data[key]
        return np.ascontiguousarray(values, dtype="float64" if values.ndim == 1 else "float32")


def _tree(model, x, y, predict, fields):
    params = model.get_params()
    rounds = params.pop("n_estimators")
    params["num_threads"] = params.pop("n_jobs")
    params["seed"] = params.pop("random_state")
    params["objective"] = "regression"
    dataset = lgb.Dataset(_MappedRows(x), label=y, feature_name=list(fields))
    booster = lgb.train(params, dataset, num_boost_round=rounds)
    return booster.predict(predict, num_threads=params["num_threads"]), booster.feature_importance(
        "gain"
    )


def train_year(root: Path, output: Path, year: int, *, out_of_sample=False, models=None) -> dict:
    """Publish as-of stock-rank scores from the fixed models and market ablation."""
    if not TRAIN_FIRST < year <= DEVELOPMENT_LAST + int(out_of_sample):
        raise ValueError("Prediction year must be 2017–2025, or 2026 with --out-of-sample")
    require_research(ROOT)
    specs = {name: _spec(name) for name in (MODEL_COLUMNS if models is None else models)}
    started = perf_counter()
    batches = pq.ParquetFile(root / f"{year}.parquet").iter_batches(
        columns=[*DECISION_FIELDS, *INPUTS],
        use_threads=False,
    )
    decisions, matrices = [], []
    for frame in _session_blocks(batches):
        frame = frame.loc[frame.known_at < frame.decision_at]
        decisions.append(frame[DECISION_FIELDS])
        matrices.append(_matrix(frame))
    result = pd.concat(decisions, ignore_index=True)
    values = np.concatenate(matrices)
    del decisions, matrices
    result["fit_at"] = pd.Timestamp(year, 1, 1, tz=NEW_YORK).tz_convert("UTC")
    result["known_at"] = (
        result.groupby("session").known_at.transform("max").clip(lower=result.fit_at.iloc[0])
    )
    result["evaluation_only"] = result.session.dt.date >= OOS_START
    output.mkdir(parents=True, exist_ok=True)
    ledger = TrialLedger(output / "trials.jsonl")
    with TemporaryDirectory(dir=output) as work:
        temp = Path(work)
        rows, cutoff = _training_files(root, year, temp)
        x = np.memmap(temp / "x", dtype="float32", mode="r", shape=(rows, len(MATRIX_FIELDS)))
        y = np.fromfile(temp / "y", dtype="float32")
        report = {
            "year": year,
            "training_cutoff": cutoff.isoformat(),
            "training_rows": rows,
            "target": TARGET,
            "fits": {},
        }
        for name, spec in specs.items():
            columns = MODEL_COLUMNS[name]
            fields = MATRIX_FIELDS[columns]
            trial = f"fit-{year}-{name}-{uuid4().hex[:8]}"
            ledger.start(
                trial,
                batch=output.name,
                candidate=name,
                counts_as_trial=False,
                parameters={
                    "year": year,
                    "training_cutoff": cutoff.isoformat(),
                    "training_rows": rows,
                    "hyperparameters": spec.model.hyperparameters,
                    "label_cost_bp": LABEL_COST_BP,
                    "embargo_sessions": EMBARGO,
                    "features": fields,
                    "target": TARGET,
                },
                note="Fixed framework calibration",
            )
            fit_start = perf_counter()
            evidence = output / f"{trial}.json"
            try:
                inputs = (create_model(spec), x[:, columns], y, values[:, columns])
                prediction, importance = (
                    _linear(*inputs) if name == "linear" else _tree(*inputs, fields)
                )
                del inputs
                result[f"{name}_score"] = prediction.astype("float32")
                report["fits"][name] = {
                    "seconds": perf_counter() - fit_start,
                    "importance_measure": "standardized coefficient"
                    if name == "linear"
                    else "split gain",
                    "feature_importance": dict(zip(fields, importance.tolist(), strict=True)),
                }
                evidence.write_text(
                    json.dumps(report["fits"][name], indent=2, allow_nan=False), encoding="utf-8"
                )
            except Exception as exc:
                ledger.finish(
                    trial, status="failed", evidence=[], note=f"{type(exc).__name__}: {exc}"
                )
                raise
            ledger.finish(trial, status="complete", evidence=[str(evidence)])
        del x
    result.to_parquet(output / f"{year}.parquet", index=False)
    report["prediction_rows"] = len(result)
    report["seconds"] = perf_counter() - started
    (output / f"{year}.json").write_text(
        json.dumps(report, indent=2, allow_nan=False), encoding="utf-8"
    )
    return report


def calibrate(output: Path, years: range, *, out_of_sample: bool = False) -> dict:
    if not REPORT_FIRST <= min(years) <= max(years) <= DEVELOPMENT_LAST + int(out_of_sample):
        raise ValueError("Calibration uses 2024?2025, or 2026 with --out-of-sample")
    require_research(ROOT)
    started = perf_counter()
    data = ScreenData()
    panel = data.panel
    month_ends = signal_positions(panel.dates, "M")
    predictions = {}
    for year in years:
        scores = pd.read_parquet(
            output / f"{year}.parquet",
            filters=[
                ("trade_date", "in", panel.dates[month_ends].tolist()),
            ],
        )
        predictions.update({d: f.set_index("security_id") for d, f in scores.groupby("trade_date")})
    first_signal = min(predictions)
    end = panel.dates.searchsorted(pd.Timestamp(max(years) + 1, 1, 1))
    replay = slice(panel.dates.get_loc(first_signal), end)
    data.panel = PricePanel(
        panel.dates[replay], panel.symbols, panel.open[replay], panel.close[replay]
    )

    def targets(date, rows, name):
        if date not in predictions:
            return None
        if name == "momentum-12-1":
            month = months[date]
            cols = panel.symbols.get_indexer(rows.index)
            score = (
                panel.close[month_ends[month - 1], cols] / panel.close[month_ends[month - 12], cols]
                - 1
            )
            scores = pd.Series(score, index=rows.index)
        else:
            scored = predictions[date]
            scores = (
                scored[f"{name}_score"]
                .where(scored.known_at < scored.decision_at)
                .reindex(rows.index)
            )
        ranked = scores.dropna().sort_index().sort_values(kind="stable")
        n = len(ranked) // 10
        if not n:
            return None
        return dict.fromkeys(ranked.index[-n:], 0.5 / n) | dict.fromkeys(ranked.index[:n], -0.5 / n)

    months = {panel.dates[p]: m for m, p in enumerate(month_ends)}
    ledger = TrialLedger(output / "trials.jsonl")
    runs = {
        name: run_daily_screen(
            data,
            lambda date, rows, name=name: targets(date, rows, name),
            name=name,
            ledger=ledger,
            batch=output.name,
            frequency="M",
            calibration=True,
            oos=out_of_sample,
        )
        for name in (*MODEL_COLUMNS, "momentum-12-1")
    }
    report = {"seconds": perf_counter() - started, "runs": runs}
    (output / "calibration.json").write_text(
        json.dumps(report, indent=2, allow_nan=False), encoding="utf-8"
    )
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["train", "calibrate"])
    parser.add_argument("--first-year", type=int, default=REPORT_FIRST)
    parser.add_argument("--last-year", type=int)
    parser.add_argument("--out-of-sample", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    last = args.last_year or DEVELOPMENT_LAST + int(args.out_of_sample)
    if not REPORT_FIRST <= args.first_year <= last <= DEVELOPMENT_LAST + int(args.out_of_sample):
        parser.error("Choose 2024–2025, or include 2026 with --out-of-sample")
    years = range(args.first_year, last + 1)
    if args.action == "train":
        for year in years:
            report = train_year(FEATURES, args.output, year, out_of_sample=args.out_of_sample)
            print(
                f"{year}: {report['training_rows']:,} matured training rows "
                f"in {report['seconds']:.1f}s",
                flush=True,
            )
    else:
        calibrate(args.output, years, out_of_sample=args.out_of_sample)
