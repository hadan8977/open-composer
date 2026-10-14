# ruff: noqa: E501
"""Preregistration artifacts for t20261008_p1_s1_dlsa (P1 stage 1 round 1, DLSA-style learned residual stat-arb).

Writes the source cards, the draft StrategySpec and the lightweight config, then runs
scripts/new_lightweight_iteration.py. The contract itself is
reports/research/iterations/t20261008_p1_s1_dlsa/contract.md (written by the lead round, frozen
before any return of this book was computed).

    uv run python scripts/p1s1_make_dossier.py
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IT = "t20261008_p1_s1_dlsa"
D = ROOT / "reports/research/iterations" / IT
CARDS = ROOT / f"reports/harness/source_cards/{IT}.jsonl"
SPEC = ROOT / f"strategy_specs/drafts/{IT}.yaml"
T22_CARDS = ROOT / "reports/harness/source_cards/t20261006_22_st_reversal.jsonl"
NOW = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

REUSE = {
    "dlsa_2021_sharpe_half_life_seven_days": "Holding axis H = 1, 5, 10 sessions and the seven-session half-life prior; the learned model is trained with a one-day objective as in the paper.",
    "avellaneda_lee_2010_residual_mean_reversion": "Defines the parametric benchmark OU-T (s-score thresholds open 1.25, close long -0.50, close short +0.75, kappa > 252/30, 60-session OU window).",
    "avellaneda_lee_2010_pca_sharpe_decline_costs_5bp": "Prior that parametric residual stat-arb decays after 2003; the OU-T points are expected near or below zero net.",
    "attention_factors_2025_cost_in_objective": "Cost enters the training objective (friction axis F0 vs F1); round 2 may add the attention-factor residual point.",
    "blitz_huij_lansdorp_verbeek_2013_residual_reversal_net": "Residual (not raw) reversal is the object; supports trading residual portfolios rather than stocks.",
    "equity_statarb_github_oos_2019_2024_negative": "Closest negative prior on recent data (PCA residual reversal OOS 2019-2024 gross 0.23, net -0.15); the stop rule is written so that this outcome stops stage 1.",
}

NEW_CARDS = [
    {
        "claim_id": "dlsa_2025_friction_table_ix_ipca_net",
        "source_url": "https://arxiv.org/pdf/2106.04028",
        "source_snapshot": "reports/research/intel/sources/mid-frequency-2026-10-04/dlsa-arxiv.txt",
        "published_or_updated_at": "2021-06-08",
        "source_type": "paper",
        "claim": "DLSA Table IX: CNN+Transformer trained with trading frictions on IPCA residuals, out of sample 2002-2016, annualized Sharpe 1.24 (K=3), 1.11 (K=5), 0.98 (K=10) with mean 5.5-6.6% and volatility about 5%; frictions are 5 bp per unit of turnover and 1 bp per short position, universal for all times and stocks, used in both training and evaluation.",
        "quote": "The first penalty term represents a slippage/transaction cost of 5 basis points per transaction, whereas the second one is a holding cost of 1 basis point per short position.",
        "impact_on_spec": "Sets the base spec (IPCA K=5, CNN+Transformer, friction-aware objective) and the published net level the replication is compared with; our costs are the measured close-tier model instead of a flat 5 bp.",
        "limitations": "Authors' backtest ending 2016; flat costs; no market impact; same-close execution convention.",
        "independent_replication": "Gross numbers reproduced 2002-2016 by one independent blog replication; no verified post-2016 net replication.",
        "applies_to_extra": [],
        "verification_method": "snapshot_text_read_by_lead_round",
        "verification_status": "opened_primary_source",
    },
    {
        "claim_id": "dlsa_implementation_details_secondary_notes",
        "source_url": "https://github.com/jjakimoto/research-issues/issues/1923",
        "source_snapshot": "reports/research/intel/sources/p1-s1-dlsa-2026-10-08/jjakimoto-research-issues-1923.html",
        "published_or_updated_at": "2026-01-01",
        "source_type": "platform_docs",
        "claim": "Reading notes of DLSA: PCA residuals use a 252-day correlation window and 60-day loading regressions, IPCA is re-estimated annually, deep models use rolling 1,000-day training windows re-estimated every 125 days after an initial four-year window; friction-aware training approximates prior allocations from the preceding epoch and the authors note this can be suboptimal and do not retune hyperparameters for the friction setting; gross IPCA-5 CNN+Transformer Sharpe 4.16.",
        "quote": "Fama-French loadings use rolling 60-day regressions; PCA uses a 252-day correlation window and 60-day loading regressions; IPCA uses 240 months of returns and characteristics and is re-estimated annually.",
        "impact_on_spec": "Fixes the PCA residual recipe (252-day correlation eigenportfolios, 60-day loading OLS), the IPCA annual refit and the 1,000/125 training schedule; our friction training computes turnover exactly inside contiguous mini-batches instead of the epoch approximation.",
        "limitations": "Secondary reading notes, not the paper; used only for implementation details that match the paper text.",
        "independent_replication": "n/a (notes)",
        "applies_to_extra": [],
        "verification_method": "fetch_and_snapshot_by_lead_round",
        "verification_status": "opened_secondary_summary",
    },
    {
        "claim_id": "attention_factors_2025_pca_ou_benchmark_gross_net",
        "source_url": "https://arxiv.org/html/2510.11616v1",
        "source_snapshot": "reports/research/intel/sources/p1-s1-dlsa-2026-10-08/attention-factors-2510.11616v1.html",
        "published_or_updated_at": "2025-10-13",
        "source_type": "paper",
        "claim": "Attention Factors (500 largest stocks, rolling 8-year window retrained yearly, OOS 1998-2021, cost 0.0005 x turnover + 0.0001 x short): attention model K=30 gross Sharpe 3.97, net 2.28; parametric PCA+OU threshold benchmark K=5 gross 0.99, net -3.44, K=30 gross 0.18, net -6.45; PCA two-step (residuals then learned signal) K=1 gross 2.26, net 1.19; tuning on the last two years of the first training window.",
        "quote": "Parametric Benchmark PCA + OU Thresh ... 30 0.18 0.40 2.24 -6.45",
        "impact_on_spec": "The parametric OU-T points are expected to be strongly negative net; the learned-vs-OU comparison (replication item a) is judged on net and gross separately; validation inside the training window only.",
        "limitations": "Authors' backtest to 2021, flat costs, GPU-scale model; no sub-period table.",
        "independent_replication": "none found",
        "applies_to_extra": [],
        "verification_method": "fetch_and_snapshot_by_lead_round",
        "verification_status": "opened_primary_source",
    },
    {
        "claim_id": "arxiv_2412_11432_withdrawn_survivorship",
        "source_url": "https://arxiv.org/abs/2412.11432",
        "source_snapshot": "reports/research/intel/sources/p1-s1-dlsa-2026-10-08/arxiv-abs-2412.11432.html",
        "published_or_updated_at": "2024-12-16",
        "source_type": "paper",
        "claim": "The only 2016-2024 extension of DLSA-style residual trading (Long and Xiao, arXiv 2412.11432) is marked withdrawn by its author; the earlier intel brief recorded that it used a static S&P 500 list (survivorship) and reported Sharpe ratios above 10.",
        "quote": "withdrawn by Wo Long",
        "impact_on_spec": "Point-in-time monthly universe including later-delisted names is mandatory; any OOS net Sharpe above 4 triggers a leakage audit before it is reported.",
        "limitations": "Withdrawn paper; used only as a cautionary example.",
        "independent_replication": "n/a",
        "applies_to_extra": [],
        "verification_method": "fetch_and_snapshot_by_lead_round",
        "verification_status": "opened_primary_source",
    },
    {
        "claim_id": "end_to_end_stat_arb_autoencoder_2024",
        "source_url": "https://arxiv.org/pdf/2402.08233",
        "source_snapshot": "reports/research/intel/sources/mid-frequency-2026-10-04/end-to-end-stat-arb-autoencoder-2402.08233.txt",
        "published_or_updated_at": "2024-02-13",
        "source_type": "paper",
        "claim": "Krause and Calliess (2024) learn the residual factor model and the trading policy end to end with an autoencoder; they report gross returns only.",
        "quote": "End-to-End Policy Learning of a Statistical Arbitrage Autoencoder Architecture",
        "impact_on_spec": "Round 2 residual-axis third point (conditional autoencoder residuals) after PCA and IPCA.",
        "limitations": "Gross only; not a net-of-cost result.",
        "independent_replication": "none found",
        "applies_to_extra": [],
        "verification_method": "snapshot_text_read_by_lead_round",
        "verification_status": "opened_primary_source",
    },
    {
        "claim_id": "local_t22_residual_reversal_rules_die_on_cost",
        "source_url": "file://reports/research/iterations/t20261006_22_st_reversal/report.md",
        "source_snapshot": "reports/research/iterations/t20261006_22_st_reversal/report.md",
        "published_or_updated_at": "2026-10-07",
        "source_type": "internal_measurement",
        "claim": "Local T-20261006-22: 24 rule-based residual-reversal cells (U500/1000/3000, industry/PCA residuals, L 5/21, H 1/5, open fill) all net negative in 2024-01-08..2026-09-15 (best -0.54, best gross 1.07 at 30.6% yearly cost); LightGBM U500 H5 gross 1.37, net -0.09 at open fill, +0.33 at close fill (post hoc, not evidence); daily correlation with v1.2 between -0.03 and 0.07.",
        "quote": "预注册的规则版不成立 ... 机器学习版未到深度，不是否定",
        "impact_on_spec": "The death cause of the shallow versions is turnover cost at the open, so this round fills at the close (MOC) and puts cost into the training objective; the low correlation with v1.2 makes the account-level test the main judgment.",
        "limitations": "Same data and window family as this round; it informed the design (disclosed).",
        "independent_replication": "n/a",
        "applies_to_extra": [],
        "verification_method": "local_report_read_by_lead_round",
        "verification_status": "internal_measurement",
    },
    {
        "claim_id": "local_t0701_intraday_daily_features_no_increment",
        "source_url": "file://reports/research/iterations/t20261007_01_cost_aware_engine/report.md",
        "source_snapshot": "reports/research/iterations/t20261007_01_cost_aware_engine/report.md",
        "published_or_updated_at": "2026-10-07",
        "source_type": "internal_measurement",
        "claim": "Local T-20261007-01: adding intraday-derived daily features to the fast composite (F axis) gave recent net Sharpe 1.617/1.599/1.551 at kappa 0.05/0.10/0.20 against 1.621/1.606/1.560 without them; the fast composite did not pass its placebo and the gain came from partial rebalancing of the slow score.",
        "quote": "S0_I3F_k005 / k010 / k020（F 轴） | 1.617 / 1.599 / 1.551",
        "impact_on_spec": "Reason the 10-08 lead round chose the learned residual signal over the intraday-feature axis as the next P1 step.",
        "limitations": "F axis was shallow (2026-only intraday files, one composite); not a refutation of intraday features.",
        "independent_replication": "n/a",
        "applies_to_extra": [],
        "verification_method": "local_results_json_read_by_lead_round",
        "verification_status": "internal_measurement",
    },
]


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def write_cards() -> list[dict]:
    rows: list[dict] = []
    for line in T22_CARDS.read_text().splitlines():
        c = json.loads(line)
        if c["claim_id"] not in REUSE:
            continue
        c["applies_to"] = ["dir:learned_residual_statarb_dlsa", IT]
        c["impact_on_spec"] = REUSE[c["claim_id"]]
        rows.append(c)
    for n in NEW_CARDS:
        snap = ROOT / n["source_snapshot"]
        rows.append(
            {
                "accessed_at": NOW,
                "applies_to": ["dir:learned_residual_statarb_dlsa", IT, *n["applies_to_extra"]],
                "claim": n["claim"],
                "claim_id": n["claim_id"],
                "fetched_at": NOW,
                "impact_on_spec": n["impact_on_spec"],
                "independent_replication": n["independent_replication"],
                "limitations": n["limitations"],
                "published_or_updated_at": n["published_or_updated_at"],
                "quote": n["quote"],
                "source_sha256": sha(snap),
                "source_snapshot": n["source_snapshot"],
                "source_type": n["source_type"],
                "source_url": n["source_url"],
                "status": "verified",
                "verification_method": n["verification_method"],
                "verification_status": n["verification_status"],
            }
        )
    CARDS.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
    return rows


SPEC_TEXT = """name: {it}
description: 'P1 stage 1 round 1 (T-20261008-31/32/33): DLSA-style learned residual statistical arbitrage on the 500 most liquid
  US stocks, preregistered 2026-10-08. PCA(5) and IPCA(5, price/volume characteristics) out-of-sample residuals, 30-session
  cumulative residual paths, parametric OU thresholds vs OU-feature FFN vs CNN+Transformer allocation trained on a Sharpe objective
  with measured close costs, rolling 1,000-session training re-estimated every 125 sessions, decision at the close of t and MOC fill
  at the close of t+1. Research test for a P1 leg; not a paper or live strategy.'
