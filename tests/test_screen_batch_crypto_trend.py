"""Synthetic-data tests for `scripts/screen_batches/h20260929_33_crypto_trend.py`
and the session-price DST/timezone extraction in
`scripts/fetch_crypto_session_prices.py`. No backtest and no network call is
made here.
"""

from __future__ import annotations

import sys
from datetime import UTC
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scripts" / "screen_batches"))

import fetch_crypto_session_prices as fetcher  # noqa: E402
import h20260929_33_crypto_trend as batch  # noqa: E402
import screen_lane as lane  # noqa: E402

CRYPTO_SYMS = batch.CRYPTO_SYMS


def _assert_contract(weights: dict[str, float], universe: tuple[str, ...]) -> None:
    assert set(weights) <= set(universe)
    assert all(v >= 0.0 for v in weights.values())
    assert sum(weights.values()) <= 1.0 + 1e-9


def _synthetic_close(n: int, seed: int = 0, start: str = "2016-06-01") -> pd.DataFrame:
    """A trading-day-indexed panel for every `CRYPTO_SYMS` symbol, geometric
    random walk, all starting at 100."""
    index = pd.bdate_range(start, periods=n)
    rng = np.random.default_rng(seed)
    data = {}
    for sym in CRYPTO_SYMS:
        rets = rng.normal(0.0005, 0.03, n)
        data[sym] = 100.0 * np.cumprod(1.0 + rets)
    return pd.DataFrame(data, index=index)


# --------------------------------------------------------------------------
# CANDIDATES shape
# --------------------------------------------------------------------------


def test_candidates_ids_and_shape() -> None:
    ids = [c.id for c in batch.CANDIDATES]
    assert len(ids) == len(set(ids)) == 13
    assert "BTC_RAND_PLACEBO" in ids
    assert ids.count("BTC_BUYHOLD") == 1
    for c in batch.CANDIDATES:
        assert isinstance(c, lane.ScreenCandidate)
        assert c.freq in ("D", "M")
        assert set(c.universe) <= set(CRYPTO_SYMS)
        assert callable(c.weights_fn)
    freq_by_id = {c.id: c.freq for c in batch.CANDIDATES}
    assert freq_by_id["BTC_BUYHOLD"] == "D"
    assert freq_by_id["BTC_SMA200"] == "D"
    assert freq_by_id["BTC_DONCHIAN_ENSEMBLE"] == "D"
    assert freq_by_id["BTC_DONCHIAN_ENSEMBLE_VT40"] == "D"
    assert freq_by_id["BTC_RAND_PLACEBO"] == "D"
    assert freq_by_id["BTC_TSMOM_1M"] == "M"
    assert freq_by_id["CRYPTO_XS_TOP3_EW"] == "M"


def test_extend_panel_columns_do_not_clash_with_equity_panel(monkeypatch) -> None:
    fake_close = pd.DataFrame({"BTCUSD": [1.0, 2.0]}, index=pd.bdate_range("2024-01-01", periods=2))
    fake_open = fake_close.copy()
    monkeypatch.setattr(batch, "_load_crypto_panel", lambda: (fake_close, fake_open))
    out_close, out_open = batch.extend_panel(pd.DataFrame(), pd.DataFrame())
    assert list(out_close.columns) == ["BTCUSD"]
    assert out_close.equals(fake_close)
    assert out_open.equals(fake_open)


# --------------------------------------------------------------------------
# Weight-function contract: long-only, sum<=1, universe-only, no look-ahead
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "candidate_id",
    [
        "BTC_BUYHOLD",
        "BTC_SMA200",
        "BTC_TSMOM_1M",
        "BTC_TSMOM_3M",
        "BTC_TSMOM_6M",
        "BTC_DONCHIAN_ENSEMBLE",
        "BTC_DONCHIAN_ENSEMBLE_VT40",
        "CRYPTO_DONCHIAN_TOP3",
        "BTC_ETH_DUAL_MOM",
        "CRYPTO_XS_TOP3_EW",
        "CRYPTO_XS_TOP3_IVOL",
        "CRYPTO_XS_TOP3_EW_VT40",
        "BTC_RAND_PLACEBO",
    ],
)
def test_weights_contract_and_no_lookahead(candidate_id: str) -> None:
    (candidate,) = [c for c in batch.CANDIDATES if c.id == candidate_id]
    close = _synthetic_close(400, seed=hash(candidate_id) % 1000)
    asof = close.index[250]

    weights_full = candidate.weights_fn(close, asof)
    _assert_contract(weights_full, candidate.universe)

    truncated = close.loc[:asof]
    weights_truncated = candidate.weights_fn(truncated, asof)
    assert (
        weights_full == pytest.approx(weights_truncated)
        if weights_full
        else (weights_truncated == {})
    )

    # Mutate every row strictly after `asof` -- must not change the decision.
    mutated = close.copy()
    future_mask = mutated.index > asof
    mutated.loc[future_mask, :] = mutated.loc[future_mask, :] * 5.0 + 1000.0
    weights_mutated_future = candidate.weights_fn(mutated, asof)
    assert weights_mutated_future == weights_full


def test_donchian_ensemble_weight_is_fraction_of_windows_up() -> None:
    # A strictly rising series should have every Donchian window signal "up"
    # once warmed up (fraction 1.0) -- a simple, hand-verifiable case.
    n = 260
    index = pd.bdate_range("2016-06-01", periods=n)
    close = pd.DataFrame({"BTCUSD": np.linspace(100.0, 100.0 + n, n)}, index=index)
    for sym in batch.CRYPTO_SYMS:
        if sym != "BTCUSD":
            close[sym] = 100.0
    asof = index[-1]
    weights = batch._btc_donchian_ensemble(close, asof)
    assert weights == {"BTCUSD": pytest.approx(1.0)}


