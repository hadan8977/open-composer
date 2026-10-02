"""Tests of the v1.2 production target generator (``open_composer.book_paper.v12_targets``).

The parity tests read the research snapshot (``data/research/equity_book``) and skip when it is
absent.  The reference is the account simulator of ``scripts/book_v12_account.py`` run through the
full-history ``realism_ladder_book_ls.Context`` (own price matrices, stateful monthly M1 sources),
so the generator's window loader and stateless tranche recomputation are checked against the
backtest's own path."""

from __future__ import annotations

import json
from datetime import date

import numpy as np
import pandas as pd
import pytest

from open_composer.book_paper import v12_targets as v12
from open_composer.book_paper.plan import round_half_away
from open_composer.book_paper.targets import BookTarget, load_target_file, write_target_file
from open_composer.research.equity_book import book_v12 as bv

SNAPSHOT = v12.RESEARCH_ROOT
HAVE_DATA = (SNAPSHOT / "panel/_calendar.parquet").exists() and (
    SNAPSHOT / "alpha/book_v1/formation_ic.parquet"
).exists()
needs_data = pytest.mark.skipif(not HAVE_DATA, reason="research snapshot not present")

# (variant, D): VIX > 20.60 on the first two dates; 2026-03-18 has an acquired name without a close
PARITY_CASES = (
    ("M0_U3000", "2025-04-10"),
    ("M0_U3000", "2026-03-18"),
    ("M0_U3000", "2026-09-10"),
    ("M1_P1000", "2026-03-18"),  # M1: monthly re-weighted, stateful in the simulator
)
VARIANT = "M0_U3000"  # primary variant of results.json
STAMP = "2026-10-02T06:00:00Z"


# ---------------------------------------------------------------------------
# pure pieces (no data)
# ---------------------------------------------------------------------------
def test_tranche_positions_are_last_decision_dates_at_or_before_d():
    for p_d in (100, 101, 102, 103, 104, 2000):
        pos = v12.tranche_positions(p_d)
        assert [p % 5 for p in pos] == [0, 1, 2, 3, 4]
        assert all(p_d - 4 <= p <= p_d for p in pos)
        assert p_d in pos


def test_primary_variant_refuses_missing_or_non_paper_decision(tmp_path):
    f = tmp_path / "results.json"
    with pytest.raises(v12.TargetRefused, match="no results file"):
        v12.primary_variant(f)
    f.write_text(json.dumps({"primary_variant": "M1_P1000"}))
    with pytest.raises(v12.TargetRefused, match="lacks"):
        v12.primary_variant(f)
    for bad in ("no paper start (P0)", "do not proceed to paper", "hold: stop, no paper", "P0"):
        f.write_text(json.dumps({"primary_variant": "M1_P1000", "decision": bad}))
        with pytest.raises(v12.TargetRefused, match="not a paper start"):
            v12.primary_variant(f)
    f.write_text(json.dumps({"primary_variant": "M1_P1000", "decision": "no paper start (P0)"}))
    with pytest.raises(v12.TargetRefused, match="not a paper start"):
        v12.primary_variant(f)
    f.write_text(json.dumps({"primary_variant": "M9", "decision": "paper_start"}))
    with pytest.raises(v12.TargetRefused, match="not a contract variant"):
        v12.primary_variant(f)
    f.write_text(json.dumps({"primary_variant": "M1_P1000", "decision": {"paper_start": True}}))
    assert v12.primary_variant(f) == "M1_P1000"
    f.write_text(json.dumps({"primary_variant": "M0_U3000", "decision": "paper_start"}))
    assert v12.primary_variant(f) == "M0_U3000"
    text = "proceed to paper incubation per section 6 with M0_U3000 (quant1 F1, quant2 F2)"
    f.write_text(json.dumps({"primary_variant": "M0_U3000", "decision": text}))
    assert v12.primary_variant(f) == "M0_U3000"


