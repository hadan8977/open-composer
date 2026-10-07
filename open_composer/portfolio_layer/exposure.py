"""Exposure of an account: stock holdings through the equity-book risk model, ETF and intraday
sleeves through return regressions on the model's daily factor returns."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
STYLE_FACTORS = ("size", "value", "momentum", "resid_vol")
MARKET_FACTOR = "market"


def load_factor_returns(years=(2024, 2025, 2026), root: Path = ROOT) -> pd.DataFrame:
    parts = []
    for y in years:
        p = root / f"data/research/equity_book/risk/factor_returns_{y}.parquet"
        if p.exists():
            parts.append(pd.read_parquet(p))
    f = pd.concat(parts)
    wide = f.pivot(index="trade_date", columns="factor", values="ret")
    wide.index = pd.to_datetime(wide.index)
    return wide.sort_index()


def regression_betas(ret: pd.Series, factors: pd.DataFrame, window: int = 252) -> pd.Series:
    """OLS loadings of the sleeve's daily return on market + style factor returns (last ``window``
    common sessions).  Units match stock exposures: loading per dollar of sleeve capital."""
    cols = [c for c in (MARKET_FACTOR, *STYLE_FACTORS) if c in factors.columns]
    df = pd.concat([ret.rename("y"), factors[cols]], axis=1, join="inner").dropna().iloc[-window:]
    if len(df) < 60:
        return pd.Series(np.nan, index=cols)
    x = np.column_stack([np.ones(len(df)), df[cols].to_numpy()])
    coef, *_ = np.linalg.lstsq(x, df["y"].to_numpy(), rcond=None)
    return pd.Series(coef[1:], index=cols)


def latest_file(folder: Path, pattern: str = "*.json") -> Path | None:
    files = sorted(folder.glob(pattern))
    return files[-1] if files else None


def book_target_exposure(targets_path: Path, root: Path = ROOT) -> dict:
    """Net beta, style and industry exposure and gross of a v1.2 target (weights are fractions
    of equity, including the SPY leg and the cash-like core)."""
    from open_composer.research.equity_book.risk import STYLES, RiskModel

    t = json.loads(targets_path.read_text())
    w = pd.Series(t["weights"], dtype=float)
    out: dict = {
        "decision_date": t["decision_date"],
        "gross": float(w.abs().sum()),
        "net": float(w.sum()),
        "n_names": int(len(w)),
    }
    rm = RiskModel(root / "data/research/equity_book/risk")
    x, _, _ = rm.at(t["decision_date"])
    beta = rm.predicted_beta(t["decision_date"], method="ewma")
    stock = w.index.intersection(x.index)
    out["modelled_share_of_gross"] = float(w[stock].abs().sum() / w.abs().sum())
    b = float((w[stock] * beta.reindex(stock).fillna(1.0)).sum())
    # names outside the cross-section: SPY is the hedge/beta-1 leg, cash-like core has no beta
    for sym, beta_sym in (("SPY", 1.0),):
        if sym in w.index and sym not in stock:
            b += float(w[sym]) * beta_sym
    out["beta"] = b
    out["risk_model_date"] = str(rm.resolve(t["decision_date"]).date())
    out["risk_model_age_days"] = int(
        (pd.Timestamp(t["decision_date"]) - rm.resolve(t["decision_date"])).days
    )
    style = {s: float((w[stock] * x.loc[stock, s]).sum()) for s in STYLES}
    ind = {g: float((w[stock] * x.loc[stock, g]).sum()) for g in rm.groups}
    # hedge ETFs (SPY) are outside the cross-section: use their regression loadings
    etf_path = root / "data/research/equity_book/etf_risk/etf_exposures.parquet"
    modelled = float(w[stock].abs().sum())
    if etf_path.exists():
        etf = pd.read_parquet(etf_path)
        etf["trade_date"] = pd.to_datetime(etf["trade_date"])
        for sym in w.index.difference(stock):
            rows = etf[
                (etf["symbol"] == sym) & (etf["trade_date"] <= pd.Timestamp(t["decision_date"]))
            ]
            if rows.empty:
                continue
            row = rows.iloc[-1]
            modelled += abs(float(w[sym]))
            for k in STYLES:
                if k in row.index and np.isfinite(row[k]):
                    style[k] += float(w[sym]) * float(row[k])
            for g in rm.groups:
                if g in row.index and np.isfinite(row[g]):
                    ind[g] += float(w[sym]) * float(row[g])
    out["modelled_share_of_gross"] = modelled / float(w.abs().sum())
    out["style"] = style
    out["industry_net"] = ind
    return out


def positions_exposure(positions_path: Path, equity: float, leverage: dict, themes: dict) -> dict:
    p = json.loads(positions_path.read_text())["positions"]
    mv = {
        q["symbol"]: float(q["market_value"]) * (-1 if "SHORT" in str(q["side"]) else 1) for q in p
    }
    gross_mv = sum(abs(v) for v in mv.values())
    gross_econ = sum(abs(v) * abs(leverage.get(s, 1)) for s, v in mv.items())
    out = {
        "gross": gross_mv / equity,  # Reg T basis: market value of longs plus shorts
        "gross_economic": gross_econ / equity,  # leveraged ETFs at their multiple
        "n_positions": len(mv),
        "market_value": float(sum(mv.values())),
    }
    out["themes"] = {
        name: sum(v * m.get(s, 0.0) for s, v in mv.items()) / equity for name, m in themes.items()
    }
    return out
