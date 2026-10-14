# ruff: noqa: E501
"""Actual source/shape/action preparation, no candidate returns or selection."""

import hashlib
import json
import re
import xml.etree.ElementTree as ET
import zipfile
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd
from evaluator import load_actions, load_bars, matrices

from open_composer.market_sessions import us_equity_session_dates

P = Path(__file__).parent
ROOT = Path.cwd()
INPUTS = P / "inputs"
NOW = datetime.now(UTC).isoformat()


def bind(p):
    p = Path(p)
    return {
        "path": str(p.resolve().relative_to(ROOT)),
        "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
        "bytes": p.stat().st_size,
    }


def save(p, x):
    Path(p).write_text(json.dumps(x, indent=2, default=str) + "\n")


review = json.loads((P / "independent-plan-review.json").read_text())
assert review["verdict"] == "approve_deep_plan"
assert any(
    b["sha256"]
    in {bind(P / "scientific-plan.json")["sha256"], bind(P / "scientific-plan-v2.json")["sha256"]}
    for b in review["bindings"].values()
)  # sourceQAauthorized; economicnativegate still requires latest approval
ledger = json.loads((INPUTS / "market-request-ledger.json").read_text())
assert len(ledger) <= 24 and sum(r.get("bytes", 0) for r in ledger) <= 16777216
for row in ledger:
    if "path" in row:
        assert bind(row["path"])["sha256"] == row["sha256"]
raw, adj = load_bars("raw"), load_bars("all")
expected = pd.DatetimeIndex(
    us_equity_session_dates(datetime(2016, 1, 4).date(), datetime(2026, 10, 12).date())
)
shape = {}
errors = []
for mode, df in [("raw", raw), ("all", adj)]:
    for s in ["SPY", "SSO", "BIL"]:
        d = df[df.symbol == s].sort_values("date")
        dates = pd.DatetimeIndex(d.date)
        missing = expected.difference(dates)
        extra = dates.difference(expected)
        finite = np.isfinite(d[["o", "h", "l", "c", "v"]].to_numpy()).all()
        ohlc = (
            (d.h >= d[["o", "c", "l"]].max(axis=1)) & (d.l <= d[["o", "c", "h"]].min(axis=1))
        ).all()
        ghost = ((d.v == 0) & (d.n == 0)).sum()
        shape[mode + "_" + s] = {
            "rows": len(d),
            "first": str(dates.min().date()),
            "last": str(dates.max().date()),
            "missing_session_dates": [str(x.date()) for x in missing],
            "extra_session_dates": [str(x.date()) for x in extra],
            "finite": bool(finite),
            "ohlc_valid": bool(ohlc),
            "ghost_rows": int(ghost),
        }
        if len(missing) or len(extra) or not finite or not ohlc or ghost:
            errors.append(mode + "_" + s + " incomplete_or_invalid")
assert not errors, errors

# Reparse actual retained issuer XLSX, not hardcoded payable dates or next-business-day guesses.
ssga = Path(
    "reports/research/program/day-goal-20261011/root-source-support/ssga-historical-distributions.xlsx"
)
receipt = Path("reports/research/program/day-goal-20261011/root-source-support/ssga-fetch.json")
assert bind(ssga)["sha256"] == json.loads(receipt.read_text())["sha256"]
N = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
with zipfile.ZipFile(ssga) as z:
    strings = [
        "".join(e.itertext())
        for e in ET.fromstring(z.read("xl/sharedStrings.xml")).findall("m:si", N)
    ]
    sheet = ET.fromstring(z.read("xl/worksheets/sheet1.xml"))
issuer = []
for row in sheet.findall(".//m:row", N):
    vals = {}
    for cell in row.findall("m:c", N):
        v = cell.find("m:v", N)
        text = "" if v is None else v.text
        vals[re.sub(r"\d", "", cell.get("r"))] = (
            strings[int(text)] if text and cell.get("t") == "s" else text
        )
    if vals.get("B") not in {"SPY", "BIL"}:
        continue
    ex = datetime.strptime(vals["D"].strip(), "%m/%d/%Y").date().isoformat()
    if not "2016-04-01" <= ex <= "2026-10-12":
        continue
    assert not vals.get("H", "").strip() or float(vals["H"]) == 0, (
        "Unmatched extra capitalgain needs source accounting"
    )
    assert not vals.get("I", "").strip() or float(vals["I"]) == 0, (
        "Unmatched extra capitalgain needs source accounting"
    )
    issuer.append(
        {
            "id": "ssga_" + vals["B"] + "_" + ex,
            "symbol": vals["B"],
            "ex_date": ex,
            "record_date": datetime.strptime(vals["E"].strip(), "%m/%d/%Y").date().isoformat(),
            "payable_date": datetime.strptime(vals["F"].strip(), "%m/%d/%Y").date().isoformat(),
            "type": "cash_dividends",
            "amount": float(vals["G"]),
            "currency": "USD",
            "foreign": False,
            "source_excel_row": int(row.get("r")),
            "source": bind(ssga),
            "blank_gains": "unknown retained; not asserted authenticatedzero, provider/factor completeness audited separately",
        }
    )
