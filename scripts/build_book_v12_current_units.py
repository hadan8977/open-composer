"""Build an isolated current-adjustment consumer root with the native book formulas.

The published forward lake is an immutable historical record.  Corporate-action
restatements require a separate, consistently adjusted input view for current
risk and virtual shares.  This producer never reads old prices as a fallback.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DAILY_COLUMNS = [
    "symbol",
    "trade_date",
    "open",
    "close",
    "dollar_adv_21",
    "dollar_adv_63",
    "beta_252_spy",
    "idio_vol_63",
    "vol_21",
]
FROZEN_SELECTION = ["adv_rank", "in_u3000", "in_p1000", "ff48", "ff48_verified"]
NATIVE_SCRIPTS = {
    "build_sec_xbrl_fundamentals",
    "build_nsi_signal",
    "collect_sec_insider_transactions",
    "build_insider_features",
    "collect_finra_short_volume",
    "build_short_volume_features",
    "collect_finra_short_interest",
    "build_short_interest_features",
    "collect_alpaca_news_packets",
    "build_news_attention_features",
    "build_equity_book_risk",
    "build_equity_book_signals",
    "build_book_v1_alpha",
    "build_equity_book_panel",
    "fetch_vix_live",
}


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def detach_outputs(paths):
    """Native writers may truncate their destination; detach named outputs first."""
    result = []
    for path in paths:
        if not path.is_file():
            continue
        before = digest(path)
        if path.stat().st_nlink > 1:
            tmp = path.with_suffix(path.suffix + ".private-copy")
            shutil.copy2(path, tmp)
            os.replace(tmp, path)
        if path.stat().st_nlink != 1 or digest(path) != before:
            raise ValueError(f"output detachment failed: {path}")
        result.append({"path": str(path), "sha256_before": before, "nlink": 1})
    return result


def daily_binding(view, declared, year):
    sources = json.loads((view / "current-units-source.json").read_text())["source_bindings"]
    inputs = [
        x
        for x in sources
        if any(f"/{y}/" in x["path"] for y in range(max(2016, year - 1), year + 1))
    ]
    for item in inputs:
        if digest(view / item["path"]) != item["sha256"]:
            raise ValueError("bound raw source changed")
    return {
        "year": year,
        "input_bindings": inputs,
        "declared_symbols_sha256": digest(declared),
        "formula_sha256": digest(ROOT / "open_composer/research/features/daily_features.py"),
        "price_hygiene_sha256": digest(ROOT / "open_composer/research/features/price_hygiene.py"),
        "columns": DAILY_COLUMNS,
        "warmup_years": [max(2016, year - 1), year],
    }


def bootstrap(source: Path, view: Path, context: Path, frozen: Path | None = None):
    """Bind actual input bytes and reuse code; no provider vintages are invented."""
    if view.exists():
        raise ValueError("view exists; preserve the previous attempt")
    view.mkdir(parents=True)
    frozen = frozen or source
    bindings = []
    for group in ("open_composer", "scripts", "config"):
        for p in (source / group).rglob("*"):
            if (
                not p.is_file()
                or "__pycache__" in p.parts
                or p.suffix not in (".py", ".json", ".yaml", ".yml", ".sh")
            ):
                continue
            q = view / p.relative_to(source)
            q.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, q)
    # Code sees this root while using the already installed MAIN interpreter.
    for group in ("data/features", "data/raw"):
        inputs = frozen if group == "data/features" else source
        for p in (inputs / group).rglob("*"):
            if not p.is_file() or any(
                x in p.parts
                for x in ("_forward_v1", "_refresh_tmp", "_refresh_backups", "daily", "daily_broad")
            ):
                continue
            if group == "data/features" and p.parent.name in ("daily", "daily_broad"):
                continue
            q = view / p.relative_to(inputs)
            q.parent.mkdir(parents=True, exist_ok=True)
            # Raw inputs are not modified by a price-view build. Feature outputs
            # may be replaced in place by the original producers.
            if (group == "data/raw" and p.suffix in (".json", ".csv", ".jsonl")) or (
                group == "data/features"
                and (
                    p.suffix != ".parquet"
                    or p.stem == "2026"
                    or p.name in ("facts.parquet", "nsi.parquet")
                )
            ):
                shutil.copy2(p, q)
            else:
                os.link(p.resolve(), q)
    for year in range(2016, 2027):
        rawroot = context if year >= 2025 else source
        for group in ("data/sip/daily", "data/sip-delisted/by_year"):
            folder = rawroot / group / str(year)
            if not folder.exists() and year < 2025:
                folder = Path("/root/codex-test/open-composer") / group / str(year)
            for p in sorted(folder.glob("*.parquet")):
                q = view / group / str(year) / p.name
                q.parent.mkdir(parents=True, exist_ok=True)
                os.link(p.resolve(), q)
                bindings.append(
                    {
                        "path": str(q.relative_to(view)),
                        "source": str(p),
                        "sha256": digest(p),
                        "bytes": p.stat().st_size,
                    }
                )
    for p in (frozen / "data/live/equity_book").rglob("*"):
        if p.is_file() and p.relative_to(frozen / "data/live/equity_book").parts[0] in (
            "signals",
            "alpha",
        ):
            q = view / "data/live/equity_book" / p.relative_to(frozen / "data/live/equity_book")
            q.parent.mkdir(parents=True, exist_ok=True)
            if (
                p.stem == "2026"
                or p.name in ("themes_2026.parquet", "formation_ic.parquet")
                or p.suffix != ".parquet"
            ):
                shutil.copy2(p, q)
            else:
                os.link(p.resolve(), q)
    # VIX is a separately observed input, not equity price reconstruction.
    for name in ("vix.csv", "vix.parquet"):
        p = source / "data/live/equity_book" / name
        if p.exists():
            q = view / "data/live/equity_book" / name
            q.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, q)
    meta = {
        "created_at_utc": datetime.now(UTC).isoformat(),
        "source_root": str(source),
        "frozen_selection_and_facts_root": str(frozen),
        "corrected_two_year_context": str(context),
        "source_bindings": bindings,
        "price_adjustment": "all",
        "historical_first_visible_certified": False,
        "old_published_price_fallback": False,
        "frozen_selection_columns": FROZEN_SELECTION,
        "selection_note": (
            "Old row keys, membership and ADV rank are frozen selection metadata, not independent "
            "price-free facts."
        ),
    }
    (view / "current-units-source.json").write_text(json.dumps(meta, indent=2) + "\n")


def daily(view: Path, declared: Path, years: list[int]):
    import duckdb

    sys.path.insert(0, str(ROOT))
    from open_composer.research.features.daily_features import build_daily_features

    names = json.loads(declared.read_text())["symbols"]
    out = view / "data/features/daily_broad"
    out.mkdir(parents=True, exist_ok=True)
    receipts = []
    for year in years:
        dest = out / f"{year}.parquet"
        receipt = dest.with_suffix(".receipt.json")
        binding = daily_binding(view, declared, year)
        if dest.exists():
            if not receipt.exists():
                raise ValueError(f"unsealed output retained, not reusable: {dest}")
            prior = json.loads(receipt.read_text())
            if prior["binding"] != binding or prior["output_sha256"] != digest(dest):
                raise ValueError("existing projection does not match its completion binding")
            print(f"daily {year}: verified completed projection", flush=True)
            continue
        globs = []
        for y in range(max(2016, year - 1), year + 1):
            for group in ("data/sip/daily", "data/sip-delisted/by_year"):
                if any((view / group / str(y)).glob("*.parquet")):
                    globs.append(str(view / group / str(y) / "*.parquet"))
        temporary = out / f".native-{year}.parquet"
        build_daily_features(
            globs,
            names,
            memory_limit="400MB",
            temp_directory=str(view / "data/_duckdb_tmp"),
            output_parquet=temporary,
            output_year=year,
            threads=1,
        )
        con = duckdb.connect()
        con.execute("SET memory_limit='200MB'")
        con.execute("SET threads=1")
        cols = ",".join(DAILY_COLUMNS)
        projection = dest.with_suffix(".projection.tmp")
        if projection.exists():
            raise ValueError("failed projection retained; choose a new attempt")
        con.execute(
            f"COPY (SELECT {cols} FROM read_parquet('{temporary}') ORDER BY symbol,trade_date) "
            f"TO '{projection}' (FORMAT PARQUET, COMPRESSION ZSTD)"
        )
        info = con.execute(
            f"SELECT count(*),min(trade_date),max(trade_date),count(distinct symbol) FROM "
            f"read_parquet('{projection}')"
        ).fetchone()
        if info[0] <= 0:
            raise ValueError("native projection is empty")
        os.replace(projection, dest)
        completed = {
            "binding": binding,
            "output_sha256": digest(dest),
            "completed_at_utc": datetime.now(UTC).isoformat(),
            "rows": info[0],
        }
        receipt.write_text(json.dumps(completed, indent=2) + "\n")
        receipts.append(
            {
                "year": year,
                "rows": info[0],
                "min": str(info[1]),
                "max": str(info[2]),
                "symbols": info[3],
                "sha256": digest(dest),
                "formula": (
                    "native build_daily_features, original year-1/year warmup, nine consumed "
                    "columns projected without numeric changes"
                ),
            }
        )
        con.close()
        temporary.unlink()  # Successful projection only; failed attempts remain.
        print(json.dumps(receipts[-1]), flush=True)
        (view / "current-units-daily.json").write_text(json.dumps(receipts, indent=2) + "\n")


def monthly(view: Path, credentials_root: Path, month_end: date, application_day: date):
    """Append one closed cohort in its month-end physical price/share units.

    Prices used by signals remain current adjustment=all. This separate pool
    step undoes only actions after the cohort date for the absolute price and
    dollar-ADV gates, then applies the original rank and fund exclusion order.
    """
    import duckdb
    import pandas as pd
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame
    from dotenv import load_dotenv

    sys.path.insert(0, str(ROOT))
    sys.path.insert(0, str(ROOT / "scripts"))
    from fetch_sip_universe import _clients

    from open_composer.research.features.universe import (
        build_pit_universe_panel,
        exclude_funds_and_etfs,
    )

    load_dotenv(credentials_root / ".env", override=False)
    globs = [
        str(view / f"data/sip/daily/{month_end.year}/*.parquet"),
        str(view / f"data/sip-delisted/by_year/{month_end.year}/*.parquet"),
    ]
    globs = [p for p in globs if list(Path(p).parent.glob("*.parquet"))]
    # Jan..Oct has the complete original 60-row lookback for the October row.
    native = build_pit_universe_panel(
        globs,
        top_n=1000000,
        min_close=0,
        memory_limit="400MB",
        temp_directory=str(view / "data/_duckdb_tmp"),
    )
    native = native.loc[native.month_end.dt.date == month_end].copy()
    if native.empty:
        raise ValueError("native source omitted the expected completed month end")
    con = duckdb.connect()
    con.execute("SET memory_limit='200MB'")
    con.execute("SET threads=1")
    endpoint = con.execute(
        f"""WITH rolling AS (
            SELECT symbol,timestamp,close,volume,
              avg(volume) OVER (PARTITION BY symbol ORDER BY timestamp ROWS 59 PRECEDING)
                AS avg_volume_60,
              avg(abs(close)) OVER (PARTITION BY symbol ORDER BY timestamp ROWS 59 PRECEDING)
                AS avg_close_60
            FROM read_parquet({globs!r},union_by_name=true))
        SELECT symbol,close AS close_all,volume AS volume_all,
          cast(timestamp as date) AS last_date,avg_volume_60,avg_close_60
        FROM rolling
        WHERE cast(timestamp as date) between DATE '{month_end.replace(day=1)}'
          and DATE '{month_end}'
        QUALIFY row_number() OVER (PARTITION BY symbol ORDER BY timestamp DESC)=1"""
    ).fetchdf()
    native = native.merge(endpoint, on="symbol", validate="one_to_one")
    archive = view / "month-end-raw"
    archive.mkdir(exist_ok=True)
    raw_path = archive / f"{month_end}-through-{application_day}.parquet"
    _, client = _clients()

    def receive(response, *args, **kwargs):
        if response.request.method != "GET":
            raise RuntimeError("GET only")
        with (archive / "http.jsonl").open("a") as stream:
            stream.write(
                json.dumps(
                    {
                        "url": response.url,
                        "status": response.status_code,
                        "received_at_utc": datetime.now(UTC).isoformat(),
                        "sha256": hashlib.sha256(response.content).hexdigest(),
                    }
                )
                + "\n"
            )
        return response

    client._session.hooks["response"] = [receive]
    if raw_path.exists():
        raw = pd.read_parquet(raw_path)
    else:
        rows = []
        names = sorted(native.symbol.unique())
        for i in range(0, len(names), 100):
            req = StockBarsRequest(
                symbol_or_symbols=names[i : i + 100],
                timeframe=TimeFrame.Day,
                start=datetime.combine(month_end.replace(day=1), datetime.min.time(), UTC),
                end=datetime.combine(application_day, datetime.min.time(), UTC),
                feed="sip",
                adjustment="raw",
            )
            frame = client.get_stock_bars(req).df
            if len(frame):
                rows.append(frame.reset_index())
            if i % 1000 == 0:
                print(f"month endpoint {i}/{len(names)}", flush=True)
        raw = pd.concat(rows, ignore_index=True)
        raw.to_parquet(raw_path, index=False)
    raw["last_date"] = pd.to_datetime(raw.timestamp, utc=True).dt.date
    raw_history = raw.copy()
    raw = raw.loc[raw.last_date <= month_end].copy()
    native["last_date"] = pd.to_datetime(native.last_date).dt.date
    bridge = native.merge(
        raw[["symbol", "last_date", "close", "volume"]].rename(
            columns={"close": "close_raw", "volume": "volume_raw"}
        ),
        on=["symbol", "last_date"],
        how="left",
        validate="one_to_one",
    )
    missing = bridge.close_raw.isna()
    if missing.any():
        # Asking for both a retired name and its current ticker can suppress
        # the retired key in a batch response. Query the exact default identity
        # separately; do not backdate `asof` to relabel a successor's bars.
        extras = []
        for symbol in bridge.loc[missing, "symbol"]:
            req = StockBarsRequest(
                symbol_or_symbols=[symbol],
                timeframe=TimeFrame.Day,
                start=datetime.combine(month_end.replace(day=1), datetime.min.time(), UTC),
                end=datetime.combine(application_day, datetime.min.time(), UTC),
                feed="sip",
                adjustment="raw",
            )
            frame = client.get_stock_bars(req).df
            if len(frame):
                frame = frame.reset_index()
                frame.to_parquet(archive / f"raw-single-default-{symbol}.parquet", index=False)
                frame["last_date"] = pd.to_datetime(frame.timestamp, utc=True).dt.date
                extras.append(frame)
        if extras:
            raw_history = pd.concat([raw_history, *extras], ignore_index=True).drop_duplicates(
                ["symbol", "last_date"], keep="last"
            )
            raw = raw_history.loc[raw_history.last_date <= month_end]
            bridge = native.merge(
                raw[["symbol", "last_date", "close", "volume"]].rename(
                    columns={"close": "close_raw", "volume": "volume_raw"}
                ),
                on=["symbol", "last_date"],
                how="left",
                validate="one_to_one",
            )
            missing = bridge.close_raw.isna()
        if missing.any():
            bridge.loc[missing].to_csv(
                archive / "missing-raw-after-single-identity.csv", index=False
            )
            raise ValueError(
                f"{int(missing.sum())} exact original identity/date endpoints are unavailable"
            )
    # Provider action terms, rather than rounded endpoint ratios, determine
    # the uniform post-cohort unit change. Keep actions inside the month.
    legacy_actions = archive / "actions.json"
    actions_path = (
        legacy_actions
        if month_end == date(2026, 10, 30) and legacy_actions.exists()
        else archive / f"actions-{month_end}-through-{application_day}.json"
    )
    if actions_path.exists():
        pages = json.loads(actions_path.read_text())
    else:
        pages = []
        names = sorted(native.symbol.unique())
        for i in range(0, len(names), 100):
            cursor = None
            while True:
                params = {
                    "symbols": ",".join(names[i : i + 100]),
                    "start": str(month_end.replace(day=1)),
                    "end": str(application_day + timedelta(days=90)),
                    "limit": 1000,
                }
                if cursor:
                    params["page_token"] = cursor
                page = client.get("/corporate-actions", params, api_version="v1")
                pages.append(page)
                cursor = page.get("next_page_token")
                if not cursor:
                    break
        actions_path.write_text(json.dumps(pages, indent=2) + "\n")
    events = {}
    known_fix = view / "current-units-known-actions-repair.json"
    repaired_symbols = (
        {r["symbol"] for r in json.loads(known_fix.read_text())["repairs"]}
        if known_fix.exists()
        else set()
    )
    for page in pages:
        for kind, rows in page.get("corporate_actions", {}).items():
            for event in rows:
                ex = event.get("ex_date")
                if ex and month_end.isoformat() < ex <= application_day.isoformat():
                    if (
                        "CQP" in repaired_symbols
                        and kind == "cash_dividends"
                        and event.get("symbol") == "CQP"
                        and ex == "2026-11-03"
                        and float(event["rate"]) in (0.775, 0.115)
                    ):
                        continue
                    if (
                        "SCCO" in repaired_symbols
                        and kind == "cash_dividends"
                        and event.get("symbol") == "SCCO"
                        and ex == "2026-11-03"
                        and float(event["rate"]) == 1.0106
                    ):
                        continue
                    events.setdefault(event.get("symbol"), []).append((kind, event))
    price_factors = {}
    volume_factors = {}
    action_receipts = []
    for symbol, items in events.items():
        pf = 1.0
        vf = 1.0
        for kind, event in items:
            if kind == "cash_dividends":
                prior = raw_history.loc[
                    (raw_history.symbol == symbol)
                    & (raw_history.last_date < date.fromisoformat(event["ex_date"]))
                ].sort_values("timestamp")
                if prior.empty:
                    raise ValueError(f"cash adjustment lacks prior physical close: {symbol}")
                physical = float(prior.iloc[-1].close)
                factor = 1 - float(event["rate"]) / physical
                if factor <= 0:
                    raise ValueError(f"invalid cash factor: {symbol}")
                pf *= factor
            elif kind in ("forward_splits", "reverse_splits"):
                factor = float(event["old_rate"]) / float(event["new_rate"])
                pf *= factor
                vf /= factor
            elif (
                kind == "stock_dividends"
                and symbol == "SCCO"
                and symbol in repaired_symbols
                and event["ex_date"] == "2026-11-03"
            ):
                factor = 1 / float(event["rate"])
                pf *= factor
                vf /= factor
            elif kind in ("spin_offs", "spinoffs"):
                raise ValueError(
                    f"actual post-month spin-off needs its provider price factor: {symbol}"
                )
            else:
                continue
            action_receipts.append(
                {"symbol": symbol, "kind": kind, "event": event, "price_factor": factor}
            )
        price_factors[symbol] = pf
        volume_factors[symbol] = vf
    bridge["post_month_price_factor"] = bridge.symbol.map(price_factors).fillna(1.0)
    bridge["post_month_volume_factor"] = bridge.symbol.map(volume_factors).fillna(1.0)
    bridge["price_to_month_unit"] = 1 / bridge.post_month_price_factor
    bridge["volume_to_month_unit"] = 1 / bridge.post_month_volume_factor
    bridge["restored_close"] = bridge.close_all * bridge.price_to_month_unit
    active = bridge.last_date == month_end
    # Adjusted prices are rounded by the source. Physical month-end endpoint
    # prices provide the exact absolute-price gate when a bar exists at t.
    bridge["endpoint_price_error"] = bridge.restored_close - bridge.close_raw
    tolerance = 0.005 * bridge.price_to_month_unit.abs() + 0.000051
    bad = active & (bridge.endpoint_price_error.abs() > tolerance)
    if bad.any():
        bridge.loc[bad].to_csv(archive / "unexplained-month-endpoint.csv", index=False)
        raise ValueError("post-month action factors do not explain physical month endpoints")
    bridge["dollar_adv_current_all"] = bridge.dollar_adv
    bridge["dollar_adv"] = (
        bridge.dollar_adv * bridge.price_to_month_unit * bridge.volume_to_month_unit
    )
    bridge["close"] = bridge.restored_close
    bridge.loc[active, "close"] = bridge.loc[active, "close_raw"]
    # Rounding is bounded explicitly, not mistaken for a precise old vintage.
    # Source prices at >=$1 have a cent tick; using half a cent also bounds the
    # finer sub-dollar quotes. Split volume truncation is <one current share.
    changed_units = (bridge.post_month_price_factor != 1) | (bridge.post_month_volume_factor != 1)
    bridge["adv_rounding_bound"] = 0.0
    bridge.loc[changed_units, "adv_rounding_bound"] = bridge.loc[changed_units, "avg_volume_60"] * (
        0.005 * bridge.loc[changed_units, "price_to_month_unit"].abs() + 0.005
    ) * bridge.loc[changed_units, "volume_to_month_unit"].abs() + bridge.loc[
        changed_units, "avg_close_60"
    ] * bridge.loc[changed_units, "price_to_month_unit"].abs() * bridge.loc[
        changed_units, "volume_to_month_unit"
    ].abs() * (bridge.loc[changed_units, "post_month_volume_factor"] != 1)
    exact_window_receipt = archive / "IGLD-60-window/receipt.json"
    exact_window = None
    if exact_window_receipt.exists() and json.loads(exact_window_receipt.read_text())[
        "month_end"
    ] == str(month_end):
        exact_window = json.loads(exact_window_receipt.read_text())
        window_folder = exact_window_receipt.parent
        for key, filename in [
            ("raw_sha256", "raw.parquet"),
            ("actions_sha256", "actions.json"),
            ("reconstruction_sha256", "reconstruction.csv"),
        ]:
            if digest(window_folder / filename) != exact_window[key]:
                raise ValueError("affected raw window evidence changed")
        source = exact_window["all_source"]
        if digest(source["path"]) != source["sha256"]:
            # A later actual D-only source revision may share this partition.
            # Preserve the accepted original bytes, and require the consumed
            # sixty IGLD close/volume rows themselves to remain exactly equal.
            frozen_source = view / "endpoint-revision-20261103/IGLD-original-source.parquet"
            if not frozen_source.exists() or digest(frozen_source) != source["sha256"]:
                raise ValueError("affected current all window source changed")
            old_window = con.execute(
                f"SELECT timestamp,close,volume FROM read_parquet('{frozen_source}') WHERE "
                f"symbol='IGLD' AND cast(timestamp as date)<=DATE '{month_end}' ORDER BY "
                f"timestamp DESC LIMIT 60"
            ).df()
            new_window = con.execute(
                f"SELECT timestamp,close,volume FROM read_parquet('{source['path']}') WHERE "
                f"symbol='IGLD' AND cast(timestamp as date)<=DATE '{month_end}' ORDER BY "
                f"timestamp DESC LIMIT 60"
            ).df()
            pd.testing.assert_frame_equal(old_window, new_window, check_exact=True)
            (window_folder / "later-endpoint-revision-window-reuse.json").write_text(
                json.dumps(
                    {
                        "old_source_path": str(frozen_source),
                        "old_source_sha256": digest(frozen_source),
                        "current_source_sha256": digest(source["path"]),
                        "consumed_60_rows_unchanged_exactly": True,
                    },
                    indent=2,
                )
                + "\n"
            )
        if (
            exact_window["symbol"] != "IGLD"
            or exact_window["month_end"] != str(month_end)
            or exact_window["rows"] != 60
            or exact_window["current_all_close_max_error"] != 0
            or exact_window["current_all_volume_max_error"] != 0
        ):
            raise ValueError("affected raw window failed original source reconstruction")
        affected = bridge.symbol.eq("IGLD")
        if (
            abs(
                float(bridge.loc[affected, "dollar_adv_current_all"].iloc[0])
                - exact_window["current_dollar_adv"]
            )
            > 1e-7
        ):
            raise ValueError("affected raw window differs from native 60-row input")
        bridge.loc[affected, "dollar_adv"] = exact_window["month_dollar_adv"]
        bridge.loc[affected, "adv_rounding_bound"] = 0.0
    (archive / "post-month-action-bridge.json").write_text(
        json.dumps(action_receipts, indent=2) + "\n"
    )
    metadata = pd.read_parquet(view / "data/features/universe/_asset_metadata.parquet")
    receipts = []
    for group, minimum, cap, floor in [
        ("universe", 5.0, 1500, None),
        ("universe_broad", 2.0, None, 1000000.0),
    ]:
        chosen = bridge.loc[bridge.close > minimum].copy()
        import numpy as np

        lower = chosen.dollar_adv - chosen.adv_rounding_bound
        upper = chosen.dollar_adv + chosen.adv_rounding_bound
        chosen["best_possible_rank"] = (
            1 + len(chosen) - np.searchsorted(np.sort(lower), upper, side="right")
        )
        chosen["worst_possible_rank"] = (
            1
            + len(chosen)
            - np.searchsorted(np.sort(upper), lower, side="right")
            - (upper > lower).astype(int)
        )
        # Match the native SQL CAST exactly (including half-to-even rounding).
        # These are the actual boundaries for the native mcap buckets, not
        # multiples of 250. Membership cutoffs are checked separately too.
        cuts = con.execute("""WITH ranks AS (
            SELECT r, CAST(r / 250 AS INTEGER) AS bucket
            FROM range(1,4002) t(r)
          ) SELECT a.r, a.bucket, b.bucket AS next_bucket
          FROM ranks a JOIN ranks b ON b.r=a.r+1
          WHERE a.r<=4000 AND a.bucket<>b.bucket ORDER BY a.r""").df()
        cuts.to_csv(archive / "native-mcap-bucket-boundaries.csv", index=False)
        boundaries = (
            [1500] if cap is not None else sorted(set(cuts.r.tolist()) | {1000, 3000, 4000})
        )
        ambiguous_rank = np.zeros(len(chosen), dtype=bool)
        for boundary in boundaries:
            ambiguous_rank |= (chosen.best_possible_rank <= boundary) & (
                chosen.worst_possible_rank > boundary
            )
        ambiguous_floor = np.zeros(len(chosen), dtype=bool)
        if floor is not None:
            ambiguous_floor = (lower <= floor) & (upper >= floor) & (chosen.adv_rounding_bound > 0)
        fund_names = set(metadata.loc[metadata.is_probable_fund_or_etf, "symbol"])
        # The ADV floor is after the full cross-section rank. A fund's floor
        # ambiguity cannot affect stock membership because the existing final
        # fund exclusion removes it either way. Rank ambiguity remains checked
        # for every name, including funds, before this final exclusion.
        floor_excluded_by_original_fund = ambiguous_floor & chosen.symbol.isin(fund_names)
        excluded_floor_names = chosen.loc[floor_excluded_by_original_fund, "symbol"].tolist()
        effective_floor_ambiguity = ambiguous_floor & ~chosen.symbol.isin(fund_names)
        gate_uncertain = (
            (~active) & changed_units & ((bridge.restored_close - minimum).abs() <= tolerance)
        )
        if ambiguous_rank.any() or effective_floor_ambiguity.any() or gate_uncertain.any():
            chosen.loc[ambiguous_rank | ambiguous_floor].to_csv(
                archive / f"{group}-sensitive-adv-boundaries.csv", index=False
            )
            bridge.loc[gate_uncertain].to_csv(
                archive / f"{group}-sensitive-price-boundaries.csv", index=False
            )
            raise ValueError(
                "source rounding can change an original pool boundary; actual 60-row affected "
                "reconstruction required"
            )
        chosen["adv_rank"] = chosen.dollar_adv.rank(method="min", ascending=False).astype("int64")
        if cap is not None:
            chosen = chosen.loc[chosen.adv_rank <= cap]
        if floor is not None:
            chosen = chosen.loc[chosen.dollar_adv >= floor]
        chosen = exclude_funds_and_etfs(chosen, metadata)
        legacy = native.loc[native.close > minimum].copy()
        legacy["adv_rank"] = legacy.dollar_adv.rank(method="min", ascending=False).astype("int64")
        if cap is not None:
            legacy = legacy.loc[legacy.adv_rank <= cap]
        if floor is not None:
            legacy = legacy.loc[legacy.dollar_adv >= floor]
        legacy = exclude_funds_and_etfs(legacy, metadata)
        dest = view / f"data/features/{group}/{month_end.year}.parquet"
        existing = pd.read_parquet(dest)
        existing_dates = pd.to_datetime(existing.month_end).dt.date
        if (existing_dates > month_end).any():
            raise ValueError("new month would overwrite a later frozen cohort")
        old = existing.loc[existing_dates < month_end].copy()
        cols = list(old.columns)
        add = chosen[cols].sort_values(["month_end", "symbol"])
        combined = pd.concat([old, add], ignore_index=True)
        pd.testing.assert_frame_equal(
            old.reset_index(drop=True),
            combined.iloc[: len(old)].reset_index(drop=True),
            check_exact=True,
        )
        reused_existing_month = bool((existing_dates == month_end).any())
        repaired_unpublished_month = False
        if reused_existing_month:
            # A previous attempt can have completed the private output before
            # its receipt failed. Accept only an exact same-source replay.
            published = (
                existing.loc[existing_dates == month_end]
                .sort_values(["month_end", "symbol"])
                .reset_index(drop=True)
            )
            try:
                pd.testing.assert_frame_equal(
                    published, add.reset_index(drop=True), check_exact=True
                )
            except AssertionError:
                if (
                    month_end != date(2026, 10, 30)
                    or not known_fix.exists()
                    or (view / "current-units-ready.json").exists()
                ):
                    raise
                # Only this not-yet-published Oct30 candidate is corrected;
                # every frozen month before it remains byte/value identical.
                evidence = archive / f"{group}-before-known-action-repair.parquet"
                if not evidence.exists():
                    os.link(dest, evidence)
                delta = published.merge(
                    add,
                    on=["month_end", "symbol"],
                    how="outer",
                    suffixes=("_before", "_after"),
                    indicator=True,
                )
                delta.to_csv(archive / f"{group}-known-action-repair-comparison.csv", index=False)
                temp = dest.with_suffix(".known-action-month.tmp")
                combined.to_parquet(temp, index=False)
                os.replace(temp, dest)
                repaired_unpublished_month = True
        else:
            temp = dest.with_suffix(".current.tmp")
            combined.to_parquet(temp, index=False)
            os.replace(temp, dest)
        changed = chosen.merge(
            legacy[["symbol", "adv_rank"]].rename(columns={"adv_rank": "legacy_adv_rank"}),
            on="symbol",
            how="outer",
            indicator=True,
        )
        changed.to_csv(archive / f"{group}-comparison.csv", index=False)
        receipts.append(
            {
                "group": group,
                "month_end": str(month_end),
                "new_rows": len(add),
                "old_rows_preserved_exactly": len(old),
                "reused_exact_existing_month": reused_existing_month,
                "known_action_unpublished_month_repaired": repaired_unpublished_month,
                "native_current_all_rows": len(legacy),
                "added_by_physical_gate": sorted(set(chosen.symbol) - set(legacy.symbol)),
                "removed_by_physical_gate": sorted(set(legacy.symbol) - set(chosen.symbol)),
                "rank_changes_common": int(
                    (
                        changed.loc[changed._merge == "both", "adv_rank"]
                        != changed.loc[changed._merge == "both", "legacy_adv_rank"]
                    ).sum()
                ),
                "last_bar_before_month_end": int((~active).sum()),
                "post_month_price_factors_from_actual_actions": True,
                "affected_exact_60_row_reconstruction": exact_window,
                "endpoint_rounding_residual_max": float(
                    bridge.loc[active, "endpoint_price_error"].abs().max()
                ),
                "rounding_boundary_check": {
                    "ADV_floor_ambiguous": int(ambiguous_floor.sum()),
                    "ADV_floor_ambiguous_but_original_final_fund_exclusion": excluded_floor_names,
                    "actual_stock_membership_ambiguity": int(effective_floor_ambiguity.sum()),
                    "rank_boundaries_ambiguous": int(ambiguous_rank.sum()),
                    "absolute_price_ambiguous": int(gate_uncertain.sum()),
                    "checked_rank_boundaries": boundaries,
                    "maximum_ADV_dollar_bound": float(chosen.adv_rounding_bound.max()),
                    "closest_ADV_floor_margin_usd": float((chosen.dollar_adv - floor).abs().min())
                    if floor is not None
                    else None,
                },
                "adv_note": (
                    "original 60-row mean in all units, divided by exact post-month price*volume "
                    "action factors; current source price rounding remains explicit"
                ),
                "sha256": digest(dest),
            }
        )
    bridge.to_csv(archive / "price-and-adv-unit-bridge.csv", index=False)
    (view / "current-units-monthly.json").write_text(json.dumps(receipts, indent=2) + "\n")
    print(json.dumps(receipts), flush=True)


def narrow_daily(view):
    """Original narrow-universe keys, same nine price-derived columns and source."""
    import duckdb
    import pandas as pd

    sys.path.insert(0, str(ROOT))
    from open_composer.research.features.universe import universe_union_symbols

    names = sorted(universe_union_symbols(view / "data/features/universe"))
    con = duckdb.connect()
    con.execute("SET memory_limit='200MB'")
    con.execute("SET threads=1")
    con.register("narrow_names", pd.DataFrame({"symbol": names}))
    dest = view / "data/features/daily"
    dest.mkdir(exist_ok=True)
    receipts = []
    for p in sorted((view / "data/features/daily_broad").glob("20*.parquet")):
        q = dest / p.name
        binding = {
            "broad_sha256": digest(p),
            "narrow_union_symbols_sha256": hashlib.sha256(
                json.dumps(sorted(names)).encode()
            ).hexdigest(),
            "columns": DAILY_COLUMNS,
        }
        complete = q.with_suffix(".receipt.json")
        if q.exists():
            if not complete.exists():
                raise ValueError("uncompleted narrow projection retained")
            prior = json.loads(complete.read_text())
            if digest(q) != prior["output_sha256"]:
                raise ValueError("narrow projection changed after completion")
            if prior["binding"] == binding:
                receipts.append({**prior, "reused_without_recomputation": True})
                continue
        temporary = q.with_suffix(".projection.tmp")
        con.execute(
            f"COPY (SELECT d.* FROM read_parquet('{p}') d SEMI JOIN narrow_names n "
            f"USING(symbol)) TO '{temporary}' (FORMAT PARQUET, COMPRESSION ZSTD)"
        )
        os.replace(temporary, q)
        receipts.append(
            {
                "binding": binding,
                "year": int(p.stem),
                "output_sha256": digest(q),
                "broad_sha256": digest(p),
                "narrow_union_count": len(names),
                "keys": "original ever-member narrow universe; no broad fallback",
            }
        )
        complete.write_text(json.dumps(receipts[-1], indent=2) + "\n")
    (view / "current-units-narrow.json").write_text(json.dumps(receipts, indent=2) + "\n")


def load_native(view, script):
    """Run native repository code with explicit private data-path bindings.

    Copied code inside an evidence view is an audit snapshot, never the
    production implementation. Each subprocess imports the installed script.
    """
    import importlib.util

    if script not in NATIVE_SCRIPTS:
        raise ValueError("not a book dependency")
    native_root = Path(os.environ.get("OC_BOOK_NATIVE_CODE_ROOT", str(ROOT))).resolve()
    os.environ["OC_EQUITY_BOOK_DIR"] = str((view / "data/live/equity_book").resolve())
    sys.path.insert(0, str(native_root))
    sys.path.insert(0, str(native_root / "scripts"))
    name = "_current_units_native_" + script
    native_path = native_root / "scripts" / f"{script}.py"
    spec = importlib.util.spec_from_file_location(name, native_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    with (view / "native-code-execution.jsonl").open("a") as stream:
        stream.write(
            json.dumps(
                {
                    "at_utc": datetime.now(UTC).isoformat(),
                    "script": script,
                    "actual_path": str(native_path),
                    "sha256": digest(native_path),
                }
            )
            + "\n"
        )
    native_default = getattr(module, "DEFAULT_DIR", None)
    book_root = (view / "data/live/equity_book").resolve()
    for key, value in list(vars(module).items()):
        if key.startswith("__"):
            continue
        if isinstance(value, Path):
            if isinstance(native_default, Path) and value.is_relative_to(native_default):
                setattr(module, key, book_root / value.relative_to(native_default))
                continue
            # OC_EQUITY_BOOK_DIR is already an explicit data path. The
            # recovery view lives below ROOT; do not rebase that path twice.
            if value.is_relative_to(view):
                continue
            try:
                relative = value.relative_to(native_root)
            except ValueError:
                continue
            setattr(module, key, view / relative)
        elif isinstance(value, str) and value.startswith(str(native_root) + "/data/"):
            setattr(module, key, str(view) + value[len(str(native_root)) :])
    if script == "build_sec_xbrl_fundamentals":
        cache_root = Path(os.environ.get("OC_BOOK_SOURCE_CACHE_ROOT", str(ROOT)))
        module.ZIP_PATH = cache_root / "data/raw/sec_xbrl/companyfacts.zip"
    if script == "collect_alpaca_news_packets":
        # Imported functions resolve paths in their defining module, not in
        # the CLI module whose Path globals were rebound above.
        from open_composer.research.news import collector

        collector.NEWS_PACKETS_ROOT = view / "data/features/news_packets"
        collector.DAILY_ROOT = collector.NEWS_PACKETS_ROOT / "_daily"
    return module


def native_run(view, command, *, spill_bytes=None):
    env = dict(
        os.environ,
        OC_EQUITY_BOOK_DIR=str((view / "data/live/equity_book").resolve()),
        OMP_NUM_THREADS="1",
        OPENBLAS_NUM_THREADS="1",
        MKL_NUM_THREADS="1",
        NUMEXPR_MAX_THREADS="1",
        POLARS_MAX_THREADS="1",
        ARROW_NUM_THREADS="1",
    )
    if spill_bytes is not None:
        env["OC_FORWARD_SPILL_BYTES"] = str(spill_bytes)
    script = Path(command[0]).stem
    argv = [
        sys.executable,
        str(ROOT / "scripts/build_book_v12_current_units.py"),
        "--stage",
        "native",
        "--view-root",
        str(view.resolve()),
        "--native-script",
        script,
        "--native-args",
        *command[1:],
    ]
    print("native: " + repr(argv), flush=True)
    subprocess.run(argv, cwd=view, env=env, check=True)


def release_successful_native_stage(view, name, day):
    """Release only this stage's accepted recomputable native candidates."""
    path = view / f"current-units-{name}.json"
    if not path.exists():
        raise ValueError("native stage has no genuine completion")
    receipt = json.loads(path.read_text())
    output = Path(receipt["output"])
    stage = view / "data/features/_current_stage" / str(day) / name
    if output.is_relative_to(stage) or digest(output) != receipt["sha256"]:
        raise ValueError("composed native output is absent or changed")
    released = []
    for file in sorted(stage.glob("*.parquet")):
        released.append({"path": str(file), "bytes": file.stat().st_size, "sha256": digest(file)})
        file.unlink()
    if released:
        receipt["successful_temporary_native_outputs_released"] = released
        receipt["failed_candidates_or_raw_sources_removed"] = False
        path.write_text(json.dumps(receipt, indent=2) + "\n")
    return released


