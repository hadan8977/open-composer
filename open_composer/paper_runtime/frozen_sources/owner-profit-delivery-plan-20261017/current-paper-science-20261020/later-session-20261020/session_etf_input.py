"""Current adjusted ETF signal panel and separately received physical units."""
import hashlib
import json
import math
import os
from datetime import date
from zoneinfo import ZoneInfo

import session_etf_common as c
from session_etf_source import PLAN, receive_sources, receive_source_reviews


def finite(value, *, positive=False, integer=False):
    assert type(value) in [int,float] and math.isfinite(value)
    assert value > 0 if positive else value >= 0
    if integer:
        assert int(value) == value
    return value


def bar_rows(objects, symbols, sessions):
    expected = set(sessions)
    rows = {}
    for page in objects:
        assert type(page) is dict and type(page.get("bars")) is dict
        assert set(page["bars"]) <= set(symbols)
        for symbol, values in page["bars"].items():
            assert type(values) is list
            for raw in values:
                assert type(raw) is dict
                stamp = c.clock(raw["t"]).astimezone(ZoneInfo("America/New_York"))
                assert (stamp.hour,stamp.minute,stamp.second,stamp.microsecond) == (0,0,0,0)
                day = stamp.date().isoformat()
                assert day in expected and (symbol,day) not in rows
                for key in ["o","h","l","c"]:
                    finite(raw[key], positive=True)
                finite(raw["v"])
                finite(raw["n"], integer=True)
                assert raw["l"] <= min(raw["o"],raw["c"]) <= max(raw["o"],raw["c"]) <= raw["h"]
                assert raw["v"] > 0 or raw["n"] > 0, "Ghost row is not source support"
                rows[(symbol,day)] = raw
    assert set(rows) == {(s,d) for s in symbols for d in sessions}, "Missing indispensable fixed-menu/session input"
    return rows


def action_rows(objects, symbols):
    output, seen = [], set()
    for page in objects:
        assert type(page) is dict and type(page.get("corporate_actions")) is dict
        for kind, values in page["corporate_actions"].items():
            assert kind in ["cash_dividends","forward_splits","reverse_splits","unit_splits"], "Unsupported ETF identity/right"
            assert type(values) is list
            for raw in values:
                assert type(raw) is dict and type(raw.get("id")) is str and raw["id"] and raw["id"] not in seen
                seen.add(raw["id"])
                assert raw.get("symbol") in symbols
                for name in ["process_date","ex_date","effective_date","payable_date","pay_date","record_date","declaration_date"]:
                    if raw.get(name) is not None:
                        assert type(raw[name]) is str and date.fromisoformat(raw[name]).isoformat() == raw[name]
                assert "2026-09-30" <= raw["process_date"] <= "2026-11-14"
                economic = raw.get("ex_date") or raw.get("effective_date")
                assert economic is not None, "Process/pay date cannot replace indispensable economic date"
                if kind == "cash_dividends":
                    finite(raw["rate"])
                else:
                    finite(raw["new_rate"],positive=True);finite(raw["old_rate"],positive=True)
                if "2026-10-19" < economic <= "2026-10-20":
                    assert kind == "cash_dividends", "Raw reference/application unit change requires affected reception"
                output.append(dict(kind=kind,terms=raw,economic_date=economic,
                    process_date=raw["process_date"],new_position_has_prior_entitlement=False))
    return output


def receive_input_code():
    code=receive_source_reviews()
    review=c.load(c.checked(code["review"]))
    assert review["current_input_implementation_accepted"] is True
    assert c.binding(__file__) in c.load(c.checked(code["manifest"]))["files"]
    return code


def digest(value):
    import numpy as np
    return hashlib.sha256(np.ascontiguousarray(value).tobytes()).hexdigest()