def test_unknown_variant_is_refused():
    with pytest.raises(v12.TargetRefused, match="variant"):
        v12.build_v12_targets("2026-09-10", variant="M2_X", data_root="/nonexistent")


def _book(form: str, virt: np.ndarray, hedge: float, close: np.ndarray, spy: float = 500.0):
    return v12._net_book(form, virt, hedge, np.ones_like(virt), close, spy, ("SGOV", 100.0))


def test_net_book_f1_tbill_fills_gross_to_cap_and_rounds_shares():
    close = np.array([50.0, 20.0, 10.0])
    virt = np.array([4000.4, -9999.5, 0.2])  # 0.2 rounds to 0
    book = _book("F1", virt, 300.0, close)
    assert list(book.stock_shares) == [4000, -10000, 0]
    assert book.spy_shares == 300
    long_f = (4000 * 50 + 300 * 500) / bv.EQUITY
    short_f = 10000 * 20 / bv.EQUITY
    assert book.long_frac == pytest.approx(long_f)
    assert book.short_frac == pytest.approx(short_f)
    assert book.tbill_fraction == pytest.approx(bv.tbill_fraction(long_f, short_f))
    assert book.tbill_shares == round_half_away(book.tbill_fraction * bv.EQUITY / 100.0)
    assert not book.scale_event


def test_net_book_f1_scales_when_gross_exceeds_cap():
    close = np.array([100.0, 100.0])
    virt = np.array([9000.0, -9500.0])  # 0.9 + 0.95 of equity -> 1.85 > 1.8
    book = _book("F1", virt, 0.0, close)
    assert book.scale_event
    assert book.scale == pytest.approx(1.8 / 1.85, rel=1e-3)
    assert book.long_frac + book.short_frac <= 1.8 + 1e-3
    assert book.tbill_fraction == pytest.approx(0.0, abs=2e-3)


def test_net_book_f2_adds_spy_core_and_has_no_tbill():
    close = np.array([50.0])
    book = _book("F2", np.array([1000.0]), -100.0, close, spy=500.0)
    assert book.tbill_symbol is None and book.tbill_shares == 0
    assert book.spy_shares == round_half_away(-100.0 + 1.0 * bv.EQUITY / 500.0)
    assert book.hedge_virtual == pytest.approx(-100.0)


# ---------------------------------------------------------------------------
# parity with the account simulator (needs the research snapshot)
# ---------------------------------------------------------------------------
def _reference(date_s: str, variant: str):
    """Target shares of both forms at ``date_s`` from the account simulator's own machinery."""
    from scripts import book_v12_account as acct
    from scripts import realism_ladder_book_ls as t25

    ctx = t25.Context()
    px = ctx.px
    p_d = int(px.dates.get_loc(pd.Timestamp(date_s)))
    start_t = px.dates[p_d - 30]
    start = int(px.dates.searchsorted(pd.Timestamp(start_t.year, start_t.month, 1)))
    flag = acct.variant_flag(variant)
    sources = [acct.make_source(ctx, variant) for _ in t25.OFFSETS]
    etf = acct.etf_series(px)
    cf = np.nan_to_num(pd.DataFrame(px.C).ffill().to_numpy(), nan=0.0)
    sims = {"F1": acct.AccountSim("F1", ctx, etf, cf), "F2": acct.AccountSim("F2", ctx, etf, cf)}
    for p in range(start, p_d + 1):
        o = p % t25.WEEK
        di = acct.decision_inputs(ctx, sources[o], flag, p)
        if di is None:
            continue
        tt = acct.tranche_from_inputs(ctx, di)
        for sim in sims.values():
            sim.refresh(o, tt, px.C[p], float(px.spy_c[p]))
    out = {}
    close_d, spy_d = px.C[p_d], float(px.spy_c[p_d])
    for form, sim in sims.items():
        virt = sim.virt.sum(axis=0)
        # the simulator carries a name without a close on D (acquired / halted) until the delisting
        # bound writes it off; a production target cannot size or order it, so it is dropped
        priced = np.isfinite(close_d) & (close_d > 0)
        unpriced = sorted(str(x) for x in px.symbols[(np.abs(virt) > 0) & ~priced])
        virt = np.where(priced, virt, 0.0)
        spy_v = float(sim.virt_h.sum()) + (bv.F2_CORE * bv.EQUITY / spy_d if form == "F2" else 0.0)
        q = bv.round_half_away_array(virt)
        spy_q = int(bv.round_half_away_array(np.array([spy_v]))[0])
        val = q * np.where(np.isfinite(close_d), close_d, 0.0)
        long_f = (val[val > 0].sum() + max(spy_q * spy_d, 0.0)) / bv.EQUITY
        short_f = (-val[val < 0].sum() + max(-spy_q * spy_d, 0.0)) / bv.EQUITY
        # the simulator's own post-trade view (state 0 -> sub-$100 positions dropped)
        res = sim._targets(1.0, close_d, spy_d)
        x = bv.tbill_fraction(long_f, short_f) if form == "F1" else 0.0
        out[form] = {
            "symbols": px.symbols,
            "shares": q,
            "spy": spy_q,
            "x": x,
            "unpriced": unpriced,
            "long_f": long_f,
            "short_f": short_f,
            "sim_long_short": (float(res[8]), float(res[9])),
            "scale_event": form == "F1" and long_f + short_f > bv.G_CAP + 1e-12,
        }
    return out