def parquet_last_date(path, column):
    """Read a scalar cutoff without retaining a historical feature frame."""
    import pyarrow.compute as pc
    import pyarrow.parquet as pq

    values = [
        pc.max(batch.column(0)).as_py()
        for batch in pq.ParquetFile(path).iter_batches(
            batch_size=8192, columns=[column], use_threads=False
        )
    ]
    return max(value for value in values if value is not None)


def compose_short_volume_prefix(old_path, built, dest, date_column):
    """The original old + fresh[date > cutoff] expression, bounded by one batch.

    Read back every written row group against its original input before atomic
    publication. No feature calculation, source refresh or historical rewrite.
    """
    import pandas as pd
    import pyarrow as pa
    import pyarrow.compute as pc
    import pyarrow.parquet as pq

    before = {str(p): digest(p) for p in (old_path, built)}
    old_file, fresh_file = pq.ParquetFile(old_path), pq.ParquetFile(built)
    schema = old_file.schema_arrow
    if not schema.equals(fresh_file.schema_arrow, check_metadata=False):
        raise ValueError("short-volume native feature schema changed; retain inputs")
    cut = parquet_last_date(old_path, date_column)
    temporary = dest.with_suffix(".composed.tmp")
    if temporary.exists():
        raise ValueError("prior short-volume composition retained; reconcile before reuse")

    def chunks():
        for batch in old_file.iter_batches(batch_size=8192, use_threads=False):
            yield pa.Table.from_batches([batch]), "old"
        for batch in fresh_file.iter_batches(batch_size=8192, use_threads=False):
            table = pa.Table.from_batches([batch])
            table = table.filter(pc.greater(table[date_column], pa.scalar(cut)))
            if table.num_rows:
                yield table, "tail"

    rows = {"old": 0, "tail": 0}
    with pq.ParquetWriter(temporary, schema, compression="snappy") as writer:
        for table, kind in chunks():
            writer.write_table(table, row_group_size=8192)
            rows[kind] += table.num_rows
    received = pq.ParquetFile(temporary)
    groups = 0
    for group, (expected, _) in enumerate(chunks()):
        actual = received.read_row_group(group, use_threads=False)
        pd.testing.assert_frame_equal(
            expected.to_pandas().reset_index(drop=True),
            actual.to_pandas().reset_index(drop=True),
            check_exact=True,
        )
        groups += 1
    if received.num_row_groups != groups or received.metadata.num_rows != sum(rows.values()):
        raise ValueError("short-volume composition row count differs")
    if before != {str(p): digest(p) for p in (old_path, built)}:
        raise ValueError("short-volume input changed during composition")
    os.replace(temporary, dest)
    return {
        "input_sha256": before, "old_rows": rows["old"], "new_rows": rows["tail"],
        "old_facts_frozen_through": str(cut), "row_groups_verified_exactly": groups,
        "batch_rows": 8192, "all_rows_read_back": True,
        "expression": "old + fresh.loc[fresh[date_column] > old[date_column].max(), old.columns]",
    }