def build_input():
    c.authority();c.kernel("ETF-input")
    code=receive_input_code()
    source=receive_sources()
    c.start("ETF-input",source["source"])
    claim=c.claim_worker("ETF-input");c.computing("ETF-input")
    begin=c.now()
    from open_composer.market_sessions import us_equity_session_dates
    import numpy as np
    import pandas as pd
    from open_composer.research.features.price_hygiene import sanitize_price_matrices
    symbols=c.load(PLAN)["symbols"]
    days=[d.isoformat() for d in us_equity_session_dates(date(2024,1,2),date(2026,10,19))]
    rows=bar_rows(source["objects"]["adjusted-history"],symbols,days)
    raw=bar_rows(source["objects"]["raw-reference"],symbols,["2026-10-16","2026-10-19"])
    actions=action_rows(source["objects"]["actions"],symbols)
    opening=pd.DataFrame([[rows[(s,d)]["o"] for s in symbols] for d in days],index=pd.DatetimeIndex(days),columns=symbols,dtype=float)
    closing=pd.DataFrame([[rows[(s,d)]["c"] for s in symbols] for d in days],index=pd.DatetimeIndex(days),columns=symbols,dtype=float)
    clean_close,clean_open,hygiene=sanitize_price_matrices(closing,opening)
    # No rescue, price-splicing or silent unsupported source-to-cash conversion.
    assert np.isfinite(clean_open.to_numpy()).all() and np.isfinite(clean_close.to_numpy()).all(), "Required signal/overlay history loses default hygiene support"
    assert not hygiene.breaks, "Default split-like trigger sessions are excluded; affected core input is blocked"
    arrays=dict(dates=np.asarray(days,dtype="U10"),symbols=np.asarray(symbols,dtype="U4"),
        opening=clean_open.to_numpy(dtype=np.float64),closing=clean_close.to_numpy(dtype=np.float64))
    destination=c.ROOT/"ETF-input/panel.npz"
    c.guard_write()
    with destination.open("xb") as stream:
        np.savez_compressed(stream,**arrays);stream.flush();os.fsync(stream.fileno())
    return c.finish("ETF-input",dict(policy="ETF-input",input_code=code,panel=c.binding(destination),
        source=source["source"],source_complete=source["source_complete"],source_completed_at=source["source_completed_at"],
        consumed=source["consumed"],source_plan=source["source_plan"],reference_day="2026-10-19",application_day="2026-10-20",
        symbols=symbols,session_count=len(days),first_session=days[0],last_session=days[-1],
        hashes={key:digest(value) for key,value in arrays.items()},
        raw_reference_marks={s:float(raw[(s,"2026-10-19")]["c"]) for s in symbols},
        raw_reference_bars={s:{d:raw[(s,d)] for d in ["2026-10-16","2026-10-19"]} for s in symbols},
        current_actions=actions,hygiene=dict(defaults=True,trigger_count=0,missing_required_support=False),
        signal_units="Provider all-adjusted OPEN/CLOSE for exact existing virtual signal recipes only",
        order_units="Separate actual raw references; raw whole-share quotes/rights/fees/account remain operating facts",
        dividends_not_credited_twice=True,process_dates_are_not_exdate_coverage_or_PIT=True,
        new_fit_count=0,new_label_count=0,new_backtest_count=0,new_historical_funded_account_count=0,
        computed_started_at=begin,computed_completed_at=c.now()))


def receive_input(*,require_peer=True):
    obj=c.receive_stage("ETF-input")
    assert obj["policy"] == "ETF-input" and obj["input_code"] == receive_input_code()
    source=receive_sources()
    _,native=c.receive_native("ETF-input")
    assert native["input"] == source["source"]
    assert c.clock(source["source_completed_at"]) <= c.clock(native["at"])
    for key in ["source","source_complete","source_completed_at","consumed","source_plan"]:
        assert obj[key] == source[key]
    assert obj["reference_day"] == "2026-10-19" and obj["application_day"] == "2026-10-20"
    assert obj["symbols"] == c.load(PLAN)["symbols"] and obj["first_session"] == "2024-01-02" and obj["last_session"] == "2026-10-19"
    assert obj["hygiene"] == dict(defaults=True,trigger_count=0,missing_required_support=False)
    import numpy as np
    with np.load(c.checked(obj["panel"],c.ROOT/"ETF-input/panel.npz"),allow_pickle=False) as z:
        assert set(z.files) == {"dates","symbols","opening","closing"}
        assert z["dates"].dtype == np.dtype("U10") and z["symbols"].dtype == np.dtype("U4")
        assert z["dates"].tolist()[0] == obj["first_session"] and z["dates"].tolist()[-1] == obj["last_session"]
        assert len(z["dates"]) == obj["session_count"] and z["symbols"].tolist() == obj["symbols"]
        assert all(digest(z[key]) == obj["hashes"][key] for key in z.files)
        for key in ["opening","closing"]:
            assert z[key].dtype == np.dtype("float64") and z[key].shape == (obj["session_count"],23)
            assert np.isfinite(z[key]).all() and (z[key]>0).all()
    if require_peer:
        review=c.load(c.ROOT/"independent-ETF-current-input-review.json")
        assert review["task_id"] == c.TASK and review["session_id"] == c.SESSION and review["policy"] == "ETF-input"
        assert review["reviewer"] == c.PEER and review["independent"] is True and review["verdict"] == "accept_complete_current_input"
        assert review["target"] == review["derived_control_witness"] == c.binding(c.ROOT/"ETF-input/output.json")
        assert review["source_linked_controls_accepted"] is True
    return obj


if __name__ == "__main__":
    print(json.dumps(build_input()))