by = {(a["symbol"], a["ex_date"]): a for a in issuer}
actions = []
repairs = []
sso_missing = []
for a in load_actions():
    s = a.get("symbol")
    ex = a.get("ex_date")
    typ = a["action_group"]
    if s not in {"SPY", "SSO", "BIL"} or not "2016-04-01" <= ex <= "2026-10-12":
        continue
    if typ == "cash_dividends":
        rate = float(a.get("rate", a.get("cash_rate")))
        r = {
            "id": a["id"],
            "symbol": s,
            "ex_date": ex,
            "type": typ,
            "amount": rate,
            "record_date": a.get("record_date"),
            "payable_date": a.get("payable_date"),
            "source": bind(INPUTS / "actions-01.json"),
            "currency_field": a.get("currency"),
            "foreign": a.get("foreign"),
        }
        assert r["foreign"] is False and a.get("currency", "USD") == "USD"
        if (s, ex) in by:
            source = by[(s, ex)]
            assert abs(rate - source["amount"]) <= 0.500001e-6, (
                s,
                ex,
                rate,
                source["amount"],
            )  # issuer sixdecimal display precision; retainproviderfullrate
            if r["payable_date"] is not None:
                assert r["payable_date"] == source["payable_date"]
            r.update(
                payable_date=source["payable_date"],
                record_date=source["record_date"],
                issuer_source=source["source"],
                issuer_row=source["source_excel_row"],
            )
            if not a.get("payable_date"):
                repairs.append(
                    {
                        "id": a["id"],
                        "symbol": s,
                        "ex_date": ex,
                        "payable_date": r["payable_date"],
                        "amount": rate,
                        "issuer_row": source["source_excel_row"],
                    }
                )
        if not r["payable_date"]:
            sso_missing.append({"id": a["id"], "symbol": s, "ex_date": ex, "amount": rate})
    elif typ in {"forward_splits", "reverse_splits"}:
        r = {
            "id": a["id"],
            "symbol": s,
            "ex_date": ex,
            "type": typ,
            "ratio": float(a["new_rate"]) / float(a["old_rate"]),
            "source": bind(INPUTS / "actions-01.json"),
        }
    else:
        raise ValueError("Unsupported fund action " + typ)
    actions.append(r)
present = {(a["symbol"], a["ex_date"]) for a in actions if a["type"] == "cash_dividends"}
added = []
for a in issuer:
    if (a["symbol"], a["ex_date"]) not in present and a["amount"] > 0:
        actions.append(a)
        added.append(
            {
                "symbol": a["symbol"],
                "ex_date": a["ex_date"],
                "amount": a["amount"],
                "payable_date": a["payable_date"],
                "issuer_row": a["source_excel_row"],
            }
        )
