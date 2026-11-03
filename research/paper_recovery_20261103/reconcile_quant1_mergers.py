"""Finite read-only reconstruction; merger receivables never change broker books."""
from collections import defaultdict
from datetime import UTC, datetime
from decimal import Decimal as D, ROUND_HALF_UP
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "reports/owner/paper-recovery-20261103"
EVIDENCE = OUT / "evidence"
CONSUMED = {}
TERMS = {
    "CBZ": ("2026-11-02", "55.00", "https://www.sec.gov/Archives/edgar/data/944148/000119312526442819/d65130d8k.htm"),
    "LXP": ("2026-11-02", "61.20", "https://www.sec.gov/Archives/edgar/data/910108/000110465926121376/tm2628722d1_8k.htm"),
    "RAMP": ("2026-11-02", "38.50", "https://www.sec.gov/Archives/edgar/data/733269/000110465926121353/tm2628592d27_8k.htm"),
    "WEAV": ("2026-10-26", "7.40", "https://www.sec.gov/Archives/edgar/data/1609151/000160915126000120/weav-20261026.htm"),
    "KVUE": ("2026-11-02", "3.50", "https://www.sec.gov/Archives/edgar/data/55785/000110465926120990/tm2628636d1_ex99-1.htm"),
}
FRACTION_SOURCE = "https://www.sec.gov/Archives/edgar/data/55785/000114036125045609/ny20059815x4_424b3.htm"


def load(path):
    raw = path.read_bytes()
    CONSUMED[str(path.relative_to(ROOT))] = hashlib.sha256(raw).hexdigest()
    return json.loads(raw, parse_float=D)