def dependencies(view, source, name, day):
    """Normal provider refreshes and original feature builders, in private outputs."""
    import pandas as pd

    sys.path.insert(0, str(ROOT / "scripts"))
    import refresh_equity_book_live as refresh

    table = next(t for t in refresh.UPSTREAM if t.name == name)
    if name == "sec_fundamentals_facts":
        from forward_refresh_io import disk_admission, stage_admission

        config = json.loads((ROOT / "config/equity-book-forward.json").read_text())
        config["disk_spill_bound_bytes"] = 512 * 1024**2
        config["version_directory"] = "current-unit-admissions"
        admission = disk_admission(
            view,
            config,
            source_root=view,
            tables=[table],
            live=view / "data/live/equity_book",
            stages=[],
            year=day.year,
            fetch=True,
        )
        current = view / "data/features" / table.output.format(year=day.year)
        stage_admission(view, config, current.stat().st_size if current.exists() else 0)
    stage = view / "data/features/_current_stage" / str(day) / name
    stage.mkdir(parents=True, exist_ok=True)
    prior_outputs = []
    if table.link_prior_years:
        # Match the original run_table contract. Native producers still load
        # their complete issuer/event history and original 2016 calendar, but
        # skip already published prior-year output partitions. Copies keep a
        # producer's possible in-place write isolated from frozen evidence.
        from forward_refresh_io import stage_admission

        source_output = source / "data/features" / table.output.format(year=day.year)
        prior = [
            p
            for p in sorted(source_output.parent.glob("[0-9][0-9][0-9][0-9].parquet"))
            if int(p.stem) < day.year
        ]
        copy_bytes = sum(p.stat().st_size for p in prior if not (stage / p.name).exists())
        limits = json.loads((ROOT / "config/equity-book-forward.json").read_text())
        stage_admission(
            view,
            limits,
            source_output.stat().st_size if source_output.exists() else 0,
            copy_bytes=copy_bytes,
        )
        for saved in prior:
            target = stage / saved.name
            if target.exists() and digest(target) != digest(saved):
                raise ValueError("existing prior-year native candidate changed: " + str(target))
            if not target.exists():
                shutil.copy2(saved, target)
            prior_outputs.append(
                {"source": str(saved), "candidate": str(target), "sha256": digest(target)}
            )
    # No in-place native writer receives an inode shared with the frozen lake.
    writable = []
    if table.in_place:
        output = view / "data/features" / table.output.format(year=day.year)
        writable = [output, *output.parent.glob("*.json")]
        if name == "sec_fundamentals_facts":
            writable += list((view / "data/features/sec_fundamentals/_batches").glob("*"))
            writable += list((view / "data/raw/sec_xbrl").glob("*.json"))
    if name == "news_attention":
        writable += list((view / "data/features/news_packets").rglob("*"))
    if name in ("short_volume_broad", "short_interest", "insider_broad"):
        for group in ("insider", "finra_short_volume", "finra_short_interest"):
            writable += list((view / "data/raw" / group).rglob("*.parquet"))
            for suffix in ("*.json", "*.csv", "*.jsonl"):
                writable += list((view / "data/raw" / group).rglob(suffix))
    detached = detach_outputs(writable)
    old_path = source / "data/features" / table.output.format(year=day.year)
    cut = None
    old = None
    stream_old = old_path.exists() and name == "short_volume_broad"
    if stream_old:
        cut = pd.Timestamp(parquet_last_date(old_path, table.date_col))
    elif old_path.exists() and name not in ("sec_fundamentals_facts", "nsi"):
        old = pd.read_parquet(old_path)
        cut = pd.to_datetime(old[table.date_col]).max()
    values = {
        "year": day.year,
        "tmp": str(stage.resolve()),
        "as_of": day.isoformat(),
        "start": str(
            (cut.date() if cut is not None else day - timedelta(days=14)) - timedelta(days=3)
        ),
        "end": day.isoformat(),
    }

    def command(parts):
        cmd = [x.format(**values) for x in parts]
        if cmd[:3] == ["uv", "run", "python"]:
            cmd = cmd[3:]
        return cmd

    if name == "sec_fundamentals_facts":
        # Exactly the native charging and owner-service reserve; only this
        # facts stage's genuinely enforced DuckDB spill allowance is tighter.
        stage_admission(view, config, old_path.stat().st_size if old_path.exists() else 0)
        (view / "current-units-facts-resource.json").write_text(
            json.dumps(
                {
                    "stage_config": config,
                    "admission": admission,
                    "step_env": {"OC_FORWARD_SPILL_BYTES": str(config["disk_spill_bound_bytes"])},
                    "native_merge": (
                        "build_sec_xbrl_fundamentals.write_facts_from_batches -> "
                        "forward_io_limits.apply_forward_limits"
                    ),
                },
                indent=2,
            )
            + "\n"
        )
        # --force on the original facts builder already streams a fresh bulk
        # download. Do not duplicate that same download as a separate pre-step.
        native_run(view, command(table.build), spill_bytes=config["disk_spill_bound_bytes"])
        stage_admission(
            view,
            config,
            (view / "data/features" / table.output.format(year=day.year)).stat().st_size,
        )
    else:
        for fetch in table.fetch:
            native_run(view, command(fetch))
        for pre in table.pre_build:
            native_run(view, command(pre))
        native_run(view, command(table.build))
    built = (
        (view / "data/features" / table.output.format(year=day.year))
        if table.in_place
        else stage / f"{day.year}.parquet"
    )
    if not built.exists():
        raise ValueError(f"original builder emitted no {name} output")
    streaming_composition = None
    if stream_old:
        dest = view / "data/features" / table.output.format(year=day.year)
        streaming_composition = compose_short_volume_prefix(old_path, built, dest, table.date_col)
    elif old is not None:
        fresh = pd.read_parquet(built)
        price_repair = []
        if name == "short_interest":
            # Keep every published FINRA fact/visibility and original narrow
            # row key. Only its two price-derived columns follow current units.
            reader = load_native(view, "build_short_interest_features")
            for saved in sorted((source / "data/features/short_interest").glob("20*.parquet")):
                saved_year = int(saved.stem)
                if saved_year > day.year:
                    continue
                prefix = pd.read_parquet(saved)
                nonprice = [
                    c for c in prefix.columns if c not in ("adv_shares_63", "short_interest_ratio")
                ]
                adv = reader.load_adv_shares(saved_year, set(prefix.symbol))
                repaired = prefix.drop(columns=["adv_shares_63", "short_interest_ratio"]).merge(
                    adv, on=["symbol", "trade_date"], how="left", validate="one_to_one", sort=False
                )
                repaired["short_interest_ratio"] = (
                    repaired.short_interest_shares
                    / repaired.adv_shares_63.where(repaired.adv_shares_63 > 0)
                )
                repaired = repaired[prefix.columns]
                pd.testing.assert_frame_equal(
                    prefix[nonprice], repaired[nonprice], check_exact=True
                )
                item = {
                    "year": saved_year,
                    "rows": len(prefix),
                    "frozen_nonprice_columns": nonprice,
                    "changed_price_derived_rows": int(
                        (
                            ~prefix.adv_shares_63.eq(repaired.adv_shares_63)
                            & ~(prefix.adv_shares_63.isna() & repaired.adv_shares_63.isna())
                        ).sum()
                    ),
                }
                if saved_year == day.year:
                    old = repaired
                else:
                    historical = view / f"data/features/short_interest/{saved_year}.parquet"
                    tmp = historical.with_suffix(".coherent.tmp")
                    repaired.to_parquet(tmp, index=False)
                    os.replace(tmp, historical)
                    item["sha256"] = digest(historical)
                price_repair.append(item)
        tail = fresh.loc[pd.to_datetime(fresh[table.date_col]) > cut]
        combined = pd.concat([old, tail[old.columns]], ignore_index=True)
        pd.testing.assert_frame_equal(
            old.reset_index(drop=True),
            combined.iloc[: len(old)].reset_index(drop=True),
            check_exact=True,
        )
        dest = view / "data/features" / table.output.format(year=day.year)
        temp = dest.with_suffix(".composed.tmp")
        combined.to_parquet(temp, index=False)
        os.replace(temp, dest)
    else:
        dest = built
    receipt = {
        "table": name,
        "completed_at_utc": datetime.now(UTC).isoformat(),
        "output": str(dest),
        "sha256": digest(dest),
        "old_facts_frozen_through": str(cut) if cut is not None else None,
        "private_writable_paths": detached,
        "native_prior_year_copies": prior_outputs,
        "streaming_prefix_composition": streaming_composition,
        "nsi_note": "price-derived NSI is recomputed from the coherent current source"
        if name == "nsi"
        else None,
        "price_derived_prefix_repair": price_repair
        if old is not None and name == "short_interest"
        else None,
    }
    (view / f"current-units-{name}.json").write_text(json.dumps(receipt, indent=2) + "\n")
    if not table.in_place:
        release_successful_native_stage(view, name, day)