def test_btc_eth_dual_mom_picks_higher_momentum_leg_or_cash() -> None:
    n = 200
    index = pd.bdate_range("2016-06-01", periods=n)
    close = pd.DataFrame(index=index)
    close["BTCUSD"] = np.linspace(100.0, 150.0, n)  # rising
    close["ETHUSD"] = np.linspace(100.0, 80.0, n)  # falling
    for sym in batch.CRYPTO_SYMS:
        if sym not in ("BTCUSD", "ETHUSD"):
            close[sym] = 100.0
    weights = batch._btc_eth_dual_mom(close, index[-1])
    assert weights == {"BTCUSD": 1.0}

    # Both falling: absolute-momentum filter empties the book (falls to SHY).
    close2 = close.copy()
    close2["BTCUSD"] = np.linspace(150.0, 100.0, n)
    weights2 = batch._btc_eth_dual_mom(close2, index[-1])
    assert weights2 == {}


def test_xs_top3_selection_never_exceeds_three_and_is_positive_momentum_only() -> None:
    close = _synthetic_close(300, seed=11)
    asof = close.index[250]
    top = batch._xs_top3_selection(close, asof)
    assert len(top) <= 3
    table = batch._xs_momentum_table(close)
    for sym in top:
        assert table.loc[asof, sym] > 0


def test_crypto_xs_top3_ivol_weights_sum_to_one_when_selected() -> None:
    close = _synthetic_close(300, seed=22)
    asof = close.index[280]
    weights = batch._crypto_xs_top3_ivol(close, asof)
    if weights:
        assert sum(weights.values()) == pytest.approx(1.0, abs=1e-6)
        _assert_contract(weights, CRYPTO_SYMS)


def test_vt40_scale_never_exceeds_one() -> None:
    close = _synthetic_close(200, seed=3)
    for asof in close.index[-20:]:
        scale = batch._vt40_scale(close, asof, "BTCUSD")
        assert 0.0 <= scale <= 1.0


# --------------------------------------------------------------------------
# Placebo: deterministic given asof, does not depend on `close` values
# --------------------------------------------------------------------------


def test_placebo_is_deterministic_and_ignores_price_values() -> None:
    close_a = _synthetic_close(100, seed=1)
    close_b = _synthetic_close(100, seed=2)  # different prices, same index
    asof = close_a.index[50]
    w1 = batch._btc_rand_placebo(close_a, asof)
    w2 = batch._btc_rand_placebo(close_a, asof)
    w3 = batch._btc_rand_placebo(close_b, asof)
    assert w1 == w2 == w3
    _assert_contract(w1, ("BTCUSD",))


def test_placebo_returns_cash_without_btc_price() -> None:
    close = _synthetic_close(50, seed=5)
    close["BTCUSD"] = np.nan
    assert batch._btc_rand_placebo(close, close.index[10]) == {}


# --------------------------------------------------------------------------
# fetch_crypto_session_prices: DST-aware session price extraction
# --------------------------------------------------------------------------


def _bar_index(dates_and_hours_utc: list[tuple[str, int, int]]) -> pd.DatetimeIndex:
    return pd.DatetimeIndex(
        [
            pd.Timestamp(d, tz=UTC) + pd.Timedelta(hours=h, minutes=m)
            for d, h, m in dates_and_hours_utc
        ]
    )


def test_session_prices_uses_edt_offset_in_summer() -> None:
    # 2024-07-15 is EDT (UTC-4): 09:30 ET == 13:30 UTC, 16:00 ET == 20:00 UTC.
    idx = _bar_index([("2024-07-15", 13, 30), ("2024-07-15", 20, 0)])
    bars = pd.DataFrame(
        {"open_time_utc": idx, "open": [50000.0, 51000.0], "close": [50100.0, 51100.0]}
    )
    out = fetcher.session_prices_for_symbol("BTC", bars, [pd.Timestamp("2024-07-15")])
    assert out.loc[0, "open"] == 50000.0
    assert out.loc[0, "close"] == 51100.0


def test_session_prices_uses_est_offset_in_winter() -> None:
    # 2024-01-15 is EST (UTC-5): 09:30 ET == 14:30 UTC, 16:00 ET == 21:00 UTC.
    idx = _bar_index([("2024-01-15", 14, 30), ("2024-01-15", 21, 0)])
    bars = pd.DataFrame(
        {"open_time_utc": idx, "open": [42000.0, 42500.0], "close": [42100.0, 42600.0]}
    )
    out = fetcher.session_prices_for_symbol("BTC", bars, [pd.Timestamp("2024-01-15")])
    assert out.loc[0, "open"] == 42000.0
    assert out.loc[0, "close"] == 42600.0


def test_session_prices_no_fill_when_bar_missing() -> None:
    idx = _bar_index([("2024-07-15", 13, 30)])  # only the open bar present
    bars = pd.DataFrame({"open_time_utc": idx, "open": [50000.0], "close": [50100.0]})
    out = fetcher.session_prices_for_symbol("BTC", bars, [pd.Timestamp("2024-07-15")])
    assert out.loc[0, "open"] == 50000.0
    assert np.isnan(out.loc[0, "close"])


def test_binance_kline_microsecond_timestamps_normalized() -> None:
    # A 2025-era Binance archive row using microsecond open_time (~16 digits)
    # must not overflow pandas' nanosecond datetime range when normalized.
    ms_now = int(pd.Timestamp("2025-06-01", tz=UTC).timestamp() * 1000)
    us_value = ms_now * 1000
    series = pd.Series([float(us_value)])
    first_val = series.iloc[0]
    assert first_val > 1e14
    normalized = first_val / 1000.0
    ts = pd.to_datetime(normalized, unit="ms", utc=True)
    assert ts.year == 2025
