"""Cache Alpaca actions used to undo SIP daily bar adjustments."""

import argparse
import os
from datetime import date
from itertools import batched
from pathlib import Path
from time import sleep

import httpx
import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from open_composer.adapters.data.sip_parquet import MARKET_DATA
from open_composer.research.features.panel import _connect

DERIVED = MARKET_DATA / "derived"
ACTIONS = "daily-us-stock-actions.parquet"
ANCHORS = "daily-us-stock-raw-anchors.parquet"
TYPES = (
    "cash_dividend", "forward_split", "reverse_split", "stock_dividend", "spin_off",
    "name_change",
)


def action_factors(con, path: Path, anchors: Path, asof: pd.Timestamp) -> tuple[dict, dict]:
    events = con.execute("""
        SELECT a.symbol, a.ex_date, a.kind, a.new_symbol,
               CASE WHEN a.kind = 'stock_dividends' THEN 1 / a.rate
                    WHEN a.kind IN ('forward_splits', 'reverse_splits') THEN a.old_rate / a.new_rate
                    ELSE 1 END AS split,
               CASE WHEN a.kind = 'cash_dividends' THEN a.rate
                    WHEN a.kind = 'spin_offs' THEN a.new_rate / a.source_rate * coalesce(r.open, b.open)
                    ELSE 0 END AS cash
        FROM read_parquet(?) a
        LEFT JOIN raw r ON r.symbol = CASE WHEN a.kind = 'spin_offs' THEN a.new_symbol END
            AND r.trade_date = a.ex_date
        LEFT JOIN read_parquet(?) b ON b.symbol = CASE WHEN a.kind = 'spin_offs' THEN a.new_symbol END
            AND b.trade_date = a.ex_date
    """, [str(path), str(anchors)]).df().drop_duplicates()
    renames = events.loc[
        events.kind.isin(["name_changes", "reverse_splits", "forward_splits"])
        & events.new_symbol.notna() & events.symbol.ne(events.new_symbol),
    ]
    incoming = {
        name: rows.sort_values("ex_date") for name, rows in renames.groupby("new_symbol")
    }
    own = {name: rows for name, rows in events.groupby("symbol", sort=False)}
    empty = events.iloc[:0]
    mapped = []
    for name in incoming:
        symbol, end = name, pd.Timestamp(asof)
        while True:
            edges = incoming.get(symbol, empty)
            predecessors = edges.loc[edges.ex_date < end]
            rows = own.get(symbol, empty)
            rows = rows.loc[rows.ex_date <= end]
            if predecessors.empty:
                mapped.append(rows.assign(symbol=name))
                break
            edge = predecessors.iloc[-1]
            mapped.append(rows.loc[rows.ex_date >= edge.ex_date].assign(symbol=name))
            symbol, end = edge.symbol, edge.ex_date
    return _by_symbol(events), _by_symbol(pd.concat(mapped).drop_duplicates())


def join_action_bars(con, selection: str):
    matched = "a.close > 0 AND b.open > 0 AND abs(a.open / a.close - b.open / b.close) <= 0.005"
    con.execute(f"""
        CREATE OR REPLACE TEMP TABLE joined AS
        SELECT b.symbol, b.trade_date, b.open AS adjusted_open, b.close AS adjusted_close,
               r.open AS raw_open, r.close AS original_raw_close, b.volume AS adjusted_volume,
               coalesce(r.close, CASE WHEN {matched} THEN a.close END) AS close,
               coalesce(r.volume, CASE WHEN {matched} THEN a.volume END) AS raw_volume,
               b.source_version
        FROM adj b
        LEFT JOIN raw r ON r.symbol = b.symbol AND r.trade_date = b.trade_date AND r.volume > 0
        LEFT JOIN anchors a ON a.symbol = b.symbol AND a.trade_date = b.trade_date
        WHERE b.close > 0 AND {selection}
        ORDER BY b.symbol, b.trade_date
    """)


def _by_symbol(events: pd.DataFrame) -> dict:
    events = events.groupby(["symbol", "ex_date"], as_index=False).agg(
        split=("split", "prod"), cash=("cash", lambda values: values.sum(skipna=False)),
    )
    return {
        symbol: (rows.ex_date.to_numpy(dtype="datetime64[ns]"), rows.split.to_numpy(), rows.cash.to_numpy())
        for symbol, rows in events.groupby("symbol", sort=False)
    }