def panel(view, source, declared, day=None):
    """Native prices/attributes, with historical selection metadata frozen."""
    import duckdb
    import pandas as pd

    os.environ["OC_EQUITY_BOOK_DIR"] = str((view / "data/live/equity_book").resolve())
    sys.path.insert(0, str(ROOT))
    sys.path.insert(0, str(ROOT / "scripts"))
    builder = load_native(view, "build_equity_book_panel")
    builder._duck_original = builder._duck
    builder._duck = lambda mem="450MB": builder._duck_original("450MB")
    original = builder.panel_symbols
    # All names read by the old price reader and actual holdings are declared
    # before score selection; new month membership enters by the native pool.
    con = duckdb.connect()
    con.execute("SET memory_limit='200MB'")
    con.execute("SET threads=1")
    reader = set(
        x[0]
        for x in con.execute(
            f"select distinct symbol from "
            f"read_parquet('{source}/data/live/equity_book/prices/20*.parquet')"
        ).fetchall()
    )
    owned = json.loads(declared.read_text()).get("actual_owned_symbols", [])
    reader.update(owned)
    builder.panel_symbols = lambda c: sorted(set(original(c)) | reader)
    frozen_panel = source / "data/live/equity_book/panel"
    if view.resolve() == source.resolve():
        if day is None:
            raise ValueError("working panel update requires explicit decision day")
        cache = view / "data/_current_selection_cache"
        header = cache / "completion.json"
        if header.exists() and json.loads(header.read_text())["decision_day"] == str(day):
            for item in json.loads(header.read_text())["files"]:
                if digest(cache / item["name"]) != item["sha256"]:
                    raise ValueError("selection cache changed")
        else:
            cache.mkdir(parents=True, exist_ok=True)
            files = []
            for path in sorted(frozen_panel.glob("20*.parquet")):
                data = pd.read_parquet(path, columns=["trade_date", "symbol", *FROZEN_SELECTION])
                target = cache / path.name
                tmp = target.with_suffix(".next")
                data.to_parquet(tmp, index=False)
                os.replace(tmp, target)
                files.append({"name": path.name, "sha256": digest(target)})
            header.write_text(
                json.dumps({"decision_day": str(day), "files": files}, indent=2) + "\n"
            )
        frozen_panel = cache
    builder.stage_hygiene(chunk=160)
    builder.stage_panel()
    builder.stage_prices()
    builder.stage_etf()
    raw_parts = list((view / "month-end-raw").glob("*-through-*.parquet"))
    raw_parts += sorted((view / "month-end-raw").glob("raw-single-default-*.parquet"))
    raw_parts += sorted((view / "physical-gates").rglob("raw.parquet"))
    if not raw_parts:
        raise ValueError("new daily absolute price gates require actual raw bars")
    raw = pd.concat(
        [pd.read_parquet(p, columns=["symbol", "timestamp", "close"]) for p in raw_parts],
        ignore_index=True,
    )
    raw["trade_date"] = pd.to_datetime(raw.timestamp, utc=True).dt.tz_localize(None).dt.normalize()
    raw = raw.rename(columns={"close": "physical_close"}).drop_duplicates(
        ["symbol", "trade_date"], keep="last"
    )
    raw = raw[["symbol", "trade_date", "physical_close"]]
    hygiene = pd.read_parquet(view / "data/live/equity_book/panel/_hygiene.parquet")
    calendar = pd.read_parquet(view / "data/live/equity_book/panel/_calendar.parquet")
    assets = pd.read_parquet(view / "data/features/universe/_asset_metadata.parquet")
    funds = set(assets.loc[assets.is_probable_fund_or_etf, "symbol"])
    frozen = []
    physical_gate_changes = []
    price_cols = [
        "open",
        "close",
        "dollar_adv_21",
        "mcap",
        "mcap_source",
        "beta_252_spy",
        "idio_vol_63",
        "vol_21",
        "is_tradeable",
    ]
    for p in sorted(frozen_panel.glob("20*.parquet")):
        target = view / "data/live/equity_book/panel" / p.name
        old = pd.read_parquet(p)
        fresh = pd.read_parquet(target)
        cut = pd.to_datetime(old.trade_date).max()
        keyed = old.drop(columns=price_cols, errors="ignore").merge(
            fresh[["trade_date", "symbol", *price_cols]],
            on=["trade_date", "symbol"],
            how="left",
            validate="one_to_one",
        )
        tail = fresh.loc[pd.to_datetime(fresh.trade_date) > cut]
        if len(tail):
            tail = tail.merge(raw, on=["symbol", "trade_date"], how="left", validate="one_to_one")
            if tail.physical_close.isna().any():
                tail.loc[tail.physical_close.isna()].to_csv(
                    view / "tail-missing-physical-close.csv", index=False
                )
                raise ValueError("new daily pool gate lacks an actual same-day physical close")
            tail = tail.merge(
                hygiene[["symbol", "first_valid_pos"]],
                on="symbol",
                how="left",
                validate="many_to_one",
            ).merge(
                calendar[["trade_date", "pos"]], on="trade_date", how="left", validate="many_to_one"
            )
            history = (tail.pos - tail.first_valid_pos + 1) >= builder.MIN_HISTORY
            eligible = (
                history & (~tail.symbol.isin(funds)) & (tail.physical_close >= builder.MIN_CLOSE)
            )
            for flag, rank in [("in_u3000", builder.U3000_RANK), ("in_p1000", builder.P1000_RANK)]:
                previous = tail[flag].copy()
                tail[flag] = (tail.adv_rank <= rank) & eligible
                changed = tail.loc[
                    tail[flag] != previous,
                    ["trade_date", "symbol", "close", "physical_close", "adv_rank", flag],
                ].copy()
                changed["flag"] = flag
                physical_gate_changes.extend(changed.to_dict("records"))
        for col in FROZEN_SELECTION:
            pd.testing.assert_series_equal(
                old[col].reset_index(drop=True), keyed[col].reset_index(drop=True), check_exact=True
            )
        result = pd.concat(
            [keyed[builder.PANEL_COLUMNS], tail[builder.PANEL_COLUMNS]], ignore_index=True
        )
        result.to_parquet(target, index=False)
        frozen.append(
            {
                "year": int(p.stem),
                "old_rows": len(old),
                "old_keys_and_selection_equal": True,
                "frozen_through": str(cut),
                "price_columns_from_new_view_only": price_cols,
                "missing_current_price_rows": int(keyed.close.isna().sum()),
                "sha256": digest(target),
            }
        )
    (view / "current-units-panel.json").write_text(
        json.dumps(
            {
                "reader_symbols_before_selection": sorted(reader),
                "frozen_metadata": frozen,
                "new_tail_physical_price_gate_changes": physical_gate_changes,
            },
            indent=2,
            default=str,
        )
        + "\n"
    )
    pd.DataFrame(physical_gate_changes).to_csv(
        view / "tail-physical-price-gate-changes.csv", index=False
    )


