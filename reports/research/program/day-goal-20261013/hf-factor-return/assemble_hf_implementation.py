# ruff: noqa: E501
"""Bind complete conditional implementation and actual inputs for one independent review."""

import importlib.metadata
import json
from datetime import UTC, datetime
from pathlib import Path

from hf_features import FEATURE, P, bind, save
from hf_models import hgb
from hf_run_models import IT


def main():
    root = Path.cwd()
    native = root / "reports/research/iterations" / IT
    native.mkdir(exist_ok=True)
    plan = json.loads((P / "scientific-plan.json").read_text())
    assert (
        json.loads((P / "independent-plan-review.json").read_text())["verdict"]
        == "approve_deep_plan"
    )
    assert (
        json.loads((P / "independent-market-cache-bridge-acceptance.json").read_text())["verdict"]
        == "approve_input_diff"
    )
    meta = json.loads((FEATURE / "feature-metadata.json").read_text())
    assert meta["n_rows"] == 136597 and meta["new_model_fits"] == 0
    defaults = dict(
        packages={
            name: importlib.metadata.version(name)
            for name in ["numpy", "scipy", "scikit-learn", "pandas", "pyarrow"]
        },
        HGB_actual_get_params=hgb(6, 0.1, 350).get_params(),
        APP_not_source_XGBoost=True,
        declared_seed=20261013,
    )
    save(P / "installed-model-implementation.json", defaults)
    definitions = {
        "data": dict(
            conditional_source=bind(P / "complete-source-input-manifest.json"),
            source_acceptance=bind(P / "independent-complete-source-input-acceptance.json"),
            raw_market_bridge=bind(P / "market-cache-bridge-manifest.json"),
            raw_market_acceptance=bind(P / "independent-market-cache-bridge-acceptance.json"),
            feature_manifest=bind(FEATURE / "feature-input-manifest.json"),
            full_feature_acceptance_pending=True,
            source_current_vintage=True,
            PIT=False,
        ),
        "features": plan["feature_and_label"],
        "labels": dict(
            realized_common_target=plan["feature_and_label"]["target"],
            Cts_training_transform=plan["feature_and_label"]["jump"],
            future_target_missing_does_not_reject_current_forecast=True,
        ),
        "validation": dict(
            models=plan["validation_and_models"], inference=plan["inference_and_contribution"]
        ),
        "costs": dict(
            execution=plan["execution_and_capital"], resources=plan["resources_and_gates"]
        ),
        "benchmarks": dict(
            definition=plan["inference_and_contribution"]["benchmarks"],
            host=plan["execution_and_capital"]["host"],
            no_20k_to4k_scaling=True,
            fractional_CIL_missing_only_actual_odd_BIL_book=True,
        ),
    }
    contracts = {}
    for name, definition in definitions.items():
        path = native / (name + "-contract.json")
        save(
            path,
            dict(
                schema_version=1,
                iter_id=IT,
                research_role="market_component_method",
                definition=definition,
                claim_scope="conditional_cohort",
                promotion_eligible=False,
            ),
        )
        contracts[name] = {"conditional_hf_factor_method": bind(path)}
    warnings = dict(
        current_vintage_and_upstream_future_cleaning_unresolved=True,
        source1min_netfactor_IDX_not_original15min_legs=True,
        simple_INVARIANCE_not_log_or_PIT_proof=True,
        source_time_labels_and_calendar_are_APP_assumptions=True,
        actual_raw_SPY_proxy_reference_not_bidask_or_fill=True,
        four_delayed_first_prices_expire_single_attempt=True,
        source_missing_last20190812_no_night_reference_fill=True,
        daily_close_and_last15close_distinct_prices=True,
        physical_BIL_odd_split_CIL_unknown_only_affected_book_metrics_NA=True,
        cash4_3_eligible_proxy_not_actual_or_lower_bound=True,
        all_history_seen_no_promotion_or_paper=True,
    )
    save(
        P / "data-capability-review.json",
        dict(
            schema_version=1,
            role="market_component_method",
            capabilities=[
                dict(
                    capability_id="market.alpaca_bars",
                    actual_raw_receipts=True,
                    cache_reuse_actual_bound_input=True,
                    paper_ready=False,
                ),
                dict(
                    capability_id="author.HFZoo.current_vintage_research_artifact",
                    official_author_archive=True,
                    schema_value_provenance_verified=True,
                    registered_production_capability=False,
                    paper_ready=False,
                ),
            ],
            warnings=warnings,
            historical_conditional_input_accepted=True,
            complete_features_and_implementation_review_pending=True,
            research_pass=False,
            paper_ready_pass=False,
        ),
    )
    save(
        P / "backtest-forensics-review.json",
        dict(
            schema_version=1,
            phase="pre_execution_risk_and_controls",
            source_seen=True,
            heldout_chronology_not_untouched_OOS=True,
            no_profit_based_hyperparameter_selection=True,
            annual_linear_fiveyear_HGB=True,
            exact_registered20pipelines=True,
            all_validation_configurations_counted=True,
            cross_target_loss_comparison_forbidden=True,
            joint_primary_maxT_family6=True,
            bootstrap_packetday_block20_draws2000=True,
            calendar_and_upstream_price_cleaning_caveats=warnings,
            DSR="descriptive IID null-Sharpe dispersion with conservative actual model+view count; not a dependence-adjusted qualification",
            PBO=None,
            SPA=None,
            reason="no selectable cohort/untouched OOS; no promotion",
            author_self_review_is_not_independent_implementation_acceptance=True,
        ),
    )
    save(
        P / "implementation-interpretations.json",
        dict(
            fractional_borrow_basis="APP2%/252/26 per heldshort intraday grid; APP2%/252 if an unclosed short remains overnight, source exact borrow-basis not reproduced",
            diagnostic_execution="Instant fractional sizing is deliberately unfunded zero-latency reference, or exactone15mshift; no first_age>0 nominalfill; no ETB/cash/brokerclaim",
            physical_execution="Cash/wholelots frozen fromprecedingknownprice; gapwholebuy skip; independent20k/4kbooks, no physicalshort/fractional/negativecash",
            firsthour="Openingexit singleattempt expires; later firsthour interiorboundary has a new missingpacket zero-risk decision, not oldpending rollover",
            BIL_control="One initial knownpriorclose lot at first postinit session dailyopening researchreference. Dailyopen/close convention inherited APP; exactquote/firstarrival/subminute auctionprice not certified",
            source_GrossSR="Original quoted-cost/intraday secondmoment unavailable; report named APPdailygross_secondmoment_ratio separately from usual netstd Sharpe",
            OLS="Source unpenalized OLS through normalizedGram lstsq/rcondNone numerical-rank convention; synthetic fullrank directOLS parity passed",
            source_feature_cost="feature metadata CPU is before finalhash; actualfull605.05 CPU incluvcharged separately, not541.54 alone",
            full_original_source_replication=False,
            scientific_candidates_targets_clocks_costs_unchanged=True,
        ),
    )
    paths = [
        P / name
        for name in [
            "scientific-plan.json",
            "execution-contract.json",
            "scientific-plan-revision.json",
            "independent-plan-review.json",
            "complete-source-input-manifest.json",
            "independent-complete-source-input-acceptance.json",
            "market-cache-bridge-manifest.json",
            "market-cache-bridge-definition-diff.json",
            "independent-market-cache-bridge-acceptance.json",
            "independent-market-resource-decision-review.json",
            "sourcecards.jsonl",
            "market-sourcecards.jsonl",
            "hf_features.py",
            "hf_models.py",
            "hf_accounts.py",
            "hf_diagnostics.py",
            "hf_run_models.py",
            "hf_evaluate.py",
            "test_hf_features.py",
            "test_hf_models.py",
            "test_hf_accounts.py",
            "test_hf_evaluation.py",
            "features-tests.xml",
            "models-tests.xml",
            "accounts-tests.xml",
            "evaluation-tests.xml",
            "features-tests-resource.txt",
            "models-tests-resource.txt",
            "accounts-tests-resource.txt",
            "evaluation-tests-resource.txt",
            "full-feature-preparation-resource.txt",
            "installed-model-implementation.json",
            "data-capability-review.json",
            "backtest-forensics-review.json",
            "implementation-interpretations.json",
            "preparation-resource-continuation-04.json",
            "funded-SPY-clock-proposed.json",
            "source-conditional-clock.json",
            "assemble_hf_implementation.py",
        ]
    ]
    paths.extend(native / (name + "-contract.json") for name in definitions)
    paths.extend(
        [
            FEATURE / "feature-metadata.json",
            FEATURE / "feature-input-manifest.json",
            FEATURE / "packet-row-clock.json",
            FEATURE / "source-day-QA.json",
            P.parent / "primary-return-next/host-close-clock-binding.json",
            Path("data/research/account_review_2026_10/returns.parquet"),
        ]
    )
    files = {str(path): bind(path) for path in paths}
    # These exact bytes were already completely hashed by the finished605.05CPU builder.
    # Independent reviewer checks them afresh; author does not burn another fullmatrixhash.
    features = json.loads((FEATURE / "feature-input-manifest.json").read_text())
    for r in features["files"]:
        assert Path(r["path"]).stat().st_size == r["bytes"]
        files[r["path"]] = r
    save(
        P / "implementation-manifest.json",
        dict(
            schema_version=1,
            task_id=plan["task_id"],
            author=plan["author"],
            reviewer=plan["reviewer"],
            as_of_utc=datetime.now(UTC).isoformat(),
            contracts=contracts,
            files=list(files.values()),
            file_count=len(files),
            primary_ids=[r["candidate_id"] for r in plan["candidates"]],
            immutable_source_and_market_nesting_reused_not_rehashed_by_author=True,
            source_feature_hashes_actual_postbuild=True,
            source_feature_acceptance_requested_with_this_full_implementation=True,
            scope="Full20pipelines/17chronologicalsource-testyears/3measurements/actual2016-2020SPYfundedproxy100feeaccounts/800unfundeddiagnostics/matched16k+independent4khost",
            dependent_physical_ex_BIL_metrics_NA_when_actual_BIL_CIL_book_unready=True,
            test_suites=4,
            synthetic_tests=25,
            test_failures=0,
            synthetic_fits_not_real_market_fits=True,
            market_fits=0,
            economic_runs=0,
            implementation_ready=False,
            native_ready=False,
            economic_execution_admitted=False,
            sourcewarnings=warnings,
            entrypoints=[bind(P / "hf_run_models.py"), bind(P / "hf_evaluate.py")],
        ),
    )
    print(
        "implementation_manifest", bind(P / "implementation-manifest.json"), len(files), flush=True
    )


if __name__ == "__main__":
    main()
