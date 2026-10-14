# ruff: noqa: E501
"""Summarize successful source statistics and seal the local-only child package."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path("/root/codex-test/open-composer")
OUT = Path(__file__).resolve().parent


def load(name):
    return json.loads((OUT / name).read_text())


def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1048576), b""):
            h.update(block)
    return h.hexdigest()


def save(name, value):
    (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def main():
    assert load("failures.json") == []
    assert load("connection-repair-resource-receipt.json")["outcome"] == "pass"
    panels = load("panel-wide-summary.json")
    assert all(p["rows"] is not None and p["rows"] > 0 for p in panels)
    schemas = load("schemas.json")
    snapshot_meta = load("actual-component-snapshots.json")
    for item in snapshot_meta:
        assert sha(ROOT / item["path"]) == item["sha256"]
    now = datetime.now(UTC).isoformat()
    receipts = {
        "attempt1/resource-receipt.json": load("attempt1/resource-receipt.json")[
            "cpu_seconds_process_lifetime"
        ],
        "attempt2/resource-receipt.json": load("attempt2/resource-receipt.json")[
            "cpu_seconds_process_lifetime"
        ],
        "resource-receipt.json": load("resource-receipt.json")["cpu_seconds_process_lifetime"],
        "connection-repair-resource-receipt.json": load("connection-repair-resource-receipt.json")[
            "cpu_seconds"
        ],
    }
    unknown = {
        "all_metadata_setup_failed_printers_lint_and_finalization": 50,
        "failed_small_connection_repair_unquoted_close_full_soft_limit": 40,
        "failed_small_connection_repair_SyntaxError_conservative_allowance": 40,
    }
    charged = sum(receipts.values()) + sum(unknown.values())
    assert charged < 600
    accounting = {
        "subtask_CPU_limit": 600,
        "shared_parent_CPU_limit": 2000,
        "measured_CPU_by_receipt": receipts,
        "unknown_CPU_charge_by_stage": unknown,
        "charges_not_measured_CPU": True,
        "subtask_cumulative_conservative_CPU": charged,
        "subtask_CPU_remaining_conservative": 600 - charged,
        "parent_remaining_requires_other_owner_accounting": True,
        "peak_measured_RSS_KiB": 491380,
        "memory_limit_MiB": 900,
        "logical_numeric_audit_tasks": 1,
        "sequential_numeric_process_attempts": 6,
        "max_concurrent_numeric_processes": 1,
        "old7200_HTTP22_24_or_model40_inherited_or_reset": False,
        "new_external_requests": 0,
        "fits": 0,
        "inference": 0,
        "strategy_economic_computations": 0,
        "orders": 0,
    }
    save("accounting.json", accounting)
    save(
        "connection-repair-failed-attempts.json",
        [
            {
                "stage": "connectionrepair1",
                "exit_code": 1,
                "exception": "ParserException near close aggregate alias",
                "measured_CPU": None,
                "unknown_CPU_charge": 40,
                "source_values_or_snapshots_mutated": False,
            },
            {
                "stage": "connectionrepair2",
                "exit_code": 1,
                "exception": "SyntaxError colon expected in resource receipt literal",
                "measured_CPU": None,
                "unknown_CPU_charge": 40,
                "data_pages_read": False,
            },
        ],
    )
    connections = {
        str(y): load(f"source_feature_connection_{y}.json")[0] for y in (2016, 2020, 2023, 2026)
    }
    table_rows = {
        str(y): load(f"snapshot_join_quality_{y}.json")[0] for y in (2016, 2020, 2023, 2026)
    }
    ambiguity = load("identity_symbol_ambiguity.json")
    blocks = {}
    for folder, excluded in [
        ("daily_broad", {"symbol", "trade_date", "open", "close"}),
        ("osap_price_broad", {"symbol", "trade_date"}),
        ("sec_fundamentals_daily", {"symbol", "trade_date", "cik"}),
    ]:
        record = next(s for s in schemas if s["path"] == f"data/features/{folder}/2016.parquet")
        columns = [c for c in record["columns"] if c not in excluded]
        blocks[folder] = {
            "actual_columns": record["columns"],
            "nominal_predictor_columns": columns,
            "nominal_predictor_count": len(columns),
            "original39_replication_claim": False,
        }
    result = {
        "schema_version": 1,
        "task_id": "DAY3-JOINT-DAILY-METHOD-LOCAL-INPUT",
        "as_of_utc": now,
        "author": "f9add224-744b-471c-b812-c43cc179fa38",
        "verdict": "broad_real_local_information_exists_current_cached_connections_need_reconciliation_no_certified_security_totalreturn_join",
        "workflow_pass_local_source_audit": True,
        "economic_input_admitted": False,
        "full39_or79_replication_ready": False,
        "training_or_inference_executed": False,
        "real_input_role": "Current-vintage real provider bar/feature snapshots, not original500factor source replication",
        "actual_wide_panel": {
            "year_span": [2016, 2026],
            "date_count": sum(p["dates"] for p in panels),
            "row_count": sum(p["rows"] for p in panels),
            "min_names_per_date": min(p["names_per_date_min"] for p in panels),
            "max_names_per_date": max(p["names_per_date_max"] for p in panels),
            "mcap_fallback_rows": sum(p["mcap_fallback_rows"] for p in panels),
            "source": "data/live/equity_book/panel; existence/coverage accepted, historical eligibility not reused",
        },
        "snapshot_retention": load("snapshot-retention-summary.json")[0],
        "snapshots": snapshot_meta,
        "snapshot_counts": table_rows,
        "source_feature_connections": connections,
        "2026_connection_note": "Raw11994records/11992keys,2duplicate keys; one duplicate dailyfeaturekey separatelyflagged. Earlier inflatedjoin counts retained only as repair history.",
        "price_equality_check_abs_threshold": 1e-5,
        "feature_blocks": blocks,
        "feature_coverage": load("feature-information-coverage.json"),
        "more_price_feature_schemas_only": [
            {k: r[k] for k in ("path", "columns", "rows")}
            for r in schemas
            if r["path"].endswith("/2016.parquet")
            and any(
                n in r["path"]
                for n in ("alpha101_broad", "alpha191_broad", "alpha158", "reversal_trend_broad")
            )
        ],
        "identity": {
            "examined_Parquet_schemas": len(schemas),
            "examined_Parquet_permanent_ID_fields": {},
            "Form4_symbol_observation_groups": len(ambiguity),
            "symbols_with_multiple_observed_CIKs": sum(r["issuer_count"] > 1 for r in ambiguity),
            "CIKs_with_multiple_observed_symbols": len(load("identity_issuer_multisymbol.json")),
            "date_PERMNO_real_dailyreturn_connection": "not evidenced in scoped local assets",
            "date_CIK_historical_shareclass_connection": "not certified; CIK issuer level and current map/filing spans are insufficient",
            "evidence_supported_episodes": "Prior bounded episodes retained as rule evidence; not widened into the investment cohort",
            "partial_original_PERMNO_CSV": "Two64KiB prefixes only; author says these raw replication CSVs are perturbed; never promoted to real-return bridge",
        },
        "SEC": {
            "actual_concepts": 9,
            "derived_fields": 7,
            "actual_fact_count_and_clock": load("SEC_fact_clock.json")[0],
            "source_provenance_groups": load("SEC_fact_provenance.json"),
            "usable_rule": "Next US session after filed date; same-day not used; currentfactexport vintage separatelyunknown",
            "mapping_limitation": "Builder uses current company_tickers mapping for allpastdates, drops duplicateCIK tickers; dated issuer shareclass not supplied",
            "useful_claim": "Real financial information beyond price-only exists; actual numeric coverage supplied, no faithful original39 claim",
        },
        "known_preprocessing_counterevidence": {
            "future_cutoffs": load("future_cutoff_ledger.json")[0],
            "full_history_sanitizer": "Existing book panel deletes history before last full-history break; reuse prices/coverage only, not causal eligibility",
            "year_mcap_fallback": "Full-year median(close*shares/ADV) calibration is future-dependent and mixes adjustedprice/unadjustedshares",
            "row_based_windows": "Existingdaily/OSAP andlabel builders countrows not sharedsessions; holes/security changes can be crossed",
            "cached_labels": "Available horizon5/10/21/etc excess/rank targets are not primitive daily security totalreturns or terminal cash; LEAD over observations can cross gaps",
            "source_price_version_mismatch": "Measured price disagreements between currentsource andcachedfeatures. Their causes may include vintage, mapping/alias and precision; cachedblocks cannot be silently treated as one coherent currentinput.",
            "classification": "Currentname-keyword probablefund flag only; US_EQUITY does not distinguish stocks/ETFs; no historicalcurrentconstituent filter applied",
            "backfill": "Keep originalbroad/daily rows: repartitionedby_year removed745278 alias rows and entire601symbols based on retrospective evidence; no terminalcash added",
        },
        "maximum_supported_current_vintage_claim": "Wide real as-recorded symbolbar/price-liquidity plus partialissuerfinancial information can support input andalgorithm-information-parity investigation after onevintage causalrebuild andexplicitidentity/terminaluncertainty. No historicalsecurity-totalreturn/fundedstockbook or faithful39/79 result follows from present joins.",
        "unavoidable_confounding_without_more_evidence": [
            "Source population is active-list survivors plus incompleteretrospectivebackfill, mixed commonstock/ADR/fund/ETF/shareclasses",
            "Symbol reuse/rename/dualclass andcurrentCIK fallback can assign wrong financial information or combine distinctsecurities",
            "All-adjusted composite lacks independent raw/split/dividend/cashdelisting chain; no missingterminal right may be treatedaszero/drop",
            "Cachedfeature/return/price vintages differ; rawshare dollar costs andmarketcap not recovered from adjustedclose alone",
        ],
        "minimum_constructible_wide_panel_recipe": [
            "Freeze exact current active+unfilteredbackfill source bytes; retain sourcefile/symbol/date/ghost/duplicate/missing rows andcoverage",
            "Use source-row lineage keys for audit; keep permanent-security/episode unknown unless datedshareclass evidence supports it. Do not call syntheticseriesIDs permanentIDs.",
            "Rebuild price/liquidity/intraday features from onefrozenvintage anddecisionprefix only; reset/withhold cross-gap/action-uncertain endpoints; preserve earlier validpastrows andheldasset/right states",
            "Represent sourceclose returns as conditional composite-price primitives; keep terminal asset receivable/unknownvaluation rows. Do not reuse futureLEAD ranks as stockreturn targets.",
            "Attach source-dated SEC concept events by independentlysupported episode/issuerlink; otherwise retain null/ambiguousfinancialblock withreason, not currentmap-certifiedhistory",
            "Keep variablecrosssection andseparate currentclassification tags; no futurecomplete intersection/currentlist backfill. Actualfourbroad snapshots demonstrate physicaljoin/missingness, not a frozen tradingcohort.",
            "Modelowner chooses sufficientinformation/returnclock/cohort/costassetspace in onecomplete scientificdelta to7b; do not allocatefits untilinput/native/resourceadmission",
        ],
        "route_comparison": {
            "public_OSAP209_monthly_to_local_returns": "No local real date+PERMNO dailyreturn/map; publicGPLcode not CRSPlicense;2GiBcondition not met",
            "public_Pelger332_balanced_returns": "Owner sourceevidence says balancedS&P500 logexcessreturn series, noPERMNO/rawsize/actionchain; do not future-intersect332",
            "JKP_CTF": "Owner schema closes id-eom/id-date/features only under WRDSCRSP/Compustat; localJKP CSVs are aggregate monthlyfactor/portfolio returns, not that stockbackbone",
            "local_current_vintage": "Genuinewide source andfinancialinformation exist, exactquality/path above; currentcachedpackage is sourcecandidate, not readyfundedsecuritybook. Firstseen/ETB are not the grounds for that conclusion",
        },
        "current_final_numeric_queries": "Successful rerun only; archivedparser failures are not zero-data results",
        "failures_retained": {
            "attempt1_parser_queries": 43,
            "attempt2_parser_queries": 40,
            "two_small_connection_repair_errors": 2,
            "archived_zero_rows_fromfailedqueries_invalid": True,
        },
        "accounting": accounting,
        "parent_or_old_artifacts_modified": False,
        "next_action": "Complete local-input scope delivered to ee; source/scientificchoice and anyinput expansion remainwithmodelowner/7b/Root admission, no additionalauthorquery/fit",
    }
    save("result.json", result)
    relevant_code = [
        "scripts/fetch_sip_universe.py",
        "scripts/update_sip_archive.py",
        "scripts/backfill_delisted_daily_bars.py",
        "scripts/repartition_delisted_by_year.py",
        "scripts/build_equity_book_panel.py",
        "scripts/build_sec_xbrl_fundamentals.py",
        "open_composer/research/features/daily_features.py",
        "open_composer/research/features/labels.py",
        "open_composer/research/features/osap_price.py",
        "open_composer/research/features/asset_metadata.py",
    ]
    save(
        "implementation-bindings.json",
        [
            {"path": p, "sha256": sha(ROOT / p), "bytes": (ROOT / p).stat().st_size}
            for p in relevant_code
        ],
    )
    manifests = [
        "data/sip/daily/_LAYOUT.json",
        "data/sip-delisted/by_year/_MANIFEST.json",
        "data/sip-delisted/broad/_manifest.json",
        "data/live/equity_book/panel/_manifest.json",
        "data/features/osap_price_broad/MANIFEST.json",
    ]
    save(
        "source-metadata-bindings.json",
        [
            {"path": p, "sha256": sha(ROOT / p), "bytes": (ROOT / p).stat().st_size}
            for p in manifests
        ],
    )
    readme = f"""# Local wide daily input feasibility

