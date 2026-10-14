"""Bind native result routing and author forensics to the complete measured output."""
# ruff: noqa: E501

import hashlib
import json
from pathlib import Path

P = Path(__file__).resolve().parent
D = Path("reports/research/iterations/t20261013_hf_factor_conditional_method")


def bind(path):
    return dict(path=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                bytes=path.stat().st_size)


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def main():
    result = json.loads((P / "complete-costed-result.json").read_text())
    assert result["inventory"]["independent4k_model_books"] == 40
    result["iter_id"] = D.name
    result["complete_owner_result"] = bind(P / "complete-costed-result.json")
    save(D / "evaluation-report.json", result)
    (D / "evaluation-report.md").write_bytes((P / "complete-costed-result.md").read_bytes())
    (D / "trial-ledger.jsonl").write_bytes((P / "economic/model-trial-ledger.jsonl").read_bytes())
    old = P / "implementation-M3-archive/native-decision-before-result.md"
    if not old.exists():
        old.write_bytes((D / "decision-record.md").read_bytes())
    (D / "decision-record.md").write_text(
        "# Complete HF conditional result\n\n"
        "Decision: stop_current_application_defer_deployment. All20 primary20bp physical "
        "accounts lose capital; source-style gross fractional evidence does not establish "
        "substantial funded absolute returns. Complete20 pipelines/800 diagnostics/100 "
        "standalone/40 independent host sleeves are in the linked result.\n\n"
        "Leading host availability corrected by independently accepted M3 to2017-10-04 "
        "close; internal missing values still block. Model/standalone output unchanged. "
        "No general source mechanism refutation, no unseenOOS or paper/Alpha promotion.\n\n"
        f"Result: {P / 'complete-costed-result.json'}\n\n"
        "Independent final result acceptance is a separate receipt, pending at this seal.\n"
    )
    forensics = dict(
        strategy_name="conditional_hf_factor_method", author="7b109880-ac40-447e-b2a6-f0ed1266ebac",
        independent_review=False, scope="Author evidence audit for independent complete result review",
        lookahead_check="warning", future_leak_check="warning", overfit_risk="high",
        multiple_testing_count=4453, pbo_proxy=None, dsr_proxy=None, pbo=None, dsr=None,
        statistical_methods=dict(
            primary_loss="Same realised All market target for exact six contrasts",
            dependence="HAC5 and2000 block20 packetday bootstrap, fixedseed20261013, jointmaxT6",
            DSR="Per-book descriptive IID-null daily Sharpe dispersion and skew/kurtosis correction; not dependence-adjusted or promotion evidence",
            DSR_results=bind(P / "economic/results/descriptive-DSR.json"),
            PBO_SPA="N/A, no selectable untouched cohort; not set to zero",
        ),
        sample_data_caveats=[
            "Real full author data, not a fixture; current-vintage net factor1m input does not certify original15m legs or PIT formation.",
            "Public full-day cleaning/interpolation and future factor screening are not eliminated by a conditional session clock or equal-window INV transform.",
            "All history seen; no untouched OOS or2026 forward market performance.",
            "Reference-price fills, cash availability proxy and APP short borrow do not certify broker/TAQ/ETB execution.",
            "Actual BIL odd-share CIL makes only affected physical books and dependent metrics N/A.",
        ],
        trade_count="Per159 physical ledger orders, exact fills/skips retained; not aggregated as independent statistical observations",
        trading_days=1259, source_common_days=4280, host_common_days=817,
        capacity_assessment="20k primary and independent4k sleeves evaluated; actual order-book/impact/quote-size capacity N/A. No deployment claim.",
        short_sample=False, conclusion="warning",
        notes=("Author chronological/scaler/label/signal clock implementation and independent M1/M2/M3 checks "
               "are retained. These cannot certify unknown upstream source causality. Primary20bp loss and "
               "matched comparison determine stop of this application; no whole-mechanism refutation."),
        result=bind(P / "complete-costed-result.json"),
        implementation=bind(P / "implementation-manifest.json"),
        implementation_review=bind(P / "independent-implementation-review.json"),
    )
    destination = Path("reports/harness/forensics/conditional_hf_factor_method-backtest-forensics.json")
    save(destination, forensics)
    destination.with_suffix(".md").write_text(
        "# Conditional HF author forensic audit\n\n"
        "Warning: current-vintage upstream factor cleaning and formation are not certified point-in-time. "
        "Chronological model fitting, exante filtering and same-target inference are explicitly bound, "
        "but do not resolve that upstream limitation. Real data and sufficient sample size are not "
        "untouched OOS. All4453 model/economic configurations remain in the descriptive multiplicity count.\n\n"
        "Primary20bp funded application loses capital. No research/ML/paper promotion; source-wide "
        "refutation is outside scope. This is the author's audit, not independent acceptance.\n"
    )
    print(json.dumps(dict(native_result=bind(D / "evaluation-report.json"),
                          author_forensics=bind(destination))))


if __name__ == "__main__":
    main()