def risk_signals_themes(view, day):
    """Original 2017 risk initialization and original current M0 signal formulas."""
    import pandas as pd

    native_run(
        view,
        [
            "scripts/build_equity_book_risk.py",
            "--start",
            "2017-01-01",
            "--end",
            str(day),
            "--out",
            str((view / "data/live/equity_book/risk").resolve()),
            "--write-from-year",
            "2024",
        ],
    )
    native_run(
        view, ["scripts/build_equity_book_signals.py", "build", "--years", str(day.year), "--force"]
    )
    alpha = load_native(view, "build_book_v1_alpha")
    from open_composer.research.equity_book.panel import PanelAttributes

    table = alpha.load_year(day.year, PanelAttributes(view / "data/live/equity_book"))
    dest = view / f"data/live/equity_book/alpha/book_v1/themes_{day.year}.parquet"
    detach_outputs([dest])
    table.to_parquet(dest, index=False)
    # M0 is the existing fixed nine-theme equal-weight strategy. It does not
    # consume formation IC to estimate weights; retain the published IC file.
    ic = view / "data/live/equity_book/alpha/book_v1/formation_ic.parquet"
    meta = {
        "completed_at_utc": datetime.now(UTC).isoformat(),
        "risk_initialization_start": "2017-01-01",
        "persisted_risk_years": [2024, 2025, 2026],
        "last_theme_date": str(pd.to_datetime(table.trade_date).max()),
        "theme_sha256": digest(dest),
        "formation_ic_sha256_retained": digest(ic),
        "variant": "M0_U3000",
        "weight_rule": "original fixed equal weighting of nine themes",
        "training_runs": 0,
        "native_code_root": str(ROOT),
    }
    (view / "current-units-risk-signals.json").write_text(json.dumps(meta, indent=2) + "\n")