def _scales(ratios, edges, split, cash_over_close, train):
    starts, stops = edges[:-1], edges[1:]
    # Prefer an observed RAW/ALL ratio inside the same action interval.
    scales = np.full((len(starts), 2), np.nan)
    for i, (lo, hi) in enumerate(zip(starts, stops, strict=True)):
        observed = ratios[lo:hi][train[lo:hi]]
        if len(observed):
            scales[i] = np.median(observed, axis=0)
    if not np.isfinite(scales[-1]).any():
        # The end of an unanchored series is the terminal basis.
        # A measured earlier scale can override it in the forward pass.
        scales[-1] = np.where(np.isfinite(scales).any(axis=0), np.nan, 1.0)
    # k = RAW price / ALL price. For the prior close A, Alpaca's cash
    # adjustment gives k_before = (k_after + cash/A) / (old_shares/new_shares).
    for i in range(len(scales) - 2, -1, -1):
        price, volume = scales[i + 1]
        predicted = [(price + cash_over_close[i]) / split[i], volume * split[i]]
        scales[i] = np.where(np.isfinite(scales[i]), scales[i], predicted)
    for i in range(1, len(scales)):
        price, volume = scales[i - 1]
        predicted = [price * split[i - 1] - cash_over_close[i - 1], volume / split[i - 1]]
        scales[i] = np.where(np.isfinite(scales[i]), scales[i], predicted)
    scales[~np.isfinite(scales) | (scales <= 0)] = np.nan
    return np.repeat(scales, stops - starts, axis=0)


def reconstruct_raw(
    frame: pd.DataFrame, actions: dict, mapped_actions: dict, *, scales_only: bool = False,
) -> np.ndarray:
    """Fill daily raw units and measure holdout error, or return factors for intraday bars."""
    dates = frame.trade_date.to_numpy()
    adj = frame[["adjusted_close", "adjusted_volume"]].to_numpy(dtype=float)
    raw = frame[["close", "raw_volume"]].to_numpy(dtype=float)
    result = np.full((len(frame), 2 if scales_only else 3), np.nan)
    for indices in frame.groupby("security_id", sort=False).indices.values():
        start, stop = indices[0], indices[-1] + 1
        day, bars, known = dates[start:stop], adj[start:stop], raw[start:stop]
        symbol = frame.symbol.iat[start]
        mapped = frame.source_version.iat[start] != "delisted-daily"
        factors = mapped_actions.get(symbol, actions.get(symbol)) if mapped else actions.get(symbol)
        if factors is None:
            positions, split, cash = np.array([], dtype=int), np.array([]), np.array([])
        else:
            ex_dates, split, cash = factors
            positions = day.searchsorted(ex_dates)
            inside = (positions > 0) & (positions < len(day))
            positions, split, cash = positions[inside], split[inside], cash[inside]
            # A suspension can place multiple event dates at the same bar.
            unique, first = np.unique(positions, return_index=True)
            positions, split, cash = (
                unique, np.multiply.reduceat(split, first) if len(first) else split,
                np.add.reduceat(cash, first) if len(first) else cash,
            )
        edges = np.r_[0, positions, len(day)]
        cash_over_close = cash / bars[positions - 1, 0]
        observed = (known > 0).all(axis=1) & (bars > 0).all(axis=1)
        ratios = np.divide(known, bars, out=np.full_like(known, np.nan), where=observed[:, None])
        if scales_only:
            result[start:stop] = _scales(ratios, edges, split, cash_over_close, observed)
            continue
        held_out = observed & (frame.session_pos.to_numpy()[start:stop] % 2 == 1)
        if held_out.any():
            estimated = bars * _scales(ratios, edges, split, cash_over_close, observed & ~held_out)
            measured = estimated[held_out] / known[held_out]
            result[indices[held_out]] = np.abs(
                np.column_stack((measured, measured.prod(axis=1))) - 1
            )
        if not observed.all():
            estimated = bars * _scales(ratios, edges, split, cash_over_close, observed)
            raw[start:stop] = np.where(np.isfinite(known), known, estimated)
    if not scales_only:
        frame[["close", "raw_volume"]] = raw
    return result


def alpaca_client() -> httpx.Client:
    headers = {
        "APCA-API-KEY-ID": os.environ["ALPACA_API_KEY_ID"],
        "APCA-API-SECRET-KEY": os.environ["ALPACA_API_SECRET_KEY"],
    }
    return httpx.Client(headers=headers, timeout=60)


