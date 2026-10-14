"""Interpret persisted native outcomes; never generate signals or repair gaps."""
import argparse
import gzip
import json
import math
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code"))
from consumer_admission import (
    P, ROOT, bind, claim_launch, native_admission, phase_admission,
    empirical_limit, empirical_remaining, settle,
)


def utc_ns(ns):
    return datetime.fromtimestamp(ns // 10**9, timezone.utc).isoformat()


def records(folder, kind):
    for path in sorted(folder.glob(f"*-{kind}.jsonl.gz")):
        with gzip.open(path, "rt") as stream:
            for line in stream:
                yield json.loads(line)


def metrics(rows):
    if not rows:
        return None
    initial = 20000.0
    peak, drawdown, previous = initial, 0.0, initial
    returns = []
    for row in rows:
        equity = row["equity"]
        peak = max(peak, equity)
        drawdown = min(drawdown, equity / peak - 1)
        returns.append(equity / previous - 1)
        previous = equity
    std = statistics.stdev(returns) if len(returns) > 1 else 0
    return dict(
        sessions=len(rows), last_utc=utc_ns(rows[-1]["at_ns"]),
        marked_return=previous / initial - 1, daily_drawdown=drawdown,
        diagnostic_Sharpe_against_zero_cash=(statistics.mean(returns) / std * math.sqrt(252)) if std else None,
        Sharpe_excess_BIL=None, full_period_performance=False,
    )


def main(args):
    row = claim_launch(args.reservation_id, "consumer")
    assert row["cells"] == args.cells
    assert row["supplemental_code"] == bind(Path(__file__).resolve())
    outcome = "failed_result_interpretation"
    try:
        native_admission(args.reservation_id)
        phase_admission(args.reservation_id, "empirical")
        empirical_limit(args.reservation_id)
        reports, daily, sources = {}, {}, []
        for cid in args.cells:
            assert empirical_remaining(args.reservation_id) > 10
            folder = P / "economic-results" / cid
            result = json.loads((folder / "result.json").read_text())
            assert result["cell"]["cell_id"] == cid
            sources.append(bind(folder / "result.json"))
            unknown = result["first_unknown"]
            cutoff = unknown["at_ns"] if unknown else 2**63 - 1
            if unknown:
                assert result["closed_attempt_R"] is None
                assert result["terminal_cash"] is None and result["terminal_equity"] is None
                assert result["known_prefix_closed_attempt_R"] == unknown["known_prefix_closed_R"]
            nav = {}
            first_mark = None
            for mark in records(folder, "NAV"):
                assert mark["at_ns"] < cutoff, "unknown NAV must be quarantined"
                first_mark = first_mark or mark
                if mark["daily_close"]:
                    nav[mark["at_ns"]] = mark
            daily[cid] = nav
            fees, fills, entries, sells, after_unknown = 0.0, 0, 0, 0, 0
            fill_tape = []
            for event in records(folder, "audit"):
                if event.get("native_at_ns", 0) >= cutoff:
                    after_unknown += 1
                    continue
                if event["action"] not in ("native_full_fill", "native_partial_fill"):
                    continue
                fills += 1
                fees += event["fee"]
                is_buy = len(event["intent_id"]) == 24 and "-" not in event["intent_id"]
                entries += is_buy
                sells += not is_buy
                fill_tape.append({k: event.get(k) for k in ("intent_id", "at", "quantity", "price", "fee")})
            closed = result["known_prefix_closed_attempt_R"]
            diagnostic = dict(
                cell=result["cell"], status=result["status"], first_unknown=unknown,
                first_unknown_utc=utc_ns(cutoff) if unknown else None,
                own_known_daily_prefix=metrics([nav[t] for t in sorted(nav)]),
                known_closed_attempts=len(closed), known_closed_R_sum=sum(closed),
                known_winning_closed_attempts=sum(r > 0 for r in closed),
                known_fill_events=fills, known_buy_fill_events=entries, known_sell_fill_events=sells,
                known_fees_USD=fees, known_fill_tape=fill_tape,
                audit_rows_at_or_after_unknown_excluded=after_unknown,
                full_period_return=None if unknown else result["terminal_equity"] / 20000 - 1,
                last_known_mark=result["last_known_account"],
                raw_exact_certified=False, promotion_eligible=False, research_pass=False,
                holding_conclusions_after_unknown=None, known_first_mark=first_mark,
            )
            reports[cid] = diagnostic
            text = (
                f"# {cid}\n\nNative outcome: `{result['status']}`. "
                f"First unknown: {diagnostic['first_unknown_utc']}; "
                f"reason: {(unknown or {}).get('reason', 'none')}.\n\n"
                f"Full 2024–25 return, continuous terminal-free Sharpe-excess-BIL and "
                f"post-gap holding conclusions: **N/A** when the path is unknown. "
                f"This report preserves the known prefix and excludes subsequent native events.\n\n"
                f"Before that boundary: {len(closed)} closed attempts, "
                f"{diagnostic['known_winning_closed_attempts']} positive, "
                f"{fills} fill events, ${fees:.2f} actual modeled fees. "
                f"The sum {sum(closed):.6f} R refers only to already closed known attempts.\n\n"
                "The six names are source-selected seen development controls. Input is conditional; "
                "two OHLC routes are separate possible paths, not global NAV bounds. "
                "No liquidation, paper readiness, unseen Alpha or private-account replication is claimed.\n"
            )
            (folder / "backtest-report.md").write_text(text)
        common = set.intersection(*(set(v) for v in daily.values()))
        assert common
        ordered = sorted(common)
        matched = {cid: metrics([daily[cid][t] for t in ordered]) for cid in args.cells}
        first = next(iter(reports.values()))["known_first_mark"]
        last = daily[args.cells[0]][ordered[-1]]
        benchmark = dict(cash=dict(marked_return=0.0), SPY=None, QQQ=None, IWM=None, sector_theme=None, BIL=None)
        if utc_ns(ordered[-1])[:10] < "2024-10-01":
            # No split/action in this interval. Use the very same conditional native marks.
            # Entry-only20bps, whole shares, retained cash, no terminal selling fee/liquidation.
            individual, ew_value = {}, 0.0
            for symbol, price in first["prices"].items():
                q = math.floor(20000 / (price * 1.002))
                value = 20000 - q * price * 1.002 + q * last["prices"][symbol]
                individual[symbol] = value / 20000 - 1
                qew = math.floor((20000 / 6) / (price * 1.002))
                ew_value += 20000 / 6 - qew * price * 1.002 + qew * last["prices"][symbol]
            benchmark.update(same_symbol_buyhold=individual, equal_weight_six_marked_return=ew_value / 20000 - 1,
                             ex_post_best_symbol_upper_control=max(individual, key=individual.get))
        result = dict(
            at_utc=datetime.now(timezone.utc).isoformat(), inputs=sources,
            interpretation_code=bind(Path(__file__).resolve()),
            cases=reports, common_known_daily_prefix=matched,
            common_prefix_end_utc=utc_ns(ordered[-1]), benchmark_partial=benchmark,
            benchmark_limits="Conditional same-mark entry-only20bps controls; concentration/exposure unmatched. Index/theme/BIL not calculated; no excess-BIL gate available. No complete economic matrix.",
            full_economic_pass=False, workflow_pass=True, research_pass=False,
            llm_contribution_pass=False, ml_contribution_pass=False, paper_ready_pass=False,
            simulated_native_execution_started=True, broker_activity=0,
            no_parameter_selection=True, parent_complete=False,
        )
        target = P / "economic-results" / args.output
        with target.open("x") as stream:
            json.dump(result, stream, indent=2)
            stream.write("\n")
        outcome = "known_prefix_interpretation_complete"
        print(json.dumps(dict(outcome=outcome, output=bind(target), matched=matched)), flush=True)
    finally:
        settle(args.reservation_id, outcome)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--reservation-id", required=True)
    parser.add_argument("--cells", nargs="+", required=True)
    parser.add_argument("--output", required=True)
    main(parser.parse_args())