实际宽面板存在：2016–2026年，{result["actual_wide_panel"]["row_count"]:,}行、{result["actual_wide_panel"]["date_count"]}日期，每日2772–3241个symbol；现成book历史资格不能复用。交付四个不按收益选择的真实宽截面，共37170源记录、16108 distinct symbols，1613鬼影原样保留，17039记录缺daily特征块，21720缺唯一SEC块。不是把这些symbol认证成股票队列或永久ID。

读取入口：result.json；schemas/input-bindings/query-ledger；四份current-vintage-wide-snapshot Parquet；feature-information-coverage；source_feature_connection；accounting。源原件及父state未改。

本地daily有44个候选派生信息字段、OSAP日频代理25列、SEC九原概念+七衍生字段。高字段数不能当原39信息复现或独立信息量。现成Alpha101/191也只是实际20/34列，本次只验schema，未冒称完整库或逐值通过。SEC2207149事实的usable_session均晚于filed，当前ticker→CIK映射仍不能证明历史shareclass。

2020-01-31：8298源键，4678连接daily，875价格不一致；2026-01-30修复daily重复键的统计乘数后11992源键/11994记录、2重复源键、5558连接、63唯一连接价格不一致、1歧义daily键。所有原始快照保留。因果/版本统一是具体构造工作，不能只拿缺PIT或ETB否定。