def fetch_actions(universe: Path) -> pd.DataFrame:
    symbols = set()
    for batch in pq.ParquetFile(universe).iter_batches(columns=["symbol"]):
        symbols.update(batch.column(0).unique().to_pylist())
    rows = {}
    with alpaca_client() as client:
        for names in batched(sorted(symbols), 250):
            params = {
                "symbols": ",".join(names), "types": ",".join(TYPES),
                "start": "2016-01-01", "end": date.today().isoformat(), "limit": 1000,
            }
            while True:
                response = client.get("https://data.alpaca.markets/v1/corporate-actions", params=params)
                response.raise_for_status()
                page = response.json()
                for kind, actions in page["corporate_actions"].items():
                    for row in actions:
                        rows[row["id"]] = {
                            **row, "kind": kind,
                            "symbol": row.get("symbol") or row.get("source_symbol") or row["old_symbol"],
                            "ex_date": row.get("ex_date") or row.get("effective_date") or row["process_date"],
                        }
                if not page["next_page_token"]:
                    break
                params["page_token"] = page["next_page_token"]
    frame = pd.DataFrame(rows.values())
    frame["ex_date"] = pd.to_datetime(frame["ex_date"])
    return frame.sort_values(["symbol", "ex_date", "id"])


def fetch_anchors(universe: Path) -> pd.DataFrame:
    # Sample annual archive ends and a few early edges for overlap checks.
    with _connect("300MB") as con:
        targets = con.execute("""
            WITH members AS (
                SELECT trade_date, symbol, source_version FROM read_parquet(?)
                WHERE is_member
            ), edges AS (
                SELECT min(trade_date) AS first, max(trade_date) AS last
                FROM members WHERE symbol = 'SPY' GROUP BY source_version, year(trade_date)
            )
            SELECT trade_date::DATE AS day, list(DISTINCT symbol ORDER BY symbol) AS symbols
            FROM members WHERE trade_date IN (
                SELECT first FROM edges WHERE year(first) IN (2016, 2020, 2024, 2026)
                UNION SELECT last FROM edges
            )
            GROUP BY 1 ORDER BY 1 DESC
        """, [str(universe)]).fetchall()
    asof = str(targets[0][0])
    rows = []
    with alpaca_client() as client:
        for day, symbols in targets:
            for names in batched(symbols, 600):
                rows.extend(_raw_bars(client, names, day, day, asof))
    return pd.concat([_bar_frame(rows), fetch_spin_bars(universe.parent / ACTIONS)]).drop_duplicates(
        ["symbol", "trade_date"]
    )


def _raw_bars(client, names, start, end, asof):
    sleep(0.34)  # Alpaca Basic permits 200 requests per minute.
    response = client.get("https://data.alpaca.markets/v2/stocks/bars", params={
        "symbols": ",".join(names), "timeframe": "1Day", "feed": "sip",
        "start": str(start), "end": f"{end}T23:59:59Z", "adjustment": "raw",
        "asof": asof, "limit": 10000,
    })
    response.raise_for_status()
    for symbol, bars in response.json()["bars"].items():
        yield from ((symbol, bar["t"][:10], bar["o"], bar["c"], bar["v"])
                    for bar in bars if bar["v"] > 0)


def _bar_frame(rows):
    frame = pd.DataFrame(rows, columns=["symbol", "trade_date", "open", "close", "volume"])
    frame["trade_date"] = pd.to_datetime(frame.trade_date)
    return frame


def fetch_spin_bars(actions_path: Path) -> pd.DataFrame:
    # The distribution's value is the first day's quoted open of the child.
    actions = pd.read_parquet(
        actions_path, columns=["new_symbol", "new_cusip", "ex_date"],
        filters=[("kind", "=", "spin_offs")],
    )
    actions = actions.loc[actions.new_symbol.ne(actions.new_cusip), ["new_symbol", "ex_date"]]
    actions = actions.rename(columns={"new_symbol": "symbol", "ex_date": "trade_date"}).drop_duplicates()
    result = []
    with alpaca_client() as client:
        for _, events in actions.groupby(actions.trade_date.dt.to_period("Q")):
            days = events.trade_date.dt.date
            for names in batched(sorted(events.symbol.unique()), 140):
                result.extend(_raw_bars(client, names, days.min(), days.max(), "-"))
    return actions.merge(_bar_frame(result), on=["symbol", "trade_date"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--universe", type=Path, default=DERIVED / "daily-us-stock-universe.parquet")
    parser.add_argument("--anchors", action="store_true")
    args = parser.parse_args()
    frame = fetch_anchors(args.universe) if args.anchors else fetch_actions(args.universe)
    cache = args.universe.parent / (ANCHORS if args.anchors else ACTIONS)
    pending = cache.with_suffix(".partial")
    frame.to_parquet(pending, index=False)
    pending.replace(cache)
    print(f"{cache.name}: {len(frame):,} rows")
