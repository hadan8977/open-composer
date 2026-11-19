"""Run and receive a registered five-feature market-exposure account comparison."""

from functools import partial

import numpy as np
import pandas as pd

from open_composer.lab.batch import write_evidence
from open_composer.lab.exposure_accounts import POLICIES, REQUIRED, WINDOWS, account, native
from open_composer.lab.exposure_inputs import INPUTS
from open_composer.lab.exposure_model import fit_models, score
from open_composer.lab.models import EngineResult
from open_composer.lab.parallel_accounts import parallel_map


def summarize(nav, fills, closes, capital):
    rows = []
    annual = []
    for (window, bp, policy), frame in nav.groupby(["window", "bp", "policy"]):
        daily = frame.set_index("day").sort_index()
        trades = fills.loc[(fills.window == window) & (fills.bp == bp) & (fills.policy == policy)]
        pnl = daily.equity.iloc[-1] - capital
        drawdown = daily.equity / daily.equity.cummax().clip(lower=capital) - 1
        rows.append(
            dict(
                window=window,
                bp=bp,
                policy=policy,
                net_usd=pnl,
                cagr=np.expm1(np.log1p(pnl / capital) * 252 / len(daily)),
                drawdown=drawdown.min(),
                exposure=daily.long_exp.mean(),
                semiconductor=daily.semiconductor_exp.mean(),
                notional=trades.net_market_notional.sum(),
                fees=trades.cost.sum(),
                fills=len(trades),
            )
        )
        if window in ("support", "middle", "primary"):
            for year, part in daily.groupby(daily.index.year):
                annual.append(
                    dict(
                        bp=bp,
                        policy=policy,
                        year=year,
                        net_log=np.log1p(part.net).sum(),
                        weight={"support": 1, "middle": 2, "primary": 3}[window],
                    )
                )
    annual = pd.DataFrame(annual)
    weighted = (annual.net_log * annual.weight).groupby([annual.bp, annual.policy]).sum() / 13
    table = pd.DataFrame(rows).merge(weighted.rename("weighted_annual_log"), on=["bp", "policy"])
    criteria, removed, shocks = [], [], []
    for bp, primary in table[table.window == "primary"].groupby("bp"):
        by = primary.set_index("policy")
        for other in REQUIRED:
            criteria.append(
                dict(
                    bp=bp,
                    control=other,
                    net_advantage=by.net_usd.model - by.at[other, "net_usd"],
                    cagr_advantage=by.cagr.model - by.at[other, "cagr"],
                    weighted_log_excess=by.weighted_annual_log.model
                    - by.at[other, "weighted_annual_log"],
                    drawdown_margin=by.drawdown.model - by.drawdown.c3,
                )
            )
        daily = nav.loc[(nav.bp == bp) & (nav.window == "primary")]
        logs = np.log1p(daily.pivot(index="day", columns="policy", values="net"))
        weights = daily.pivot(index="day", columns="policy", values="long_exp")
        entering = weights.shift(1, fill_value=0.0)
        different = entering.model.gt(1e-8) != entering.c3.gt(1e-8)
        spells = different.ne(different.shift()).cumsum()
        gain = (logs.model - logs.c3)[different].groupby(spells).sum()
        best = (
            (spells == gain.idxmax()) & different
            if len(gain) and gain.max() > 0
            else different & False
        )
        retained = capital * np.expm1(logs.loc[~best].sum())
        for other in REQUIRED:
            removed.append(
                dict(
                    bp=bp,
                    control=other,
                    start=str(logs.index[best][0].date()) if best.any() else None,
                    end=str(logs.index[best][-1].date()) if best.any() else None,
                    sessions=int(best.sum()),
                    model_net=retained.model,
                    control_net=retained[other],
                    remaining_advantage=retained.model - retained[other],
                )
            )
        blocks = []
        for i in range(0, len(weights) - 21, 21):
            first, last = weights.index[[i, i + 21]]
            prior = weights.iloc[i - 5] if i >= 5 else None
            blocks.append(
                dict(
                    bp=bp,
                    start=str(first.date()),
                    end=str(last.date()),
                    tqqq_return=closes.at[last, "TQQQ"] / closes.at[first, "TQQQ"] - 1,
                    model_weight=weights.model.iloc[i],
                    c3_weight=weights.c3.iloc[i],
                    model_delta5=weights.model.iloc[i] - prior.model if prior is not None else None,
                    c3_delta5=weights.c3.iloc[i] - prior.c3 if prior is not None else None,
                )
            )
        blocks.sort(key=lambda row: row["tqqq_return"])
        shocks.extend(
            [
                dict(row, event=tag)
                for tag, group in [("loss", blocks[:3]), ("rebound", blocks[-3:])]
                for row in group
            ]
        )
    criteria = pd.DataFrame(criteria)
    passes = (criteria[["net_advantage", "cagr_advantage", "weighted_log_excess"]] > 0).all().all()
    return (
        table,
        annual,
        criteria,
        pd.DataFrame(removed),
        pd.DataFrame(shocks),
        ("PASS" if passes and (criteria.drawdown_margin >= 0).all() else "FAIL"),
    )


