"""T-20260929-34: build the point-in-time megacap-by-liquidity menu used by
`scripts/screen_batches/h20260929_34_levered_single_stock.py`.

For each month-end trading day, among the S&P 500 constituents that were
actually members of the index *as of that date* (per
`data/sip-delisted/sp500_ticker_start_end_fja05680.csv`), rank by the median
daily dollar volume (close * volume) over the trailing 63 trading days
*ending on or before that date* and keep the top 50 (a superset of the top
20 cut used by half the candidates). No market-cap data is available locally,
so dollar volume is used as the liquidity/size proxy -- noted in
data-feasibility.json and the candidate manifest.

Only look-behind data is used at every step: the membership interval check
and the trailing-63-session window both stop at the month-end date itself,
and the rolling median requires a full 63-session window (min_periods=63)
before a ticker is eligible, so a newly listed name cannot appear until it
has 63 sessions of history.

Sources combined (point-in-time no-survivorship-bias panel):
  - data/sip/daily/<year>/*.parquet       (currently-listed symbols)
  - data/sip-delisted/daily/*.parquet     (delisted since 2016 symbols)

Run under a memory cap, one year of price history loaded into duckdb at a
time (`memory_limit='600MB'`, `threads=2`), per the runbook's guidance for
any job that reads the SIP archive on this box:

    flock /tmp/oc-autoround-heavy.lock scripts/run_capped.sh --mem 1.5G -- \\
        uv run python scripts/build_h20260929_34_menu.py

Writes reports/research/iterations/h20260929_34_levered_single_stock/menu.parquet
with columns (month_end: date, symbol: str, rank: int, dollar_vol_median63: float).
"""

from __future__ import annotations

import sys
from pathlib import Path

import duckdb
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

MEMBERSHIP_CSV = ROOT / "data/sip-delisted/sp500_ticker_start_end_fja05680.csv"
OUT_DIR = ROOT / "reports/research/iterations/h20260929_34_levered_single_stock"
OUT_PATH = OUT_DIR / "menu.parquet"

DATA_START_YEAR = 2016  # data/sip-delisted/daily and data/sip/daily both start 2016-01
DATA_END_YEAR = 2026
TOP_N_MAX = 50
ROLL_WINDOW = 63


def load_membership() -> pd.DataFrame:
    df = pd.read_csv(MEMBERSHIP_CSV)
    df["start_date"] = pd.to_datetime(df["start_date"])
    df["end_date"] = pd.to_datetime(df["end_date"].fillna("2099-01-01"))
    # Only intervals that can possibly overlap the data we have.
    df = df[df["end_date"] >= f"{DATA_START_YEAR}-01-01"].reset_index(drop=True)
    return df


def load_spy_calendar() -> pd.DatetimeIndex:
    con = duckdb.connect()
    con.execute("SET memory_limit='600MB'")
    con.execute("SET threads=2")
    frame = con.execute(
        f"""
        SELECT DISTINCT timestamp::DATE AS d
        FROM read_parquet('data/sip/daily/*/*.parquet')
        WHERE symbol = 'SPY' AND timestamp::DATE >= DATE '{DATA_START_YEAR}-01-01'
        ORDER BY d
        """
    ).df()
    con.close()
    return pd.DatetimeIndex(pd.to_datetime(frame["d"]))


def month_end_dates(index: pd.DatetimeIndex) -> list[pd.Timestamp]:
    ser = pd.Series(index, index=index)
    key = index.to_period("M")
    last = ser.groupby(key).transform("max")
    return list(index[ser == last])