date+PERMNO真实单股return桥在限定本地源中未证实。原作者两份64KiB replication CSV本身也明确扰动；header不能升级为真实市场路径。公开OSAP209为月度PERMNO特征；Pelger332平衡ticker的logexcessreturns无ID/actions；本地JKP月度CSV为factor/portfolio returns，不能替代许可CRSP/Compustat股票backbone。无下载或2GiB触发。

最小宽构造：冻结active+原始backfill版本→保留全部源记录/未知分类/鬼影/重复→同版本决策前缀重建充分价格/流动性块→证据支持的episode/issuer连接SEC，否则金融块保留unknown→终值权利与未知valuation不断链。当前版本的原始信息对照有路径，证券总收益/资产费用空间的完整模型输入尚无合格连接。模型owner与7b决定新的完整应用定义，作者不训练、不计算策略收益。

失败原件在attempt1/attempt2与connection-repair-failed-attempts。旧失败panel rows=0不代表数据为空，最终覆盖只来自成功复算。实测CPU累计{sum(receipts.values()):.6f}秒，未知保守charge130秒，总{charged:.6f}/600，RSS峰491380KiB；同一数值审核的顺序修复，最大并发1。新共享2000CPU由modelowner跨owner汇总。旧7200、22/24或model40未继承。当前外部请求/fit/inference/策略经济计算均0。
"""
    (OUT / "README.zh.md").write_text(readme)
    files = [
        p
        for p in sorted(OUT.rglob("*"))
        if p.is_file()
        and not any(t in p.parts for t in ("__pycache__", "_duck_tmp"))
        and p.name
        not in (
            "package-manifest.json",
            "current-state.json",
            "handoff.txt",
            "handoff-receipt.json",
        )
    ]
    sealed = {
        "task_id": result["task_id"],
        "author": result["author"],
        "sealed_at_utc": now,
        "kind": "complete_local_source_feasibility_and_actual_wide_component_snapshot",
        "independent_scientific_acceptance": "modelowner and7b, not author",
        "sourcefacts_workflow_pass": True,
        "training_or_economic_admitted": False,
        "current_coverage_only_successful_queries": True,
        "historical_failed_outputs_not_valid_coverage": [
            "attempt1/panel-wide-summary.json",
            "attempt2/panel-wide-summary.json",
        ],
        "files": [
            {"path": str(p.relative_to(OUT)), "bytes": p.stat().st_size, "sha256": sha(p)}
            for p in files
        ],
        "mutable_not_sealed": ["current-state.json", "handoff.txt", "handoff-receipt.json"],
        "accounting": accounting,
    }
    save("package-manifest.json", sealed)
    state = load("current-state.json")
    state.update(
        status="complete_actual_local_wide_input_feasibility_delivered",
        as_of_utc=now,
        result="result.json",
        manifest={"path": "package-manifest.json", "sha256": sha(OUT / "package-manifest.json")},
        coverage=result["actual_wide_panel"],
        real_gaps=result["unavoidable_confounding_without_more_evidence"],
        cumulative=accounting,
        next_action=result["next_action"],
        numeric_process_attempts=6,
        all_final_reported_numeric_statistics_successful=True,
    )
    save("current-state.json", state)
    (OUT / "handoff.txt").write_text(
        f"local-input完整包已封，manifest SHA{sha(OUT / 'package-manifest.json')}。"
        f"{result['actual_wide_panel']['row_count']}真实panel行/{result['actual_wide_panel']['date_count']}日期；37170未删源记录、16108symbols、1613ghost；"
        "2020实际8298keys/4678join/875价版本差；2026去除歧义daily键统计乘数后11992keys/11994records/5558join/63差。"
        "48daily字段(44派生)/25OSAP代理/16SEC信息有真实值，SECCIK历史shareclass不认证。"
        "无本地真实PERMNO日return/action连接；原rawreplicationCSV也扰动、JKP只是factorportfolios，不升级。"
        "成功coverage/失败原件/全部CPU保留，模型准备不准入；最大当前版本信息主张和最小宽构造详result，非旧price3/0945。"
        f"累计保守CPU{charged:.6f}/600，外部/拟合/经济0。父state/旧包未改。请直接作为完整本地输入决定包接收，无需重拉。\n"
    )
    print(
        json.dumps(
            {
                "manifest_sha256": sha(OUT / "package-manifest.json"),
                "panel": result["actual_wide_panel"],
                "CPU": charged,
                "remaining_subtask_CPU": 600 - charged,
                "files": len(files),
            }
        )
    )


if __name__ == "__main__":
    main()
