"""T-20261002-27: book v1.2 forms in the paper engine (SPY hedge leg, variable T-bill leg).

Dry-run only: fake clients and states, no network, no credentials.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest
from pydantic import ValidationError
from test_book_paper import (
    DECISION,
    EXECUTION,
    NOW,
    FakeClient,
    etb,
    failed_checks,
    plan_for,
)

from open_composer.book_paper.plan import (
    AccountState,
    BookEngineError,
    RiskLimits,
    build_plan,
    submit_plan,
)
from open_composer.book_paper.post_close import realized_exposures
from open_composer.book_paper.targets import (
    SCHEMA_VERSION_V2,
    BookTarget,
    BookTargetError,
    NameExposure,
    convert_f1_target_to_f2,
    load_target_file,
    payload_sha256,
    seal_target,
    write_target_file,
)

LONGS = {"L1": 0.20, "L2": 0.15, "L3": 0.15}
SHORTS = {"S1": -0.20, "S2": -0.15, "S3": -0.15}
PRICES = {"L1": 50.0, "L2": 25.0, "L3": 100.0, "S1": 50.0, "S2": 25.0, "S3": 100.0}
SPY_PX, SGOV_PX = 500.0, 100.0
WIDE = RiskLimits(max_name_weight=0.25)  # the toy books hold a few big names
# v1 target fixture and its SHA-256, computed with the engine as of commit 9dcb7d5 (before schema 2)
V1_FIXTURE_SHA256 = "dba00106ade93231fa19c4f75c9bc0c47950130996af30932e14eb87b59ee0b7"


def exposures(long_beta: float, short_beta: float) -> dict[str, NameExposure]:
    out = {
        s: NameExposure(beta=long_beta, industry="a", size=9.0, dollar_adv_21=5e7, vol_21=0.02)
        for s in LONGS
    }
    out |= {
        s: NameExposure(beta=short_beta, industry="b", size=9.0, dollar_adv_21=5e7, vol_21=0.02)
        for s in SHORTS
    }
    out["SGOV"] = NameExposure(beta=0.0, industry="tbill", size=0.0)
    out["SPY"] = NameExposure(beta=1.0, industry="index", size=0.0)
    return out


def f1_target(
    *,
    hedge: float = 0.35,
    core: float = 0.45,
    long_beta: float = 0.4,
    short_beta: float = 1.1,
    **overrides,
) -> BookTarget:
    """F1 v2: dollar-neutral 0.5 / 0.5 stocks, stock beta = 0.5 * 0.4 - 0.5 * 1.1 = -0.35."""
    weights = {**LONGS, **SHORTS, "SGOV": core}
    prices = {**PRICES, "SGOV": SGOV_PX, "SPY": SPY_PX}
    fields = {
        "schema_version": SCHEMA_VERSION_V2,
        "book_id": "t20261002_book_v12:F1",
        "account": "quant1",
        "form": "F1",
        "decision_date": DECISION,
        "execution_date": EXECUTION,
        "equity_basis": 1_000_000.0,
        "core_symbol": "SGOV",
        "core_weight": core,
        "hedge_symbol": "SPY" if hedge else None,
        "hedge_weight": hedge,
        "weights": weights | ({"SPY": hedge} if hedge else {}),
        "reference_prices": prices,
        "exposures": exposures(long_beta, short_beta),
        "logged_at_utc": "2026-09-17T21:00:00Z",
    }
    fields.update(overrides)
    return seal_target(BookTarget(**fields))


def f2_target(*, hedge: float = 0.2, scale: float = 0.5, **overrides) -> BookTarget:
    """F2 v2: SPY 1.0 + hedge merged into one SPY position, overlay beta = -hedge."""
    overlay = {
        "L1": 0.1 * scale / 0.5,
        "L2": 0.1 * scale / 0.5,
        "S1": -0.1 * scale / 0.5,
        "S2": -0.1 * scale / 0.5,
    }
    weights = overlay | {"SPY": 1.0 + hedge}
    fields = {
        "schema_version": SCHEMA_VERSION_V2,
        "book_id": "t20261002_book_v12:F2",
        "account": "quant2",
        "form": "F2",
        "decision_date": DECISION,
        "execution_date": EXECUTION,
        "equity_basis": 1_000_000.0,
        "core_symbol": "SPY",
        "core_weight": 1.0,
        "hedge_symbol": "SPY",
        "hedge_weight": hedge,
        "weights": weights,
        "reference_prices": {k: PRICES[k] for k in overlay} | {"SPY": SPY_PX},
        "exposures": {
            "L1": NameExposure(beta=0.5, industry="a", size=9.0),
            "L2": NameExposure(beta=0.5, industry="a", size=9.0),
            "S1": NameExposure(beta=1.5, industry="b", size=9.0),
            "S2": NameExposure(beta=1.5, industry="b", size=9.0),
            "SPY": NameExposure(beta=1.0, industry="index", size=0.0),
        },
        "logged_at_utc": "2026-09-17T21:00:00Z",
    }
    fields.update(overrides)
    return seal_target(BookTarget(**fields))


def client_for(*symbols: str, **kw) -> FakeClient:
    return FakeClient(assets={s: etb(s) for s in symbols}, **kw)


F1_SYMBOLS = (*LONGS, *SHORTS, "SGOV", "SPY")


def check_table(plan) -> dict[str, dict]:
    return {c["name"]: c for c in plan.payload["checks"]}


# --------------------------------------------------------------------------------------
# F1 with hedge
# --------------------------------------------------------------------------------------


def test_f1_v2_with_hedge_passes_every_check_and_matches_hand_computation() -> None:
    target = f1_target()
    plan = plan_for(target, client_for(*F1_SYMBOLS), limits=WIDE)
    assert plan.status == "ok", failed_checks(plan)
    checks = check_table(plan)
    assert {"core_leg", "beta_neutral", "gross_leverage"} <= set(checks)
    assert checks["beta_neutral"]["value"] == pytest.approx(0.0, abs=1e-9)
    assert "hedge" in checks["beta_neutral"]["detail"]
    assert checks["gross_leverage"]["value"] == pytest.approx(1.8)
    assert checks["core_leg"]["value"] == pytest.approx(0.45)
    # hand computation: 1e6 equity, whole shares
    by = {o["symbol"]: o for o in plan.orders}
    assert len(plan.orders) == 8
    assert (by["L1"]["qty"], by["L2"]["qty"], by["L3"]["qty"]) == (4000, 6000, 1500)
    assert (by["S1"]["qty"], by["S2"]["qty"], by["S3"]["qty"]) == (4000, 6000, 1500)
    assert by["SPY"]["qty"] == 700 and by["SPY"]["side"] == "buy"  # 0.35e6 / 500
    assert by["SGOV"]["qty"] == 4500 and by["SGOV"]["side"] == "buy"  # 0.45e6 / 100
    summary = plan.payload["summary"]
    assert summary["buy_notional"] == pytest.approx(500_000 + 350_000 + 450_000)
    assert summary["sell_notional"] == pytest.approx(500_000)
    assert summary["n_target_names"] == 6  # stock overlay only
    assert summary["post_trade_long_notional"] == pytest.approx(500_000)
    assert summary["post_trade_short_notional"] == pytest.approx(500_000)


def test_f1_without_hedge_fails_beta_neutral() -> None:
    target = f1_target(hedge=0.0, core=0.8)
    plan = plan_for(target, client_for(*F1_SYMBOLS), limits=WIDE)
    assert failed_checks(plan) == {"beta_neutral"}
    assert check_table(plan)["beta_neutral"]["value"] == pytest.approx(-0.35)


def test_hedge_sign_error_fails_beta_neutral() -> None:
    target = f1_target(hedge=-0.35)
    plan = plan_for(target, client_for(*F1_SYMBOLS), limits=WIDE)
    assert "beta_neutral" in failed_checks(plan)
    assert check_table(plan)["beta_neutral"]["value"] == pytest.approx(-0.70)
    assert plan.status == "blocked"


def test_f1_core_above_one_is_rejected() -> None:
    with pytest.raises(ValidationError, match="core_weight must be in"):
        f1_target(core=1.2, hedge=0.0)
    with pytest.raises(ValidationError, match="core_weight must be in"):
        f1_target(core=-0.1, hedge=0.0)


def test_max_name_weight_ignores_spy_and_sgov() -> None:
    # stock names at 1% (inside the default 1.25% cap); SPY 35% and SGOV 40% are not names
    target = f1_target(
        hedge=0.351,
        core=0.4,
        weights={
            "L1": 0.01,
            "L2": 0.01,
            "L3": 0.01,
            "S1": -0.01,
            "S2": -0.01,
            "S3": -0.01,
            "SGOV": 0.4,
            "SPY": 0.351,
        },
        long_beta=0.0,
        short_beta=11.7,
    )
    plan = plan_for(target, client_for(*F1_SYMBOLS))
    checks = check_table(plan)
    assert checks["max_name_weight"]["passed"]
    assert checks["max_name_weight"]["value"] == pytest.approx(0.01)
    assert checks["gross_stock"]["passed"] and checks["net_dollar"]["passed"]
    assert checks["exposures_complete"]["passed"]


def test_core_leg_fails_when_the_tbill_leg_cannot_be_traded() -> None:
    target = f1_target()
    client = client_for(*F1_SYMBOLS, positions={"SGOV": 1.5})  # fractional position is skipped
    plan = plan_for(target, client, limits=WIDE)
    assert {"core_leg", "whole_share_positions"} <= failed_checks(plan)


# --------------------------------------------------------------------------------------
# F2 with merged SPY
# --------------------------------------------------------------------------------------


def test_f2_v2_merged_spy_builds_one_order_and_passes_core_leg() -> None:
    target = f2_target(hedge=0.2)
    assert target.weights["SPY"] == pytest.approx(1.2)
    plan = plan_for(target, client_for("L1", "L2", "S1", "S2", "SPY"), limits=WIDE)
    assert plan.status == "ok", failed_checks(plan)
    spy_orders = [o for o in plan.orders if o["symbol"] == "SPY"]
    assert len(spy_orders) == 1 and spy_orders[0]["qty"] == 2400  # 1.2e6 / 500
    checks = check_table(plan)
    assert checks["core_leg"]["passed"] and checks["core_leg"]["value"] == pytest.approx(1.2)
    # overlay beta = 0.2 * 0.5 - 0.2 * 1.5 = -0.2; hedge executed = 1.2 - 1.0
    assert checks["beta_neutral"]["value"] == pytest.approx(0.0, abs=1e-9)
    assert checks["gross_leverage"]["value"] == pytest.approx(1.6)
    assert target.target_gross == pytest.approx(0.4)  # SPY is neither stock nor core overlay


def test_f2_core_weight_other_than_one_is_rejected() -> None:
    with pytest.raises(ValidationError, match="F2 core_weight must be exactly 1.0"):
        f2_target(core_weight=0.9, weights={"L1": 0.2, "SPY": 1.1})


def test_merged_weight_identity_is_enforced() -> None:
    with pytest.raises(ValidationError, match="core leg weight"):
        f2_target(hedge=0.2, weights={"L1": 0.2, "L2": 0.2, "S1": -0.2, "S2": -0.2, "SPY": 1.0})
    with pytest.raises(ValidationError, match="hedge leg weight"):
        f1_target(hedge=0.35, weights={**LONGS, **SHORTS, "SGOV": 0.45, "SPY": 0.30})


def test_gross_leverage_above_limit_is_blocked() -> None:
    # SPY 1.35 + overlay 0.7 = 2.05
    target = f2_target(
        hedge=0.35,
        weights={"L1": 0.175, "L2": 0.175, "S1": -0.175, "S2": -0.175, "SPY": 1.35},
    )
    plan = plan_for(target, client_for("L1", "L2", "S1", "S2", "SPY"), limits=WIDE)
    assert plan.status == "blocked"
    assert "gross_leverage" in failed_checks(plan)
    assert check_table(plan)["gross_leverage"]["value"] == pytest.approx(2.05)


# --------------------------------------------------------------------------------------
# schema, hash, files
# --------------------------------------------------------------------------------------


def _v1_fixture(**kw) -> BookTarget:
    fields = {
        "book_id": "hash_fixture_v1",
        "account": "quant1",
        "form": "F1",
        "decision_date": date(2026, 9, 17),
        "execution_date": date(2026, 9, 18),
        "equity_basis": 1_000_000.0,
        "core_symbol": "SGOV",
        "weights": {"A": 0.01, "B": -0.01, "SGOV": 1.0},
        "reference_prices": {"A": 50.0, "B": 25.0, "SGOV": 100.0},
        "exposures": {
            "A": NameExposure(beta=1.0, industry="i", size=9.0, dollar_adv_21=5e7, vol_21=0.02),
            "B": NameExposure(beta=0.8, industry="j", size=8.0),
            "SGOV": NameExposure(beta=0.0, industry="tbill", size=0.0),
        },
        "logged_at_utc": "2026-09-17T21:00:00Z",
    }
    fields.update(kw)
    return BookTarget(**fields)


def test_v1_target_hash_is_unchanged() -> None:
    assert payload_sha256(_v1_fixture()) == V1_FIXTURE_SHA256


def test_v1_file_omits_schema_2_fields_and_round_trips(tmp_path) -> None:
    path = write_target_file(tmp_path, _v1_fixture())
    text = path.read_text()
    assert "hedge_weight" not in text and "core_weight" not in text
    assert load_target_file(path).payload_sha256 == V1_FIXTURE_SHA256


def test_v2_file_round_trips_and_hash_covers_the_hedge(tmp_path) -> None:
    target = f1_target()
    path = write_target_file(tmp_path, target)
    loaded = load_target_file(path)
    assert loaded.hedge_weight == 0.35 and loaded.core_weight == 0.45
    assert loaded.payload_sha256 == payload_sha256(f1_target())
    other = f1_target(hedge=0.30, weights={**LONGS, **SHORTS, "SGOV": 0.45, "SPY": 0.30})
    assert other.payload_sha256 != target.payload_sha256
    tampered = path.read_text().replace('"hedge_weight": 0.35', '"hedge_weight": 0.36')
    path.write_text(tampered)
    with pytest.raises(BookTargetError):
        load_target_file(path)


def test_schema_1_rejects_new_fields_and_bad_hedges() -> None:
    with pytest.raises(ValidationError, match="schema_version 2"):
        _v1_fixture(hedge_symbol="SPY", hedge_weight=0.1)
    with pytest.raises(ValidationError, match="hedge_symbol must be"):
        f1_target(hedge_symbol="QQQ")
    with pytest.raises(ValidationError, match="hedge_weight"):
        f1_target(hedge=1.6, weights={**LONGS, **SHORTS, "SGOV": 0.45, "SPY": 1.6})
    with pytest.raises(ValidationError, match="needs hedge_symbol"):
        f1_target(hedge=0.0, hedge_weight=0.1)


def test_f1_to_f2_conversion_refuses_a_target_with_a_hedge() -> None:
    with pytest.raises(BookTargetError, match="cannot be converted"):
        convert_f1_target_to_f2(f1_target(), spy_price=SPY_PX)


def test_realized_exposures_count_the_hedge_in_beta_not_in_stock_weights() -> None:
    target = f1_target()
    positions = {
        "L1": 4000,
        "L2": 6000,
        "L3": 1500,
        "S1": -4000,
        "S2": -6000,
        "S3": -1500,
        "SPY": 700,
        "SGOV": 4500,
    }
    prices = {**PRICES, "SPY": SPY_PX, "SGOV": SGOV_PX}
    out = realized_exposures(target, positions, prices, 1_000_000.0)
    assert out["net_weight"] == pytest.approx(0.0)
    assert out["gross_weight"] == pytest.approx(1.0)
    assert out["hedge_weight"] == pytest.approx(0.35)
    assert out["beta"] == pytest.approx(0.0, abs=1e-9)


# --------------------------------------------------------------------------------------
# submission
# --------------------------------------------------------------------------------------


def test_submit_plan_still_refuses_outside_the_window_for_v2_targets() -> None:
    client = client_for(*F1_SYMBOLS)
    plan = plan_for(f1_target(), client, limits=WIDE)
    assert plan.status == "ok"
    too_early = datetime(2026, 9, 18, 12, 0, tzinfo=UTC)  # 08:00 ET
    with pytest.raises(BookEngineError, match="09:30"):
        submit_plan(client, plan, now=too_early)
    assert client.submitted == []
    blocked = plan_for(f1_target(hedge=-0.35), client, limits=WIDE)
    with pytest.raises(BookEngineError, match="blocked"):
        submit_plan(client, blocked, now=NOW)
    assert client.submitted == []


def test_build_plan_accepts_a_state_without_a_client() -> None:
    state = AccountState(equity=1_000_000.0, positions={})
    target = f2_target()
    plan = build_plan(
        target,
        state,
        as_of=EXECUTION,
        now=NOW,
        asset_lookup=lambda s: etb(s),
        limits=WIDE,
    )
    assert plan.status == "ok", failed_checks(plan)