@needs_data
@pytest.mark.parametrize(("variant", "date_s"), PARITY_CASES)
def test_generator_target_shares_equal_the_account_simulator(variant, date_s):
    ref = _reference(date_s, variant)
    bundle = v12.build_v12_bundle(date_s, variant=variant, logged_at_utc=STAMP, fill_lookahead=True)
    if date_s != "2026-09-10":  # VIX > 20.60 on D: the newest tranche runs at half scale
        assert min(t.vscale for t in bundle.tranches) == 0.5
    again = v12.build_v12_targets(date_s, variant=variant, logged_at_utc=STAMP, fill_lookahead=True)
    for account, form in (("quant1", "F1"), ("quant2", "F2")):
        target = bundle.targets[account]
        assert isinstance(target, BookTarget) and target.schema_version == 2
        assert target.payload_sha256 == again[account].payload_sha256  # stable across two calls
        assert target.book_id == f"t20261002_book_v12:{variant}:{form}"
        r = ref[form]
        assert not r["scale_event"]
        gen = {
            s: round_half_away(w * target.equity_basis / target.reference_prices[s])
            for s, w in target.stock_weights.items()
        }
        gen = {s: q for s, q in gen.items() if q}
        want = {str(s): int(q) for s, q in zip(r["symbols"], r["shares"], strict=True) if q}
        assert len(gen) > 100
        assert sorted(bundle.unpriced[form]) == r["unpriced"]
        assert gen == want, f"{date_s} {form}: stock target shares differ"
        spy_w = target.weights["SPY"]
        spy_q = round_half_away(spy_w * target.equity_basis / target.reference_prices["SPY"])
        assert abs(spy_q - r["spy"]) <= 1
        if form == "F1":
            assert target.core_weight == pytest.approx(r["x"], abs=1e-12)
            sgov_close = target.reference_prices[target.core_symbol]
            sgov_q = target.core_weight * target.equity_basis / sgov_close
            assert abs(sgov_q - r["x"] * bv.EQUITY / sgov_close) <= 1.0
        else:
            assert target.core_weight == 1.0


@needs_data
def test_parity_dates_include_high_vix_decision_dates():
    vix = pd.read_csv(v12.default_vix_dir(SNAPSHOT) / "VIXCLS.csv", na_values=["."])
    vix["observation_date"] = pd.to_datetime(vix["observation_date"])
    s = vix.set_index("observation_date")["VIXCLS"]
    assert s.loc["2025-04-10"] > 20.60 and s.loc["2026-03-18"] > 20.60
    assert s.loc["2026-09-10"] <= 20.60


