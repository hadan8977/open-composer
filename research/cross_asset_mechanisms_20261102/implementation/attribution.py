"""Accepted A4 attribution, using saved source inputs and the shared costed book.

Only L1/H1 are selectable starts. All controls, root iterations and receipts are
accounting diagnostics. Existing accounts and historical results stay immutable.
"""
from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path
import sys
import time

import numpy as np
import pandas as pd
from scipy.optimize import brentq

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mechanisms as m
from open_composer.lab.metrics import dsr_summary

ROOT, BASE, OLD = m.ROOT, m.BASE, m.OUT
RUN = BASE / "runs/mechanisms-20261102-2"
OUT = RUN / "worker/evidence"


def save(name, value):
    m.save(OUT / name, value)


def allocation_rules(raw, valid, monthly):
    """Close-prescribed shares; only the caller's next-open book makes them effective."""
    decisions = raw.loc[monthly].clip(.25, .75)
    a4 = decisions.reindex(raw.index).ffill().fillna(.5)
    l1 = decisions.shift(1).reindex(raw.index).ffill().fillna(.5)
    # On the decision index, shift the mean before propagating to other sessions.
    eligible = decisions.where(valid.loc[monthly])
    h1 = eligible.expanding().mean().shift(1).reindex(raw.index).ffill().fillna(.5)
    return {"A4": a4, "L1": l1, "H1": h1}


class Attribution(m.Study):
    def __init__(self):
        super().__init__()
        self.uses = {}
        self.fixed_cache = {}

    def account(self, name, targets, events, cost, window, purpose):
        # The original implementation's immutable reader also validates receipts
        # through EngineResult. Route writes only to this run's evidence folder.
        source = OLD if (OLD / "accounts" / name / "complete.json").exists() else OUT
        previous = m.OUT
        m.OUT = source
        try:
            result = super().account(name, targets, events, cost, window, purpose)
        finally:
            m.OUT = previous
        self.uses[result.metadata["account_folder"]] = result
        return result

    def fixed(self, alpha, cost):
        key = (cost, round(float(alpha), 12))
        if key in self.fixed_cache:
            return self.fixed_cache[key]
        old_name = {.25: "candidate-A1", .5: "control-original50", .75: "candidate-A2"}.get(float(alpha))
        name = f"{old_name}-{cost}" if old_name else f"fixed-{cost}-{float(alpha):.12f}"
        weights = self.d1 * float(alpha) + self.s3 * (1 - float(alpha))
        out = self.account(name, weights, self.d1events | self.s3events | self.monthly,
                           cost, m.DEVELOPMENT, "fixed D1/S3 common-event attribution control; nonselectable")
        self.fixed_cache[key] = out
        return out

    def match_fixed(self, candidate, cost):
        target = float(candidate.net_returns.std(ddof=1) * np.sqrt(252))
        evaluations = []

        def gap(alpha):
            out = self.fixed(float(alpha), cost)
            risk = float(out.net_returns.std(ddof=1) * np.sqrt(252))
            evaluations.append({"alpha": float(alpha), "volatility": risk, "gap": risk - target,
                                "account": out.metadata["account_folder"]})
            return risk - target

        # Frozen deterministic bracket diagnostics; never examine their profit
        # to choose a root. The midpoint books already exist in the parent run.
        grid = [.25, .375, .5, .625, .75]
        gaps = [gap(a) for a in grid]
        brackets = [(a, b) for a, b, ga, gb in zip(grid[:-1], grid[1:], gaps[:-1], gaps[1:]) if ga * gb < 0]
        exact = [a for a, g in zip(grid, gaps) if abs(g) < 1e-12]
        roots = exact + [float(brentq(gap, a, b, xtol=1e-10)) for a, b in brackets]
        roots = sorted(set(round(r, 12) for r in roots))
        if len(roots) != 1:
            # A failed or ambiguous fit stays unmatched; do not choose on P&L.
            return None, None, {"matched": False, "target_volatility": target,
                               "roots": roots, "evaluations": evaluations,
                               "reason": "zero or multiple bracketed roots; no profit-based root selection"}
        alpha = roots[0]
        control = self.fixed(alpha, cost)
        risk_gap = float(control.net_returns.std(ddof=1) * np.sqrt(252) - target)
        return alpha, control, {"matched": abs(risk_gap) <= 1e-6, "vol_gap": risk_gap,
                               "target_volatility": target, "roots": roots,
                               "monotone_on_frozen_grid": bool(np.all(np.diff(gaps) < 0)),
                               "evaluations": evaluations,
                               "reason": "ex-post development risk normalization; common A4 event schedule; no reference selection"}


