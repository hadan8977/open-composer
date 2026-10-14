"""Convert selected records to a fail-closed lifecycle and causal-clock packet."""

import hashlib
import json
import resource
import sys
import time as clock
from datetime import UTC, date, datetime, time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT))
from open_composer.market_sessions import (  # noqa: E402
    NEW_YORK,
    next_us_equity_session,
    previous_us_equity_session,
    us_equity_session_close,
    us_equity_session_dates,
)
from open_composer.research.features.price_hygiene import (  # noqa: E402
    is_ghost_bar,
    sanitize_price_matrices,
)

OUT = Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(name, value):
    (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str) + "\n")


def utc(day, tm):
    return datetime.combine(day, tm, tzinfo=NEW_YORK).astimezone(UTC).isoformat()


def main():
    started = clock.monotonic()
    selection = json.loads((OUT / "frozen-selection.json").read_text())
    lifecycle = json.loads((OUT / "lifecycle-contract.json").read_text())
    original = pd.read_parquet(OUT / "selected-bars.parquet")
    original["ghost_bar"] = is_ghost_bar(original)
    original["episode_id"] = ""
    original["historical_symbol_role"] = "observed_vendor_label"
    original["raw_price_semantics_accepted"] = False
    episode_by_case = {x["case_id"]: x["id"] for x in lifecycle["episodes"]}
    for i, row in original.iterrows():
        cid, d = row.case_id, row.bar_session
        ep = episode_by_case[cid]
        if cid == "cancel_reissue_WW_2025":
            ep = (
                "EP105319_OLD_COMMON"
                if row.ghost_bar or d <= "2025-06-24"
                else "EP105319_NEW_COMMON"
            )
        original.loc[i, "episode_id"] = ep
        if cid == "rename_ELV_2022" and row.symbol == "ELV" and d < "2022-06-28":
            original.loc[i, "historical_symbol_role"] = "backfilled_alias_not_independent_security"
        if row.ghost_bar:
            original.loc[i, "historical_symbol_role"] = (
                "non_executable_placeholder_old_asset_not_erased"
            )
    original.to_parquet(OUT / "observations.parquet", index=False)

    eligibility, requests, per_case = [], [], []
    prefix_hygiene = []
    for case in selection["cases"]:
        data = original.loc[original.case_id == case["id"]].copy()
        sessions = us_equity_session_dates(
            date.fromisoformat(case["start"]), date.fromisoformat(case["end"])
        )
        # The source clock, not a later best price, chooses the rename tape.
        if case["id"] == "rename_ELV_2022":
            data = data.loc[
                ((data.bar_session < "2022-06-28") & (data.symbol == "ANTM"))
                | ((data.bar_session >= "2022-06-28") & (data.symbol == "ELV"))
            ]
        assert not data.duplicated("bar_session").any(), (
            "ambiguous selected source; do not choose a winning vintage"
        )
        data = data.set_index("bar_session")
        idx = pd.DatetimeIndex(sessions)
        close = pd.DataFrame(index=idx, columns=[case["id"]], dtype=float)
        op = close.copy()
        for d, row in data.iterrows():
            if not row.ghost_bar:
                close.loc[pd.Timestamp(d), case["id"]] = row.close
                op.loc[pd.Timestamp(d), case["id"]] = row.open
        for day in sessions:
            prefix = close.loc[: pd.Timestamp(day)]
            clean_close, _, report = sanitize_price_matrices(prefix, op.loc[prefix.index])
            d = day.isoformat()
            row = data.loc[d] if d in data.index else None
            value = clean_close.iloc[-1, 0]
            prior_month_end = previous_us_equity_session(day.replace(day=1))
            observed_prior20 = int(
                close.loc[: pd.Timestamp(prior_month_end)].iloc[-20:, 0].notna().sum()
            )
            reasons = [
                "no_raw_total_return_action_vintage_chain",
                "no_accepted_marketwide_prior_month_top500_membership",
                "Rf_publication_packet_missing",
                "NBBO_endpoints_missing",
                "ETB_borrow_funding_packet_missing",
                "historical_bar_first_visibility_unverified",
            ]
            if row is None:
                reasons.append("no_selected_bar")
            elif row.ghost_bar:
                reasons.append("ghost_bar_not_price")
            if observed_prior20 < 20:
                reasons.append("bounded_extract_has_less_than20_prior_month_sessions")
            if case["id"] == "reused_SNOW_new_2020":
                reasons.append("new_issuer_share_class_not_certified")
            split_like = case["id"] == "split_AAPL_2020" and d == "2020-08-31"
            if split_like:
                reasons.append("known_split_like_trigger_session_excluded")
            latest_residual_decision = previous_us_equity_session(previous_us_equity_session(day))
            entry = next_us_equity_session(day)
            exit_day = next_us_equity_session(entry)
            request = {
                "case_id": case["id"],
                "decision_session": d,
                "decision_cutoff_utc": utc(day, us_equity_session_close(day)),
                "feature_available_at_utc": None,
                "entry_window_start_utc": utc(entry, time(9, 45)),
                "entry_window_end_utc": utc(entry, time(9, 45, 5)),
                "exit_window_start_utc": utc(exit_day, time(9, 45)),
                "exit_window_end_utc": utc(exit_day, time(9, 45, 5)),
                "entry_quote": None,
                "exit_quote": None,
                "gross_mid_mid_label": None,
                "label_available_at_utc": None,
                "label_matured": False,
                "latest_ordinary_mature_residual_decision": latest_residual_decision.isoformat(),
                "mature_residual_count": 0,
                "mature_PCA_count": 0,
                "required_residual_history": 30,
                "required_PCA_history": 252,
                "policy_window_calendar_years": 8,
                "split_like_trigger_excluded": split_like,
                "no_new_target": True,
                "existing_inventory_and_terminal_rights": (
                    "retain; never remove or assume free liquidation"
                ),
            }
            requests.append(request)
            eligibility.append(
                {
                    "case_id": case["id"],
                    "session": d,
                    "episode_id": None if row is None else row.episode_id,
                    "source_row_sha256": None if row is None else row.source_row_sha256,
                    "prefix_cutoff": d,
                    "completed_bar_visible_at": None,
                    "sanitized_vendor_close_today": None if pd.isna(value) else float(value),
                    "historical_raw_close": None,
                    "ghost_bar": None if row is None else bool(row.ghost_bar),
                    "prior_month_end": prior_month_end.isoformat(),
                    "prior20_observed_within_bounded_extract": observed_prior20,
                    "raw_dollar_ADV20": None,
                    "marketwide_ADV_rank": None,
                    "eligible_under_APP": False,
                    "eligibility_status": "blocked_input_not_economic_rejection",
                    "Ret_D1": None,
                    "Ret_W1": None,
                    "STD_W1": None,
                    "z_D1": None,
                    "z_W1": None,
                    "z_STD": None,
                    "m_D1": None,
                    "m_W1": None,
                    "m_STD": None,
                    "Rf": None,
                    "normalization_fit": False,
                    "reasons": reasons,
                }
            )
            prefix_hygiene.append(
                {
                    "case_id": case["id"],
                    "cutoff": d,
                    "prefix_sessions": len(prefix),
                    "masked_price_cells": report.price_cells_masked,
                    "detected_breaks": [x.as_dict() for x in report.breaks],
                    "past_output_rows_rewritten": False,
                }
            )
        per_case.append(
            {
                "case_id": case["id"],
                "raw_records": int((original.case_id == case["id"]).sum()),
                "selected_clock_records": len(data),
                "calendar_sessions": len(sessions),
                "non_ghost_clock_records": int((~data.ghost_bar).sum()),
                "ghost_clock_records": int(data.ghost_bar.sum()),
                "APP_eligible_rows": 0,
                "accepted_total_return_features": 0,
                "matured_0945_labels": 0,
            }
        )

    def jsonl(name, rows):
        (OUT / name).write_text(
            "".join(json.dumps(r, ensure_ascii=False, default=str) + "\n" for r in rows)
        )

    jsonl("eligibility-feature-clock.jsonl", eligibility)
    jsonl("label-clock-requests.jsonl", requests)
    jsonl("prefix-hygiene.jsonl", prefix_hygiene)

    # Relevant counterexample: demonstrate future break erasure without deleting
    # a single original price row or an old claim from this packet.
    ww = original.loc[(original.case_id == "cancel_reissue_WW_2025") & ~original.ghost_bar].copy()
    ww.index = pd.to_datetime(ww.bar_session)
    wc = ww[["close"]].reindex(
        pd.DatetimeIndex(us_equity_session_dates(date(2025, 5, 1), date(2025, 7, 11)))
    )
    wo = ww[["open"]].reindex(wc.index).rename(columns={"open": "close"})
    pre, _, pre_rep = sanitize_price_matrices(wc.loc[:"2025-05-09"], wo.loc[:"2025-05-09"])
    full, _, full_rep = sanitize_price_matrices(wc, wo)
    assert pre.loc["2025-05-09", "close"] == wc.loc["2025-05-09", "close"]
    assert pd.isna(full.loc["2025-05-09", "close"])
    join = original.loc[
        (original.case_id == "rename_ELV_2022") & (original.bar_session == "2022-06-27")
    ]
    assert len(join) == 2 and join.volume.nunique() == 1 and join.close.nunique() == 2
    write(
        "key-case-evidence.json",
        {
            "WW_future_erasure": {
                "date": "2025-05-09",
                "observed_close": float(wc.loc["2025-05-09", "close"]),
                "same_day_prefix_sanitized_close": float(pre.loc["2025-05-09", "close"]),
                "full_future_history_sanitized_close": None,
                "prefix_masked_cells": pre_rep.price_cells_masked,
                "full_history_masked_cells": full_rep.price_cells_masked,
            },
            "ANTM_ELV_incompatible_vintages": join[
                [
                    "symbol",
                    "bar_session",
                    "close",
                    "volume",
                    "trade_count",
                    "source_path",
                    "source_row_sha256",
                ]
            ].to_dict("records"),
            "terminal_price_rows": original.loc[
                (original.case_id == "terminal_ATVI_2023")
                & original.bar_session.isin(["2023-10-12", "2023-10-13"]),
                ["bar_session", "close", "volume", "trade_count", "ghost_bar", "source_row_sha256"],
            ].to_dict("records"),
            "Form4_interval_cannot_certify": {
                "ATVI_last_filing": "2023-10-16",
                "pre_open_halt_requested": "2023-10-13",
                "ANTM_last_filing": "2022-06-13",
                "rename_effective": "2022-06-28",
                "ELV_first_filing": "2022-11-02",
                "WW_same_CIK_form4_interval_crosses_distinct_common_issuances": True,
            },
            "delayed_filing": {
                "WW_report_date": "2025-06-23",
                "effective_date": "2025-06-24",
                "accepted_utc": "2025-06-25T12:00:55Z",
                "source": "records/CIK0000105319.json",
                "effect_is_not_visibility": True,
            },
        },
    )

    claims = []
    for action in lifecycle["actions"]:
        claims.append(
            {
                "claim_id": action["id"],
                "episode_id": action["episode"],
                "economic_terminal_asset": "pending_equity_conversion_right"
                if action["type"] == "reorganization_equity_entitlement"
                else "cash_receivable"
                if action["type"] == "cash_merger_receivable"
                else "share_base_or_dividend_entitlement",
                "cash_per_eligible_share": action.get("cash_entitlement_per_eligible_share"),
                "conversion_ratio": action.get(
                    "old_to_new_individual_ratio", action.get("new_shares_per_old_share")
                ),
                "economic_effective_date": action.get(
                    "effective_date",
                    action.get("split_adjusted_trading_from", action.get("payable_date")),
                ),
                "visible_timestamp_evidence": action.get("filing_acceptance_utc"),
                "actually_spendable_at": None,
                "terminal_claim_removed": False,
                "terminal_mark_used_as_price": False,
                "terminal_cash_settlement_verified": False,
                "source": action["source"],
            }
        )
    write(
        "held-asset-action-ledger.json",
        {
            "semantics": (
                "Unit-entitlement templates, not positions/orders/P&L. "
                "For a share held by a later authorized run, retain its class-qualified claim "
                "until conversion and settlement; null amounts/counts mean unresolved, not zero."
            ),
            "entries": claims,
        },
    )
    coverage = {
        "raw_records": len(original),
        "forensic_cases": len(per_case),
        "security_episodes": len(lifecycle["episodes"]),
        "per_case": per_case,
        "decision_rows": len(eligibility),
        "APP_eligible_rows": 0,
        "accepted_feature7_rows": 0,
        "matured_0945_labels": 0,
        "economic_returns": None,
        "all_pre20261013_dates_seen_diagnostic": True,
    }
    write("coverage.json", coverage)
    deps = [
        "open_composer/market_sessions.py",
        "open_composer/research/features/price_hygiene.py",
        "open_composer/research/corporate_action_reconciliation.py",
        "scripts/update_sip_archive.py",
        "scripts/repartition_delisted_by_year.py",
        "scripts/fetch_sip_universe.py",
        "open_composer/adapters/data/sip_parquet.py",
    ]
    write(
        "implementation-bindings.json",
        [{"path": p, "bytes": (ROOT / p).stat().st_size, "sha256": sha(ROOT / p)} for p in deps],
    )
    usage = resource.getrusage(resource.RUSAGE_SELF)
    write(
        "packet-build-receipt.json",
        {
            "cpu_seconds": usage.ru_utime + usage.ru_stime,
            "wall_seconds": clock.monotonic() - started,
            "max_rss_kib": usage.ru_maxrss,
            "threads": 1,
            "market_requests": 0,
            "economic_computations": 0,
            "fits": 0,
            "coverage": coverage,
        },
    )
    print(json.dumps(coverage))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        usage = resource.getrusage(resource.RUSAGE_SELF)
        with (OUT / "failed-prep-attempts.jsonl").open("a") as f:
            f.write(
                json.dumps(
                    {
                        "command": "build_packet.py",
                        "cpu_seconds": usage.ru_utime + usage.ru_stime,
                        "max_rss_kib": usage.ru_maxrss,
                        "error": repr(exc),
                        "economic_computations": 0,
                    }
                )
                + "\n"
            )
        raise