def physical_sources(view, day, application_day, declared, start):
    """Actual raw daily gates and execution-day action terms, GET requests only."""
    import pandas as pd
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame

    sys.path.insert(0, str(ROOT / "scripts"))
    from fetch_sip_universe import _clients

    names = json.loads(declared.read_text())["symbols"]
    folder = view / "physical-gates" / f"{day}-for-{application_day}"
    folder.mkdir(parents=True, exist_ok=True)
    _, client = _clients()

    def receive(response, *args, **kwargs):
        if response.request.method != "GET":
            raise ValueError("source reader allows GET only")
        with (folder / "http.jsonl").open("a") as f:
            f.write(
                json.dumps(
                    {
                        "url": response.url,
                        "status": response.status_code,
                        "received_at_utc": datetime.now(UTC).isoformat(),
                        "sha256": hashlib.sha256(response.content).hexdigest(),
                    }
                )
                + "\n"
            )
        return response

    client._session.hooks["response"] = [receive]
    frames = []
    pages = []
    for i in range(0, len(names), 100):
        chunk = names[i : i + 100]
        req = StockBarsRequest(
            symbol_or_symbols=chunk,
            timeframe=TimeFrame.Day,
            start=datetime.combine(start, datetime.min.time(), UTC),
            end=datetime.combine(day + timedelta(days=1), datetime.min.time(), UTC),
            feed="sip",
            adjustment="raw",
        )
        frame = client.get_stock_bars(req).df
        if len(frame):
            frames.append(frame.reset_index())
        cursor = None
        while True:
            params = {
                "symbols": ",".join(chunk),
                "start": str(start),
                "end": str(application_day + timedelta(days=90)),
                "limit": 1000,
            }
            if cursor:
                params["page_token"] = cursor
            page = client.get("/corporate-actions", params, api_version="v1")
            pages.append(page)
            cursor = page.get("next_page_token")
            if not cursor:
                break
        if i % 1000 == 0:
            print(f"physical gates/actions {i}/{len(names)}", flush=True)
    raw = pd.concat(frames, ignore_index=True)
    path = folder / "raw.parquet"
    raw.to_parquet(path, index=False)
    actions = folder / "actions.json"
    actions.write_text(json.dumps(pages, indent=2) + "\n")
    receipt = {
        "captured_at_utc": datetime.now(UTC).isoformat(),
        "start": str(start),
        "day": str(day),
        "execution_day": str(application_day),
        "feed": "sip",
        "adjustment": "raw",
        "identity_asof": None,
        "declared_names_sha256": digest(declared),
        "raw_sha256": digest(path),
        "actions_sha256": digest(actions),
        "historical_first_visible_certified": False,
    }
    (folder / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")


def execution_consumer_scope(view, source, declared, day, held_evidence=None):
    """Derive the complete native reader set before scores or targets exist."""
    import duckdb

    con = duckdb.connect()
    con.execute("SET memory_limit='200MB'")
    con.execute("SET threads=1")
    groups = {}
    for label, glob, where in (
        ("published_price_readers", source / "data/live/equity_book/prices/20*.parquet", "true"),
        (
            "native_ever_adv4000",
            view / "data/features/universe_broad/*.parquet",
            f"adv_rank<=4000 AND month_end<=DATE '{day}'",
        ),
    ):
        groups[label] = sorted(
            r[0]
            for r in con.execute(
                f"SELECT DISTINCT symbol FROM read_parquet('{glob}') WHERE {where}"
            ).fetchall()
        )
    groups["actual_held"] = json.loads(declared.read_text()).get("actual_owned_symbols", [])
    if not groups["actual_held"] and held_evidence is not None:
        groups["actual_held"] = sorted(r["symbol"] for r in json.loads(held_evidence.read_text()))
    if not groups["actual_held"]:
        raise ValueError("actual holdings must be declared before execution-unit selection")
    groups["native_etf_legs"] = ["SPY", "SGOV", "BIL"]
    names = sorted(set().union(*(set(v) for v in groups.values())))
    superset = set(json.loads(declared.read_text())["symbols"])
    if set(names) - superset:
        raise ValueError("native consumer absent from predeclared source superset")
    result = {
        "declared_at_utc": datetime.now(UTC).isoformat(),
        "before_target_selection": True,
        "day": str(day),
        "symbols": names,
        "count": len(names),
        "groups": groups,
        "source_superset_count": len(superset),
        "outside_execution_scope": sorted(superset - set(names)),
        "source_declaration_sha256": digest(declared),
        "held_evidence_sha256": digest(held_evidence) if held_evidence else None,
        "scope_formula_sha256": digest(ROOT / "scripts/build_equity_book_panel.py"),
        "monthly_full_cross_section_is_separately_validated": True,
    }
    path = view / "current-units-execution-consumers.json"
    if path.exists():
        prior = json.loads(path.read_text())
        if prior["symbols"] == names and prior["groups"] == groups and prior["day"] == str(day):
            return prior
        retained = view / "execution-consumer-evidence" / (digest(path) + ".json")
        retained.parent.mkdir(exist_ok=True)
        if not retained.exists():
            shutil.copy2(path, retained)
    path.write_text(json.dumps(result, indent=2) + "\n")
    return result


def endpoint_bridge(view, day, application_day):
    """Verify All's current unit against raw dollars and received actual actions."""
    import duckdb
    import pandas as pd

    folder = view / "physical-gates" / f"{day}-for-{application_day}"
    raw = pd.read_parquet(folder / "raw.parquet")
    raw["trade_date"] = pd.to_datetime(raw.timestamp, utc=True).dt.date
    raw = raw.loc[raw.trade_date == day]
    ghost = raw.volume.eq(0) & raw.trade_count.fillna(0).eq(0)
    ghost &= raw.open.eq(raw.high) & raw.high.eq(raw.low) & raw.low.eq(raw.close)
    ghost_names = sorted(raw.loc[ghost, "symbol"].unique())
    raw = raw.loc[~ghost]
    con = duckdb.connect()
    con.execute("SET memory_limit='250MB'")
    con.execute("SET threads=1")
    current = (
        con.execute(
            f"SELECT symbol,open,close,volume FROM "
            f"read_parquet('{view}/data/sip/daily/{day.year}/*.parquet') WHERE cast(timestamp "
            f"as date)=DATE '{day}'"
        )
        .fetchdf()
        .drop_duplicates("symbol")
    )
    paired = current.merge(
        raw[["symbol", "open", "close", "volume"]],
        on="symbol",
        suffixes=("_all", "_raw"),
        validate="one_to_one",
    )
    events = {}
    seen = set()
    known_fix = view / "current-units-known-actions-repair.json"
    repaired = (
        {r["symbol"]: r for r in json.loads(known_fix.read_text())["repairs"]}
        if known_fix.exists()
        else {}
    )
    for page in json.loads((folder / "actions.json").read_text()):
        for kind, rows in page.get("corporate_actions", {}).items():
            for event in rows:
                if event.get("id") in seen:
                    continue
                seen.add(event.get("id"))
                ex = event.get("ex_date")
                if ex and str(day) < ex <= str(application_day):
                    if (
                        "CQP" in repaired
                        and kind == "cash_dividends"
                        and event.get("symbol") == "CQP"
                        and ex == "2026-11-03"
                        and float(event["rate"]) in (0.775, 0.115)
                    ):
                        continue
                    if (
                        "SCCO" in repaired
                        and kind == "cash_dividends"
                        and event.get("symbol") == "SCCO"
                        and ex == "2026-11-03"
                        and float(event["rate"]) == 1.0106
                    ):
                        continue
                    events.setdefault(event.get("symbol"), []).append((kind, event))
    rows = []
    for r in paired.itertuples():
        pf = 1.0
        vf = 1.0
        terms = []
        for kind, event in events.get(r.symbol, []):
            if kind == "cash_dividends":
                pf *= 1 - float(event["rate"]) / float(r.close_raw)
            elif kind in ("forward_splits", "reverse_splits"):
                ratio = float(event["old_rate"]) / float(event["new_rate"])
                pf *= ratio
                vf /= ratio
            elif (
                kind == "stock_dividends"
                and r.symbol == "SCCO"
                and r.symbol in repaired
                and event["ex_date"] == "2026-11-03"
            ):
                ratio = 1 / float(event["rate"])
                pf *= ratio
                vf /= ratio
            elif kind in ("spin_offs", "spinoffs"):
                raise ValueError(f"execution spin-off requires provider factor: {r.symbol}")
            else:
                continue
            terms.append({"kind": kind, "event": event})
        open_error = float(r.open_all - r.open_raw * pf)
        close_error = float(r.close_all - r.close_raw * pf)
        volume_error = float(r.volume_all - r.volume_raw * vf)
        price_tolerance = 0.005051 * max(1, repaired.get(r.symbol, {}).get("price_multiplier", 1))
        ok = (
            abs(open_error) <= price_tolerance
            and abs(close_error) <= price_tolerance
            and abs(volume_error) < 1.00001
        )
        rows.append(
            {
                "symbol": r.symbol,
                "open_raw": r.open_raw,
                "close_raw": r.close_raw,
                "open_all": r.open_all,
                "close_all": r.close_all,
                "postreference_price_factor": pf,
                "postreference_share_factor": vf,
                "open_error_usd": open_error,
                "close_error_usd": close_error,
                "volume_error_current_shares": volume_error,
                "model_share_to_broker_current_share": 1.0,
                "same_unit": bool(ok),
                "events": terms,
            }
        )
    scope_path = view / "current-units-execution-consumers.json"
    if not scope_path.exists():
        raise ValueError(
            "execution consumers must be frozen from native readers before target generation"
        )
    scope = json.loads(scope_path.read_text())
    scope_names = set(scope["symbols"])
    missing_actual_raw = (scope_names & set(raw.symbol)) - set(paired.symbol)
    if missing_actual_raw:
        raise ValueError(
            "received real consumer endpoint absent from current All: "
            + repr(sorted(missing_actual_raw))
        )
    errors = [r for r in rows if r["symbol"] in scope_names and not r["same_unit"]]
    result = {
        "checked_at_utc": datetime.now(UTC).isoformat(),
        "decision_day": str(day),
        "execution_day": str(application_day),
        "matched_names": len(rows),
        "consumer_scope_sha256": digest(scope_path),
        "execution_consumer_names": len(scope_names),
        "matched_execution_consumer_names": sum(r["symbol"] in scope_names for r in rows),
        "native_ghost_placeholder_names": ghost_names,
        "consumer_names_without_current_real_raw_bar": sorted(scope_names - set(raw.symbol)),
        "superset_diagnostic_unexplained_names": [r["symbol"] for r in rows if not r["same_unit"]],
        "unexplained_names": [r["symbol"] for r in errors],
        "all_adjustment_semantics": (
            "split price+volume; cash dividend/spin-off price; identity asof is not a "
            "price-vintage cutoff"
        ),
        "broker_existing_qty_changed_by_view": False,
        "cash_or_dividends_booked_by_view": False,
        "rows": rows,
    }
    (view / "current-units-execution-bridge.json").write_text(json.dumps(result, indent=2) + "\n")
    if errors:
        raise ValueError("execution-day source unit bridge refused; see named source residuals")
    print(json.dumps({k: v for k, v in result.items() if k != "rows"}), flush=True)


def stage_raw_only(source, context, destination):
    """A temporary source view; no feature tree or bulk ZIP is copied."""
    if destination.exists():
        raise ValueError("previous unfinished source attempt retained")
    destination.mkdir(parents=True)
    bindings = []
    for year in range(2016, 2027):
        root = context if year >= 2025 else source
        for group in ("data/sip/daily", "data/sip-delisted/by_year"):
            for path in sorted((root / group / str(year)).glob("*.parquet")):
                relative = path.relative_to(root)
                target = destination / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                os.link(path, target)
                bindings.append(
                    {
                        "path": str(relative),
                        "source": str(path),
                        "sha256": digest(path),
                        "bytes": path.stat().st_size,
                    }
                )
    meta = {
        "created_at_utc": datetime.now(UTC).isoformat(),
        "source_root": str(source),
        "corrected_two_year_context": str(context),
        "source_bindings": bindings,
        "price_adjustment": "all",
        "historical_first_visible_certified": False,
        "old_published_price_fallback": False,
        "frozen_selection_columns": FROZEN_SELECTION,
    }
    (destination / "current-units-source.json").write_text(json.dumps(meta, indent=2) + "\n")


def native_partition_files(root, years, names):
    """Pass only actual name/SPY partitions to the unchanged native builder."""
    import duckdb

    con = duckdb.connect()
    con.execute("SET memory_limit='150MB'")
    con.execute("SET threads=1")
    paths = []
    for year in years:
        for group in ("data/sip/daily", "data/sip-delisted/by_year"):
            files = list((root / group / str(year)).glob("*.parquet"))
            if not files:
                continue
            con.register("requested", __import__("pandas").DataFrame({"symbol": names}))
            paths.extend(
                Path(r[0])
                for r in con.execute(
                    f"SELECT DISTINCT filename FROM "
                    f"read_parquet('{root / group / str(year)}/*.parquet',filename=true) WHERE "
                    f"symbol IN (SELECT symbol FROM requested) ORDER BY filename"
                ).fetchall()
            )
    con.close()
    return [str(p) for p in dict.fromkeys(paths)]


def replace_reader_link(source, target):
    """Atomically replace a reader without colliding with prior attempt links.

    rename(source, target) is a no-op when both names share an inode. A private
    temporary directory removes its leftover link after that no-op as well.
    Existing failed-attempt paths are never reused or removed here.
    """
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".source-next-", dir=target.parent) as work:
        temporary = Path(work) / target.name
        os.link(source, temporary)
        os.replace(temporary, target)


def publish_incremental_daily_sources(view, new_source, results):
    """Receive completed projections, then publish the actual raw reader links."""
    old_meta = json.loads((view / "current-units-source.json").read_text())
    new_meta = json.loads((new_source / "current-units-source.json").read_text())
    old_paths = {item["path"] for item in old_meta["source_bindings"]}
    new_paths = {item["path"] for item in new_meta["source_bindings"]}
    for item in new_meta["source_bindings"]:
        replace_reader_link(new_source / item["path"], view / item["path"])
    for relative in old_paths - new_paths:
        (view / relative).unlink()
    (view / "current-units-source.json").write_bytes(
        (new_source / "current-units-source.json").read_bytes()
    )
    (view / "current-units-known-actions-repair.json").write_bytes(
        (new_source / "current-units-known-actions-repair.json").read_bytes()
    )
    (view / "current-units-incremental.json").write_text(json.dumps(results, indent=2) + "\n")