def inventory():
    ledger = m.TrialLedger(BASE / "trials.jsonl")
    events = ledger.events()
    starts = [e for e in events if e.event == "started"]
    ends = {e.trial_id: e for e in events if e.event == "finished"}
    return {"n_trials": ledger.n_trials, "known_ancestor_candidates": sum(e.count for e in events if e.event == "prior_exposure"),
            "selectable_starts": sum(e.counts_as_trial for e in starts),
            "failed_starts": sum(e.status == "failed" and e.counts_as_trial for e in ends.values()),
            "unfinished": [e.trial_id for e in starts if e.trial_id not in ends],
            "distinct_lineage_mechanisms": 25,
            "unknown": "Broader S3 ancestry, earlier failed starts and historical provider dollars remain unknown"}


def account_diagnostics(study):
    """Read saved orders, returns and marks; no signal/account replay."""
    rows = []
    for folder, out in sorted(study.uses.items()):
        daily = out.ledger
        orders = pd.DataFrame(out.native["orders"])
        orders["trade_date"] = pd.to_datetime(orders.trade_date).dt.as_unit("ns")
        orders["decision_date"] = pd.to_datetime(orders.decision_date).dt.as_unit("ns")
        orders["share_change"] = orders.dollar_trade / orders.price
        shares = orders.pivot_table(index="trade_date", columns="symbol", values="share_change", aggfunc="sum")
        shares = shares.reindex(index=daily.index, columns=study.close.columns).fillna(0).cumsum()
        dollars = (shares * study.close.reindex(index=daily.index, columns=shares.columns)).where(shares.ne(0), 0)
        prior = daily.equity.shift(1).fillna(m.CAPITAL)
        costs = daily.filter(regex="^cost_").sum(axis=1) * prior
        trades = orders.groupby("trade_date").dollar_trade.sum().reindex(daily.index, fill_value=0)
        cash = m.CAPITAL - trades.cumsum() - costs.cumsum()
        error = float((dollars.sum(axis=1) + cash - daily.equity).abs().max())
        curve_error = float((m.CAPITAL * (1 + daily.net).cumprod() - daily.equity).abs().max())
        fee_error = float((daily.cost_spread * prior).sum() - orders.dollar_trade.abs().sum() * out.metadata["cost_bp_per_side"] / 10000)
        decision_positions = study.index.get_indexer(orders.decision_date)
        fill_positions = study.index.get_indexer(orders.trade_date)
        fill_error = max(abs(o.price - study.open.loc[o.trade_date, o.symbol]) for o in orders.itertuples())
        assert max(error, curve_error, abs(fee_error), fill_error) < 1e-5
        assert np.all(fill_positions == decision_positions + 1)
        assert out.native["info"]["frozen_halted_trades"] == 0
        weights = dollars.div(daily.equity, axis=0)
        annual = pd.DataFrame({"profit_usd": daily.equity.diff().fillna(daily.equity.iloc[0] - m.CAPITAL),
                               "direct_order_cost_usd": daily.cost_spread * prior,
                               "financing_usd": daily.cost_margin * prior}).groupby(daily.index.year).sum()
        rows.append({"account": folder, "reused": folder.startswith(str(OLD.relative_to(ROOT))),
                     "metrics": m.metrics(out), "order_count": len(orders),
                     "mean_symbol_weights": weights.mean().to_dict(),
                     "mean_levered_ETF_face_weight": float(weights[["TQQQ", "SOXL", "UPRO", "USD", "TECL"]].sum(axis=1).mean()),
                     "mean_SHY_BIL_weight": float(weights[["SHY", "BIL"]].sum(axis=1).mean()),
                     "year_contributions": annual.to_dict(orient="index"),
                     "reconciliation": {"share_cash_max_error_usd": error, "curve_max_error_usd": curve_error,
                                        "actual_order_fee_error_usd": fee_error, "fill_error": fill_error}})
    save("account-diagnostics.json", rows)
    return rows


