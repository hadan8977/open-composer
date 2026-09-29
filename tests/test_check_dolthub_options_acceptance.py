"""Tests for the pure metric helpers of scripts/check_dolthub_options_acceptance.py."""

from __future__ import annotations

import importlib.util
import sys
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "check_dolthub_options_acceptance.py"
spec = importlib.util.spec_from_file_location("check_dolthub_options_acceptance", SCRIPT)
assert spec and spec.loader
chk = importlib.util.module_from_spec(spec)
sys.modules["check_dolthub_options_acceptance"] = chk
spec.loader.exec_module(chk)

DAY = date(2026, 9, 28)
EXP = date(2026, 10, 9)  # 11 calendar days out


def leg(strike: float, cp: str, bid: float, ask: float, delta: float, vol: float = 0.2) -> dict:
    return {
        "date": DAY,
        "act_symbol": "SPY",
        "expiration": EXP,
        "strike": strike,
        "call_put": cp,
        "bid": bid,
        "ask": ask,
        "vol": vol,
        "delta": delta,
    }


def chain(spot: float) -> pd.DataFrame:
    rows = []
    for k, c_delta in ((760.0, 0.6), (766.0, 0.5), (772.0, 0.4)):
        call = max(spot - k, 0) + 6
        put = max(k - spot, 0) + 6
        rows.append(leg(k, "Call", call - 0.05, call + 0.05, c_delta))
        rows.append(leg(k, "Put", put - 0.05, put + 0.05, c_delta - 1))
    return pd.DataFrame(rows)


def test_parity_recovers_spot_and_atm_spread() -> None:
    out = chk.chain_day_metrics(chain(766.0), DAY, ref_close=766.0)
    assert out["parity"] == pytest.approx(766.0, abs=1e-9)
    assert out["parity_dte"] == 11
    assert out["atm_delta"] == pytest.approx(0.5)
    assert out["atm_spread"] == pytest.approx(0.10 / 6.0, rel=1e-6)
    assert out["stale_n"] == 0


def test_stale_quotes_are_detected() -> None:
    df = pd.concat(
        [chain(766.0), pd.DataFrame([leg(700.0, "Call", 0.5, 0.6, 0.6)])], ignore_index=True
    )
    # intrinsic 66 at spot 766, mid 0.55: below intrinsic by far more than 1% of spot
    out = chk.chain_day_metrics(df, DAY, ref_close=766.0)
    assert out["stale_n"] == 1


def test_no_expiry_far_enough_gives_no_parity() -> None:
    df = chain(766.0).assign(expiration=date(2026, 9, 29))  # DTE 1 < 3
    out = chk.chain_day_metrics(df, DAY, ref_close=766.0)
    assert "parity" not in out and "atm_spread" not in out


def test_symbol_judgement_requires_every_check() -> None:
    criteria = {
        "thresholds": {
            "coverage_since_2019_min": 0.85,
            "coverage_since_2024_min": 0.90,
            "parity_median_abs_rel_dev_max": 0.001,
            "atm_rel_spread_median_max": {"SPY": 0.03},
            "bad_quote_share_max": 0.02,
        }
    }
    cov = {"SPY": {"since_2019": {"coverage": 0.9}, "since_2024": {"coverage": 0.95}}}
    par = {
        "SPY": {"clean_window": {"criterion_median_abs_dev": 0.0005, "closer_reference": "close_d"}}
    }
    spr = {"SPY": {"full": {"atm_median": 0.01}, "since_2024": {"atm_median": 0.01}}}
    bad = {"SPY": {"band_bad_share_excluding_stale": 0.001}}
    ok = chk.symbol_judgement("SPY", cov, par, spr, bad, {}, criteria)
    assert ok["meets_every_criterion"]
    cov["SPY"]["since_2024"]["coverage"] = 0.87
    failed = chk.symbol_judgement("SPY", cov, par, spr, bad, {}, criteria)
    assert not failed["meets_every_criterion"]
    assert failed["checks"]["coverage_since_2024"] is False