def incremental_daily(view, new_source, declared, old_declared, day, *, resource_config=None):
    """Reuse complete years; update only actual changed names under native formulas."""
    import duckdb
    import pandas as pd

    from open_composer.research.features.daily_features import build_daily_features

    old_meta = json.loads((view / "current-units-source.json").read_text())
    new_meta = json.loads((new_source / "current-units-source.json").read_text())
    old_map = {r["path"]: r for r in old_meta["source_bindings"]}
    new_map = {r["path"]: r for r in new_meta["source_bindings"]}
    old_names = set(json.loads(old_declared.read_text())["symbols"])
    names = set(json.loads(declared.read_text())["symbols"])
    con = duckdb.connect()
    con.execute("SET memory_limit='250MB'")
    con.execute("SET threads=1")
    from forward_io_limits import apply_forward_limits

    apply_forward_limits(con)
    temporary_directory = view / "data/_duckdb_tmp"
    temporary_directory.mkdir(parents=True, exist_ok=True)
    con.execute(f"SET temp_directory='{temporary_directory}'")
    changed_by_year = {}
    import pyarrow.parquet as pq

    schema_changed = set()
    for year in range(2016, day.year + 1):
        paths = [
            p
            for p in set(old_map) | set(new_map)
            if f"/{year}/" in p
            and old_map.get(p, {}).get("sha256") != new_map.get(p, {}).get("sha256")
        ]
        left = [str(view / p) for p in paths if p in old_map]
        right = [str(new_source / p) for p in paths if p in new_map]

        def schemas(files):
            return {
                tuple((field.name, str(field.type)) for field in pq.ParquetFile(path).schema_arrow)
                for path in files
            }

        if schemas(left) != schemas(right):
            schema_changed.add(year)
        for path in left:
            relative = str(Path(path).relative_to(view))
            if digest(path) != old_map[relative]["sha256"]:
                raise ValueError("old completed source changed before update")

        def sql(files):
            fields = [
                "symbol",
                "timestamp",
                "open",
                "high",
                "low",
                "close",
                "volume",
                "trade_count",
            ]
            if not files:
                return (
                    "SELECT "
                    + ",".join(
                        "NULL::"
                        + (
                            "VARCHAR"
                            if c == "symbol"
                            else "TIMESTAMPTZ"
                            if c == "timestamp"
                            else "DOUBLE"
                        )
                        + " "
                        + c
                        for c in fields
                    )
                    + " WHERE false"
                )
            available = {
                r[0]
                for r in con.execute(
                    f"SELECT * FROM read_parquet({files!r},union_by_name=true) LIMIT 0"
                ).description
            }
            columns = ",".join(c if c in available else "NULL::DOUBLE " + c for c in fields)
            return f"SELECT {columns} FROM read_parquet({files!r},union_by_name=true)"

        delta = (
            con.execute(
                f"SELECT DISTINCT symbol FROM (({sql(left)} EXCEPT ALL {sql(right)}) UNION ALL "
                f"({sql(right)} EXCEPT ALL {sql(left)}))"
            ).fetchall()
            if paths
            else []
        )
        changed_by_year[year] = set(r[0] for r in delta)
    results = []
    for year in range(2016, day.year + 1):
        dest = view / f"data/features/daily_broad/{year}.parquet"
        receipt = dest.with_suffix(".receipt.json")
        if not dest.exists() or not receipt.exists():
            raise ValueError("incremental source requires actual prior completion")
        prior = json.loads(receipt.read_text())
        binding = prior["binding"]
        if prior["output_sha256"] != digest(dest) or binding["formula_sha256"] != digest(
            ROOT / "open_composer/research/features/daily_features.py"
        ):
            raise ValueError("cannot reuse changed output/formula")
        hygiene = binding.get("price_hygiene_sha256")
        if hygiene is None:
            snapshot = view / "open_composer/research/features/price_hygiene.py"
            if not snapshot.exists():
                raise ValueError("old hygiene formula evidence missing")
            hygiene = digest(snapshot)
        if hygiene != digest(ROOT / "open_composer/research/features/price_hygiene.py"):
            raise ValueError("native ghost formula changed; reuse refused")
        if binding["declared_symbols_sha256"] != digest(old_declared):
            raise ValueError("old declaration does not match genuine completion")
        expected = [
            {k: r[k] for k in ("path", "sha256", "bytes")}
            for r in old_meta["source_bindings"]
            if any(f"/{y}/" in r["path"] for y in range(max(2016, year - 1), year + 1))
        ]
        actual = [{k: r[k] for k in ("path", "sha256", "bytes")} for r in binding["input_bindings"]]
        if sorted(expected, key=lambda r: r["path"]) != sorted(actual, key=lambda r: r["path"]):
            raise ValueError("old completion source binding differs")
        affected = set(names ^ old_names)
        for y in range(max(2016, year - 1), year + 1):
            affected.update(changed_by_year[y])
            if y in schema_changed:
                affected.update(names | old_names)
        if "SPY" in affected:
            affected = set(names) | old_names
        native_names = sorted((affected & names) | {"SPY"})
        new_binding = daily_binding(new_source, declared, year)
        old_sha = digest(dest)
        if affected:
            if resource_config is not None:
                from forward_refresh_io import stage_admission

                stage_admission(view, resource_config, dest.stat().st_size)
            partitions = native_partition_files(
                new_source, range(max(2016, year - 1), year + 1), native_names
            )
            temporary = dest.with_suffix(".increment-native.tmp")
            build_daily_features(
                partitions,
                native_names,
                memory_limit="350MB",
                temp_directory=str(view / "data/_duckdb_tmp"),
                output_parquet=temporary,
                output_year=year,
                threads=1,
            )
            con.register("affected", pd.DataFrame({"symbol": sorted(affected)}))
            columns = ",".join(DAILY_COLUMNS)
            composed = dest.with_suffix(".increment-composed.tmp")
            con.execute(
                f"COPY (SELECT * FROM read_parquet('{dest}') WHERE symbol NOT IN (SELECT "
                f"symbol FROM affected) UNION ALL SELECT {columns} FROM "
                f"read_parquet('{temporary}') WHERE symbol IN (SELECT symbol FROM affected) "
                f"AND trade_date<=DATE '{day}' ORDER BY symbol,trade_date) TO '{composed}' "
                f"(FORMAT PARQUET,COMPRESSION ZSTD)"
            )
            # The unchanged rows are copied directly from the genuine old
            # projection; a native result never substitutes them.
            os.replace(composed, dest)
            temporary.unlink()
            if resource_config is not None:
                stage_admission(view, resource_config, dest.stat().st_size)
        result = {
            "binding": new_binding,
            "output_sha256": digest(dest),
            "completed_at_utc": datetime.now(UTC).isoformat(),
            "rows": con.execute(f"select count(*) from read_parquet('{dest}')").fetchone()[0],
            "prior_output_sha256": old_sha,
            "reused_without_recomputation": not bool(affected),
            "actual_changed_input_symbols": sorted(affected),
            "unchanged_rows_copied_directly": True,
            "price_source_metadata_paths_are_provenance_not_formula_input": True,
        }
        receipt.write_text(json.dumps(result, indent=2) + "\n")
        results.append({"year": year, **result})
        print(
            json.dumps(
                {"incremental_year": year, "affected": len(affected), "reused": not bool(affected)}
            ),
            flush=True,
        )
    # Only now exchange the actual raw reader inodes. Existing source snapshots
    # and the first recovery's raw-before2025/accepted context remain untouched.
    publish_incremental_daily_sources(view, new_source, results)
    return results


KNOWN_ACTIONS = {
    "CQP": {
        "cash": 0.89,
        "shares": 1.0,
        "raw_close": 64.51,
        "vendor_cash": [0.115, 0.775, 0.89],
        "source": "https://www.sec.gov/Archives/edgar/data/1383650/000138365026000040/cqp20263rdqtrerex991.htm",
    },
    "SCCO": {
        "cash": 1.30,
        "shares": 1.0106,
        "raw_close": 179.36,
        "vendor_cash": [1.0106, 1.30],
        "source": "https://www.sec.gov/Archives/edgar/data/1001838/000110465926117588/scco-20261020x8k.htm",
    },
}


def known_action_state(symbol, raw_open, raw_close, raw_volume, all_open, all_close, all_volume):
    """Classify the two proved 2026-11-03 source defects; no guessed third state."""
    spec = KNOWN_ACTIONS[symbol]
    if abs(raw_close - spec["raw_close"]) > 1e-10:
        raise ValueError("proved raw anchor changed")
    vendor = 1.0
    for rate in spec["vendor_cash"]:
        vendor *= 1 - rate / raw_close
    correct = (1 - spec["cash"] / raw_close) / spec["shares"]

    def matches(price_factor, volume_factor):
        return (
            abs(all_open - raw_open * price_factor) <= 0.005051
            and abs(all_close - raw_close * price_factor) <= 0.005051
            and abs(all_volume - raw_volume * volume_factor) < 1.00001
        )

    if matches(vendor, 1):
        classification = "vendor_known_misadjustment"
        price_multiplier = correct / vendor
        volume_multiplier = spec["shares"]
    elif matches(correct, spec["shares"]):
        classification = "vendor_already_correct"
        price_multiplier = volume_multiplier = 1.0
    else:
        raise ValueError("known action has third source state; repair refused")
    return {
        "classification": classification,
        "vendor_price_factor": vendor,
        "correct_price_factor": correct,
        "correct_volume_factor": spec["shares"],
        "price_multiplier": price_multiplier,
        "volume_multiplier": volume_multiplier,
    }


def transform_known_action(frame, symbol, price_multiplier, volume_multiplier):
    """Only the named symbol before the actual ex-date; leave E+ bars intact."""
    import numpy as np
    import pandas as pd

    out = frame.copy()
    mask = out.symbol.eq(symbol) & (
        pd.to_datetime(out.timestamp, utc=True) < pd.Timestamp("2026-11-03", tz="UTC")
    )
    for column in ("open", "high", "low", "close", "vwap"):
        if column in out:
            out.loc[mask, column] *= price_multiplier
    if volume_multiplier != 1:
        out.loc[mask, "volume"] = np.floor(out.loc[mask, "volume"] * volume_multiplier)
    pd.testing.assert_frame_equal(frame.loc[~mask], out.loc[~mask], check_exact=True)
    residual = (frame.loc[mask, "volume"] * volume_multiplier - out.loc[mask, "volume"]).abs()
    if len(residual) and residual.max() >= 1.00001:
        raise ValueError("share-volume conversion exceeded source rounding bound")
    return out, mask, float(residual.max()) if len(residual) else 0.0


def validate_known_action_signature(symbol, classification, cash, stocks):
    """Accept only the two proved provider signatures, conditional on actual bars."""
    spec = KNOWN_ACTIONS[symbol]
    if symbol == "SCCO" and (len(stocks) != 1 or float(stocks[0]["rate"]) != 1.0106):
        raise ValueError("stock-distribution signature changed")
    observed = sorted(float(e["rate"]) for e in cash)
    allowed = [spec["vendor_cash"]]
    if classification == "vendor_already_correct":
        allowed.append([spec["cash"]])
    elif classification != "vendor_known_misadjustment":
        raise ValueError("unknown source classification")
    if observed not in allowed:
        raise ValueError("source action signature inconsistent with classified bars")


