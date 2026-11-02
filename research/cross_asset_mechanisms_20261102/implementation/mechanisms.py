"""Accepted D1 contribution study; all accounting is the shared native book.

Run prepare once, then run. Saved market accounts are reused, never overwritten.
Definitions come from scope.md, accepted before this implementation.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import sys
import time

import numpy as np
import pandas as pd
from scipy.optimize import brentq

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
import screen_lane as lane
from screen_batches import h20260928_02_cross_asset as source
from open_composer.lab import DSRConfig, EngineResult, Experiment, TrialLedger, Variant, book_engine, run_batch
from open_composer.lab.batch import write_evidence
from open_composer.lab.metrics import return_metrics
from open_composer.research.agent_workflow import Results, Counts, require_research
from open_composer.research.equity_book.backtest import BookConfig, flat_cost
from open_composer.research.features.price_hygiene import sanitize_price_matrices

DIRECTION = "cross_asset_mechanisms_20261102"
BASE = ROOT / "research" / DIRECTION
OUT = BASE / "runs/mechanisms-20261102-1/worker/evidence"
CAPITAL = 20_000.0
DEVELOPMENT = ("2023-09-18", "2025-12-31")
SYMBOLS = sorted(set(source.DEFENSIVE) | {"BIL", "SHY", "SPY", "QQQ", "SOXL", "TECL", "TQQQ", "UPRO", "USD"})
IDS = [f"{family}{i}" for family in "FWXMTA" for i in range(1, 5)]
DESCRIPTIONS = {
    "F1": "Failed rank to SHY", "F2": "Failed rank to BIL",
    "F3": "Failed rank to SPY above trailing 200-close mean, otherwise SHY",
    "F4": "Failed rank redistributed to passing ranks, otherwise SHY",
    "W1": "Equal passing defensive weights at original defensive total",
    "W2": "Inverse trailing 63-session volatility at original defensive total",
    "W3": "W2; cap each combined-account asset target at 40%, excess SHY",
    "W4": "Top two passing ranks, original rank weights renormalized to defensive total",
    "X1": "Remove TLT", "X2": "Remove GLD", "X3": "Remove DBC", "X4": "Remove UUP",
    "M1": "12-calendar-month return only", "M2": "1-calendar-month return only",
    "M3": "3/6/12-calendar-month blend, observed one calendar month earlier",
    "M4": "Original score divided by trailing 63-session daily volatility, including BIL hurdle",
    "T1": "Weekly Friday close", "T2": "Daily, only changed rank/pass state",
    "T3": "Monthly; retain prior accepted D1 target if all target deltas <10 percentage points",
    "T4": "Daily rank/pass state confirmed at two consecutive closes",
    "A1": "25% original D1 / 75% source S3", "A2": "75% original D1 / 25% source S3",
    "A3": "Monthly inverse 63-session costed standalone sleeve volatility",
    "A4": "A3 with D1 share clipped to [25%,75%]",
}


def save(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    write_evidence(path, value)


def prepare() -> None:
    require_research(ROOT)
    save(OUT / "definitions.json", {
        "scope": str((BASE / "scope.md").relative_to(ROOT)),
        "accepted_review": str((BASE / "runs/mechanisms-20261102-1/plan_review_resume_2/review.md").relative_to(ROOT)),
        "variants": DESCRIPTIONS, "development": DEVELOPMENT, "cost_bp_per_side": [10, 20],
        "signal": "completed close, next session open; no account receives a new target's overnight return",
        "monthly_offset": 0, "families_1_to_5_d1_share": .5,
        "W3_detail": "Cap asset targets after adding both sleeve target vectors; SHY absorbs excess",
        "T3_detail": "Compare D1 proposed target with previous accepted D1 target; 0.10 or larger triggers; no holding-return eligibility",
        "allocation_detail": "Fixed shares restored at either underlying decision event; native shares drift between events",
        "control_detail": "Practical pure S3 uses native signal/change events. Ex-post fixed-k S3/SHY control rebalances daily, with actual costs; k fit only on development separately by cost",
        "bootstrap": {"block_sessions": 21, "draws": 1000, "seed": 20261102, "purpose": "paired diagnostic, never selection"},
        "source_spec": "strategy_specs/drafts/h20260928_02_cross_asset_sleeve.yaml",
        "source_spec_validation": "oc spec validate passed before dependent implementation; unchanged historical spec is a source, not the new consumer contract",
        "implementation_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    })
    # The admitted source loader drops zero-volume/zero-trade ghosts. No provider refresh.
    lane.base.WARMUP_START = lane.PANEL_START
    started = time.monotonic()
    raw_close, raw_open = lane.base.load_panel(SYMBOLS)
    raw_close = raw_close.reindex(columns=SYMBOLS)
    raw_open = raw_open.reindex(index=raw_close.index, columns=SYMBOLS)
    raw_close.to_parquet(OUT / "raw-close.parquet")
    raw_open.to_parquet(OUT / "raw-open.parquet")
    close, open_, hygiene = sanitize_price_matrices(raw_close, raw_open)
    assert open_ is not None
    # Keep missing warmup prices in place; primary windows must have a complete common panel.
    for a, b in [DEVELOPMENT, ("2024-01-08", "2026-09-17"), ("2026-01-02", "2026-09-17")]:
        if close.loc[a:b].isna().any().any() or open_.loc[a:b].isna().any().any():
            raise ValueError(f"Incomplete common price panel {a}..{b}")
    close.to_parquet(OUT / "close.parquet")
    open_.to_parquet(OUT / "open.parquet")
    save(OUT / "data.json", {"symbols": SYMBOLS, "first": close.index[0], "last": close.index[-1],
         "sessions": len(close), "hygiene": hygiene.manifest(), "load_seconds": time.monotonic() - started,
         "source": "Existing data/sip/daily/*/*.parquet, source loader; no fetch, all historical windows seen",
         "missing_by_symbol": close.isna().sum().to_dict(),
         "input_hashes": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in [OUT / "raw-close.parquet", OUT / "raw-open.parquet"]}})
    print("prepared", json.dumps(json.loads((OUT / "data.json").read_text()), default=str), flush=True)


class Study:
    def __init__(self):
        self.close = pd.read_parquet(OUT / "close.parquet")
        self.open = pd.read_parquet(OUT / "open.parquet")
        # CSV receipts use ns, while parquet/native data may use us. Same dates,
        # same prices: normalize representation before any exact calendar guard.
        self.close.index = self.close.index.as_unit("ns")
        self.open.index = self.open.index.as_unit("ns")
        self.index = self.close.index
        self.monthly = pd.Series(lane.base.rebalance_flags(self.index, "monthly"), index=self.index)
        self.vol = self.close.pct_change(fill_method=None).rolling(63).std(ddof=1)
        self.mean200 = self.close.SPY.rolling(200).mean()
        self.score = {}
        # Shared calendar-return definition, vectorized over names/dates without future reads.
        for months in [1, 3, 6, 12]:
            prior = self.index.searchsorted(self.index - pd.DateOffset(months=months), side="right") - 1
            values = self.close.to_numpy() / self.close.to_numpy()[np.maximum(prior, 0)] - 1
            values[prior < 0] = np.nan
            self.score[months] = pd.DataFrame(values, index=self.index, columns=self.close.columns)
        self.blend = sum(self.score[m] for m in [1, 3, 6, 12]) / 4
        self.s3, self.s3events = self.source_s3()
        self.targets = {}
        self.d1, self.d1events = self.d1_targets("original")

    def source_s3(self):
        lo, lc = lane.salvage.legs(self.close, self.open)
        boost = lane.salvage.boost_window(lane.salvage.dip_signal(self.close), lane.tranche.S3_BOOST_HOLD)
        effective, cols = lane.tranche.offset_effective(self.close, lo, lc, 0, boost)
        # Source rows are already next-open effective. Undo that shift for close decisions.
        # Every item in row i+1 is determined by closes <=i; never use its market outcome.
        frame = pd.DataFrame(effective, index=self.index, columns=cols).reindex(columns=SYMBOLS, fill_value=0)
        decided = frame.shift(-1)
        decided.iloc[-1] = decided.iloc[-2]
        events = self.monthly | decided.diff().abs().max(axis=1).gt(1e-12)
        return decided, events

    def d1_targets(self, cid):
        if cid in self.targets:
            return self.targets[cid]
        score = self.blend
        if cid == "M1": score = self.score[12]
        if cid == "M2": score = self.score[1]
        if cid == "M3":
            old = self.index.searchsorted(self.index - pd.DateOffset(months=1), side="right") - 1
            score = (self.score[3] + self.score[6] + self.score[12]) / 3
            score = pd.DataFrame(score.to_numpy()[np.maximum(old, 0)], index=self.index, columns=SYMBOLS)
            score.iloc[old < 0] = np.nan
        if cid == "M4": score = self.blend / self.vol
        names = list(source.DEFENSIVE)
        if cid.startswith("X"): names.remove(names[int(cid[1]) - 1])
        rw = np.array(source.RANK_WEIGHTS[:len(names)])
        rw /= rw.sum()
        weights = pd.DataFrame(0., index=self.index, columns=SYMBOLS)
        events = pd.Series(False, index=self.index)
        current = pd.Series(0., index=SYMBOLS)
        current.SHY = 1.
        committed = previous_observed = None
        for i, day in enumerate(self.index):
            evaluate = bool(self.monthly.iloc[i])
            if cid == "T1": evaluate = day.weekday() == 4
            if cid in ("T2", "T4"): evaluate = True
            if evaluate:
                row = score.iloc[i]
                valid = np.isfinite(row[names + ["BIL"]]).all()
                ranked = sorted(names, key=lambda s: -row[s]) if valid else names
                passed = [s for s in ranked if valid and row[s] >= row.BIL]
                state = (tuple(ranked), tuple(passed)) if valid else ((), ())
                commit = True
                if cid == "T2": commit = state != committed
                if cid == "T4": commit = state == previous_observed and state != committed
                previous_observed = state
                if commit:
                    w = pd.Series(0., index=SYMBOLS)
                    if not valid:
                        w.SHY = 1.
                    else:
                        fallback = {"F1": "SHY", "F2": "BIL"}.get(cid, "SPY")
                        if cid == "F3" and not (self.close.SPY.iloc[i] > self.mean200.iloc[i]): fallback = "SHY"
                        for s, rank_weight in zip(ranked, rw, strict=True):
                            w[s if s in passed else fallback] += rank_weight
                        defensive_total = float(w[names].sum())
                        if cid == "F4":
                            w[:] = 0.
                            if passed:
                                norm = sum(rw[ranked.index(s)] for s in passed)
                                for s in passed: w[s] = rw[ranked.index(s)] / norm
                            else: w.SHY = 1.
                        if cid in ("W1", "W2", "W3", "W4") and passed:
                            chosen = passed[:2] if cid == "W4" else passed
                            if cid == "W1": rel = np.ones(len(chosen))
                            elif cid in ("W2", "W3"): rel = 1 / self.vol.loc[day, chosen].to_numpy()
                            else: rel = np.array([rw[ranked.index(s)] for s in chosen])
                            if not np.isfinite(rel).all() or np.any(rel <= 0):
                                raise ValueError(f"Missing trailing risk at {day} {cid}")
                            w[names] = 0.
                            w[chosen] = defensive_total * rel / rel.sum()
                    if cid == "T3" and (w - current).abs().max() < .10 - 1e-12:
                        commit = False
                    if commit:
                        current = w
                        committed = state
                        events.iloc[i] = True
            weights.iloc[i] = current.to_numpy()
        self.targets[cid] = (weights, events)
        return weights, events

    def account(self, name, targets, events, cost, window, purpose):
        folder = OUT / "accounts" / name
        if (folder / "complete.json").exists():
            meta = json.loads((folder / "complete.json").read_text())
            daily = pd.read_csv(folder / "ledger.csv", index_col=0, parse_dates=True)
            return EngineResult(engine="equity_book.run_book", initial_equity_usd=CAPITAL,
                end_equity_usd=meta["end_equity_usd"], native=json.loads((folder / "native.json").read_text()),
                ledger=daily, net_returns=daily.net, metadata=meta)
        folder.mkdir(parents=True, exist_ok=False)
        save(folder / "started.json", {"at": datetime.now(UTC).isoformat(), "purpose": purpose, "cost": cost, "window": window})
        require_research(ROOT)
        start_pos = int(self.index.searchsorted(pd.Timestamp(window[0])))
        begin = self.index[start_pos - 1]
        signal_dates = list(events.index[events & (events.index >= begin) & (events.index <= window[1])])
        signal_dates = sorted(set(signal_dates) | {begin})
        orders = []
        native_cost = flat_cost(cost)

        def cost_fn(trades, state):
            cost_dollars = native_cost(trades, state)
            for row in trades.to_dict("records"):
                row["decision_date"] = state.decision_date
                orders.append(row)
            return cost_dollars

        def decide(day, state):
            w = targets.loc[day]
            if not np.isfinite(w).all() or abs(w.sum() - 1.) > 1e-9 or w.min() < -1e-10:
                raise ValueError(f"Invalid causal target {name} {day}")
            return w[w.abs() > 1e-14].to_dict()

        started = time.monotonic()
        output = book_engine(self.close, self.open, decide, config=BookConfig(
            initial_equity=CAPITAL, start=str(begin.date()), end=window[1], signal_dates=signal_dates,
            cost_bp_per_side=cost, cost_fn=cost_fn, exec_price="open", margin_rate=.065))
        assert output.ledger.net.iloc[0] == 0.  # prep close is cash, first development fill is costed
        daily = output.ledger.loc[window[0]:window[1]].copy()
        meta = {"end_equity_usd": output.end_equity_usd, "window": window, "cost_bp_per_side": cost,
            "purpose": purpose, "elapsed_seconds": time.monotonic() - started,
            "first_fill_decision": str(begin.date()), "account_folder": str(folder.relative_to(ROOT))}
        output.native["orders"] = orders
        output.native["original_panel_hygiene"] = json.loads((OUT / "data.json").read_text())["hygiene"]
        daily.to_csv(folder / "ledger.csv", index_label="timestamp")
        save(folder / "native.json", output.native)
        save(folder / "complete.json", meta)
        output = EngineResult(engine=output.engine, initial_equity_usd=CAPITAL,
             end_equity_usd=output.end_equity_usd, native=output.native, ledger=daily, net_returns=daily.net, metadata=meta)
        print("account", name, round(output.net_profit_usd, 2), flush=True)
        return output

    def combined(self, cid, cost):
        d1, ev = self.d1_targets(cid if not cid.startswith("A") else "original")
        alpha = pd.Series(.5, index=self.index)
        if cid == "A1": alpha[:] = .25
        if cid == "A2": alpha[:] = .75
        if cid in ("A3", "A4"):
            histories = []
            for label, target, event in [("d1", self.d1, self.d1events), ("s3", self.s3, self.s3events)]:
                out = self.account(f"warmup-{label}-{cost}", target, event, cost,
                    (str(self.index[1].date()), str(self.index[-1].date())), "costed causal allocation history; development weights read only trailing development rows; reference rows used only for later diagnostics")
                histories.append(out.net_returns.reindex(self.index).rolling(63).std(ddof=1))
            # D1 inverse-vol share = vol(S3)/(vol(D1)+vol(S3)); warmup is exactly equal.
            raw = (histories[1] / (histories[0] + histories[1])).where((histories[0] > 0) & (histories[1] > 0), .5)
            alpha = raw.where(self.monthly).ffill().fillna(.5)
            if cid == "A4": alpha = alpha.clip(.25, .75)
        weights = d1.mul(alpha, axis=0) + self.s3.mul(1 - alpha, axis=0)
        if cid == "W3":
            excess = (weights - .4).clip(lower=0).sum(axis=1)
            weights = weights.clip(upper=.4)
            weights.SHY += excess
        events = ev | self.s3events | self.monthly
        return weights, events

    def control(self, k, cost):
        weights = self.s3 * k
        weights.SHY += 1 - k
        return self.account(f"match-{cost}-{k:.10f}", weights, pd.Series(True, index=self.index), cost,
                            DEVELOPMENT, "ex-post same-volatility diagnostic control; not an economic trial")

    def match(self, output, cost):
        target = float(output.net_returns.std(ddof=1) * np.sqrt(252))
        def gap(k): return float(self.control(float(k), cost).net_returns.std(ddof=1) * np.sqrt(252) - target)
        g0, g1 = gap(0.), gap(1.)
        if g0 * g1 > 0:
            k = 0. if abs(g0) < abs(g1) else 1.
            return k, self.control(k, cost), {"matched": False, "vol_gap": min(abs(g0), abs(g1)), "reason": "target outside unlevered endpoint range"}
        k = float(brentq(gap, 0., 1., xtol=1e-7))
        control = self.control(k, cost)
        risk_gap = float(control.net_returns.std(ddof=1) * np.sqrt(252) - target)
        return k, control, {"matched": abs(risk_gap) < 1e-6, "vol_gap": risk_gap,
                             "reason": "development ex-post k; no reference-window fit"}


def metrics(output):
    daily, r = output.ledger, output.net_returns
    m = return_metrics(r, CAPITAL)
    equity = daily.equity.to_numpy()
    peak = np.maximum.accumulate(np.r_[CAPITAL, equity])[1:]
    streak = longest = 0
    for flag in equity < peak - 1e-8:
        streak = streak + 1 if flag else 0
        longest = max(longest, streak)
    previous_equity = daily.equity.shift(1).fillna(CAPITAL)
    costcols = [c for c in daily if c.startswith("cost_")]
    m.update({"cagr_252": float((output.end_equity_usd / CAPITAL) ** (252 / len(r)) - 1),
              "volatility_annual": float(r.std(ddof=1) * np.sqrt(252)),
              "longest_underwater_sessions": longest, "turnover_total": float(daily.turnover.sum()),
              "turnover_annual": float(daily.turnover.mean() * 252),
              "trade_sessions": int((daily.turnover > 1e-12).sum()),
              "rebalance_sessions": int(daily.is_trade_day.sum()),
              "mean_long_exposure": float(daily.long_exp.mean()),
              "mean_cash_exposure": float(daily.cash_exp.mean()),
              "costs_usd": {c: float((daily[c] * previous_equity).sum()) for c in costcols},
              "max_order_usd": max((abs(o["dollar_trade"]) for o in output.native["orders"]), default=0.),
              "account": output.metadata["account_folder"]})
    return m


def paired_bootstrap(candidate, control):
    a, b = candidate.net_returns.to_numpy(), control.net_returns.to_numpy()
    assert candidate.net_returns.index.equals(control.net_returns.index)
    n, length = len(a), 21
    rng = np.random.default_rng(20261102)
    starts = rng.integers(0, n - length + 1, size=(1000, int(np.ceil(n / length))))
    take = (starts[:, :, None] + np.arange(length)).reshape(1000, -1)[:, :n]
    increments = CAPITAL * (np.prod(1 + a[take], axis=1) - np.prod(1 + b[take], axis=1))
    means = (a[take] - b[take]).mean(axis=1) * 252
    return {"usd_increment_95pct": np.quantile(increments, [.025, .975]).tolist(),
            "annual_arithmetic_return_difference_95pct": np.quantile(means, [.025, .975]).tolist(),
            "block_sessions": 21, "draws": 1000, "seed": 20261102,
            "interpretation": "conditional paired moving-block uncertainty on seen development; no selection adjustment or OOS claim"}


def run(recovery=False):
    study = Study()
    ledger = TrialLedger(BASE / "trials.jsonl")
    for key, count, paths, note in [
        ("prior-cross-asset", 2, ["reports/research/iterations/h20260928_02_cross_asset_sleeve/trial-ledger.jsonl"], "D1/D2 unique selectable candidates; four windows, 21 fixed median offsets and 10/20bp are views, not extra free trials"),
        ("prior-defense-first", 2, ["reports/research/iterations/h20260923_12_s3_defense_first/trial-ledger.jsonl", "reports/research/iterations/h20260923_12_s3_defense_first/placebo.parquet"], "DF01/DF02; DF00 reference, EW/SPY/SHY controls and 80 random-rank null simulations excluded from selectable count but preserved; broader S3 ancestry unknown")]:
        if not any(e.trial_id == key for e in ledger.events()): ledger.import_prior(key, count=count, evidence=paths, note=note)
    if not (OUT / "trial-inventory.json").exists(): save(OUT / "trial-inventory.json", {"known_prior_selectable": 4, "new_predeclared": 24,
         "original_screen_offsets": "21 per candidate, median predetermined, no best-offset selection",
         "preceding_nulls": 80, "broader_S3_and_prior_failed_start_history": "unknown; count is conditional lower bound",
         "unknown_compute_costs": "Historical provider dollars and full earlier research usage unknown; retain run.json invalid Reply attempts and resumed session usage"})
    controls = {}
    for cost in [10, 20]:
        for label, weights, ev in [("s3", study.s3, study.s3events), ("d1", study.d1, study.d1events),
                    ("original50", *study.combined("original", cost))]:
            controls[label, cost] = study.account(f"control-{label}-{cost}", weights, ev, cost, DEVELOPMENT, "nonselectable practical control")
        for label in ["BIL", "SHY", "EW"]:
            w = pd.DataFrame(0., index=study.index, columns=SYMBOLS)
            if label == "EW": w[list(source.DEFENSIVE)] = .25
            else: w[label] = 1.
            ev = study.monthly if label == "EW" else pd.Series(False, index=study.index)
            controls[label, cost] = study.account(f"control-{label}-{cost}", w, ev, cost, DEVELOPMENT, "nonselectable simple control")
        ew = pd.DataFrame(0., index=study.index, columns=SYMBOLS)
        ew[list(source.DEFENSIVE)] = .125
        ew += study.s3 * .5
        controls["EW50", cost] = study.account(f"control-EW50-{cost}", ew, study.s3events | study.monthly, cost, DEVELOPMENT, "same-allocation naive-basket control")
    control_pairs = []
    for cost in [10, 20]:
        for label in ["original50", "EW50"]:
            output = controls[label, cost]
            k, matched, status = study.match(output, cost)
            control_pairs.append({"label": label, "cost_bp_per_side": cost, "control_k": k,
                 "account_metrics": metrics(output), "matched_metrics": metrics(matched), "match": status,
                 "increment_matched_usd": output.net_profit_usd - matched.net_profit_usd})
    save(OUT / "simple-control-pairs.json", control_pairs)
    paired = []
    def evaluate(cid):
        primary = None
        for cost in [10, 20]:
            w, ev = study.combined(cid, cost)
            output = controls["original50", cost] if cid == "T3" and cost == 20 else study.account(
                f"candidate-{cid}-{cost}", w, ev, cost, DEVELOPMENT,
                "predeclared variant" if cost == 10 else "same variant cost-stress view")
            k, control, match_info = study.match(output, cost)
            row = {"candidate": cid, "description": DESCRIPTIONS[cid], "cost_bp_per_side": cost,
                   "candidate_metrics": metrics(output), "matched_control_metrics": metrics(control),
                   "control_k": k, "match": match_info,
                   "increment_matched_usd": output.net_profit_usd - control.net_profit_usd,
                   "increment_practical_s3_usd": output.net_profit_usd - controls["s3", cost].net_profit_usd,
                   "increment_original50_usd": output.net_profit_usd - controls["original50", cost].net_profit_usd,
                   "increment_EW50_usd": output.net_profit_usd - controls["EW50", cost].net_profit_usd,
                   "paired_uncertainty": paired_bootstrap(output, control)}
            save(OUT / "pairs" / f"{cid}-{cost}.json", row)
            paired.append(row)
            if cost == 10:
                primary = output
                primary.native["paired_comparison"] = row
        return primary
    experiment = Experiment(direction=DIRECTION,
        data_and_exposure="SIP local immutable panel; 2023-09-18..2025-12-31 seen development, offset 0; causal close decisions/next-open fills. 2026 and stress only diagnostics.",
        costs="10/20bp per side on actual netted asset orders, initial entry included; native 6.5%/360 fee-residual financing. Fractional native shares; unknown deployment impact/capacity and provider dollars.",
        baseline="Paired ex-post same-vol fixed-k S3/SHY daily costed account, separately by variant/cost; practical S3, original50, EW50 and BIL/SHY saved too",
        limitations=("Seen development, no OOS/paper acceptance; original K1 pass/K2 fail unchanged",
                     "Trial count is conditional on four known ancestor candidates; broader historical exposure and failed-start costs unknown",
                     "Fractional accounting; whole-share, spread/auction impact and ADV capacity not established"))
    rf = study.close.BIL.pct_change(fill_method=None).loc[DEVELOPMENT[0]:DEVELOPMENT[1]]
    batch = run_batch(ROOT, experiment=experiment, batch_id="mechanisms-24-receipt-repair" if recovery else "mechanisms-24-v1",
        variants=[Variant(cid, {"mechanism": DESCRIPTIONS[cid], "definition": "worker/evidence/definitions.json"}, lambda cid=cid: evaluate(cid)) for cid in IDS],
        dsr_config=DSRConfig(method="campaign_statistics", benchmark=rf, benchmark_note="Aligned BIL close-to-close total-return series; no silent fill",
                             hac_lag=21, assumptions="Native campaign expected-maximum Sharpe under cumulative known selectable starts; min(iid,HAC21), sample moments; unknown broader ancestry limits inference"))
    if batch.failures: raise RuntimeError(f"Preserved candidate failures require scoped repair: {batch.failures}")
    # Publication choice is based solely on completed development 10bp paired dollars.
    winner = max([p for p in paired if p["cost_bp_per_side"] == 10 and p["match"]["matched"]], key=lambda p: p["increment_matched_usd"])
    save(OUT / "development-selection.json", {"selected": winner["candidate"], "criterion": "largest development 10bp incremental dollars at matched volatility", "row": winner,
        "seen_data": True, "reference_windows_opened_for_selection": False})
    timing_pairs = []
    for cost in [10, 20]:
        pair = next(p for p in paired if p["candidate"] == winner["candidate"] and p["cost_bp_per_side"] == cost)
        k = pair["control_k"]
        cw = study.s3 * k
        cw.SHY += 1 - k
        out = study.account(f"timing-source-events-{cost}", cw, study.s3events, cost, DEVELOPMENT,
                            "same development k, source event schedule instead of daily normalization; no re-fit")
        timing_pairs.append({"cost_bp_per_side": cost, "development_k_unchanged": k, "metrics": metrics(out),
                             "candidate_minus_control_usd": pair["candidate_metrics"]["net_profit_usd"] - out.net_profit_usd,
                             "vol_gap_control_minus_candidate": metrics(out)["volatility_annual"] - pair["candidate_metrics"]["volatility_annual"],
                             "interpretation": "Timing sensitivity only; k is not re-fit, so disclose remaining risk gap"})
    save(OUT / "control-timing-sensitivity.json", timing_pairs)
    # Diagnostic accounts do not fit k, parameters or candidate identity on reference returns.
    diagnostic = []
    for cost in [10, 20]:
        winner_pair = next(p for p in paired if p["candidate"] == winner["candidate"] and p["cost_bp_per_side"] == cost)
        k = winner_pair["control_k"]
        for window_label, window in [("stress_seen", ("2016-05-02", "2023-09-15")),
                  ("anchor_seen", ("2024-01-08", "2026-09-17")), ("2026_contaminated", ("2026-01-02", "2026-09-17"))]:
            win_w, win_ev = study.combined(winner["candidate"], cost)
            cw = study.s3 * k
            cw.SHY += 1 - k
            for label, weights, ev in [(winner["candidate"], win_w, win_ev), ("s3", study.s3, study.s3events),
                    ("original50", *study.combined("original", cost)), ("fixed_development_k", cw, pd.Series(True, index=study.index))]:
                out = study.account(f"diagnostic-{window_label}-{label}-{cost}", weights, ev, cost, window, "seen reference diagnostic; no selection/fit")
                diagnostic.append({"window": window_label, "cost": cost, "label": label, "metrics": metrics(out), "development_k": k})
    save(OUT / "comparisons.json", paired)
    pd.DataFrame([{**{k:v for k,v in p.items() if not isinstance(v, dict)},
                   **{f"candidate_{k}":v for k,v in p["candidate_metrics"].items() if not isinstance(v, dict)},
                   **{f"control_{k}":v for k,v in p["matched_control_metrics"].items() if not isinstance(v, dict)}} for p in paired]).to_csv(OUT / "comparison-table.csv", index=False)
    save(OUT / "controls.json", {f"{label}-{cost}": metrics(out) for (label, cost), out in controls.items()})
    save(OUT / "diagnostics.json", diagnostic)
    started = list((OUT / "accounts").glob("*/started.json"))
    completed = list((OUT / "accounts").glob("*/complete.json"))
    # T3 is a frozen, exposed configuration but no new economic mechanism:
    # rank targets are multiples of 10pp, so a strictly-below-10pp band cannot
    # suppress a nonzero target change. Keep both attempts in n_trials.
    counts = Counts(economic_comparisons=sum(p["candidate"] != "T3" for p in paired) * 2 + len(control_pairs) + len(timing_pairs), financial_accounts=len(completed), model_fits=0,
                    variants=len(batch.results) - 1, paper_candidates=0, diagnostic_steps=len(paired))
    save(OUT / "counts.json", {"counts": counts.model_dump(), "native_account_starts": len(started),
         "predeclared_configurations_evaluated": len(batch.results), "distinct_new_economic_mechanisms": len(batch.results) - 1,
         "redundant_configuration": "T3: targets are 10pp multiples; strictly below 10pp threshold is original-equivalent. All exposed starts remain counted.",
         "native_accounts_completed": len(completed), "failed_or_unresolved_native_accounts": len(started)-len(completed),
         "economic_comparisons_definition": "23 nonredundant mechanisms x two costs x two baselines = 92; four simple-control same-vol pairs and two fixed-k timing sensitivity pairs = 98. T3 duplicates excluded; normalization-search accounts not selectable trials",
         "diagnostic_steps_definition": "48 paired bootstrap summaries; bootstrap draws are not economic trials",
         "account_inventory": [str(p.relative_to(ROOT)) for p in completed],
         "account_seconds": sum(json.loads(p.read_text())["elapsed_seconds"] for p in completed),
         "unknown_costs": "Provider dollars and complete all-phase token usage finalized externally by existing driver, including invalid Reply/recovery; historical S3 ancestry unknown"})
    selected = Results.model_validate_json(batch.results[winner["candidate"]].read_text())
    selected.baseline_net_profit_usd = winner["matched_control_metrics"]["net_profit_usd"]
    selected.counts = counts
    selected.counts_artifact = str((OUT / "counts.json").relative_to(ROOT))
    selected.source_artifacts += [str((OUT / f).relative_to(ROOT)) for f in ["comparisons.json", "controls.json", "simple-control-pairs.json", "control-timing-sensitivity.json", "diagnostics.json", "trial-inventory.json", "counts.json", "development-selection.json", "definitions.json", "data.json"]]
    save(OUT / "results.json", selected.model_dump())
    # Numerical engine publishes the schema-valid contract consumed by fresh Lead.
    (BASE / "results.json").write_text(selected.model_dump_json(indent=2) + "\n")
    print("DONE", winner["candidate"], "increment", winner["increment_matched_usd"], counts.model_dump(), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=["prepare", "run", "recover"])
    args = parser.parse_args()
    prepare() if args.phase == "prepare" else run(recovery=args.phase == "recover")