def run_exposure(
    root,
    folder,
    *,
    features,
    start,
    sealed_start,
    end,
    capital,
    costs,
    horizon,
    embargo,
    half_life,
    penalty,
    switch_cost,
    registration,
):
    training = [("session", "<", pd.Timestamp(sealed_start))]
    state = pd.read_parquet(INPUTS / "state.parquet", filters=training)
    prices = pd.read_parquet(INPUTS / "marks.parquet", filters=training)
    fits, labels = fit_models(
        state,
        prices.close.unstack(),
        horizon=horizon,
        embargo=embargo,
        half_life=half_life,
        penalty=penalty,
        sealed_start=sealed_start,
    )
    write_evidence(folder / "fits.json", fits)
    labels.to_parquet(folder / "training-labels.parquet")
    # The pre-September fit is durable before the sealed account evaluation opens.
    state = pd.read_parquet(INPUTS / "state.parquet").loc[start:end]
    prices = pd.read_parquet(INPUTS / "marks.parquet")
    weekly = score(state, fits)
    weekly.to_parquet(folder / "weekly.parquet")
    close = prices.close.unstack().loc[start:end]
    open_ = prices.open.unstack().reindex_like(close)
    cfg = native.load_strategy_spec(native.SPEC).portfolio.etf_rotation
    signals = native.signal_inputs(open_, close, cfg, include_rotation=True)
    list(
        parallel_map(
            partial(
                account,
                open_=open_,
                close=close,
                signals=signals,
                cfg=cfg,
                weekly=weekly,
                hurdle=switch_cost,
                costs=costs,
                output=folder,
            ),
            WINDOWS,
        )
    )
    nav = pd.concat(
        [pd.read_parquet(folder / f"nav-{w}.parquet") for w in WINDOWS], ignore_index=True
    )
    fills = pd.concat(
        [pd.read_parquet(folder / f"fills-{w}.parquet") for w in WINDOWS], ignore_index=True
    )
    table, annual, criteria, removed, shocks, verdict = summarize(nav, fills, close, capital)
    for name, data in [
        ("accounts", table),
        ("annual", annual),
        ("criteria", criteria),
        ("episodes", removed),
        ("shocks", shocks),
    ]:
        data.to_csv(folder / f"{name}.csv", index=False)
    headline = table.query("window == 'primary' and bp == 10 and policy == 'model'").iloc[0]
    packet = dict(
        verdict=verdict,
        primary=table.query("window == 'primary'").round(6).to_dict("records"),
        criteria=criteria.round(6).to_dict("records"),
        episodes=removed.round(6).to_dict("records"),
        ledgers=[p.relative_to(root).as_posix() for p in sorted(folder.iterdir())],
        exposure="C3-exposed 2016-2025 and 2026 through Nov 17, including the Oct 28-Nov 17 one-shot. No untouched post-freeze observations.",
    )
    returns = (
        nav.query("window == 'primary' and bp == 10 and policy == 'model'").set_index("day").net
    )
    baseline = criteria.query("bp == 10 and control == 'c3'").iloc[0]
    return EngineResult(
        "Native C3/run_book and expanding ridge",
        capital,
        capital + float(headline.net_usd),
        packet,
        net_returns=returns,
        baseline_net_profit_usd=float(headline.net_usd - baseline.net_advantage),
    )
