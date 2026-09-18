"""Backfill SIP daily bars for symbols missing from ``data/sip/daily`` (delisted,
acquired, or simply outside the active-asset list at archive-fetch time).

Why: the archive was fetched from Alpaca's *active* asset list, so every company
that was acquired or delisted since 2016 is absent (survivorship bias). The
2026-09-17 probe showed Alpaca still serves full daily history for such names
(TWTR, ATVI, SPLK, PXD, SIVB) even though the assets endpoint does not list
them; the only missing piece is a historical symbol list. See
``reports/research/hypotheses/D-20260917-01-broad-universe-and-delisted-backfill.md``.

Candidate symbols = union of
  A. issuer symbols in the parsed Form 4 quarters (``data/raw/insider/parsed``),
  B. SEC ``company_tickers.json`` (current operating companies),
  C. Alpaca INACTIVE assets on listed exchanges (NASDAQ/NYSE/AMEX/ARCA/BATS),
  D. 13D/13G issuer symbols (``data/features/sec_13d/filings.parquet``),
minus the archive symbols, minus symbols already fetched under
``data/sip-delisted/daily`` (the 2026-09-03 S&P-removed batch).

Output layout (same parquet schema as the archive shards):
  data/sip-delisted/broad/_candidates.parquet     one row per candidate + source flags
  data/sip-delisted/broad/daily/batch-NNNN.parquet 40 symbols per batch, may be empty
  data/sip-delisted/broad/_manifest.json           batch -> symbols, rows, symbols_with_bars
Resumable: a batch whose parquet exists is skipped. Run detached via
``scripts/run_capped.sh``; the script name differs from ``fetch_sip_universe.py``
on purpose so the nightly ``update_sip_archive.py`` lock is not triggered, and
it sleeps through the 21:45-22:45 UTC archive-update window.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE_LAYOUT = ROOT / "data" / "sip" / "daily" / "_LAYOUT.json"
PARSED_FORM4 = [
    ROOT / "data" / "raw" / "insider" / "parsed",
    ROOT / "data" / "raw" / "insider" / "tail" / "parsed",
]
SEC_TICKERS = ROOT / "data" / "raw" / "sec_13d" / "company_tickers.json"
SEC_13D = ROOT / "data" / "features" / "sec_13d" / "filings.parquet"
PRIOR_DELISTED = ROOT / "data" / "sip-delisted" / "daily"
OUT = ROOT / "data" / "sip-delisted" / "broad"
LOG_PATH = ROOT / "logs" / "backfill_delisted_daily.log"

BATCH_SIZE = 40
MAX_RETRIES = 5
LISTED_EXCHANGES = {"NASDAQ", "NYSE", "AMEX", "ARCA", "BATS"}
SYMBOL_RE = re.compile(r"^[A-Z]{1,5}$")
BAR_COLUMNS = [
    "symbol",
    "timestamp",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "trade_count",
    "vwap",
]

LOG = logging.getLogger("backfill_delisted")


def _setup_logging() -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.FileHandler(LOG_PATH), logging.StreamHandler(sys.stdout)],
    )


def _clients():
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
    from alpaca.data.historical import StockHistoricalDataClient
    from alpaca.trading.client import TradingClient

    key = os.getenv("ALPACA_API_KEY_ID")
    secret = os.getenv("ALPACA_API_SECRET_KEY")
    if not key or not secret:
        raise SystemExit("ALPACA_API_KEY_ID / ALPACA_API_SECRET_KEY are not configured")
    return StockHistoricalDataClient(key, secret), TradingClient(key, secret, paper=True)


def _norm(sym) -> str | None:
    if sym is None or (isinstance(sym, float) and pd.isna(sym)):
        return None
    s = str(sym).strip().upper()
    return s if SYMBOL_RE.match(s) else None


def archive_symbols() -> set[str]:
    layout = json.loads(ARCHIVE_LAYOUT.read_text())
    return {s for shard in layout["shard_symbols"].values() for s in shard}


def form4_symbols() -> pd.DataFrame:
    frames = []
    for root in PARSED_FORM4:
        for path in sorted(root.glob("*.parquet")):
            cols = ["issuer_symbol", "filing_date"]
            try:
                frame = pd.read_parquet(path, columns=cols + ["issuer_cik"])
            except Exception:  # noqa: BLE001 - older files may lack issuer_cik
                frame = pd.read_parquet(path, columns=cols)
                frame["issuer_cik"] = pd.NA
            frames.append(frame)
    if not frames:
        return pd.DataFrame(
            columns=["symbol", "form4_filings", "form4_first", "form4_last", "form4_cik"]
        )
    df = pd.concat(frames, ignore_index=True)
    df["symbol"] = df["issuer_symbol"].map(_norm)
    df = df.dropna(subset=["symbol"])
    df["filing_date"] = pd.to_datetime(df["filing_date"], errors="coerce")
    g = df.groupby("symbol")
    out = pd.DataFrame(
        {
            "form4_filings": g.size(),
            "form4_first": g["filing_date"].min(),
            "form4_last": g["filing_date"].max(),
            "form4_cik": g["issuer_cik"].agg(
                lambda s: s.dropna().astype(str).mode().iloc[0] if s.notna().any() else None
            ),
        }
    ).reset_index()
    return out


def sec_symbols() -> set[str]:
    raw = json.loads(SEC_TICKERS.read_text())
    rows = list(raw.values()) if isinstance(raw, dict) else raw
    return {s for s in (_norm(r.get("ticker")) for r in rows) if s}


def inactive_listed_symbols(trading_client) -> dict[str, str]:
    from alpaca.trading.enums import AssetClass, AssetStatus
    from alpaca.trading.requests import GetAssetsRequest

    assets = trading_client.get_all_assets(
        GetAssetsRequest(status=AssetStatus.INACTIVE, asset_class=AssetClass.US_EQUITY)
    )
    out = {}
    for a in assets:
        exch = a.exchange.value if a.exchange else None
        s = _norm(a.symbol)
        if s and exch in LISTED_EXCHANGES:
            out[s] = a.name or ""
    return out


def sec13d_symbols() -> set[str]:
    if not SEC_13D.exists():
        return set()
    df = pd.read_parquet(SEC_13D, columns=["issuer_symbol"])
    return {s for s in df["issuer_symbol"].map(_norm) if s}


def prior_delisted_symbols() -> set[str]:
    syms: set[str] = set()
    for path in sorted(PRIOR_DELISTED.glob("*.parquet")):
        syms |= set(pd.read_parquet(path, columns=["symbol"])["symbol"].unique())
    return syms


def build_candidates(trading_client) -> pd.DataFrame:
    arch = archive_symbols()
    prior = prior_delisted_symbols()
    f4 = form4_symbols().set_index("symbol")
    sec = sec_symbols()
    inactive = inactive_listed_symbols(trading_client)
    d13 = sec13d_symbols()
    union = set(f4.index) | sec | set(inactive) | d13
    LOG.info(
        "sources: form4=%d sec=%d inactive_listed=%d 13d=%d union=%d archive=%d prior_delisted=%d",
        len(f4),
        len(sec),
        len(inactive),
        len(d13),
        len(union),
        len(arch),
        len(prior),
    )
    cands = sorted(union - arch - prior)
    rows = []
    for s in cands:
        rows.append(
            {
                "symbol": s,
                "in_form4": s in f4.index,
                "in_sec_tickers": s in sec,
                "in_alpaca_inactive_listed": s in inactive,
                "in_13d": s in d13,
                "alpaca_inactive_name": inactive.get(s),
                "form4_filings": int(f4.loc[s, "form4_filings"]) if s in f4.index else 0,
                "form4_first": f4.loc[s, "form4_first"] if s in f4.index else pd.NaT,
                "form4_last": f4.loc[s, "form4_last"] if s in f4.index else pd.NaT,
                "form4_cik": f4.loc[s, "form4_cik"] if s in f4.index else None,
            }
        )
    frame = pd.DataFrame(rows)
    LOG.info("candidates after removing archive and prior: %d", len(frame))
    return frame


def _sip_safe_end(now: datetime) -> datetime:
    return now - timedelta(minutes=16)


def _empty_bars() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "symbol": pd.Series(dtype="string"),
            "timestamp": pd.Series(dtype="datetime64[ns, UTC]"),
            **{c: pd.Series(dtype="float64") for c in BAR_COLUMNS[2:]},
        }
    )


def _fetch(data_client, symbols: list[str], start: datetime, end: datetime) -> pd.DataFrame:
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame

    request = StockBarsRequest(
        symbol_or_symbols=symbols,
        timeframe=TimeFrame.Day,
        start=start,
        end=end,
        feed="sip",
        adjustment="all",
    )
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            df = data_client.get_stock_bars(request).df
            break
        except Exception as exc:  # noqa: BLE001
            msg = str(exc)
            if attempt == MAX_RETRIES or ("invalid symbol" in msg.lower() and len(symbols) > 1):
                if len(symbols) > 1:
                    mid = len(symbols) // 2
                    LOG.warning("splitting batch of %d after error: %s", len(symbols), msg[:120])
                    left = _fetch(data_client, symbols[:mid], start, end)
                    right = _fetch(data_client, symbols[mid:], start, end)
                    return pd.concat([left, right], ignore_index=True)
                LOG.error("symbol %s failed permanently: %s", symbols[0], msg[:160])
                return _empty_bars()
            wait = min(60, 2**attempt)
            LOG.warning(
                "batch failed (%s), retry %d/%d in %ds", msg[:120], attempt, MAX_RETRIES, wait
            )
            time.sleep(wait)
    if df is None or df.empty:
        return _empty_bars()
    df = df.reset_index()
    for c in BAR_COLUMNS:
        if c not in df.columns:
            df[c] = pd.NA
    df = df[BAR_COLUMNS]
    df["symbol"] = df["symbol"].astype("string")
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    for c in BAR_COLUMNS[2:]:
        df[c] = pd.to_numeric(df[c], errors="coerce").astype("float64")
    return df


def _in_archive_update_window(now: datetime) -> bool:
    minutes = now.hour * 60 + now.minute
    return 21 * 60 + 45 <= minutes <= 22 * 60 + 45


def run(*, start_year: int, limit: int | None, rebuild_candidates: bool) -> int:
    data_client, trading_client = _clients()
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "daily").mkdir(exist_ok=True)
    cand_path = OUT / "_candidates.parquet"
    if cand_path.exists() and not rebuild_candidates:
        cands = pd.read_parquet(cand_path)
        LOG.info("loaded %d candidates from %s", len(cands), cand_path)
    else:
        cands = build_candidates(trading_client)
        cands.to_parquet(cand_path, index=False)
    symbols = sorted(cands["symbol"].tolist())
    if limit:
        symbols = symbols[:limit]
    batches = [symbols[i : i + BATCH_SIZE] for i in range(0, len(symbols), BATCH_SIZE)]
    manifest_path = OUT / "_manifest.json"
    manifest = (
        json.loads(manifest_path.read_text())
        if manifest_path.exists()
        else {"batch_size": BATCH_SIZE, "batches": {}}
    )
    if manifest.get("batch_size") != BATCH_SIZE:
        raise SystemExit("existing manifest has a different batch size; refuse to resume")
    start = datetime(start_year, 1, 1, tzinfo=UTC)
    done = 0
    for i, batch in enumerate(batches):
        path = OUT / "daily" / f"batch-{i:04d}.parquet"
        if path.exists():
            continue
        now = datetime.now(UTC)
        while _in_archive_update_window(now):
            LOG.info("inside archive-update window; sleeping 5 min")
            time.sleep(300)
            now = datetime.now(UTC)
        frame = _fetch(data_client, batch, start, _sip_safe_end(now))
        tmp = path.with_suffix(".tmp.parquet")
        frame.to_parquet(tmp, index=False)
        tmp.replace(path)
        with_bars = sorted(frame["symbol"].unique().tolist()) if not frame.empty else []
        manifest["batches"][f"{i:04d}"] = {
            "symbols": batch,
            "rows": int(len(frame)),
            "symbols_with_bars": with_bars,
            "fetched_at": now.isoformat(),
        }
        manifest_path.write_text(json.dumps(manifest, indent=1))
        done += 1
        LOG.info(
            "batch %04d/%04d: %d symbols, %d with bars, %d rows",
            i,
            len(batches) - 1,
            len(batch),
            len(with_bars),
            len(frame),
        )
        time.sleep(0.3)
    total_with = sum(len(b["symbols_with_bars"]) for b in manifest["batches"].values())
    total_rows = sum(b["rows"] for b in manifest["batches"].values())
    manifest["summary"] = {
        "candidates": len(symbols),
        "batches_total": len(batches),
        "batches_done": len(manifest["batches"]),
        "symbols_with_bars": total_with,
        "rows": total_rows,
        "updated_at": datetime.now(UTC).isoformat(),
    }
    manifest_path.write_text(json.dumps(manifest, indent=1))
    LOG.info("finished: %d new batches this run; %s", done, manifest["summary"])
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--start-year", type=int, default=2016)
    parser.add_argument(
        "--limit", type=int, default=None, help="only the first N candidate symbols"
    )
    parser.add_argument("--rebuild-candidates", action="store_true")
    args = parser.parse_args()
    _setup_logging()
    return run(
        start_year=args.start_year, limit=args.limit, rebuild_candidates=args.rebuild_candidates
    )


if __name__ == "__main__":
    raise SystemExit(main())