def repair_known_execution_actions(view, declared, day):
    """Apply only the two issuer-proved current source corrections, then native nine columns."""
    import duckdb
    import pandas as pd
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame

    sys.path.insert(0, str(ROOT))
    sys.path.insert(0, str(ROOT / "scripts"))
    from fetch_sip_universe import _clients

    from open_composer.research.features.daily_features import build_daily_features

    con = duckdb.connect()
    con.execute("SET memory_limit='200MB'")
    con.execute("SET threads=1")
    completed = view / "current-units-known-actions-repair.json"
    if completed.exists():
        prior = json.loads(completed.read_text())
        for item in prior["private_source_outputs"]:
            if digest(view / item["path"]) != item["sha256"]:
                raise ValueError("completed private correction changed")
        return prior
    folder = view / "known-action-source-repair"
    folder.mkdir(exist_ok=True)
    _, client = _clients()

    def receive(response, *args, **kwargs):
        if response.request.method != "GET":
            raise ValueError("source GET only")
        with (folder / "http.jsonl").open("a") as stream:
            stream.write(
                json.dumps(
                    {
                        "url": response.url,
                        "status": response.status_code,
                        "captured_at_utc": datetime.now(UTC).isoformat(),
                        "sha256": hashlib.sha256(response.content).hexdigest(),
                    }
                )
                + "\n"
            )
        return response

    client._session.hooks["response"] = [receive]
    raw_path = folder / "anchor-raw.parquet"
    if not raw_path.exists():
        client.get_stock_bars(
            StockBarsRequest(
                symbol_or_symbols=sorted(KNOWN_ACTIONS),
                timeframe=TimeFrame.Day,
                start=datetime(2026, 11, 2, tzinfo=UTC),
                end=datetime(2026, 11, 3, tzinfo=UTC),
                feed="sip",
                adjustment="raw",
            )
        ).df.reset_index().to_parquet(raw_path, index=False)
    action_path = folder / "provider-actions.json"
    if not action_path.exists():
        page = client.get(
            "/corporate-actions",
            {
                "symbols": ",".join(sorted(KNOWN_ACTIONS)),
                "start": "2026-10-01",
                "end": "2026-12-31",
                "limit": 1000,
            },
            api_version="v1",
        )
        if page.get("next_page_token"):
            raise ValueError("named action page incomplete")
        action_path.write_text(json.dumps(page, indent=2) + "\n")
    actions = json.loads(action_path.read_text())["corporate_actions"]
    raw = pd.read_parquet(raw_path).set_index("symbol")
    states = []
    for symbol, spec in KNOWN_ACTIONS.items():
        cash = [
            e
            for e in actions.get("cash_dividends", [])
            if e.get("symbol") == symbol and e.get("ex_date") == "2026-11-03"
        ]
        stocks = [
            e
            for e in actions.get("stock_dividends", [])
            if e.get("symbol") == symbol and e.get("ex_date") == "2026-11-03"
        ]
        row = raw.loc[symbol]
        values = con.execute(
            f"select open,close,volume from "
            f"read_parquet('{view}/data/sip/daily/2026/*.parquet') where symbol='{symbol}' and "
            f"cast(timestamp as date)=DATE '2026-11-02'"
        ).fetchall()
        if len(values) != 1:
            raise ValueError("actual current all anchor missing/duplicated")
        state = known_action_state(
            symbol, float(row.open), float(row.close), float(row.volume), *values[0]
        )
        validate_known_action_signature(symbol, state["classification"], cash, stocks)
        actual_close = float(values[0][1])
        corrected = actual_close * state["price_multiplier"]
        states.append(
            {
                "symbol": symbol,
                **state,
                "issuer_SEC_source": spec["source"],
                "cash_total_usd": spec["cash"],
                "stock_distribution_ratio": spec["shares"],
                "provider_cash_events": cash,
                "provider_stock_events": stocks,
                "actual_raw_anchor": float(row.close),
                "actual_all_anchor_before": actual_close,
                "corrected_all_anchor": corrected,
                "no_market_move_reference": float(row.close) * state["correct_price_factor"],
                "rounding_error_usd": corrected - float(row.close) * state["correct_price_factor"],
                "half_cent_bound_usd": 0.005051 * state["price_multiplier"],
                "unfixed_no_market_move_false_return": float(row.close)
                * state["correct_price_factor"]
                / actual_close
                - 1,
            }
        )
    meta_path = view / "current-units-source.json"
    meta = json.loads(meta_path.read_text())
    original_meta = folder / "source-manifest-before.json"
    if original_meta.exists():
        raise ValueError("incomplete action correction retained; reconcile named progress")
    original_meta.write_bytes(meta_path.read_bytes())
    needs = [s for s in states if s["classification"] == "vendor_known_misadjustment"]
    outputs = []
    if needs:
        symbols = ",".join("'" + s["symbol"] + "'" for s in needs)
        files = con.execute(
            f"select distinct filename from "
            f"read_parquet('{view}/data/sip/daily/20*/*.parquet',filename=true) where symbol "
            f"in ({symbols})"
        ).fetchall()
        for (name,) in files:
            path = Path(name)
            relative = path.relative_to(view)
            original = folder / "original-all" / relative
            original.parent.mkdir(parents=True, exist_ok=True)
            os.link(path, original)
            frame = pd.read_parquet(path)
            fixed = frame.copy()
            changes = []
            for state in needs:
                fixed, mask, residual = transform_known_action(
                    fixed, state["symbol"], state["price_multiplier"], state["volume_multiplier"]
                )
                if mask.any():
                    changes.append(
                        {
                            "symbol": state["symbol"],
                            "rows": int(mask.sum()),
                            "share_volume_rounding_max": residual,
                        }
                    )
            unaffected = ~frame.symbol.isin([s["symbol"] for s in needs])
            pd.testing.assert_frame_equal(
                frame.loc[unaffected], fixed.loc[unaffected], check_exact=True
            )
            tmp = path.with_suffix(".known-actions.tmp")
            fixed.to_parquet(tmp, index=False)
            item = {
                "path": str(relative),
                "original_all": str(original),
                "original_sha256": digest(original),
                "sha256": digest(tmp),
                "changed_symbols": changes,
                "other_symbols_exactly_preserved": True,
            }
            os.replace(tmp, path)
            outputs.append(item)
            for binding in meta["source_bindings"]:
                if binding["path"] == str(relative):
                    binding.setdefault("upstream_sha256_before_action_repairs", binding["sha256"])
                    binding.update(sha256=item["sha256"], bytes=path.stat().st_size)
            (folder / "source-file-progress.json").write_text(json.dumps(outputs, indent=2) + "\n")
    meta["known_action_repairs"] = states
    meta_path.write_text(json.dumps(meta, indent=2) + "\n")
    proof = {
        "completed_at_utc": datetime.now(UTC).isoformat(),
        "repairs": states,
        "private_source_outputs": outputs,
        "raw_anchor_sha256": digest(raw_path),
        "provider_actions_sha256": digest(action_path),
        "original_manifest_sha256": digest(original_meta),
        "E_and_later_bars_unchanged": True,
        "broker_qty_writes": 0,
        "broker_cash_writes": 0,
        "no_market_move_reference_is_scenario_not_actual_E_return": True,
        "stock_dividend_payable_day": "2026-11-19",
        "original_broker_state_is_authoritative": True,
        "native_daily_recomputations": [],
    }
    for year in range(2016, day.year + 1):
        dest = view / f"data/features/daily_broad/{year}.parquet"
        if not dest.exists() or not needs:
            continue
        receipt = dest.with_suffix(".receipt.json")
        previous = dest.with_suffix(".before-known-actions.receipt.json")
        if not receipt.exists():
            raise ValueError("affected rebuild requires genuine prior completion")
        previous.write_bytes(receipt.read_bytes())
        globs = [
            str(view / f"{g}/{y}/*.parquet")
            for y in range(max(2016, year - 1), year + 1)
            for g in ("data/sip/daily", "data/sip-delisted/by_year")
            if list((view / g / str(y)).glob("*.parquet"))
        ]
        native = folder / f"native-{year}.parquet"
        build_daily_features(
            globs,
            [s["symbol"] for s in needs] + ["SPY"],
            memory_limit="350MB",
            temp_directory=str(view / "data/_duckdb_tmp"),
            output_parquet=native,
            output_year=year,
            threads=1,
        )
        temporary = dest.with_suffix(".known-actions-composed.tmp")
        columns = ",".join(DAILY_COLUMNS)
        con.execute(
            f"COPY (SELECT * FROM read_parquet('{dest}') WHERE symbol NOT IN ({symbols}) UNION "
            f"ALL SELECT {columns} FROM read_parquet('{native}') WHERE symbol IN ({symbols}) "
            f"ORDER BY symbol,trade_date) TO '{temporary}' (FORMAT PARQUET,COMPRESSION ZSTD)"
        )
        difference = con.execute(
            f"SELECT count(*) FROM ((SELECT * FROM read_parquet('{dest}') WHERE symbol NOT IN "
            f"({symbols}) EXCEPT ALL SELECT * FROM read_parquet('{temporary}') WHERE symbol "
            f"NOT IN ({symbols})) UNION ALL (SELECT * FROM read_parquet('{temporary}') WHERE "
            f"symbol NOT IN ({symbols}) EXCEPT ALL SELECT * FROM read_parquet('{dest}') WHERE "
            f"symbol NOT IN ({symbols})))"
        ).fetchone()[0]
        if difference:
            raise ValueError("named action repair changed another symbol daily row")
        old_sha = digest(dest)
        os.replace(temporary, dest)
        result = {
            "binding": daily_binding(view, declared, year),
            "output_sha256": digest(dest),
            "prior_completion": str(previous),
            "prior_output_sha256": old_sha,
            "completed_at_utc": datetime.now(UTC).isoformat(),
            "rows": con.execute(f"select count(*) from read_parquet('{dest}')").fetchone()[0],
            "recomputed_symbols": [s["symbol"] for s in needs],
            "unaffected_symmetric_difference_rows": difference,
        }
        receipt.write_text(json.dumps(result, indent=2) + "\n")
        proof["native_daily_recomputations"].append({"year": year, **result})
        (folder / "daily-progress.json").write_text(
            json.dumps(proof["native_daily_recomputations"], indent=2) + "\n"
        )
        print(
            json.dumps({"affected_native_year": year, "unaffected_difference": difference}),
            flush=True,
        )
    completed.write_text(json.dumps(proof, indent=2) + "\n")
    print(json.dumps(states), flush=True)
    return proof


def main():
    ap = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    ap.add_argument("--source-root", type=Path, default=ROOT)
    ap.add_argument("--view-root", type=Path, required=True)
    ap.add_argument("--source-context", type=Path)
    ap.add_argument("--declared-symbols", type=Path)
    ap.add_argument(
        "--stage",
        choices=(
            "bootstrap",
            "daily",
            "monthly",
            "narrow",
            "dependency",
            "panel",
            "risk-signals",
            "physical",
            "bridge",
            "known-actions-repair",
            "native",
        ),
        required=True,
    )
    ap.add_argument("--credentials-root", type=Path, default=ROOT)
    ap.add_argument("--month-end", type=date.fromisoformat, default=date(2026, 10, 30))
    ap.add_argument("--application-day", type=date.fromisoformat, default=date(2026, 11, 3))
    ap.add_argument("--day", type=date.fromisoformat, default=date(2026, 11, 2))
    ap.add_argument("--start", type=date.fromisoformat, default=date(2026, 10, 17))
    ap.add_argument("--table")
    ap.add_argument("--native-script", choices=sorted(NATIVE_SCRIPTS))
    ap.add_argument("--native-args", nargs=argparse.REMAINDER, default=[])
    ap.add_argument("--years", type=int, nargs="+", default=list(range(2016, 2027)))
    args = ap.parse_args()
    from dotenv import load_dotenv

    load_dotenv(args.credentials_root / ".env", override=False)
    os.environ["OC_BOOK_SOURCE_CACHE_ROOT"] = str(args.credentials_root.resolve())
    if args.stage == "bootstrap":
        bootstrap(args.source_root, args.view_root, args.source_context)
    if args.stage == "daily":
        daily(args.view_root, args.declared_symbols, args.years)
    if args.stage == "monthly":
        monthly(args.view_root, args.credentials_root, args.month_end, args.application_day)
    if args.stage == "narrow":
        narrow_daily(args.view_root)
    if args.stage == "dependency":
        dependencies(args.view_root, args.source_root, args.table, args.day)
    if args.stage == "panel":
        panel(args.view_root, args.source_root, args.declared_symbols, args.day)
    if args.stage == "risk-signals":
        risk_signals_themes(args.view_root, args.day)
    if args.stage == "physical":
        physical_sources(
            args.view_root, args.day, args.application_day, args.declared_symbols, args.start
        )
    if args.stage == "known-actions-repair":
        repair_known_execution_actions(args.view_root, args.declared_symbols, args.day)
    if args.stage == "bridge":
        endpoint_bridge(args.view_root, args.day, args.application_day)
    if args.stage == "native":
        module = load_native(args.view_root, args.native_script)
        sys.argv = [str(ROOT / "scripts" / f"{args.native_script}.py"), *args.native_args]
        result = module.main()
        if isinstance(result, int):
            raise SystemExit(result)


if __name__ == "__main__":
    main()