@needs_data
def test_written_target_files_round_trip_through_the_engine_loader(tmp_path):
    targets = v12.build_v12_targets("2026-09-10", variant=VARIANT, logged_at_utc=STAMP)
    for target in targets.values():
        path = write_target_file(tmp_path, target)
        loaded = load_target_file(path)
        assert loaded.payload_sha256 == target.payload_sha256
        assert loaded.decision_date == date(2026, 9, 10)
        assert loaded.execution_date == date(2026, 9, 11)
        assert target.reference_prices["SPY"] > 0
    f1, f2 = targets["quant1"], targets["quant2"]
    assert f1.hedge_symbol == "SPY" and f1.core_symbol in ("SGOV", "BIL")
    assert f2.core_symbol == "SPY" and f2.core_weight == 1.0
    assert f2.weights["SPY"] == pytest.approx(1.0 + f2.hedge_weight)


# ---------------------------------------------------------------------------
# daily driver and CLI (no data, no broker)
# ---------------------------------------------------------------------------
def _driver():
    from scripts import run_book_v12_daily as driver

    return driver


def test_driver_refuses_submit_without_the_env_var(monkeypatch, tmp_path, capsys):
    driver = _driver()
    monkeypatch.delenv(driver.SUBMIT_ENV, raising=False)
    code = driver.main(
        [
            "--submit",
            "--root",
            str(tmp_path),
            "--lock-file",
            str(tmp_path / "l"),
            "--log-file",
            str(tmp_path / "x.log"),
        ]
    )
    assert code == driver.EXIT_SUBMIT_OFF == 4
    assert "OC_BOOK_V12_SUBMIT" in capsys.readouterr().out
    assert not (tmp_path / "x.log").exists()  # refused before anything else happened
    assert driver.submit_enabled({driver.SUBMIT_ENV: "1"})
    assert not driver.submit_enabled({driver.SUBMIT_ENV: "true"})
    assert not driver.submit_enabled({})


def test_driver_targets_exit_2_when_the_data_root_is_missing_or_stale(tmp_path):
    driver = _driver()
    args = [
        "--targets",
        "--root",
        str(tmp_path),
        "--lock-file",
        str(tmp_path / "l"),
        "--log-file",
        str(tmp_path / "x.log"),
    ]
    assert driver.main([*args, "--data-root", str(tmp_path / "nowhere")]) == driver.EXIT_FRESH == 2


def test_driver_plan_without_targets_is_refused(tmp_path):
    driver = _driver()
    args = [
        "--plan",
        "--root",
        str(tmp_path),
        "--lock-file",
        str(tmp_path / "l"),
        "--log-file",
        str(tmp_path / "x.log"),
    ]
    assert driver.main(args) == driver.EXIT_REFUSED == 3


def test_driver_lock_is_exclusive(tmp_path):
    import fcntl

    driver = _driver()
    lock_path = tmp_path / "l"
    with open(lock_path, "w") as held:
        fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
        code = driver.main(
            [
                "--plan",
                "--root",
                str(tmp_path),
                "--lock-file",
                str(lock_path),
                "--log-file",
                str(tmp_path / "x.log"),
            ]
        )
    assert code == driver.EXIT_LOCKED == 6


@needs_data
def test_cli_targets_summary_exit_codes(tmp_path):
    from typer.testing import CliRunner

    from open_composer.cli import app

    runner = CliRunner()
    stale = runner.invoke(
        app, ["book-paper", "targets", "--decision-date", "2027-01-04", "--variant", VARIANT]
    )
    assert stale.exit_code == 2
    ok = runner.invoke(
        app, ["book-paper", "targets", "--decision-date", "2026-09-10", "--variant", VARIANT]
    )
    assert ok.exit_code == 0, ok.output
    assert "summary only" in ok.output and "quant1" in ok.output and "quant2" in ok.output