actions = sorted(actions, key=lambda a: (a["ex_date"], a["symbol"], a["type"]))
save(
    INPUTS / "normalized-actions.json",
    {
        "actions": actions,
        "issuer": bind(ssga),
        "issuer_receipt": bind(receipt),
        "provider": bind(INPUTS / "actions-01.json"),
        "repairs": repairs,
        "added_source_actions": added,
        "unresolved_payable": sso_missing,
        "all_amounts_consumed_from_actual_bound_fields": True,
        "amount_match_precision": "Issuer6decimaldisplay versusproviderfullrate, tolerance0.500001microUSD; providerfullrate retained, no inventedamount.",
        "cash_account_ready_for_common_2020_scope": {"SPY": True, "SSO": True, "BIL": True},
        "original_2016_SSO_cash_ready": False,
        "currency_caveat": "Alpaca rate usesUSD fixedUS-listedfund accounting; currencyfield absent preserved. SSGA explicitly USD; no foreign dividends.",
    },
)
c, o, ac, hygiene = matrices(raw, adj, actions)
save(INPUTS / "price-hygiene.json", hygiene.manifest())
# Corporate-action completeness check: unexplained adjustment-factor changes are not a strategy filter.
reconciliation = {}
for s in ["SPY", "SSO", "BIL"]:
    factor = ac[s] / c[s]
    changes = factor / factor.shift() - 1
    actiondates = {pd.Timestamp(a["ex_date"]) for a in actions if a["symbol"] == s}
    unexpected = changes[
        (changes.abs() > 0.001)
        & ~changes.index.isin(actiondates)
        & (changes.index >= pd.Timestamp("2016-04-01"))
    ]
    reconciliation[s] = {
        "provider_adjustment_factor_unexplained_above10bp": {
            str(k.date()): float(v) for k, v in unexpected.items()
        },
        "bound_action_count": sum(a["symbol"] == s for a in actions),
        "limits": "Backadjustment ratios rounded;10bp diagnostic flagsmaterialunknowns, not proof of everytinycashaction. ActualissuerSPY/BIL suppliesincome/paydates; unknowncapitalgainblanks remain caveat.",
    }
    assert unexpected.empty, (s, reconciliation[s])
    daily = factor / factor.shift()
    prev = c[s].shift()
    pred = pd.Series(1.0, index=c.index)
    for day in c.index[c.index >= pd.Timestamp("2020-01-02")]:
        ev = [a for a in actions if a["symbol"] == s and a["ex_date"] == str(day.date())]
        split = np.prod([a["ratio"] for a in ev if a["type"] != "cash_dividends"])
        div = sum(a["amount"] for a in ev if a["type"] == "cash_dividends")
        pred.loc[day] = split * prev.loc[day] / (prev.loc[day] - split * div)
    residual = (daily - pred).loc["2020-01-02":].abs()
    reconciliation[s]["full2020_action_factor_check"] = {
        "formula": "all/raw adjustmentfactor ratio=split*prevrawclose/(prevrawclose-split*knowncashamount)",
        "max_abs_factor_residual": float(residual.max()),
        "unexplained_above_0_5bp_dates": {
            str(k.date()): float(v) for k, v in residual[residual > 5e-5].items()
        },
        "tolerance": 5e-5,
    }
    # Action-free intervals must each admit one constantall/rawfactor atliteralcentresolution.
    segment = c.loc["2020-01-02":, s]
    low = (ac.loc[segment.index, s] - 0.005) / segment
    high = (ac.loc[segment.index, s] + 0.005) / segment
    boundaries = [segment.index[0]] + sorted(
        d for d in actiondates if d > segment.index[0] and d <= segment.index[-1]
    )
    segments = []
    for j, start in enumerate(boundaries):
        end = (
            boundaries[j + 1]
            if j + 1 < len(boundaries)
            else segment.index[-1] + pd.Timedelta(days=1)
        )
        use = segment.index[(segment.index >= start) & (segment.index < end)]
        lo, hi = float(low.loc[use].max()), float(high.loc[use].min())
        item = {
            "start": str(start.date()),
            "end": str(use[-1].date()),
            "lower": lo,
            "upper": hi,
            "passes": lo <= hi + 1e-12,
            "sessions": len(use),
        }
        segments.append(item)
        assert item["passes"], (s, item)
    transitions = []
    for j in range(1, len(segments)):
        day = pd.Timestamp(segments[j]["start"])
        ev = [a for a in actions if a["symbol"] == s and a["ex_date"] == str(day.date())]
        split = np.prod([a["ratio"] for a in ev if a["type"] != "cash_dividends"])
        div = sum(a["amount"] for a in ev if a["type"] == "cash_dividends")
        previous = segments[j - 1]
        current = segments[j]
        observed_low = current["lower"] / previous["upper"]
        observed_high = current["upper"] / previous["lower"]
        priorclose_discount = split * prev.loc[day] / (prev.loc[day] - split * div)
        exclose_reinvestment = split * (1 + div / c.loc[day, s])
        expected_low = min(priorclose_discount, exclose_reinvestment)
        expected_high = max(priorclose_discount, exclose_reinvestment)
        item = {
            "date": str(day.date()),
            "observed_factor_interval": [observed_low, observed_high],
            "two_physical_convention_range": [float(expected_low), float(expected_high)],
            "passes": bool(
                observed_low <= expected_high + 1e-6 and observed_high >= expected_low - 1e-6
            ),
        }
        transitions.append(item)
        # Preserve unmatchedknown-transition warnings: exactvendorfactorconvention unverified.
    reconciliation[s]["full2020_cent_interval_actionchain"] = {
        "segments": segments,
        "transitions": transitions,
        "passes": all(t["passes"] for t in transitions),
        "unmatched_known_transition_warnings": [t for t in transitions if not t["passes"]],
        "research_consistency_scope": "Allknown-action-freeintervals constantatcentresolution;largeunexplainedchangesabsent;knowntransitionformula differences retainedwarnings,not certifiedexactvendortransform",
        "declared_adjusted_price_rounding_halfwidth_USD": 0.005,
        "method": "Everyknown-action-freeinterval constantfactor atcentresolution;knowneventtransition bracketspreviousclose-discountandexclose-reinvestment,1e-6 coefficientroundingmargin. No assumedexactproviderformula, no return/outcomeeligibilityfilter.",
        "limits": "Currentvintageprovider-adjustment conventions inferred/uncertified. Omissionsbelowdisplayresolution cannotbecertified; rawfundedledger usesboundactualactions. Thisisresearch-inputconsistency,notactualPIT/paperproof.",
        "max_point_factor_residual": float(residual.max()),
    }