def load_year_dollar_volume(year: int, tickers: list[str]) -> pd.DataFrame:
    """One year of (symbol, date, dollar_vol) for the requested tickers,
    combining the currently-listed and delisted-since-2016 archives, with the
    same ghost-bar hygiene filter `run_h20260918_05_recent_menu.load_panel`
    applies (drop zero-volume/zero-trade-count vendor artifacts)."""
    con = duckdb.connect()
    con.execute("SET memory_limit='600MB'")
    con.execute("SET threads=2")
    in_list = ",".join(f"'{t}'" for t in tickers)
    parts = []
    listed_glob = ROOT / "data" / "sip" / "daily" / str(year)
    if listed_glob.exists():
        parts.append(f"read_parquet('data/sip/daily/{year}/*.parquet')")
    parts.append("read_parquet('data/sip-delisted/daily/*.parquet')")
    union_sql = " UNION ALL BY NAME ".join(f"SELECT * FROM {p}" for p in parts)
    query = f"""
        WITH src AS ({union_sql})
        SELECT symbol, timestamp::DATE AS d, close, volume, trade_count
        FROM src
        WHERE symbol IN ({in_list})
              AND date_part('year', timestamp) = {year}
    """
    frame = con.execute(query).df()
    con.close()
    if frame.empty:
        return frame
    ghost = (frame["volume"].fillna(0) <= 0) & (frame["trade_count"].fillna(0) <= 0)
    frame = frame.loc[~ghost].copy()
    # a (symbol, date) pair can appear twice if a ticker symbol was reused by
    # two different listings that both overlap this calendar year; keep the
    # higher-volume row (avoids double counting / duplicate index errors).
    frame = frame.sort_values("volume", ascending=False).drop_duplicates(
        subset=["symbol", "d"], keep="first"
    )
    frame["dollar_vol"] = frame["close"] * frame["volume"]
    return frame[["symbol", "d", "dollar_vol"]]


def main() -> int:
    membership = load_membership()
    tickers = sorted(membership["ticker"].unique())
    print(f"candidate tickers (membership overlaps >= {DATA_START_YEAR}): {len(tickers)}")

    calendar = load_spy_calendar()
    print(
        f"trading calendar sessions: {len(calendar)} ({calendar[0].date()}..{calendar[-1].date()})"
    )
    month_ends = month_end_dates(calendar)
    print(f"month-end dates: {len(month_ends)}")

    yearly_frames = []
    for year in range(DATA_START_YEAR, DATA_END_YEAR + 1):
        yf = load_year_dollar_volume(year, tickers)
        print(f"  year {year}: {len(yf)} (symbol, date) rows")
        if not yf.empty:
            yearly_frames.append(yf)
    daily = pd.concat(yearly_frames, ignore_index=True)
    daily["d"] = pd.to_datetime(daily["d"])

    wide = daily.pivot_table(index="d", columns="symbol", values="dollar_vol", aggfunc="first")
    wide = wide.reindex(calendar).sort_index()
    roll_median = wide.rolling(ROLL_WINDOW, min_periods=ROLL_WINDOW).median()

    # membership mask: True where `symbol` was an S&P 500 member on date `d`.
    intervals = membership.groupby("ticker")[["start_date", "end_date"]].apply(
        lambda g: list(zip(g["start_date"], g["end_date"], strict=True))
    )

    def is_member(symbol: str, d: pd.Timestamp) -> bool:
        for start, end in intervals.get(symbol, []):
            if start <= d <= end:
                return True
        return False

    rows: list[dict] = []
    for d in month_ends:
        if d not in roll_median.index:
            continue
        row = roll_median.loc[d].dropna()
        if row.empty:
            continue
        members = [s for s in row.index if is_member(s, d)]
        row = row.loc[members]
        if row.empty:
            continue
        ranked = row.sort_values(ascending=False).iloc[:TOP_N_MAX]
        for rank, (symbol, dv) in enumerate(ranked.items(), start=1):
            rows.append(
                {
                    "month_end": d,
                    "symbol": symbol,
                    "rank": rank,
                    "dollar_vol_median63": float(dv),
                }
            )
        print(f"  {d.date()}: {len(members)} eligible members, top1={ranked.index[0]}")

    out = pd.DataFrame(rows)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out.to_parquet(OUT_PATH, index=False)
    print(
        f"wrote {OUT_PATH} ({len(out)} rows, {out['month_end'].nunique()} months,"
        f" {out['symbol'].nunique()} unique symbols ever in top {TOP_N_MAX})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