timeframe: daily
universe:
- SPY
- IWM
lifecycle: draft
position_direction: long_short
entry:
  all:
  - close > 0
  any: []
exit:
  all: []
  any:
  - close <= 0
risk:
  max_trades_per_day: 1000
  max_position_weight: 0.02
  stop_loss_pct: null
  take_profit_pct: null
portfolio:
  mode: hybrid_adaptive_router
  max_symbols_per_day: 500
  gross_exposure_limit: 1.0
  max_symbol_weight: 0.02
  same_day_flatten: false
  duplicate_signal_policy: stable_signal_id
  selected_route_label: {it}:learned_residual_statarb
costs:
  commission_pct: 0.0
  slippage_bps: 10.0
  impact_model: linear
  impact_eta: 0.0
  impact_gamma: 0.0
execution:
  backend: nautilus_trader
  mode: manual_signal
  signal_on: bar_close
  fill_assumption: next_bar_open  # schema only allows next_bar_open; the contract fill is MOC at the close of t+1 (contract.md section 6)
  broker: none
data:
  source: alpaca
  symbol: SPY
  path: data/research/equity_book/panel
  feed: sip
data_assumptions:
  source: alpaca
  adjusted: true
  timezone: America/New_York
  acquisition_tier: research_strict
  session_scope: regular
  forward_fill_allowed: false
  zero_return_substitution_allowed: false
  nonfinite_action: fail_closed
  historical_quality_paper_eligible: false
  historical_quality_is_paper_authorization: false
