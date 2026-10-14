"""Causal raw-minute/chart/action components only; no economic replay."""

from __future__ import annotations

import hashlib
import json
import resource
import time as clock
from collections import defaultdict
from datetime import date, datetime, time, timedelta
from decimal import Decimal, localcontext
from pathlib import Path

from open_composer.market_sessions import (
    NEW_YORK,
    us_equity_session_close,
    us_equity_session_dates,
)

P = Path(__file__).resolve().parents[1]
ROOT = P.parents[4]
OUT = P / "acquisition/components"
PRICE = ("o", "h", "l", "c", "vw")


def encode(value):
    if isinstance(value, Decimal):
        return str(value)
    raise TypeError(type(value).__name__)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=encode)


def binding(path):
    return {
        "path": str(path.relative_to(ROOT)),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def save(path, value):
    path.write_text(json.dumps(value, indent=2, default=encode, allow_nan=False) + "\n")


def minute_grid(day):
    close = us_equity_session_close(day)
    if close is None:
        return []
    t = datetime.combine(day, time(9, 30), tzinfo=NEW_YORK)
    end = datetime.combine(day, close, tzinfo=NEW_YORK)
    grid = []
    while t < end:
        grid.append(t)
        t += timedelta(minutes=1)
    return grid


def valid(r):
    try:
        p = [Decimal(str(r[k])) for k in PRICE]
        return (
            all(x.is_finite() and x > 0 for x in p)
            and Decimal(str(r["l"])) <= min(Decimal(str(r["o"])), Decimal(str(r["c"])))
            and Decimal(str(r["h"])) >= max(Decimal(str(r["o"])), Decimal(str(r["c"])))
            and Decimal(str(r["v"])) >= 0
        )
    except (KeyError, ValueError, ArithmeticError):
        return False


def completed_chartbars(day, by_time):
    grid = minute_grid(day)
    result = []
    for i in range(0, len(grid), 60):
        interval = grid[i : i + 60]
        missing = [x.isoformat() for x in interval if x not in by_time or not by_time[x]["valid"]]
        part = {
            "start_NY": interval[0].isoformat(),
            "end_NY": (interval[-1] + timedelta(minutes=1)).isoformat(),
            "duration_minutes": len(interval),
            "missing_or_invalid": missing,
            "complete": not missing,
        }
        if not missing:
            rows = [by_time[x]["row"] for x in interval]
            part.update(
                o=rows[0]["o"],
                h=max(Decimal(str(r["h"])) for r in rows),
                l=min(Decimal(str(r["l"])) for r in rows),
                c=rows[-1]["c"],
                v=sum(Decimal(str(r["v"])) for r in rows),
                source_refs=[by_time[x]["ref"] for x in interval],
            )
        result.append(part)
    return result


def ema(closes, period):
    if not closes:
        return None
    value = Decimal(str(closes[0]))
    alpha = Decimal(2) / Decimal(period + 1)
    for x in closes[1:]:
        value += alpha * (Decimal(str(x)) - value)
    return value


def main():
    resource.setrlimit(resource.RLIMIT_CPU, (120, 121))
    start_cpu = clock.process_time()
    assert ROOT == Path.cwd(), (str(ROOT), str(Path.cwd()))
    assert not OUT.exists(), "no_overwrite_or_implicit_replay"
    OUT.mkdir()
    manifest = json.loads((P / "acquisition/request-manifest.json").read_text())
    ledger = json.loads((P / "acquisition/market/request-ledger.json").read_text())
    entries = [(a, None) for a in ledger["attempts"]]
    for x in manifest["reuse_existing_entities"]:
        previous = json.loads((ROOT / x["ledger"]["path"]).read_text())
        matched = [a for a in previous["attempts"] if a.get("entity") == x["entity"]]
        assert len(matched) == 1
        entries.append((matched[0], x["use"]))
    entities = []
    by_id = defaultdict(lambda: defaultdict(list))
    actions = []
    daily = defaultdict(list)
    for a, reuse in entries:
        item = a["entity"]
        path = ROOT / item["path"]
        assert binding(path) == item
        if not a.get("entity_complete") or a.get("http_status", 200) != 200:
            continue
        obj = json.loads(path.read_bytes(), parse_float=Decimal)
        ei = len(entities)
        entities.append(
            {
                **item,
                "request_id": a.get("id", a.get("request_id")),
                "params": a["params"],
                "current_fetched_at": a.get("current_fetched_at"),
                "historical_first_visible": None,
                "reuse_only": reuse,
                "next_page_token": obj.get("next_page_token"),
            }
        )
        for symbol, rows in obj.get("bars", {}).items():
            if reuse and symbol not in ("TSLA", "SMCI"):
                continue
            for i, row in enumerate(rows):
                ref = {"entity_index": ei, "json_pointer": f"/bars/{symbol}/{i}"}
                if a["params"]["timeframe"] == "1Min":
                    by_id[a.get("id", a.get("request_id"))][symbol].append({"row": row, "ref": ref})
                else:
                    daily[symbol].append({"row": row, "ref": ref})
        for kind, rows in obj.get("corporate_actions", {}).items():
            for i, row in enumerate(rows):
                if reuse and not any(
                    row.get(k) in ("TSLA", "SMCI")
                    for k in (
                        "symbol",
                        "old_symbol",
                        "new_symbol",
                        "source_symbol",
                        "acquirer_symbol",
                    )
                ):
                    continue
                actions.append(
                    {
                        "action_type": kind,
                        "row": row,
                        "ref": {
                            "entity_index": ei,
                            "json_pointer": f"/corporate_actions/{kind}/{i}",
                        },
                        "economic_effective_date": row.get("ex_date") or row.get("effective_date"),
                        "process_date_is_not_effective_date": True,
                        "actual_receipt": None,
                        "actual_spendable_at": None,
                    }
                )
    save(OUT / "entity-registry.json", entities)
    save(OUT / "actions.json", actions)
    save(OUT / "daily-context.json", daily)
    cases = json.loads((P / "revisions/v2/source-figure-case-timelines.json").read_text())["cases"]
    summary = []
    with localcontext() as ctx:
        ctx.prec = 60
        for case, frozen_clock in zip(cases, manifest["case_clocks"], strict=True):
            symbol = case["source_ticker"]
            available = by_id[symbol + "_minute_raw"]
            candidate_symbols = ("SBE", "CHPT") if symbol == "CHPT" else (symbol,)
            report = {
                "case": case,
                "clock": frozen_clock,
                "source_claim": "Retrospective illustration, not actual traderfill",
                "alias_candidates_kept_separate": True,
                "symbol_components": {},
            }
            for candidate in candidate_symbols:
                grouped = defaultdict(list)
                for item in available[candidate]:
                    t = datetime.fromisoformat(item["row"]["t"].replace("Z", "+00:00")).astimezone(
                        NEW_YORK
                    )
                    grouped[t].append(item)
                by_time = {}
                conflicts = []
                identical_duplicates = []
                for t, items in grouped.items():
                    unique = {canonical(x["row"]) for x in items}
                    ok = (
                        len(unique) == 1
                        and t.second == 0
                        and t.microsecond == 0
                        and valid(items[0]["row"])
                    )
                    by_time[t] = {
                        **items[0],
                        "valid": ok,
                        "duplicate_refs": [x["ref"] for x in items[1:]],
                    }
                    if len(unique) > 1:
                        conflicts.append(t.isoformat())
                    elif len(items) > 1:
                        identical_duplicates.append(t.isoformat())
                start = date.fromisoformat(frozen_clock["prefix_start_session"])
                end = date.fromisoformat(frozen_clock["date_candidate"])
                session_summaries = []
                charts = []
                minutes = []
                for day in us_equity_session_dates(start, end):
                    grid = minute_grid(day)
                    missing = [
                        x.isoformat() for x in grid if x not in by_time or not by_time[x]["valid"]
                    ]
                    session_summaries.append(
                        {
                            "day": str(day),
                            "session_close_NY": str(us_equity_session_close(day)),
                            "expected_minutes": len(grid),
                            "missing_or_invalid_minutes": missing,
                            "complete_RTH": not missing,
                        }
                    )
                    charts += completed_chartbars(day, by_time)
                    minutes += [
                        {"timestamp_NY": t.isoformat(), **by_time[t]} for t in grid if t in by_time
                    ]
                prior_day = frozen_clock["prior_session"]
                prior_bars = [r for r in charts if r["start_NY"][:10] == prior_day]
                prior_grid = minute_grid(date.fromisoformat(prior_day))
                prior_complete = all(t in by_time and by_time[t]["valid"] for t in prior_grid)
                prior_low = (
                    min((Decimal(str(by_time[t]["row"]["l"])) for t in prior_grid), default=None)
                    if prior_complete
                    else None
                )
                prefix = [r for r in charts if r["complete"] and r["start_NY"][:10] < str(end)]
                sensitivities = []
                for count in (126, 252):
                    window = prefix[-count:]
                    enough = len(window) == count
                    sensitivities.append(
                        {
                            "window_completed_chartbars": count,
                            "available": enough,
                            "actual_completed_prefix_count": len(prefix),
                            "first_seed_bar": window[0]["start_NY"] if enough else None,
                            "seed_policy": "firstcloseofdeclaredfinitewindow_notfirstepisode",
                            "EMA21": ema([r["c"] for r in window], 21) if enough else None,
                            "EMA50": ema([r["c"] for r in window], 50) if enough else None,
                            "not_signal_eligibility_filter": True,
                        }
                    )
                report["symbol_components"][candidate] = {
                    "observed_source_records": len(available[candidate]),
                    "unique_timestamps_all_requested_hours": len(grouped),
                    "RTH_minutes_retained": len(minutes),
                    "conflicting_timestamp_keys": conflicts,
                    "identical_duplicate_timestamp_keys": identical_duplicates,
                    "sessions": session_summaries,
                    "chartbars": charts,
                    "RTH_minutes": minutes,
                    "prior_RTH_complete": prior_complete,
                    "prior_RTH_low": prior_low,
                    "prior_last_chartbar": prior_bars[-1] if prior_bars else None,
                    "EMA_finite_window_sensitivity": sensitivities,
                    "daily_is_context_only_not_PDL_or_execution": True,
                }
            casepath = OUT / (case["case_id"] + ".json")
            save(casepath, report)
            summary.append(
                {
                    "case_id": case["case_id"],
                    "binding": binding(casepath),
                    "symbols": {
                        k: {
                            key: val[key]
                            for key in (
                                "observed_source_records",
                                "RTH_minutes_retained",
                                "prior_RTH_complete",
                                "prior_RTH_low",
                            )
                        }
                        for k, val in report["symbol_components"].items()
                    },
                }
            )
            save(OUT / "progress.json", summary)
    save(
        OUT / "component-result.json",
        {
            "cases": summary,
            "entity_registry": binding(OUT / "entity-registry.json"),
            "actions": binding(OUT / "actions.json"),
            "daily_context": binding(OUT / "daily-context.json"),
            "actual_source_requests": ledger["requests_used"],
            "actual_entity_bytes": ledger["complete_entity_bytes"],
            "economic_runs": 0,
            "firstvisible_unknown": True,
            "new_identity_certification": False,
        },
    )
    save(
        OUT / "build-resource.json",
        {
            "CPU": clock.process_time() - start_cpu,
            "RSS_KiB": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            "economic_runs": 0,
        },
    )
    print(json.dumps({"cases": len(summary), "economic_runs": 0}))


if __name__ == "__main__":
    main()
