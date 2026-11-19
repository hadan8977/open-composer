"""Replay the registered leveraged-index policies on the original development prices."""
import json
import sys

import pandas as pd

from open_composer.lab.models import EngineResult


def replay_bridge(root, folder, *, freeze, prices, block_sessions):
    # Import the registered pure policy and formation accounting, never their main routines.
    runs = root / "research/levered_index_trend_20261119/runs"
    sys.path.insert(0, str(runs / "lt-20261119-5-4/worker"))
    from equal_exposure import MAPPED, gross_by_formation, replay, summarize

    frozen = json.loads((root / freeze).read_text(encoding="utf-8"))
    capital = frozen["capital_usd"]
    cand, comp = frozen["candidate"], frozen["comparator"]
    open_, close = replay.prices(replay.archive(prices["start"], frozen["development_end"]))
    if close.index[-1] != pd.Timestamp(frozen["development_end"]):
        raise ValueError("Development archive ends before the frozen endpoint")
    cfg = replay.load_strategy_spec(replay.SPEC).portfolio.etf_rotation
    signals = replay.signal_inputs(open_, close, cfg, include_rotation=True)
    gates, vol, (schedule, update) = signals
    mapped = [{"TQQQ": sum(w.get(s, 0) for s in cfg.menu), "SHY": w["SHY"]} for w in schedule]
    previous = close.index.to_series().shift()
    month_end = previous.map(lambda day: pd.notna(day) and replay.rot._is_period_end_month(day.date()))
    formation = previous.where(month_end).ffill().rename("formation")
    days = close.loc[frozen["development_start"]:frozen["development_end"]].index
    windows = [(days[0], days[-1])] + [
        (days[i], days[i + block_sessions - 1])
        for i in range(0, len(days) - block_sessions + 1, block_sessions)
    ]
    accounts, episodes, nav, fills = [], [], [], []
    for block, (start, end) in enumerate(windows):
        for bp in frozen["costs_bps_per_side"]:
            for name in (comp, MAPPED, cand):
                policy = comp if name == MAPPED else name
                inputs = (gates, vol, (mapped, update)) if name == MAPPED else signals
                account, _ = replay.replay(policy, bp, start, end, open_, close, inputs, cfg, stop_view=False)
                daily, trades, _ = replay.audited_path(account)
                labels = dict(block=block, bp=bp, name=name)
                pnl, units = gross_by_formation(daily, trades, open_, close, formation, capital)
                episodes.append(pnl.reset_index().assign(**labels))
                accounts.append(dict(start=start, end=end, **labels))
                cash = daily.equity - (units * close.loc[daily.index]).sum(axis=1)
                nav.append(daily[["equity", "fees_usd"]].assign(cash=cash, **labels).rename_axis("day").reset_index())
                fills.append(trades.assign(**labels))
    summary, sensitivity, formations = summarize(pd.DataFrame(accounts), pd.concat(episodes), comp, cand, capital)
    paths = {}
    for name, table in (("nav", pd.concat(nav)), ("fills", pd.concat(fills)), ("formations", formations),
                        ("bridge", summary), ("sensitivity", sensitivity)):
        path = folder / f"{name}.parquet"
        table.to_parquet(path, index=False)
        paths[name] = path.relative_to(root).as_posix()
    headline = summary.loc[summary.scope.str.startswith("2024")]
    return EngineResult("Registered leveraged-index replay / run_book", capital,
                        capital + float(headline.iloc[0].mapped_usd),
                        {"bridge": headline.dropna(axis=1).to_dict("records"), "ledgers": paths},
                        limitations=["Headline P&L sums separate fresh-cash restart accounts."])