factors:
  learned_residual_allocation:
    source: expression
    expression: -(close / lag(close, 5) - 1)
    default: 0.0
    description: Documentation-only stand-in. The real allocation is a function of the 30-session cumulative factor-residual
      path (PCA or IPCA residuals) learned by scripts/p1s1_train.py on a Sharpe objective; decision at the close of t, MOC fill
      at the close of t+1.
    params:
      decision_lag_sessions: 0
llm_review:
  enabled: false
  model: null
required_capabilities:
- market.alpaca_bars
research_design:
  iter_id: {it}
  candidate_manifest_path: reports/research/iterations/{it}/candidate-manifest.json
  data_feasibility_path: reports/research/iterations/{it}/data-feasibility.json
  source_cards_path: reports/harness/source_cards/{it}.jsonl
  source_card_claim_ids:
{claim_ids}
  parameter_space:
    residual_model:
    - pca5
    - ipca5_pv
    signal_model:
    - ou_threshold
    - ou_features_ffn
    - cnn_transformer
    friction_in_objective:
    - f0
    - f1
    holding_H:
    - 1
    - 5
    - 10
  candidate_budget: 8
  selection_objective: Recent-window (2024-01-08..panel end) net Sharpe at 1x measured close cost through run_book, median over
    rebalance offsets for H > 1; the selected spec is the median of the top three (contract.md section 9).
  anti_overfit_notes:
  - contract.md was frozen before any return of this book was computed; only data-coverage counts and published numbers were read.
  - Hyperparameters are the DLSA benchmark values fixed in advance; early stopping uses the last 125 sessions of each training window only.
  - Grid, stop rules, selection rule and placebo are not changed after results; bug fixes are dated amendments.
  - Sessions after the research snapshot (2026-09-17) are not read in this round.
  validation_plan:
  - 'T-20261008-31: residual store, block calendar, OU-T specs S7 S8 and the evaluation harness; identity, projection and no-lookahead tests.'
  - 'T-20261008-32: OU-FFN and CNN+Transformer training on Modal (S1, S4, S5, S6 weights; S2, S3 reuse S1 weights).'
  - 'T-20261008-33: all 8 specs through run_book, offsets, D0 diagnostic, placebo, v1.2 combination, DSR, mechanical status.'
