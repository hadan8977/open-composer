# ruff: noqa: E501 -- Literal audit output.
"""Causal contemporaneous source features and dated folds only, no forward labels."""

import json
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from open_composer.market_sessions import us_equity_session_dates

D = Path(__file__).resolve().parent
SYMS = "SPY QQQ IWM EFA EEM IEF TLT GLD DBC UUP".split()


def features(close):
    r = close.pct_change(fill_method=None)
    vol = r.ewm(span=60, adjust=False, min_periods=60).std(bias=False)
    out = []
    for h in [1, 21, 63, 126, 252]:
        out.append((close / close.shift(h) - 1) / (vol * np.sqrt(h)))
    pstd = close.rolling(63, min_periods=63).std(ddof=1)
    for s, long in [(8, 24), (16, 48), (32, 96)]:
        q = (
            close.ewm(alpha=1 / s, adjust=False, min_periods=s).mean()
            - close.ewm(alpha=1 / long, adjust=False, min_periods=long).mean()
        ) / pstd
        out.append(q / q.rolling(252, min_periods=252).std(ddof=1))
    return np.stack([z.to_numpy() for z in out], axis=-1), vol.to_numpy(), r.to_numpy()


def main():
    c = pd.read_parquet(D / "ETF-sanitized-close.parquet")[SYMS]
    dates = c.index.strftime("%Y-%m-%d").to_numpy(dtype="U10")
    cal = np.array(
        [d.isoformat() for d in us_equity_session_dates(date(2016, 1, 4), date(2026, 9, 30))],
        dtype="U10",
    )
    assert np.array_equal(dates, cal), (
        "Independent session calendar mismatch; do not innerjoin/delete"
    )
    x, vol, r = features(c)
    valid = np.isfinite(x).all(-1) & np.isfinite(vol) & (vol > 1e-8)
    prefix = 800
    a, _, _ = features(c.iloc[:prefix])
    assert np.allclose(a, x[:prefix], equal_nan=True)
    scale = np.array([2.0, 0.5, 3.0, 0.25, 5.0, 4.0, 0.2, 1.5, 6.0, 0.3])
    scaled, sv, sr = features(c * scale)
    assert np.allclose(scaled, x, equal_nan=True, atol=1e-7, rtol=1e-7)
    assert np.allclose(sr, r, equal_nan=True)
    folds = []
    for year in [2024, 2025, 2026]:
        complete = np.flatnonzero(valid.all(1))
        # Only calendar maturity/support indices; no forward-return label array is created here.
        matured = complete[
            (complete + 2 < len(dates))
            & (dates[np.minimum(complete + 2, len(dates) - 1)] < str(year) + "-01-01")
        ]
        nval = max(1, int(np.ceil(len(matured) * 0.1)))
        val = matured[-nval:]
        tr = matured[(matured + 2) < val[0]]
        test = np.flatnonzero(
            (dates >= str(year) + "-01-01")
            & (dates < str(year + 1) + "-01-01")
            & (dates >= "2024-01-02")
        )
        test = test[test + 2 < len(dates)]
        assert (
            valid[test].all() and tr[-1] + 2 < val[0] and dates[val[-1] + 2] < str(year) + "-01-01"
        )
        folds.append(
            dict(
                year=year,
                train=tr.tolist(),
                validation=val.tolist(),
                test=test.tolist(),
                train_n=len(tr),
                validation_n=len(val),
                test_n=len(test),
                train_last_mature_endpoint=str(dates[tr[-1] + 2]),
                validation_first=str(dates[val[0]]),
                validation_last_mature_endpoint=str(dates[val[-1] + 2]),
            )
        )
    first = int(np.flatnonzero(dates >= "2024-01-02")[0])
    assert len(dates) - first == 689
    np.savez_compressed(
        D / "source-features.npz",
        dates=dates,
        symbols=np.array(SYMS),
        close=c.to_numpy(),
        returns=r,
        vol=vol,
        features=x,
        valid=valid,
        eval_first=np.array(first),
    )
    (D / "fold-calendar.json").write_text(
        json.dumps(
            dict(
                folds=folds,
                all_seen=True,
                no_forward_labels=True,
                decisions=sum(f["test_n"] for f in folds),
                last_decision=str(dates[-3]),
            ),
            indent=2,
        )
        + "\n"
    )
    (D / "feature-input-qa.json").write_text(
        json.dumps(
            dict(
                causal_prefix_parity=True,
                uniform_future_adjustment_multiplier_invariance=True,
                independent_calendar_equal=True,
                feature_columns=8,
                shape=list(x.shape),
                first_complete_by_symbol={
                    s: str(dates[np.flatnonzero(valid[:, j])[0]]) for j, s in enumerate(SYMS)
                },
                eval_current_feature_missing=int((~valid[first:]).sum()),
                eval_calendar_sessions=689,
                eval_decisions=687,
                financial_labels_created=False,
                real_fits=0,
            ),
            indent=2,
        )
        + "\n"
    )
    print(
        "Actual8feature calendar/prefix/unitinvariance/folds received, no forward labels/fits/books",
        flush=True,
    )


if __name__ == "__main__":
    main()