def main():
    quantities = defaultdict(D)
    cash = D(0)
    activities = load(EVIDENCE / "quant1/activities-all.json")
    assert len({r["id"] for r in activities}) == len(activities)
    for row in activities:
        day = (row.get("transaction_time") or row["date"])[:10]
        assert day <= "2026-11-02"
        if row["activity_type"] == "FILL":
            assert row["side"] in {"buy", "sell", "sell_short"}
            delta = D(row["qty"]) * (1 if row["side"] == "buy" else -1)
            quantities[row["symbol"]] += delta
            cash -= delta * D(row["price"])
        else:
            cash += D(row.get("net_amount", "0"))
            if "qty" in row:
                quantities[row["symbol"]] += D(row["qty"])
    quantities = {s: q for s, q in quantities.items() if q}
    positions = load(EVIDENCE / "quant1/positions.json")
    account = load(EVIDENCE / "quant1/account.json")
    assert quantities == {p["symbol"]: D(p["qty"]) for p in positions}
    assert cash == D(account["cash"])
    marks = {}
    for path in sorted((EVIDENCE / "market").glob("raw-*.json")):
        if ".receipt." in path.name:
            continue
        for symbol, rows in load(path)["bars"].items():
            for row in rows:
                key = (symbol, row["t"][:10])
                assert key not in marks or marks[key] == row
                marks[key] = row
    missing = {s for s in quantities if (s, "2026-11-02") not in marks}
    assert missing == set(TERMS)
    assert not any(r["activity_type"] != "FILL" and r.get("symbol") in missing for r in activities)
    liquid_value = sum(q * D(str(marks[s, "2026-11-02"]["c"])) for s, q in quantities.items() if s not in missing)
    receivables = []
    cards = []
    for symbol, (effective, per_share, source) in TERMS.items():
        assert quantities[symbol] > 0
        amount = quantities[symbol] * D(per_share)
        received = next(p for p in positions if p["symbol"] == symbol)
        receivables.append({"symbol": symbol, "effective_date": effective, "old_quantity": str(quantities[symbol]), "cash_terms_per_share_usd": per_share, "contract_cash_receivable_usd": str(amount), "broker_saved_market_value_usd": received["market_value"], "last_raw_bar_date": max(d for s, d in marks if s == symbol), "source_url": source, "broker_posting_observed": False})
        claim = f"{symbol} merger completed {effective}; shares ceased trading and each eligible share became a right to ${per_share} cash"
        if symbol == "KVUE":
            claim += " plus 0.14625 KMB shares, subject to fractional-share cash rules"
        cards.append({"claim_id": f"t20261002_book_v12:{symbol.lower()}-completed-merger-20261103", "claim": claim + ".", "source_url": source, "source_type": "regulatory_docs", "accessed_at": "2026-11-03", "applies_to": ["company_filing_data", "alpaca_paper_execution"], "impact_on_spec": "Classify the observed held legacy symbol as a completed-merger receivable; preserve native untradable limits and broker account records.", "limitations": "Issuer terms do not prove broker processing or authorize a cash/position mutation. This is current retrospective reconciliation, not a historical trading signal."})
    # The agreement specifies Bloomberg daily VWAP. SIP VWAP is only a proxy;
    # even a cent-rounded estimate is not the eventual broker cash-in-lieu.
    days = ["2026-10-26", "2026-10-27", "2026-10-28", "2026-10-29", "2026-10-30"]
    daily_vwap = {d: D(str(marks["KMB", d]["vw"])) for d in days}
    fractional_price_proxy = sum(daily_vwap.values()) / D(5)
    total_shares = quantities["KVUE"] * D("0.14625")
    whole_shares = int(total_shares)
    fraction = total_shares - D(whole_shares)
    cash_in_lieu_proxy = (fraction * fractional_price_proxy).quantize(D("0.01"), rounding=ROUND_HALF_UP)
    kmb_close = D(str(marks["KMB", "2026-11-02"]["c"]))
    cash_receivable = sum(D(r["contract_cash_receivable_usd"]) for r in receivables)
    successor_stock_value = D(whole_shares) * kmb_close
    estimated_equity = cash + liquid_value + cash_receivable + successor_stock_value + cash_in_lieu_proxy
    result = {
        "checked_at": datetime.now(UTC).isoformat(), "valuation_date": "2026-11-02",
        "method": "Independently reconstruct all broker FILL/nontrade cash and quantities, then raw same-day closes plus completed-merger contractual receivables. No broker or runtime writes.",
        "activity_count": len(activities), "fill_count": sum(r["activity_type"] == "FILL" for r in activities),
        "position_count": len(quantities), "positions_match_broker": True, "cash_match_broker": True,
        "cash_from_all_activities_usd": str(cash), "same_day_raw_marked_position_value_usd": str(liquid_value),
        "pending_mergers": receivables, "contract_cash_receivable_usd": str(cash_receivable),
        "kvue_successor_whole_KMB_shares": whole_shares, "KMB_raw_nov02_close_usd": str(kmb_close),
        "kvue_successor_stock_value_usd": str(successor_stock_value), "kvue_fractional_KMB_entitlement": str(fraction),
        "kvue_fractional_cash_proxy_usd": str(cash_in_lieu_proxy), "KMB_SIP_daily_VWAP_proxy": {d: str(v) for d, v in daily_vwap.items()},
        "fractional_terms_source_url": FRACTION_SOURCE,
        "estimated_economic_equity_usd": str(estimated_equity), "estimated_profit_from_initial_1m_usd": str(estimated_equity - D(1000000)),
        "estimated_return_pct": str((estimated_equity / D(1000000) - 1) * 100),
        "broker_latest_observed_equity_usd_unchanged": account["equity"],
        "exact_broker_Nov02_close_available": False,
        "limitations": ["Merger receivables are unposted; never add them to broker cash while also retaining the old shares.", "Cash-in-lieu uses saved SIP VWAP as a proxy for the contractual Bloomberg VWAP; actual custodian allocation, tax and fees are not yet observed.", "Other unposted dividends remain excluded as in the original actual-performance report.", "This is a retrospective valuation of actual positions, not a continuously executed strategy backtest."],
        "source_bindings": CONSUMED,
    }
    (OUT / "quant1-merger-reconciliation.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    cards.append({"claim_id": "t20261002_book_v12:kvue-fractional-cash-20261103", "claim": "The Kenvue merger contract pays fractional KMB shares in cash rounded to cents using the average Bloomberg daily VWAP across the five trading days ending immediately before closing.", "source_url": FRACTION_SOURCE, "source_type": "regulatory_docs", "accessed_at": "2026-11-03", "applies_to": ["company_filing_data"], "impact_on_spec": "Use a separately labelled proxy estimate until actual broker cash-in-lieu is observed.", "limitations": "Saved SIP daily VWAP is not the specified Bloomberg series; no exact cash posting is inferred."})
    (OUT / "quant1-merger-source-cards.jsonl").write_text("".join(json.dumps(c, ensure_ascii=False) + "\n" for c in cards))
    print(json.dumps({k: v for k, v in result.items() if k not in {"source_bindings", "pending_mergers", "method", "limitations", "KMB_SIP_daily_VWAP_proxy"}}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