def run():
    started = time.monotonic()
    m.require_research(ROOT)
    OUT.mkdir(parents=True, exist_ok=True)
    save("definitions.json", {"scope": str((BASE / "allocation-attribution-scope.md").relative_to(ROOT)),
        "accepted_review": str((RUN / "plan_review/review.md").relative_to(ROOT)),
        "freeze": "Definitions saved before any new account outcome",
        "same_risk": "Separate 10/20bp root in [0.25,0.75], volatility tolerance 1e-6; deterministic five-node bracket; no favorable-root choice",
        "same_average": "Arithmetic mean of A4 close-target share shifted one session to development opens",
        "prewindow": "A4 share at final close before development; held constant",
        "L1": "Previous monthly clipped A4 decision; 50/50 when no prior decision",
        "H1": "Expanding arithmetic mean of earlier valid-positive-vol monthly clipped A4 decisions; current excluded; all saved prehistory; empty=50/50",
        "events": "Union of original D1, S3 and monthly events for every new book; both sleeve targets restored together",
        "costs": "Actual netted 10/20bp order amounts plus native 6.5%/360 residual-cash financing; scenario-specific costed standalone histories",
        "data": "Saved sanitized matrices only; development 2023-09-18..2025-12-31, seen; no reference accounts or refresh",
        "bootstrap": "Paired 21-session moving blocks, 1000 draws, seed 20261102; controls not refit; conditional on fit and known selection",
        "trial_start_floor_before": inventory(), "new_selectable_variants": ["L1", "H1"],
        "execution": "Sequential native book and shared lab batch/DSR/trial ledger; no new model fitting"})
    save("data.json", json.loads((OLD / "data.json").read_text()))
    study = Attribution()
    study.d1.to_parquet(OUT / "source-d1-close-targets.parquet")
    study.s3.to_parquet(OUT / "source-s3-close-targets.parquet")
    events = study.d1events | study.s3events | study.monthly
    events.to_csv(OUT / "common-close-events.csv", index_label="timestamp")
    allocations, outputs = {}, {}
    allocation_summaries = []
    for cost in [10, 20]:
        histories = []
        for label, target, event in [("d1", study.d1, study.d1events), ("s3", study.s3, study.s3events)]:
            # Existing completed warmup accounts, no repeated numerical work.
            warmup = study.account(f"warmup-{label}-{cost}", target, event, cost,
                (str(study.index[1].date()), str(study.index[-1].date())), "reuse saved costed standalone volatility")
            histories.append(warmup.net_returns.reindex(study.index).rolling(63).std(ddof=1))
        valid = (histories[0] > 0) & (histories[1] > 0)
        raw = (histories[1] / (histories[0] + histories[1])).where(valid, .5)
        rules = allocation_rules(raw, valid, study.monthly)
        allocations[cost] = rules
        pd.DataFrame({**rules, "raw_inverse_vol": raw, "valid": valid, "monthly": study.monthly}).to_csv(
            OUT / f"allocation-close-history-{cost}.csv", index_label="timestamp")
        effective = rules["A4"].shift(1).loc[m.DEVELOPMENT[0]:m.DEVELOPMENT[1]]
        before = study.index[study.index < m.DEVELOPMENT[0]][-1]
        allocation_summaries.append({"cost": cost, "open_effective_mean": float(effective.mean()),
            "prewindow_share": float(rules["A4"].loc[before]), "prewindow_close": before,
            "development_sessions": len(effective), "effective_sessions_at_cap": int(effective.eq(.75).sum()),
            "monthly_decisions_inside": int(study.monthly.loc[m.DEVELOPMENT[0]:m.DEVELOPMENT[1]].sum()),
            "monthly_updates_effective_inside": int(study.monthly.shift(1, fill_value=False).loc[m.DEVELOPMENT[0]:m.DEVELOPMENT[1]].sum()),
            "earlier_valid_monthly_decisions": int((study.monthly & valid & (study.index < m.DEVELOPMENT[0])).sum()),
            "same_average_is_ex_post": True, "prewindow_is_causal": True})
        for cid in ["A4"]:
            w = study.d1.mul(rules[cid], axis=0) + study.s3.mul(1 - rules[cid], axis=0)
            outputs[cid, cost] = study.account(f"candidate-{cid}-{cost}", w, events, cost, m.DEVELOPMENT, "reuse accepted A4 account")
            old_w, old_ev = study.combined("A4", cost)
            assert np.max(np.abs(w.to_numpy() - old_w.to_numpy())) < 1e-12
            assert events.equals(old_ev)
    save("allocation-summary.json", allocation_summaries)
    # Warmups are reused inputs, not new primary accounts needing a second audit.
    study.uses = {k: v for k, v in study.uses.items() if "warmup-" not in k}
    rf = study.close.BIL.pct_change(fill_method=None).loc[m.DEVELOPMENT[0]:m.DEVELOPMENT[1]]
    dsr_config = m.DSRConfig(method="campaign_statistics", benchmark=rf,
        benchmark_note="Exact-calendar BIL close-to-close total return; no fill", hac_lag=21,
        assumptions="Entire cumulative known starts including failures and L1/H1; native min(iid,HAC21); broader S3 ancestry unknown")

    def evaluate(cid):
        for cost in [10, 20]:
            alpha = allocations[cost][cid]
            w = study.d1.mul(alpha, axis=0) + study.s3.mul(1 - alpha, axis=0)
            outputs[cid, cost] = study.account(f"attribution-{cid}-{cost}", w, events, cost, m.DEVELOPMENT,
                "prespecified selectable timing intervention" if cost == 10 else "same intervention cost-stress view")
        return outputs[cid, 10]

    batch = m.run_batch(ROOT, experiment=m.Experiment(direction=m.DIRECTION,
        data_and_exposure="Saved sanitized prices/source signals; 575 seen development sessions; close decisions next-open fills; no refresh or reference selection",
        costs="Actual netted 10/20bp orders and native residual cash financing; cost-responsive rules differ slightly across fee scenarios",
        baseline="A4 and fixed D1/S3 controls on common A4 event union; detailed diagnostics follow in this run",
        limitations=("Known trial floor includes failures; broader S3 ancestry unknown", "No unseen/paper/deployment evidence")),
        batch_id="allocation-attribution-l1-h1-v1",
        variants=[m.Variant(cid, {"definition": str((OUT / "definitions.json").relative_to(ROOT)), "prespecified": True},
                            lambda cid=cid: evaluate(cid)) for cid in ["L1", "H1"]], dsr_config=dsr_config)
    if batch.failures:
        raise RuntimeError(f"Retained failures need scoped repair: {batch.failures}")
    trials = inventory()
    save("trial-inventory.json", trials)
    pairs = []

    def pair(cid, cost, control_label, control, extra=None):
        candidate = outputs[cid, cost]
        cm, bm = m.metrics(candidate), m.metrics(control)
        row = {"candidate": cid, "cost": cost, "control": control_label,
               "candidate_metrics": cm, "control_metrics": bm,
               "increment_usd": candidate.net_profit_usd - control.net_profit_usd,
               "control_minus_candidate_vol_gap": bm["volatility_annual"] - cm["volatility_annual"],
               "paired_uncertainty": {**m.paired_bootstrap(candidate, control),
                   "conditioning": "Control fixed at fitted development coefficient; no within-bootstrap refit; known selection unadjusted"},
               **(extra or {})}
        pairs.append(row)
        return row

    for cost in [10, 20]:
        summary = next(s for s in allocation_summaries if s["cost"] == cost)
        fixed_average = study.fixed(summary["open_effective_mean"], cost)
        fixed_pre = study.fixed(summary["prewindow_share"], cost)
        practical = {f"fixed_{a:.2f}": study.fixed(a, cost) for a in [.25, .5, .75]}
        practical["pure_S3"] = study.account(f"control-s3-{cost}", study.s3, study.s3events, cost,
                                             m.DEVELOPMENT, "reuse higher-return/higher-risk S3 alternative")
        for cid in ["A4", "L1", "H1"]:
            alpha, control, match = study.match_fixed(outputs[cid, cost], cost)
            if control is not None:
                pair(cid, cost, "same_risk_fixed_D1", control, {"fixed_D1_share": alpha, "match": match})
            else:
                save(f"unmatched-{cid}-{cost}.json", match)
            for label, ctrl in {"same_average_A4": fixed_average, "prewindow_fixed_A4": fixed_pre, **practical}.items():
                pair(cid, cost, label, ctrl)
            if cid != "A4":
                pair(cid, cost, "A4", outputs["A4", cost])
    save("comparisons.json", pairs)
    diagnostics = account_diagnostics(study)
    statistics = {f"{cid}-{cost}": dsr_summary(out.net_returns, n_trials=trials["n_trials"], config=dsr_config)
                  for (cid, cost), out in outputs.items()}
    save("conditional-dsr.json", statistics)
    counts = m.Counts(economic_comparisons=len(pairs),
        financial_accounts=len(list((OUT / "accounts").glob("*/complete.json"))),
        model_fits=0, variants=2, paper_candidates=0, diagnostic_steps=len(pairs))
    save("counts.json", {"counts": counts.model_dump(), "new_account_starts": len(list((OUT / "accounts").glob("*/started.json"))),
        "new_accounts_completed": counts.financial_accounts,
        "reused_development_accounts": sum(d["reused"] for d in diagnostics),
        "reused_standalone_histories": 4, "distinct_lineage_mechanisms": 25,
        "known_trial_starts_including_ancestors": trials["n_trials"],
        "comparison_definition": "3 rules x 2 costs x (own same-risk + A4 same-average + prewindow + fixed25/50/75 + pureS3), plus L1/H1 vs A4 at both costs; overlapping controls retained and labeled",
        "new_accounts_definition": "All actual new native books including fixed-control root evaluations; reused accounts excluded",
        "diagnostic_steps_definition": "One paired conditional interval per reported pair; bootstrap draws not economic starts",
        "account_seconds_new": sum(d["metrics"]["sessions"] * 0 + study.uses[d["account"]].metadata["elapsed_seconds"] for d in diagnostics if not d["reused"]),
        "engine_elapsed_seconds": time.monotonic() - started,
        "observed_at": datetime.now(UTC).isoformat(),
        "unknown_costs": "Provider dollars unknown; this worker/Lead final tokens pending existing driver; previous failed publication costs retained in run1"})
    primary = next(p for p in pairs if p["candidate"] == "A4" and p["cost"] == 10 and p["control"] == "same_risk_fixed_D1")
    result = m.Results(direction=m.DIRECTION, kind="financial", engine="lab.run_batch + existing Study account cache + lab.book_engine/equity_book.run_book",
        source_artifacts=[str((OUT / f).relative_to(ROOT)) for f in ["definitions.json", "comparisons.json", "allocation-summary.json", "account-diagnostics.json", "conditional-dsr.json", "trial-inventory.json", "counts.json"]]
            + [str((OLD / "results.json").relative_to(ROOT)), str((RUN / "plan_review/review.md").relative_to(ROOT))],
        data_and_exposure="575 seen development sessions 2023-09-18..2025-12-31; 27 monthly updates effective inside; saved sanitized data only; causal close/next-open and common events",
        costs="Actual netted 10/20bp per-side order amounts including initial entry; 6.5%/360 native negative-cash financing; cost-responsive targets separately computed; fractional shares",
        baseline="Ex-post same-volatility fixed D1/S3 control for A4, fitted solely on development separately by cost on common events; other fixed/causal controls in comparisons",
        n_trials=trials["n_trials"], net_profit_usd=primary["candidate_metrics"]["net_profit_usd"],
        baseline_net_profit_usd=primary["control_metrics"]["net_profit_usd"], dsr=statistics["A4-10"]["dsr"],
        dsr_note=json.dumps(statistics["A4-10"], ensure_ascii=False), counts=counts,
        counts_artifact=str((OUT / "counts.json").relative_to(ROOT)),
        limitations=["Conditional fitted-control intervals; known selection not adjusted, broader S3 ancestry unknown",
            "All windows seen; only 27 monthly updates; reference reports reused without new reference batch",
            "Original D1 K1 pass/K2 +0.037 below +0.05 unchanged; no promotion or paper authority",
            "Carlson full text unavailable: local adaptation, no faithful replication claim",
            "Whole-share/capacity/opening execution and real broker fees unknown; historical provider dollars incomplete",
            "Prior stress normalization books each contain two frozen price-unavailable order attempts; retained references only"])
    save("results.json", result.model_dump())
    (BASE / "results.json").write_text(result.model_dump_json(indent=2) + "\n")
    print("DONE", json.dumps(counts.model_dump()), "A4 residual", primary["increment_usd"], flush=True)


if __name__ == "__main__":
    run()