notes:
  intent: Decide whether a learned residual stat-arb leg on the 500 most liquid names earns a positive net Sharpe after measured close costs in 2024-2026 and raises the account-level same-vol Sharpe of v1.2.
  hypothesis_id: T-20261008-31
  previous_link: t20261007_01_cost_aware_engine
  broker_writes: false
  promotion_eligible: false
  contract_status: preregistered
"""

CANDIDATES = [
    ("S1_IPCA_CT_F1_H1", "ipca5_pv", "cnn_transformer", "f1", 1, "base"),
    (
        "S2_IPCA_CT_F1_H5",
        "ipca5_pv",
        "cnn_transformer",
        "f1",
        5,
        "holding axis (S1 weights, rebalance every 5, median of 5 offsets)",
    ),
    (
        "S3_IPCA_CT_F1_H10",
        "ipca5_pv",
        "cnn_transformer",
        "f1",
        10,
        "holding axis (S1 weights, rebalance every 10, median of 10 offsets)",
    ),
    (
        "S4_IPCA_CT_F0_H1",
        "ipca5_pv",
        "cnn_transformer",
        "f0",
        1,
        "friction axis: Sharpe objective without cost terms",
    ),
    ("S5_PCA_CT_F1_H1", "pca5", "cnn_transformer", "f1", 1, "residual axis: PCA(5) residuals"),
    (
        "S6_IPCA_OUFFN_F1_H1",
        "ipca5_pv",
        "ou_features_ffn",
        "f1",
        1,
        "model axis middle point: OU features + FFN allocation",
    ),
    (
        "S7_IPCA_OUT_H1",
        "ipca5_pv",
        "ou_threshold",
        "none",
        1,
        "model axis parametric point (Avellaneda-Lee thresholds)",
    ),
    ("S8_PCA_OUT_H1", "pca5", "ou_threshold", "none", 1, "parametric benchmark on PCA residuals"),
]


def main() -> None:
    rows = write_cards()
    claim_ids = "\n".join(f"  - {r['claim_id']}" for r in rows)
    SPEC.write_text(SPEC_TEXT.format(it=IT, claim_ids=claim_ids))
    sources = []
    for r in rows:
        sources.append(
            {
                "claim_id": r["claim_id"],
                "url": r["source_url"],
                "published_or_updated_at": r["published_or_updated_at"],
                "source_type": r["source_type"],
                "credibility": "internal_measurement"
                if r["source_type"] == "internal_measurement"
                else (
                    "peer_reviewed_or_working_paper"
                    if r["source_type"] == "paper"
                    else "secondary_or_platform"
                ),
                "core_claim": r["claim"],
                "project_applicability": r["impact_on_spec"],
                "reflection": r["limitations"],
            }
        )
    config = {
        "iter_id": IT,
        "strategy_name": IT,
        "representative_spec_path": f"strategy_specs/drafts/{IT}.yaml",
        "path_name": "learned_residual_statarb_dlsa",
        "hypothesis_id": "T-20261008-31",
        "objective": "P1 stage 1 round 1: test whether a DLSA-style learned residual stat-arb policy (IPCA/PCA residuals, CNN+Transformer trained on a cost-aware Sharpe objective) on the 500 most liquid US names keeps a positive net Sharpe after measured close costs in 2024-2026, beats the parametric OU benchmark, and raises the same-vol account Sharpe of the stock long-short book v1.2",
        "benchmark_family": [
            "parametric_ou_threshold_same_residuals",
            "ou_features_ffn_same_residuals",
            "pca_vs_ipca_residuals_same_model",
            "friction_free_training_same_model",
            "existing_stock_long_short_book_v12",
            "placebo_residual_space_permutation_fixed_per_block",
            "cash_proxy_bil",
        ],
        "candidates": [
            {
                "candidate_id": cid,
                "parameters": {
                    "universe": "top 500 by dollar_adv_21 at the last session of the previous month, is_tradeable, short-eligible (borrow rule v1), full 252-session return history; later-delisted names included",
                    "residual_model": res,
                    "signal_model": model,
                    "friction_in_objective": fr,
                    "holding_H": h,
                    "role": role,
                    "execution": "decision at close t, MOC fill at close t+1, earns close t+1 -> close t+2",
                    "training": "rolling min(1000, available) decision sessions ending 2 sessions before each 125-session test block; last 125 training sessions = early-stopping validation; 3 seeds averaged"
                    if model != "ou_threshold"
                    else "none (fixed rule)",
                    "contract": f"reports/research/iterations/{IT}/contract.md",
                },
            }
            for cid, res, model, fr, h, role in CANDIDATES
        ],
        "cost_table": {
            "base_cost_bps": "model",
            "judged_cost": "cost model v1 via costfn.make_cost_fn('close') (close-snapshot half spread by price/ADV/vol/year, square-root impact at actual trade dollars on a 300,000 USD book, 0.5 bp fees per side) and borrow 25 bp a year on short notional",
            "stress_cost_bps": "2x model",
            "two_x_cost_check": "net_k = gross - k x costs on the same weight paths, k = 0.5, 1, 2, for every spec",
            "paper_cost_sensitivity": "DLSA flat 5 bp per unit turnover plus 1 bp per day short holding, S1 and S7 only, reported not selected",
        },
        "sources": sources,
        "topic_coverage": [
            "learned_residual_signal_dlsa",
            "residual_factor_model_pca_ipca",
            "parametric_ou_benchmark",
            "cost_in_training_objective",
            "post_publication_decay_out_of_sample",
            "survivorship_point_in_time_universe",
            "transaction_cost_and_capacity",
            "holding_period_rebalance_speed",
            "integration_with_book_v12",
        ],
        "hypothesis": {
            "statement": "A CNN+Transformer allocation learned on 30-session cumulative IPCA/PCA residual paths of the 500 most liquid US stocks, trained on a Sharpe objective that charges the measured close costs, earns a positive net Sharpe in 2024-2026 with a close-to-close one-session execution lag, beats the parametric OU threshold rule on the same residuals, and adds same-vol Sharpe to the stock long-short book v1.2.",
            "failure_mode": "Short-horizon residual mean reversion in liquid US names has decayed after 2016 (equity-statarb OOS 2019-2024 gross 0.23), the one-session lag removes the fast component, or turnover at measured close spreads consumes the gross edge; learning adds nothing over OU on our shorter (2016+) training history.",
            "measurement": "contract.md: 8 specs, OOS 2020-02-13..2026-09-17 in 14 blocks of 125 sessions, run_book with cost_model_v1 close tier, recent window 2024-01-08.., stress overlap 2020-02-13..2023-08-31, by-year table, D0 same-close diagnostic, 100-seed residual-space placebo, inverse-vol monthly combination with v1.2 A1_M0_U3000_F1, DSR with N = 8 and N = 125.",
            "stop_pivot": "Stop stage 1 if every spec has recent net Sharpe <= 0, or if the learned models do not beat OU-T on recent net Sharpe in any of the three comparable pairs; otherwise round 2 (U1000, conditional autoencoder residuals, K 3/5/10, partial rebalancing). Death by cost with a working signal goes to P1 stage 3 (near-close execution) before the line is closed.",
        },
        "decision": {
            "path": "learned_residual_statarb_dlsa",
            "decision": "pending",
            "reason": "Preregistered 2026-10-08 by the 01:07 lead round before any return of this book was computed; executed by briefs T-20261008-31, -32, -33.",
            "next_iteration_suggestion": "contract.md section 11: continue_round2 -> t2026xxxx_p1_s1_dlsa_r2; stop -> death cause in the registry and the program.",
        },
        "source_cards_path": f"reports/harness/source_cards/{IT}.jsonl",
    }
    D.mkdir(parents=True, exist_ok=True)
    cfg_path = D / "lightweight-config.json"
    cfg_path.write_text(json.dumps(config, indent=1, ensure_ascii=False) + "\n")
    r = subprocess.run(
        [
            "uv",
            "run",
            "python",
            "scripts/new_lightweight_iteration.py",
            str(cfg_path),
            "--overwrite",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    print(r.stdout[-2500:], r.stderr[-2500:])


if __name__ == "__main__":
    main()