save(INPUTS / "action-completeness.json", reconciliation)
fq = Path("reports/research/program/regime-french-source-20261010-1917/official-daily.zip")
with zipfile.ZipFile(fq) as z:
    text = z.read("F-F_Research_Data_Factors_daily.csv").decode()
flines = [
    ln
    for ln in text.splitlines()
    if re.match(r"^\d{8},", ln.strip()) and "20150101" <= ln.strip()[:8] <= "20260831"
]
assert flines
save(
    INPUTS / "french-input-shape.json",
    {
        "source": bind(fq),
        "rows": len(flines),
        "first_date": flines[0].split(",")[0],
        "last_date": flines[-1].split(",")[0],
        "columns": ["date", "Mkt-RF", "SMB", "HML", "RF"],
        "vintage": "current202608CRSP, notoriginalPIT",
        "float_market_payloads_decoded": 0,
        "numeric_parser_execution": "deferreduntilnativeeconomicgate; date/schema QA only",
    },
)
bindings = {
    n: bind(p)
    for n, p in {
        "plan": P / "scientific-plan.json",
        "independent_plan": P / "independent-plan-review.json",
        "contract": P / "execution-contract.json",
        "calendar": P / "calendar-packet.json",
        "cash_calendar": P / "cash-calendar.json",
        "market_ledger": INPUTS / "market-request-ledger.json",
        "actions": INPUTS / "normalized-actions.json",
        "completeness": INPUTS / "action-completeness.json",
        "hygiene": INPUTS / "price-hygiene.json",
        "french_shape": INPUTS / "french-input-shape.json",
        "host_clock": Path(
            "reports/research/program/day-goal-20261013/primary-return-next/host-close-clock-binding.json"
        ),
    }.items()
}
accept = {
    "schema_version": 1,
    "as_of": NOW,
    "actual_market_responses": len(ledger),
    "actual_market_bytes": sum(r.get("bytes", 0) for r in ledger),
    "cash_account_input_ready_for_proposed_2020_scope": {"SPY": True, "SSO": True, "BIL": True},
    "original_2016_application": "N/A_input_unready_preserved",
    "reason": "15SSO source cashrecords lackactualpayable_date2016-2019; documentednativeissuerreference read returnedempty2-byte[] once, no retries. Source40/40 exhausted; no inferredpayday or secretpaidendpoint. Originalpre2020 cashscopeunready, proposed2020completefields+factorQA conditionalonR4approval. SPY/BIL repaired/reconciled usingexistingofficialissuerworkbook, no newsource request.",
    "shapes": shape,
    "bindings": bindings,
    "source_paydate_repairs": len(repairs),
    "issuer_added_missing_distributions": len(added),
    "economic_runs": 0,
    "scope": "Proposedcommonfunded2020-2026sixstreams afterlatestR4plan+implementation/native gates;original2016SSO cashscope remainsN/A. Actualpaydate/price/actionfields present, cashavailabilityunverifiedconservativeproxy; openingreference notactualfills.",
    "workflow_input_pass": "actual_fields_2020_scope;latestR4_andimplementation/native_authorization_required",
    "research_pass": False,
    "paper_ready_pass": False,
}
save(INPUTS / "input-acceptance.json", accept)
state = json.loads((P / "current-state.json").read_text())
state.update(
    status="actual_fields_complete_for_proposed_2020_scope_independent_delta_pending",
    new_market_requests=len(ledger),
    new_market_bytes=accept["actual_market_bytes"],
    actual_input_acceptance=bind(INPUTS / "input-acceptance.json"),
    next_action="Completecurrent6stream implementation andindependentmanifest acceptance afterR4inputscope delta;original2016SSOcash N/A preserved.",
)
save(P / "current-state.json", state)
print(
    "accept",
    bind(INPUTS / "input-acceptance.json"),
    "repairs",
    len(repairs),
    "added",
    len(added),
    "SSO_missing",
    len(sso_missing),
)
