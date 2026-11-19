"""Point-in-time inputs for weekly leveraged-index exposure decisions."""

from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

from open_composer.adapters.data.sip_parquet import ALL_VERSIONS, MARKET_DATA, load_sip_bars
from open_composer.market_sessions import NEW_YORK, us_equity_session_dates

ROOT = Path(__file__).resolve().parents[2]
INPUTS = ROOT / "research/proof_a3_exposure/inputs"
FEATURES = ["qqq_sma200_gap", "tqqq_vol21", "breadth50", "vix3m_minus_vix", "variance_premium"]
SYMBOLS = "SPY QQQ TQQQ BIL SOXX SOXL TECL UPRO USD SHY".split()


def midnight(index):
    return (index + pd.Timedelta(days=1)).tz_localize(NEW_YORK).tz_convert("UTC")


def prepare(start, end):
    """Cold panel build. Only marks and contemporaneous state, without labels."""
    dates = pd.DatetimeIndex(us_equity_session_dates(start, end), name="session")
    calendar = pd.DataFrame({"day": dates, "pos": np.arange(len(dates)), "cutoff": midnight(dates)})
    universe = MARKET_DATA / "derived/daily-us-stock-universe.parquet"
    with duckdb.connect(config={"memory_limit": "600MB", "threads": 2}) as con:
        con.register("calendar", calendar)
        parts = []
        for year in dates.year.unique():
            parts.append(
                con.execute(
                    """
                WITH history AS (
                    SELECT day, pos, cutoff, adjusted_close, security_type, security_type_known_at,
                           avg(adjusted_close) OVER w AS sma, count(adjusted_close) OVER w AS n,
                           min(pos) OVER w AS first_pos, max(known_at) OVER w AS last_known
                    FROM read_parquet(?) JOIN calendar ON trade_date = day
                    WHERE is_member AND trade_date BETWEEN ? AND ?
                    WINDOW w AS (PARTITION BY security_id ORDER BY pos ROWS BETWEEN 49 PRECEDING AND CURRENT ROW)
                )
                SELECT day, max(greatest(last_known,security_type_known_at)) AS breadth_known_at,
                       count(*) AS eligible, avg((adjusted_close > sma)::INT) AS breadth50
                FROM history WHERE year(day) = ? AND n = 50 AND first_pos = pos - 49
                  AND last_known <= cutoff AND security_type = 'operating' AND security_type_known_at <= cutoff
                GROUP BY day ORDER BY day
            """,
                    [
                        str(universe),
                        pd.Timestamp(year - 1, 10, 1),
                        pd.Timestamp(year, 12, 31),
                        int(year),
                    ],
                ).df()
            )
    breadth = pd.concat(parts).set_index("day").reindex(dates)

    archives = []
    for version in ALL_VERSIONS[:2]:
        bars = load_sip_bars(
            SYMBOLS,
            start=str(start),
            end=f"{end}T23:59:59Z",
            root=MARKET_DATA / version,
            allow_missing=False,
        )
        bars["session"] = bars.timestamp.dt.tz_convert(NEW_YORK).dt.tz_localize(None).dt.normalize()
        archives.append(bars.set_index(["session", "symbol"])[["open", "close"]])
    primary, supplement = archives
    pieces = [primary]
    for symbol in SYMBOLS:
        old = primary.xs(symbol, level="symbol")
        new = supplement.xs(symbol, level="symbol")
        tail = new.loc[new.index > old.index.max()]
        if not tail.empty:
            anchor = old.index.max()
            tail = tail * (old.at[anchor, "close"] / new.at[anchor, "close"])
            pieces.append(tail.assign(symbol=symbol).set_index("symbol", append=True))
    marks = pd.concat(pieces).sort_index()
    marks = marks.reindex(pd.MultiIndex.from_product([dates, SYMBOLS], names=["session", "symbol"]))
    if marks.isna().any().any():
        raise ValueError("Incomplete regular-session ETF marks")
    marks.to_parquet(INPUTS / "marks.parquet")
    closes = marks.close.unstack()
    state = breadth.assign(
        qqq_sma200_gap=closes.QQQ / closes.QQQ.rolling(200).mean() - 1,
        tqqq_vol21=closes.TQQQ.pct_change().rolling(21).std() * np.sqrt(252),
    )
    local = pd.read_parquet(ROOT / "data/options/vix_term/vix_term.parquet").set_index("date")
    local.index = pd.to_datetime(local.index)
    for column in ["vix", "vix3m"]:
        official = pd.read_csv(INPUTS / f"{column.upper()}_History.csv")
        series = official.set_index(pd.to_datetime(official.DATE, format="%m/%d/%Y")).CLOSE
        # Both inputs are historical Cboe closes. Never carry an observation across sessions.
        state[column] = local[column].combine_first(series).reindex(dates)
    state["vix3m_minus_vix"] = state.vix3m - state.vix
    state["variance_premium"] = (state.vix / 100) ** 2 - 252 * closes.SPY.pct_change().rolling(
        21
    ).var()
    state["cboe_known_at"] = (
        (dates + pd.Timedelta(hours=16, minutes=15)).tz_localize(NEW_YORK).tz_convert("UTC")
    )
    state["decision_at"] = midnight(dates)
    state["bar_known_at"] = midnight(dates)
    state.to_parquet(INPUTS / "state.parquet")


if __name__ == "__main__":
    import json
    from datetime import date

    spec = json.loads((INPUTS.parent / "experiment.json").read_text())["parameters"]
    prepare(date.fromisoformat(spec["start"]), date.fromisoformat(spec["end"]))
