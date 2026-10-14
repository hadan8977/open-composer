# ruff: noqa: E501
"""One bounded local source/connection audit. No fitting, network or portfolio returns."""

from __future__ import annotations

import csv
import hashlib
import json
import os
import resource
import signal
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

CPU_START = time.process_time()
ROOT = Path("/root/codex-test/open-composer")
OUT = Path(__file__).resolve().parent
AUDIT_YEARS = (2016, 2020, 2023, 2026)
AUDIT_DATES = ("2016-01-29", "2020-01-31", "2023-01-31", "2026-01-30")
FEATURE_ROOTS = (
    "daily_broad",
    "osap_price_broad",
    "sec_fundamentals_daily",
    "labels_broad",
    "alpha101_broad",
    "alpha191_broad",
    "alpha158",
    "intraday_daily",
    "reversal_trend_broad",
    "short_volume_broad",
)


def utc():
    return datetime.now(UTC).isoformat()


def save(name, value):
    path = OUT / name
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, default=str, allow_nan=False) + "\n"
    )
    temporary.replace(path)


def full_sha(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sql_path(path):
    return "'" + str(path).replace("'", "''") + "'"


def read_table(paths):
    return "read_parquet([" + ",".join(sql_path(p) for p in paths) + "],union_by_name=true)"


def main():
    wall_start = time.monotonic()
    assert Path.cwd() == ROOT
    state = json.loads((OUT / "current-state.json").read_text())
    prior_cpu = state.get("prior_numeric_attempt_CPU_seconds", 0)
    process_cap = min(540, int(600 - 50 - prior_cpu) - 5)
    assert process_cap > 0
    resource.setrlimit(resource.RLIMIT_CPU, (process_cap, process_cap + 5))
    state.update(status="running_single_local_numeric_audit", started_at_utc=utc())
    save("current-state.json", state)
    sys.path.insert(0, str(ROOT))
    import duckdb
    import pyarrow.parquet as pq

    con = duckdb.connect()
    con.execute("SET threads=1")
    con.execute("SET memory_limit='320MB'")
    con.execute("SET preserve_insertion_order=false")
    con.execute(f"SET temp_directory={sql_path(OUT / '_duck_tmp')}")
    con.execute("SET max_temp_directory_size='2GB'")
    con.execute("SET TimeZone='UTC'")
    failures, inputs, schemas, queries = [], {}, {}, []
    if state.get("same_scope_recovery"):
        for item in json.loads((OUT / "input-bindings.json").read_text()):
            if (ROOT / item["path"]).stat().st_mtime_ns == item["mtime_ns"]:
                inputs[item["path"]] = item
    parsed_rows = 0

    def bind(path, payload_read=False):
        key = str(path.relative_to(ROOT))
        if key not in inputs:
            st = path.stat()
            with path.open("rb") as handle:
                handle.seek(-8, os.SEEK_END)
                trailer = handle.read(8)
                length = int.from_bytes(trailer[:4], "little")
                assert trailer[4:] == b"PAR1"
                handle.seek(-8 - length, os.SEEK_END)
                footer = handle.read(length) + trailer
            inputs[key] = {
                "path": key,
                "bytes": st.st_size,
                "mtime_ns": st.st_mtime_ns,
                "footer_sha256": hashlib.sha256(footer).hexdigest(),
                "footer_bytes": len(footer),
                "full_file_sha256": None,
                "hash_scope": "Parquet footer; full hash deferred unless value pages read",
                "value_pages_read": False,
            }
        if payload_read and not inputs[key]["value_pages_read"]:
            inputs[key]["full_file_sha256"] = full_sha(path)
            inputs[key]["value_pages_read"] = True
            inputs[key]["hash_scope"] = "full file"
        return inputs[key]

    def schema(path):
        key = str(path.relative_to(ROOT))
        if key in schemas:
            return schemas[key]["columns"]
        bind(path)
        pf = pq.ParquetFile(path)
        columns = pf.schema_arrow.names
        schemas[key] = {
            "path": key,
            "columns": columns,
            "types": {f.name: str(f.type) for f in pf.schema_arrow},
            "rows": pf.metadata.num_rows,
            "row_groups": pf.metadata.num_row_groups,
            "key_value_metadata_keys": list((pf.metadata.metadata or {}).keys()),
            "permanent_id_fields": [
                c
                for c in columns
                if c.lower() in ("permno", "permco", "security_id", "permanent_id")
            ],
            "action_or_terminal_fields": [
                c
                for c in columns
                if any(
                    w in c.lower()
                    for w in ("dlret", "delist", "cfac", "dividend", "split", "cash_receipt")
                )
            ],
        }
        return columns

    def query(name, sql, paths):
        nonlocal parsed_rows
        # ROWS is reserved in DuckDB; quote the output alias, keep exact column semantics.
        sql = sql.replace(" rows,", ' AS "rows",').replace(" rows ", ' AS "rows" ')
        sql = sql.replace(" names,", ' AS "names",').replace(" names ", ' AS "names" ')
        if state.get("same_scope_recovery") and (OUT / (name + ".json")).exists():
            rows = json.loads((OUT / (name + ".json")).read_text())
            queries.append(
                {
                    "id": name,
                    "status": "reused_successful_same_scope_attempt1",
                    "output_rows": len(rows),
                    "cpu_seconds": 0,
                }
            )
            return rows
        before = time.process_time()
        for path in paths:
            bind(path, True)
        try:
            cursor = con.execute(sql)
            names = [c[0] for c in cursor.description]
            rows = [dict(zip(names, row, strict=True)) for row in cursor.fetchall()]
            parsed_rows += len(rows)
            save(name + ".json", rows)
            queries.append(
                {
                    "id": name,
                    "sql": sql,
                    "input_files": len(paths),
                    "output_rows": len(rows),
                    "cpu_seconds": time.process_time() - before,
                    "status": "pass",
                }
            )
            print(
                json.dumps(
                    {"stage": name, "rows": len(rows), "cpu": round(time.process_time(), 3)}
                ),
                flush=True,
            )
            return rows
        except Exception as exc:
            failures.append(
                {
                    "query_id": name,
                    "type": type(exc).__name__,
                    "message": str(exc)[:1200],
                    "cpu_seconds": time.process_time() - before,
                }
            )
            save("failures.json", failures)
            return None

    def stop_cpu(_sig, _frame):
        save(
            "interrupted-resource-receipt.json",
            {
                "cpu_seconds": time.process_time(),
                "reason": "540CPU hard numerical ceiling",
                "failures": failures,
            },
        )
        raise SystemExit(75)

    signal.signal(signal.SIGXCPU, stop_cpu)
    try:
        feature_files = {}
        for root_name in FEATURE_ROOTS:
            folder = ROOT / "data/features" / root_name
            feature_files[root_name] = sorted(folder.glob("[0-9][0-9][0-9][0-9].parquet"))
            for path in feature_files[root_name]:
                schema(path)
        panels = sorted((ROOT / "data/live/equity_book/panel").glob("[0-9]*.parquet"))
        for path in panels:
            schema(path)
        special = {
            "asset": ROOT / "data/features/universe/_asset_metadata.parquet",
            "cik_history": ROOT / "data/raw/sec_ma/cik_symbol_history.parquet",
            "sic_map": ROOT / "data/features/sic_map/sic_map.parquet",
            "facts": ROOT / "data/features/sec_fundamentals/facts.parquet",
            "alias_exclusions": ROOT / "data/sip-delisted/broad/_alias_exclusions.parquet",
            "hygiene": ROOT / "data/live/equity_book/panel/_hygiene.parquet",
        }
        for path in special.values():
            if path.exists():
                schema(path)
        archive_inventory = []
        raw_backfill = sorted((ROOT / "data/sip-delisted/broad/daily").glob("*.parquet"))
        if raw_backfill:
            schema(raw_backfill[0])
            query(
                "unfiltered_backfill_by_date",
                "SELECT CAST(timestamp AS DATE) d,count(*) rows,count(DISTINCT symbol) names,"
                "sum(CASE WHEN volume=0 AND coalesce(trade_count,0)=0 THEN 1 ELSE 0 END) ghost "
                f"FROM {read_table(raw_backfill)} GROUP BY 1 ORDER BY 1",
                raw_backfill,
            )
        for year in range(2016, 2027):
            for role, directory in (
                ("active_source", ROOT / f"data/sip/daily/{year}"),
                ("repartitioned_backfill", ROOT / f"data/sip-delisted/by_year/{year}"),
            ):
                paths = sorted(directory.glob("*.parquet"))
                if paths:
                    schema(paths[0])
                archive_inventory.append(
                    {
                        "year": year,
                        "role": role,
                        "files": len(paths),
                        "bytes": sum(p.stat().st_size for p in paths),
                        "representative_schema_path": str(paths[0].relative_to(ROOT))
                        if paths
                        else None,
                    }
                )
                if year in AUDIT_YEARS and paths:
                    expr = read_table(paths)
                    query(
                        f"archive_{role}_{year}",
                        f"SELECT CAST(timestamp AS DATE) d,count(*) rows,count(DISTINCT symbol) names,"
                        "sum(CASE WHEN volume=0 AND coalesce(trade_count,0)=0 THEN 1 ELSE 0 END) ghost,"
                        "sum(CASE WHEN close IS NULL OR close<=0 THEN 1 ELSE 0 END) invalid_close "
                        f"FROM {expr} GROUP BY 1 ORDER BY 1",
                        paths,
                    )
        save("archive-inventory.json", archive_inventory)
        panel_results = []
        for path in panels:
            rows = query(
                "panel_" + path.stem,
                "SELECT trade_date,count(*) rows,count(DISTINCT symbol) names,"
                "sum(CASE WHEN in_u3000 THEN 1 ELSE 0 END) in_u3000,"
                "sum(CASE WHEN mcap_source<>'sec' THEN 1 ELSE 0 END) mcap_fallback "
                f"FROM {read_table([path])} GROUP BY 1 ORDER BY 1",
                [path],
            )
            if rows is None:
                panel_results.append(
                    {
                        "year": path.stem,
                        "rows": None,
                        "dates": None,
                        "status": "N/A_query_failure_not_empty_data",
                    }
                )
                continue
            panel_results.append(
                {
                    "year": path.stem,
                    "rows": sum(r["rows"] for r in rows),
                    "dates": len(rows),
                    "names_per_date_min": min((r["names"] for r in rows), default=None),
                    "names_per_date_max": max((r["names"] for r in rows), default=None),
                    "mcap_fallback_rows": sum(r["mcap_fallback"] for r in rows),
                    "first": rows[0]["trade_date"] if rows else None,
                    "last": rows[-1]["trade_date"] if rows else None,
                }
            )
        save("panel-wide-summary.json", panel_results)
        history = special["cik_history"]
        query(
            "identity_symbol_ambiguity",
            "SELECT symbol,count(DISTINCT cik) issuer_count,min(first_date) first_observed_filing,"
            "max(last_date) last_observed_filing "
            f"FROM {read_table([history])} GROUP BY symbol ORDER BY issuer_count DESC,symbol",
            [history],
        )
        query(
            "identity_issuer_multisymbol",
            f"SELECT cik,count(DISTINCT symbol) symbols FROM {read_table([history])} "
            "GROUP BY 1 HAVING count(DISTINCT symbol)>1 ORDER BY 2 DESC,1",
            [history],
        )
        asset = special["asset"]
        query(
            "asset_classification",
            "SELECT status,is_probable_fund_or_etf,count(*) rows "
            f"FROM {read_table([asset])} GROUP BY 1,2 ORDER BY 1,2",
            [asset],
        )
        facts = special["facts"]
        if facts.exists():
            columns = schema(facts)
            candidates = [
                c
                for c in ("concept", "tag", "filed", "usable_session", "source_dataset", "restated")
                if c in columns
            ]
            group_cols = [c for c in ("concept", "source_dataset", "restated") if c in candidates]
            if group_cols:
                query(
                    "SEC_fact_provenance",
                    "SELECT " + ",".join(group_cols) + ",count(*) rows "
                    f"FROM {read_table([facts])} GROUP BY ALL",
                    [facts],
                )
            if "filed" in candidates and "usable_session" in candidates:
                query(
                    "SEC_fact_clock",
                    "SELECT count(*) rows,"
                    "sum(CASE WHEN usable_session<=filed THEN 1 ELSE 0 END) non_later_usable "
                    f"FROM {read_table([facts])}",
                    [facts],
                )
        hyg = special["hygiene"]
        query(
            "future_cutoff_ledger",
            "SELECT count(*) symbols,"
            "sum(CASE WHEN cutoff_date IS NOT NULL THEN 1 ELSE 0 END) future_dependent_cutoffs,"
            f"min(cutoff_date) first_cutoff,max(cutoff_date) last_cutoff FROM {read_table([hyg])}",
            [hyg],
        )
        snapshots, feature_coverage = [], []
        for year, day in zip(AUDIT_YEARS, AUDIT_DATES, strict=True):
            base = ROOT / f"data/features/daily_broad/{year}.parquet"
            osap = ROOT / f"data/features/osap_price_broad/{year}.parquet"
            fund = ROOT / f"data/features/sec_fundamentals_daily/{year}.parquet"
            labels = ROOT / f"data/features/labels_broad/{year}.parquet"
            available = [p for p in (base, osap, fund, labels) if p.exists()]
            for path in available:
                bind(path, True)
                cols = schema(path)
                numeric = [
                    c
                    for c in cols
                    if schemas[str(path.relative_to(ROOT))]["types"][c].startswith(
                        ("float", "double", "int", "uint")
                    )
                    and c not in ("cik",)
                ]
                selections = ",".join(
                    f"count({c}) n_{c}, count(DISTINCT {c}) v_{c}" for c in numeric
                )
                if selections:
                    cov = query(
                        f"field_coverage_{path.parent.name}_{year}",
                        f"SELECT count(*) rows,count(DISTINCT symbol) names,{selections} "
                        f"FROM {read_table([path])} WHERE trade_date=DATE {sql_path(day)}",
                        [path],
                    )
                    feature_coverage.append(
                        {"path": str(path.relative_to(ROOT)), "audit_date": day, "coverage": cov}
                    )
            if not base.exists() or not osap.exists() or not fund.exists():
                continue
            ocols, fcols = schema(osap), schema(fund)
            oselect = ",".join(
                f"o.{c} AS osap_{c}" for c in ocols if c not in ("symbol", "trade_date")
            )
            fselect = ",".join(
                f"f.{c} AS sec_{c}" for c in fcols if c not in ("symbol", "trade_date")
            )
            # Null only ambiguous feature blocks, never delete an asset row or failed endpoint.
            source_files = sorted((ROOT / f"data/sip/daily/{year}").glob("*.parquet"))
            source_files += raw_backfill
            for source_path in source_files:
                bind(source_path, True)
            source_with_lineage = read_table(source_files).replace(
                "union_by_name=true)", "union_by_name=true,filename=true)"
            )
            sql = f"""WITH b AS (SELECT *, CAST(timestamp AS DATE) trade_date
                    FROM {source_with_lineage} WHERE CAST(timestamp AS DATE)=DATE {sql_path(day)}),
              d AS (SELECT * FROM {read_table([base])} WHERE trade_date=DATE {sql_path(day)}
                    QUALIFY count(*) OVER(PARTITION BY symbol,trade_date)=1),
              o AS (SELECT * FROM {read_table([osap])} WHERE trade_date=DATE {sql_path(day)}
                    QUALIFY count(*) OVER(PARTITION BY symbol,trade_date)=1),
              f AS (SELECT * FROM {read_table([fund])} WHERE trade_date=DATE {sql_path(day)}
                    QUALIFY count(*) OVER(PARTITION BY symbol,trade_date)=1)
              SELECT b.symbol,b.trade_date,b.filename source_file,b.timestamp source_bar_timestamp,
                     b.close source_current_adjusted_close,b.volume source_volume,
                     b.trade_count source_trade_count,
                     (b.volume=0 AND coalesce(b.trade_count,0)=0) source_ghost_retained,
                     d.* EXCLUDE(symbol,trade_date),{oselect},{fselect},
                     a.is_probable_fund_or_etf current_name_fund_heuristic,
                     CASE WHEN f.cik IS NULL THEN 'no_unique_currentmap_issuer_block'
                     ELSE 'current_SEC_CIK_mapping_historical_security_class_unverified' END identity_status,
                     false permanent_security_link_certified,
                     false complete_terminal_action_chain_certified
              FROM b LEFT JOIN d USING(symbol,trade_date)
              LEFT JOIN o USING(symbol,trade_date) LEFT JOIN f USING(symbol,trade_date)
              LEFT JOIN {read_table([asset])} a USING(symbol)"""
            outfile = OUT / f"current-vintage-wide-snapshot-{year}.parquet"
            if not (state.get("same_scope_recovery") and outfile.exists()):
                con.execute(
                    f"COPY ({sql}) TO {sql_path(outfile)} (FORMAT PARQUET,COMPRESSION ZSTD)"
                )
            query(
                "snapshot_join_quality_" + str(year),
                "SELECT count(*) rows,count(DISTINCT symbol) names,"
                "sum(CASE WHEN sec_cik IS NOT NULL THEN 1 ELSE 0 END) current_CIK_block_rows,"
                "sum(CASE WHEN osap_mom6m IS NOT NULL THEN 1 ELSE 0 END) osap_mom6m_rows,"
                "sum(CASE WHEN current_name_fund_heuristic THEN 1 ELSE 0 END) probable_funds,"
                "sum(CASE WHEN current_name_fund_heuristic IS NULL THEN 1 ELSE 0 END) unknown_class "
                f"FROM {read_table([outfile])}",
                [outfile],
            )
            snapshots.append(
                {
                    "path": str(outfile.relative_to(ROOT)),
                    "bytes": outfile.stat().st_size,
                    "sha256": full_sha(outfile),
                    "source_date": day,
                    "source_paths": [str(p.relative_to(ROOT)) for p in (base, osap, fund, asset)],
                    "selection": "All raw active/backfill records on frozen date; ghosts/duplicates/unknowns retained; no future completeness or current classification filter",
                    "role": "Actual wide current-vintage feature/return source snapshot; not a qualified economic panel",
                }
            )
            # Actual row-key, price-vintage and multiplicity checks on four fixed crosssections.
            source_expr = read_table(source_files)
            query(
                "source_feature_connection_" + str(year),
                f"""WITH b AS(SELECT symbol,CAST(timestamp AS DATE) trade_date,count(*) n,
                      min(close) min_close,max(close) max_close FROM {source_expr}
                      WHERE CAST(timestamp AS DATE)=DATE {sql_path(day)} GROUP BY 1,2),
                    d AS(SELECT symbol,trade_date,close FROM {read_table([base])}
                         WHERE trade_date=DATE {sql_path(day)})
                    SELECT count(*) source_keys,sum(b.n) source_records,
                      sum(CASE WHEN b.n>1 THEN 1 ELSE 0 END) duplicate_source_keys,
                      sum(CASE WHEN b.min_close<>b.max_close THEN 1 ELSE 0 END) conflicting_close_keys,
                      sum(CASE WHEN d.symbol IS NOT NULL THEN 1 ELSE 0 END) joined_to_daily,
                      sum(CASE WHEN d.symbol IS NOT NULL AND abs(d.close-b.min_close)>1e-5 THEN 1 ELSE 0 END) price_version_mismatch_keys
                    FROM b LEFT JOIN d USING(symbol,trade_date)""",
                source_files + [base],
            )
        save("actual-component-snapshots.json", snapshots)
        save("feature-information-coverage.json", feature_coverage)
        # Partial date+PERMNO evidence is retained as partial, not called an absent field or complete panel.
        prefixes = []
        native_dir = (
            ROOT
            / "reports/research/program/day-goal-20261011/source-led-selection/root-dlsa-source/input-package"
        )
        for path in sorted(native_dir.glob("*.csv.first64KiB")):
            text = path.read_text()
            rows = list(csv.reader(text.splitlines()))
            prefixes.append(
                {
                    "path": str(path.relative_to(ROOT)),
                    "bytes": path.stat().st_size,
                    "sha256": full_sha(path),
                    "header": rows[0] if rows else [],
                    "complete_lines_only_count_upper": max(len(rows) - 2, 0),
                    "first_complete_record": rows[1] if len(rows) > 2 else None,
                    "complete_file_present_here": False,
                    "status": "Original author explicitly perturbed these replication CSVs too; PERMNO header does not make prefix genuine market return/action data. Partial only, no usable real dailyreturn/ID connection.",
                }
            )
        save("partial-PERMNO-evidence.json", prefixes)
        changed = []
        for key, item in inputs.items():
            if (ROOT / key).stat().st_mtime_ns != item["mtime_ns"]:
                changed.append(key)
        save(
            "source-version-stability.json",
            {"changed_during_audit": changed, "source_current_vintage_only": True},
        )
        save("schemas.json", list(schemas.values()))
        save("input-bindings.json", list(inputs.values()))
        save("query-ledger.json", queries)
        save("failures.json", failures)
        save(
            "audit-summary.json",
            {
                "panel_years": panel_results,
                "snapshots": snapshots,
                "schemas": len(schemas),
                "bound_files": len(inputs),
                "all_schema_permanent_id_fields": {
                    k: v["permanent_id_fields"]
                    for k, v in schemas.items()
                    if v["permanent_id_fields"]
                },
                "source_version_changed": changed,
                "failures": failures,
                "all_values_read_for_source_quality_only": True,
                "future_complete_cohort_selection": False,
                "portfolio_or_strategy_returns": 0,
                "fits_or_inference": 0,
                "external_requests": 0,
            },
        )
    finally:
        con.close()
        save(
            "resource-receipt.json",
            {
                "cpu_seconds_process_lifetime": time.process_time(),
                "wall_seconds": time.monotonic() - wall_start,
                "peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                "memory_cap_mib": 900,
                "threads": 1,
                "numeric_process_CPU_soft_limit": process_cap,
                "prior_numeric_attempt_CPU_seconds_preserved": prior_cpu,
                "new_subpackage_CPU_limit": 600,
                "old_CPU_or_HTTP_caps_inherited": False,
                "small_read_setup_failure_finalization_unknown_CPU_charge": 50,
                "failures": failures,
                "aggregate_output_records": parsed_rows,
                "external_requests": 0,
                "strategy_economic_computations": 0,
                "fits": 0,
                "metadata_setup_failure": "One pre-job summary printer treateddictrecords aslist; no numericaljob/data mutation; covered by50CPUunknown allowance",
            },
        )
        print((OUT / "resource-receipt.json").read_text(), flush=True)


if __name__ == "__main__":
    main()
